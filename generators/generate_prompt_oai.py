#!/usr/bin/env python3
"""Generate synthetic philosophy prompts via an OpenAI-compatible endpoint.

For self-hosted models, e.g. llama.cpp's llama-server, and for hosted
gateways such as OpenRouter. Same sampling, inputs, and outputs as
generate_prompt.py. Reasoning that arrives inline as <think>...</think>
(llama-server with --reasoning-format none) or in a reasoning_content or
reasoning field goes into the sidecar and is stripped from the saved prompt.

With --web-tools, the model gets web_search (DuckDuckGo via ddgs) and
web_fetch (httpx + trafilatura) as client-executed function calls, looped
until the model stops calling tools -- a poor man's version of the server
tools the Anthropic runs get. llama-server must be launched with --jinja so
tool calls are parsed. Only the final assistant message becomes the prompt,
so mid-loop narration is dropped for free.

Usage:
    .venv/bin/python generators/generate_prompt_oai.py -n 50 --web-tools \
        --base-url http://127.0.0.1:8088 --model qwen3.8-27b

    # OpenRouter: bearer key from a file, an explicit reasoning effort, and
    # (since OpenRouter reports it) each prompt's cost in its sidecar
    .venv/bin/python generators/generate_prompt_oai.py -n 1000 --web-tools \
        --base-url https://openrouter.ai/api --model deepseek/deepseek-v4-pro \
        --api-key-file api_keys/openrouter.txt --reasoning-effort high \
        --quantizations fp8,bf16,fp16 --concurrency 32
"""

import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import httpx
import trafilatura
import yaml
from ddgs import DDGS

# The meta-prompt components live in meta_prompt/ at the repo root; put the
# root on sys.path so they import when this file runs as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from meta_prompt import assemble  # noqa: E402
from generate_prompt import REPO_ROOT, create_batch_dir, next_output_path  # noqa: E402

THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)

MAX_TOOL_ROUNDS = 8
FETCH_CHAR_LIMIT = 6000

WEB_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web. Returns titles, URLs, and snippets "
            "of the top results. Use only when the prompt genuinely requires "
            "real source material you are not certain of. Snippets are not "
            "reliable for verbatim quotation -- to quote a passage exactly, "
            "follow up with web_fetch on a result.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch a web page by URL and return its main text "
            "content (truncated). Use for reading a specific page, e.g. to "
            "quote a passage verbatim.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
]

# DuckDuckGo dislikes bursts; serialize searches across worker threads.
search_lock = threading.Lock()


def run_web_search(query):
    with search_lock:
        results = DDGS().text(query, max_results=5)
        time.sleep(1.5)
    if not results:
        return "No results."
    return "\n\n".join(
        f"[{i + 1}] {r.get('title', '')}\n{r.get('href', '')}\n{r.get('body', '')}"
        for i, r in enumerate(results)
    )


def run_web_fetch(url):
    response = httpx.get(
        url, timeout=20.0, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (research script)"},
    )
    response.raise_for_status()
    text = trafilatura.extract(response.text) or ""
    if not text:
        return "Could not extract text content from that page."
    if len(text) > FETCH_CHAR_LIMIT:
        text = text[:FETCH_CHAR_LIMIT] + "\n[truncated]"
    return text


def run_tool(name, arguments):
    try:
        args = json.loads(arguments or "{}")
        if name == "web_search":
            return run_web_search(args["query"])
        if name == "web_fetch":
            return run_web_fetch(args["url"])
        return f"Unknown tool: {name}"
    except Exception as e:
        return f"Tool error: {e!r}"


