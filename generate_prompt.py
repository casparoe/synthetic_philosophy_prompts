#!/usr/bin/env python3
"""Generate synthetic philosophy prompts.

Samples a few task types (task_types.yaml), a length instruction
(prompt_length.yaml), a persona (personas.txt), a writing style
(writing_styles.txt), and a handful of domains (domains.txt), renders prompt.j2
with them, asks Claude to write a prompt (picking a domain and task type from
the offered ones), and saves the result under prompts/ together with a
.meta.yaml sidecar recording the sampled parameters.

Usage:
    .venv/bin/python generate_prompt.py [-n NUM_PROMPTS] [--num-domains K] [--model MODEL]
"""

import argparse
import random
import re
import sys
from datetime import datetime, timezone
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
    parser.add_argument(
        "--num-task-types",
        type=int,
        default=3,
        help="how many task types the model gets to pick between (default: 3)",
    )
    parser.add_argument("--model", default="claude-sonnet-5")
    parser.add_argument(
        "--effort",
        default="xhigh",
        choices=["low", "medium", "high", "xhigh", "max"],
        help="reasoning effort for the generating model (default: xhigh)",
    )
    args = parser.parse_args()

    domains, personas, writing_styles, task_types, length_instructions = load_inputs()
    env = Environment(
        loader=FileSystemLoader(REPO_ROOT), trim_blocks=True, lstrip_blocks=True
    )
    template = env.get_template("prompt.j2")
    client = anthropic.Anthropic()

    PROMPTS_DIR.mkdir(exist_ok=True)
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
        )

        response = client.messages.create(
            model=args.model,
            max_tokens=16000,
            output_config={"effort": args.effort},
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

        metadata = {
            "prompt_file": out_path.name,
            "model": args.model,
            "effort": args.effort,
            "task_types_offered": [t["type"] for t in sampled_task_types],
            "length": length_name,
            "persona": persona,
            "writing_style": writing_style,
            "domains_offered": sampled_domains,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        out_path.with_suffix(".meta.yaml").write_text(
            yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True)
        )
        offered = " / ".join(t["type"] for t in sampled_task_types)
        print(f"[{offered} | {length_name}] -> {out_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
