#!/usr/bin/env python3
"""Generate synthetic philosophy prompts.

Samples a task type (task_types.yaml), a length instruction (prompt_length.yaml),
and a handful of domains (domains.txt), renders prompt.j2 with them, asks Claude
to write a prompt, and saves the result under prompts/.

Usage:
    .venv/bin/python generate_prompt.py [-n NUM_PROMPTS] [--num-domains K] [--model MODEL]
"""

import argparse
import random
import re
import sys
from pathlib import Path

import anthropic
import yaml
from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = REPO_ROOT / "prompts"

SYSTEM_PROMPT = (
    "You write prompts for a dataset. Reply with the prompt text only -- "
    "no preamble, no commentary, and no quotation marks around the prompt."
)


def load_inputs():
    domains = [
        line.strip()
        for line in (REPO_ROOT / "domains.txt").read_text().splitlines()
        if line.strip()
    ]
    task_types = yaml.safe_load((REPO_ROOT / "task_types.yaml").read_text())
    length_instructions = yaml.safe_load((REPO_ROOT / "prompt_length.yaml").read_text())
    return domains, task_types, length_instructions


def next_output_path():
    indices = [
        int(m.group(1))
        for p in PROMPTS_DIR.glob("prompt_*.txt")
        if (m := re.fullmatch(r"prompt_(\d+)\.txt", p.name))
    ]
    return PROMPTS_DIR / f"prompt_{max(indices, default=0) + 1:05d}.txt"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-n", "--num-prompts", type=int, default=1)
    parser.add_argument(
        "--num-domains",
        type=int,
        default=5,
        help="how many domains the model gets to pick between (default: 5)",
    )
    parser.add_argument("--model", default="claude-sonnet-5")
    args = parser.parse_args()

    domains, task_types, length_instructions = load_inputs()
    env = Environment(
        loader=FileSystemLoader(REPO_ROOT), trim_blocks=True, lstrip_blocks=True
    )
    template = env.get_template("prompt.j2")
    client = anthropic.Anthropic()

    PROMPTS_DIR.mkdir(exist_ok=True)
    for _ in range(args.num_prompts):
        task_type = random.choice(task_types)
        length_name, length_instruction = random.choice(
            list(length_instructions.items())
        )
        meta_prompt = template.render(
            domains=random.sample(domains, k=min(args.num_domains, len(domains))),
            prompt_type=task_type["type"],
            examples=task_type["examples"],
            notes=task_type.get("notes"),
            length_instruction=length_instruction,
        )

        response = client.messages.create(
            model=args.model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": meta_prompt}],
        )
        if response.stop_reason != "end_turn":
            print(
                f"warning: skipping response with stop_reason={response.stop_reason!r}",
                file=sys.stderr,
            )
            continue

        prompt_text = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()
        out_path = next_output_path()
        out_path.write_text(prompt_text + "\n")
        print(f"[{task_type['type']} | {length_name}] -> {out_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