def served_model_name(client, requested):
    """Name of the loaded model as the server reports it; also verifies
    connectivity. A gateway lists many models, in which case the requested
    one is returned if it is among them."""
    data = client.get("/v1/models").json()
    for key, name_key in (("data", "id"), ("models", "name")):
        if data.get(key):
            names = [m.get(name_key) for m in data[key]]
            return requested if requested in names else names[0]
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
        help="model name sent with each request and recorded in the sidecars "
        "(llama-server ignores it; gateways route on it)",
    )
    parser.add_argument(
        "--api-key-file",
        metavar="FILE",
        help="send the key in FILE as a bearer token (hosted services such as OpenRouter)",
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=["low", "medium", "high", "xhigh"],
        help="request this much reasoning via the reasoning.effort field "
        "(OpenRouter and compatible servers); default: the model's own default",
    )
    parser.add_argument(
        "--quantizations",
        metavar="LIST",
        help="OpenRouter only: route only to providers serving the model at one "
        "of these quantizations, comma-separated, e.g. fp8,bf16,fp16 (default: "
        "any, including 4-bit and undisclosed)",
    )
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=24576)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument(
        "--web-tools",
        action="store_true",
        help="give the model client-executed web search/fetch tools",
    )
    parser.add_argument(
        "--first-id",
        type=int,
        default=1,
        metavar="N",
        help="never number a prompt below N, to stay clear of a batch being "
        "generated concurrently on another machine (default: 1, no effect)",
    )
    args = parser.parse_args()
    quantizations = args.quantizations.split(",") if args.quantizations else None
    # OpenRouter reports the cost and the serving provider of each request.
    openrouter = "openrouter.ai" in args.base_url

    components = assemble.load()
    headers = {}
    if args.api_key_file:
        headers["Authorization"] = "Bearer " + Path(args.api_key_file).read_text().strip()
    client = httpx.Client(
        base_url=args.base_url,
        headers=headers,
        timeout=httpx.Timeout(3600.0, connect=30.0),
    )
    served = served_model_name(client, args.model)  # fails fast if the server is down

    batch_dir = create_batch_dir()
    components.snapshot(batch_dir / "inputs")
    config = {
        "batch": batch_dir.name,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "api": "openai_compatible",
        "base_url": args.base_url,
        "model": args.model,
        "served_model": served,
        "reasoning_effort": args.reasoning_effort,
        "quantizations": quantizations,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "web_tools": args.web_tools,
        "num_prompts": args.num_prompts,
        "concurrency": args.concurrency,
        "num_domains": args.num_domains,
        "num_task_types": args.num_task_types,
    }
    if args.first_id > 1:
        config["first_id"] = args.first_id
    (batch_dir / "batch.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    print(f"writing batch to {batch_dir.relative_to(REPO_ROOT)}", flush=True)

    path_lock = threading.Lock()

    def generate_one(sample):
        meta_prompt = components.render(
            sample, web_tools=args.web_tools, strict_quotes=args.web_tools
        )

        def attempt_turns():
            """Run one full tool-round conversation. Returns a dict with the
            final choice and content plus the run's counters, or None if the
            model was still calling tools after MAX_TOOL_ROUNDS."""
            messages = [{"role": "user", "content": meta_prompt}]
            stats = {
                "searches": 0,
                "fetches": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0,
                "providers": set(),
                "reasoning_parts": [],
            }
            for _ in range(MAX_TOOL_ROUNDS):
                request = {
                    "model": args.model,
                    "messages": messages,
                    "max_tokens": args.max_tokens,
                    "temperature": args.temperature,
                    "top_p": 0.95,
                }
                if args.web_tools:
                    request["tools"] = WEB_TOOL_SCHEMAS
                if args.reasoning_effort:
                    request["reasoning"] = {"effort": args.reasoning_effort}
                if openrouter:
                    request["usage"] = {"include": True}
                if quantizations:
                    request["provider"] = {"quantizations": quantizations}
                response = client.post("/v1/chat/completions", json=request)
                response.raise_for_status()
                data = response.json()
                choice = data["choices"][0]
                message = choice["message"]
                usage = data.get("usage") or {}
                stats["input_tokens"] += usage.get("prompt_tokens", 0)
                stats["output_tokens"] += usage.get("completion_tokens", 0)
                stats["cost"] += float(usage.get("cost") or 0)
                if data.get("provider"):
                    stats["providers"].add(data["provider"])
                content = message.get("content") or ""
                stats["reasoning_parts"] += THINK_RE.findall(content)
                for key in ("reasoning_content", "reasoning"):
                    if message.get(key):
                        stats["reasoning_parts"].append(message[key])
                tool_calls = message.get("tool_calls") or []
                if not tool_calls:
                    return {"choice": choice, "content": content, **stats}
                # Echo the assistant turn (thinking stripped) plus results.
                # Gateways that return reasoning_details expect them echoed
                # back so the model keeps its train of thought across rounds.
                assistant = {
                    "role": "assistant",
                    "content": THINK_RE.sub("", content).strip() or None,
                    "tool_calls": tool_calls,
                }
                if message.get("reasoning_details"):
                    assistant["reasoning_details"] = message["reasoning_details"]
                messages.append(assistant)
                for tool_call in tool_calls:
                    function = tool_call.get("function") or {}
                    name = function.get("name", "")
                    if name == "web_search":
                        stats["searches"] += 1
                    elif name == "web_fetch":
                        stats["fetches"] += 1
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.get("id"),
                            "content": run_tool(name, function.get("arguments")),
                        }
                    )
            return None

        # Connection failures (server restarts, network blips) get retried
        # with a minute between attempts; the whole conversation restarts
        # from scratch on each attempt.
        result = None
        for attempt in range(4):
            try:
                result = attempt_turns()
                break
            except httpx.HTTPError as e:
                print(
                    f"warning: request failed ({e.__class__.__name__}), "
                    f"retry {attempt + 1}/4 in 60s",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(60)
            except Exception as e:
                print(
                    f"warning: unexpected error, skipping this prompt: {e!r}",
                    file=sys.stderr,
                )
                return
        else:
            print(
                "warning: request kept failing, skipping this prompt",
                file=sys.stderr,
            )
            return
        if result is None:
            print(
                f"warning: still calling tools after {MAX_TOOL_ROUNDS} rounds, "
                "skipping this prompt",
                file=sys.stderr,
            )
            return
        choice, content = result["choice"], result["content"]
        if choice.get("finish_reason") != "stop":
            print(
                f"warning: skipping response with finish_reason="
                f"{choice.get('finish_reason')!r}",
                file=sys.stderr,
            )
            return
        prompt_text = THINK_RE.sub("", content).strip()
        if "<think>" in prompt_text or not prompt_text:
            print(
                "warning: empty or truncated-thinking response, skipping",
                file=sys.stderr,
            )
            return
        reasoning_summary = "\n\n".join(
            p.strip() for p in result["reasoning_parts"] if p.strip()
        )

        # Writing the .txt reserves the number, so both happen under the lock.
        with path_lock:
            out_path = next_output_path(batch_dir, args.first_id)
            out_path.write_text(prompt_text + "\n")
        metadata = {
            "prompt_file": out_path.name,
            "model": args.model,
            "effort": args.reasoning_effort,
            "web_searches": result["searches"],
            "web_fetches": result["fetches"],
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
        }
        if openrouter:
            metadata["cost_usd"] = round(result["cost"], 6)
            metadata["providers"] = sorted(result["providers"])
        metadata.update(sample)
        metadata["reasoning_summary"] = reasoning_summary or None
        metadata["generated_at"] = datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        )
        out_path.with_suffix(".meta.yaml").write_text(
            yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True)
        )
        offered = " / ".join(sample["task_types_offered"])
        extras = ", ".join(sample["additional_instructions"]) or "none"
        cost = f" ${result['cost']:.3f}" if openrouter else ""
        print(
            f"[{offered} | {extras}]{cost} -> {out_path.relative_to(REPO_ROOT)}",
            flush=True,
        )

    samples = [
        components.sample(args.num_domains, args.num_task_types)
        for _ in range(args.num_prompts)
    ]
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(generate_one, sample) for sample in samples]
        try:
            for future in as_completed(futures):
                future.result()
        except BaseException:
            executor.shutdown(wait=False, cancel_futures=True)
            raise


if __name__ == "__main__":
    main()
