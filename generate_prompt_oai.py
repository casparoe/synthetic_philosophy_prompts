#!/usr/bin/env python3
"""Generate synthetic philosophy prompts via an OpenAI-compatible endpoint.

For self-hosted models, e.g. llama.cpp's llama-server. Same sampling,
inputs, and outputs as generate_prompt.py, but there are no web tools (the
template renders without that paragraph) and no Anthropic-specific request
features. Reasoning that arrives inline as <think>...</think> (llama-server
with --reasoning-format none) or in a reasoning_content field goes into the
sidecar and is stripped from the saved prompt.

Usage:
    .venv/bin/python generate_prompt_oai.py -n 50 \
        --base-url http://127.0.0.1:8088 --model qwen3.8-27b
"""

import argparse
import random
import re
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import httpx
import yaml
from jinja2 import Environment, FileSystemLoader

from generate_prompt import (
    INPUT_FILES,
    REPO_ROOT,
    create_batch_dir,
    load_inputs,
    next_output_path,
)

THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)


def served_model_name(client):
    """Best-effort name of the loaded model; also verifies connectivity."""
    data = client.get("/v1/models").json()
    for key, name_key in (("data", "id"), ("models", "name")):
        if data.get(key):
            return data[key][0].get(name_key)
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-n", "--num-prompts", type=int, default=1)
    parser.add_argument("--num-domains", type=int, default=5)
    parser.add_argument("--num-task-types", type=int, default=3)
    parser.add_argument("--base-url", default="http://127.0.0.1:8088")
    parser.add_argument(
        "--model",
        default="qwen3.8-27b",
        help="name recorded in the sidecars (llama-server ignores it)",
    )
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=12288)
    parser.add_argument("--temperature", type=float, default=0.7)
    args = parser.parse_args()

    domains, personas, writing_styles, task_types, length_instructions = load_inputs()
    env = Environment(
        loader=FileSystemLoader(REPO_ROOT), trim_blocks=True, lstrip_blocks=True
    )
    template = env.get_template("prompt.j2")
    client = httpx.Client(
        base_url=args.base_url, timeout=httpx.Timeout(3600.0, connect=30.0)
    )
    served = served_model_name(client)  # fails fast if the server is down

    batch_dir = create_batch_dir()
    inputs_dir = batch_dir / "inputs"
    inputs_dir.mkdir()
    for name in INPUT_FILES:
        shutil.copy2(REPO_ROOT / name, inputs_dir / name)
    (batch_dir / "batch.yaml").write_text(
        yaml.safe_dump(
            {
                "batch": batch_dir.name,
                "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "api": "openai_compatible",
                "base_url": args.base_url,
                "model": args.model,
                "served_model": served,
                "temperature": args.temperature,
                "max_tokens": args.max_tokens,
                "web_tools": False,
                "num_prompts": args.num_prompts,
                "concurrency": args.concurrency,
                "num_domains": args.num_domains,
                "num_task_types": args.num_task_types,
            },
            sort_keys=False,
        )
    )
    print(f"writing batch to {batch_dir.relative_to(REPO_ROOT)}", flush=True)

    path_lock = threading.Lock()

    def generate_one(
        sampled_task_types,
        length_name,
        length_instruction,
        persona,
        writing_style,
        sampled_domains,
    ):
        meta_prompt = template.render(
            domains=sampled_domains,
            task_types=sampled_task_types,
            length_instruction=length_instruction,
            prompt_persona=persona,
            prompt_writing_style=writing_style,
            web_tools=False,
        )
        try:
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": args.model,
                    "messages": [{"role": "user", "content": meta_prompt}],
                    "max_tokens": args.max_tokens,
                    "temperature": args.temperature,
                    "top_p": 0.95,
                },
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(
                f"warning: request failed, skipping this prompt: {e!r}",
                file=sys.stderr,
            )
            time.sleep(5)
            return
        choice = data["choices"][0]
        if choice.get("finish_reason") != "stop":
            print(
                f"warning: skipping response with finish_reason="
                f"{choice.get('finish_reason')!r}",
                file=sys.stderr,
            )
            return
        message = choice["message"]
        content = message.get("content") or ""
        thinks = THINK_RE.findall(content)
        prompt_text = THINK_RE.sub("", content).strip()
        if "<think>" in prompt_text or not prompt_text:
            print(
                "warning: empty or truncated-thinking response, skipping",
                file=sys.stderr,
            )
            return
        parts = [message.get("reasoning_content") or "", *thinks]
        reasoning_summary = "\n\n".join(p.strip() for p in parts if p.strip())
        usage = data.get("usage") or {}

        # Writing the .txt reserves the number, so both happen under the lock.
        with path_lock:
            out_path = next_output_path(batch_dir)
            out_path.write_text(prompt_text + "\n")
        metadata = {
            "prompt_file": out_path.name,
            "model": args.model,
            "effort": None,
            "web_searches": 0,
            "web_fetches": 0,
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "task_types_offered": [t["type"] for t in sampled_task_types],
            "length": length_name,
            "persona": persona,
            "writing_style": writing_style,
            "domains_offered": sampled_domains,
            "reasoning_summary": reasoning_summary or None,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        out_path.with_suffix(".meta.yaml").write_text(
            yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True)
        )
        offered = " / ".join(t["type"] for t in sampled_task_types)
        print(
            f"[{offered} | {length_name}] -> {out_path.relative_to(REPO_ROOT)}",
            flush=True,
        )

    samples = [
        (
            random.sample(task_types, k=min(args.num_task_types, len(task_types))),
            *random.choice(list(length_instructions.items())),
            random.choice(personas),
            random.choice(writing_styles),
            random.sample(domains, k=min(args.num_domains, len(domains))),
        )
        for _ in range(args.num_prompts)
    ]
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(generate_one, *sample) for sample in samples]
        try:
            for future in as_completed(futures):
                future.result()
        except BaseException:
            executor.shutdown(wait=False, cancel_futures=True)
            raise


if __name__ == "__main__":
    main()
