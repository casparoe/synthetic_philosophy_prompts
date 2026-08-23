#!/usr/bin/env python3
"""Generate synthetic philosophy prompts.

Samples a few task types (task_types.yaml), a length instruction
(prompt_length.yaml), a persona (personas.txt), a writing style
(writing_styles.txt), and a handful of domains (domains.txt), renders prompt.j2
with them, asks Claude to write a prompt (picking a domain and task type from
the offered ones), and saves the result together with a .meta.yaml sidecar
recording the sampled parameters.

Each invocation creates a fresh batch directory prompts/batch_NNN/ holding the
generated prompts, a batch.yaml with the run parameters, and an inputs/
snapshot of the parameter files as they were at startup (the script reads them
only once, so mid-run edits never affect a running batch). Prompt numbering is
global across all batches.

Usage:
    .venv/bin/python generate_prompt.py [-n NUM_PROMPTS] [--num-domains K] [--model MODEL]
"""

import argparse
import random
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import yaml
from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = REPO_ROOT / "prompts"

WEB_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search"},
    {"type": "web_fetch_20260209", "name": "web_fetch"},
]

# Files snapshotted into each batch's inputs/ directory for provenance.
INPUT_FILES = [
    "prompt.j2",
    "domains.txt",
    "personas.txt",
    "writing_styles.txt",
    "task_types.yaml",
    "prompt_length.yaml",
]


def load_lines(filename):
    return [
        line.strip()
        for line in (REPO_ROOT / filename).read_text().splitlines()
        if line.strip()
    ]


def load_inputs():
    domains = load_lines("domains.txt")
    personas = load_lines("personas.txt")
    writing_styles = load_lines("writing_styles.txt")
    task_types = yaml.safe_load((REPO_ROOT / "task_types.yaml").read_text())
    length_instructions = yaml.safe_load((REPO_ROOT / "prompt_length.yaml").read_text())
    return domains, personas, writing_styles, task_types, length_instructions


def create_batch_dir():
    existing = [
        int(m.group(1))
        for p in PROMPTS_DIR.glob("batch_*")
        if (m := re.fullmatch(r"batch_(\d+)", p.name))
    ]
    # batch_000 is reserved for prompts generated before batches existed.
    n = max(existing, default=0) + 1
    while True:
        batch_dir = PROMPTS_DIR / f"batch_{n:03d}"
        try:
            batch_dir.mkdir(parents=True)
            return batch_dir
        except FileExistsError:
            n += 1


def next_output_path(batch_dir):
    indices = [
        int(m.group(1))
        for p in PROMPTS_DIR.glob("**/prompt_*.txt")
        if (m := re.fullmatch(r"prompt_(\d+)\.txt", p.name))
    ]
    return batch_dir / f"prompt_{max(indices, default=0) + 1:05d}.txt"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-n", "--num-prompts", type=int, default=1)
    parser.add_argument(
        "--num-domains",
        type=int,
        default=5,
        help="how many domains the model gets to pick between (default: 5)",
    )
    parser.add_argument(
        "--num-task-types",
        type=int,
        default=3,
        help="how many task types the model gets to pick between (default: 3)",
    )
    parser.add_argument("--model", default="claude-sonnet-5")
    parser.add_argument(
        "--effort",
        default="max",
        choices=["low", "medium", "high", "xhigh", "max"],
        help="reasoning effort for the generating model (default: max)",
    )
    parser.add_argument(
        "--no-web-tools",
        action="store_true",
        help="don't give the generating model web search/fetch tools",
    )
    args = parser.parse_args()

    domains, personas, writing_styles, task_types, length_instructions = load_inputs()
    env = Environment(
        loader=FileSystemLoader(REPO_ROOT), trim_blocks=True, lstrip_blocks=True
    )
    template = env.get_template("prompt.j2")
    client = anthropic.Anthropic()

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
                "model": args.model,
                "effort": args.effort,
                "web_tools": not args.no_web_tools,
                "num_prompts": args.num_prompts,
                "num_domains": args.num_domains,
                "num_task_types": args.num_task_types,
            },
            sort_keys=False,
        )
    )
    print(f"writing batch to {batch_dir.relative_to(REPO_ROOT)}")

    for _ in range(args.num_prompts):
        sampled_task_types = random.sample(
            task_types, k=min(args.num_task_types, len(task_types))
        )
        length_name, length_instruction = random.choice(
            list(length_instructions.items())
        )
        persona = random.choice(personas)
        writing_style = random.choice(writing_styles)
        sampled_domains = random.sample(domains, k=min(args.num_domains, len(domains)))
        meta_prompt = template.render(
            domains=sampled_domains,
            task_types=sampled_task_types,
            length_instruction=length_instruction,
            prompt_persona=persona,
            prompt_writing_style=writing_style,
            web_tools=not args.no_web_tools,
        )

        request = {
            "model": args.model,
            "max_tokens": 32000,
            "thinking": {"type": "adaptive", "display": "summarized"},
            "output_config": {"effort": args.effort},
        }
        if not args.no_web_tools:
            request["tools"] = WEB_TOOLS

        # Server tools can pause long turns (stop_reason "pause_turn"); resume
        # by passing the accumulated assistant content back.
        messages = [{"role": "user", "content": meta_prompt}]
        assistant_blocks = []
        try:
            for _ in range(5):
                with client.messages.stream(**request, messages=messages) as stream:
                    response = stream.get_final_message()
                assistant_blocks.extend(response.content)
                if response.stop_reason != "pause_turn":
                    break
                messages = [
                    {"role": "user", "content": meta_prompt},
                    {"role": "assistant", "content": assistant_blocks},
                ]
        except anthropic.APIError as e:
            print(f"warning: API error, skipping this prompt: {e}", file=sys.stderr)
            time.sleep(30)
            continue
        if response.stop_reason != "end_turn":
            print(
                f"warning: skipping response with stop_reason={response.stop_reason!r}",
                file=sys.stderr,
            )
            continue

        # The model sometimes narrates before tool calls ("I'll research...");
        # only text after the last tool-use/tool-result block is the prompt.
        cut = -1
        for i, block in enumerate(assistant_blocks):
            if block.type not in ("text", "thinking"):
                cut = i
        prompt_text = "".join(
            block.text for block in assistant_blocks[cut + 1 :] if block.type == "text"
        ).strip()
        reasoning_summary = "\n\n".join(
            block.thinking
            for block in assistant_blocks
            if block.type == "thinking" and block.thinking
        ).strip()
        tool_calls = [b.name for b in assistant_blocks if b.type == "server_tool_use"]
        out_path = next_output_path(batch_dir)
        out_path.write_text(prompt_text + "\n")

        metadata = {
            "prompt_file": out_path.name,
            "model": args.model,
            "effort": args.effort,
            "web_searches": tool_calls.count("web_search"),
            "web_fetches": tool_calls.count("web_fetch"),
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
        print(f"[{offered} | {length_name}] -> {out_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
