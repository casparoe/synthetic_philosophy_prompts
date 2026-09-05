#!/usr/bin/env python3
"""Assemble the meta-prompt: the prompt that asks a model to write a prompt.

The meta-prompt is prompt.j2 rendered with components drawn from the other
files in this directory:

    domains.txt         philosophical domains; a handful are offered per prompt
    task_types.yaml     prompt genres with examples and notes; a few are offered
    prompt_length.yaml  named length instructions; one is chosen
    personas.txt        author personas; one is chosen
    writing_styles.txt  writing-style instructions; one is chosen

One draw is recorded as a *sample*: which domains and task types were offered
and which length, persona, and writing style were chosen. Samples use the same
keys as the per-prompt .meta.yaml sidecars and the samples.yaml files under
prompts/, so the meta-prompt behind any existing prompt can be rebuilt.

The generators in generators/ import this module. Run it directly to print one
assembled meta-prompt:

    .venv/bin/python meta_prompt/assemble.py [--seed N] [--web-tools] [--show-sample]

    # the meta-prompt behind an existing prompt, from its batch's snapshot
    .venv/bin/python meta_prompt/assemble.py --components prompts/batch_028/inputs \
        --sample prompts/batch_028/prompt_22866.meta.yaml --strict-quotes
"""

import argparse
import random
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

COMPONENTS_DIR = Path(__file__).resolve().parent
TEMPLATE_FILE = "prompt.j2"

# Everything the meta-prompt is built from. The generators copy these into
# each batch's inputs/ directory for provenance.
COMPONENT_FILES = [
    TEMPLATE_FILE,
    "domains.txt",
    "personas.txt",
    "writing_styles.txt",
    "task_types.yaml",
    "prompt_length.yaml",
]

# The record of one draw, in the order the .meta.yaml sidecars use.
SAMPLE_KEYS = [
    "task_types_offered",
    "length",
    "persona",
    "writing_style",
    "domains_offered",
]


def _load_lines(path):
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


@dataclass
class Components:
    """The component files of one directory, read once, plus the template."""

    source: Path
    domains: list
    personas: list
    writing_styles: list
    task_types: list  # dicts with "type" and optional "examples"/"notes"
    length_instructions: dict  # name -> instruction text
    template: object  # jinja2.Template

    def sample(self, num_domains=5, num_task_types=3, rng=random):
        """Draw the parameters for one prompt. Pass a seeded random.Random as
        rng for a reproducible draw."""
        return {
            "task_types_offered": [
                t["type"]
                for t in rng.sample(
                    self.task_types, k=min(num_task_types, len(self.task_types))
                )
            ],
            "length": rng.choice(list(self.length_instructions)),
            "persona": rng.choice(self.personas),
            "writing_style": rng.choice(self.writing_styles),
            "domains_offered": rng.sample(
                self.domains, k=min(num_domains, len(self.domains))
            ),
        }

    def render(self, sample, web_tools=False, strict_quotes=False):
        """Render the meta-prompt for one sample.

        web_tools tells the model it may search and fetch (the generator has
        to actually provide the tools). strict_quotes adds the rule against
        quoting from memory; the template only shows it together with
        web_tools.
        """
        by_name = {t["type"]: t for t in self.task_types}
        return self.template.render(
            domains=sample["domains_offered"],
            task_types=[by_name[name] for name in sample["task_types_offered"]],
            length_instruction=self.length_instructions[sample["length"]],
            prompt_persona=sample["persona"],
            prompt_writing_style=sample["writing_style"],
            web_tools=web_tools,
            strict_quotes=strict_quotes,
        )

    def snapshot(self, dest_dir):
        """Copy the component files into dest_dir (a batch's inputs/)."""
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        for name in COMPONENT_FILES:
            shutil.copy2(self.source / name, dest_dir / name)


def load(directory=COMPONENTS_DIR):
    """Read the components from a directory, by default this one. Pass a
    batch's inputs/ directory to work from the snapshot a past run used."""
    directory = Path(directory)
    env = Environment(
        loader=FileSystemLoader(directory), trim_blocks=True, lstrip_blocks=True
    )
    return Components(
        source=directory,
        domains=_load_lines(directory / "domains.txt"),
        personas=_load_lines(directory / "personas.txt"),
        writing_styles=_load_lines(directory / "writing_styles.txt"),
        task_types=yaml.safe_load((directory / "task_types.yaml").read_text()),
        length_instructions=yaml.safe_load(
            (directory / "prompt_length.yaml").read_text()
        ),
        template=env.get_template(TEMPLATE_FILE),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--num-domains", type=int, default=5, help="domains to offer (default: 5)"
    )
    parser.add_argument(
        "--num-task-types",
        type=int,
        default=3,
        help="task types to offer (default: 3)",
    )
    parser.add_argument(
        "--web-tools",
        action="store_true",
        help="include the instructions for a model that has web search/fetch",
    )
    parser.add_argument(
        "--strict-quotes",
        action="store_true",
        help="also include the rule against quoting from memory (implies --web-tools)",
    )
    parser.add_argument("--seed", type=int, help="seed the draw so it can be repeated")
    parser.add_argument(
        "--components",
        metavar="DIR",
        default=COMPONENTS_DIR,
        help="read the components from DIR, e.g. a batch's inputs/ snapshot "
        "(default: this directory)",
    )
    parser.add_argument(
        "--sample",
        metavar="FILE",
        help="render this sample instead of drawing one; a prompt's .meta.yaml "
        "sidecar works",
    )
    parser.add_argument(
        "--show-sample",
        action="store_true",
        help="also print the drawn parameters as YAML to stderr",
    )
    args = parser.parse_args()

    components = load(args.components)
    if args.sample:
        data = yaml.safe_load(Path(args.sample).read_text())
        missing = [key for key in SAMPLE_KEYS if key not in data]
        if missing:
            parser.error(f"{args.sample} lacks sample keys: {', '.join(missing)}")
        sample = {key: data[key] for key in SAMPLE_KEYS}
    else:
        rng = random.Random(args.seed) if args.seed is not None else random
        sample = components.sample(args.num_domains, args.num_task_types, rng)
    if args.show_sample:
        print(
            yaml.safe_dump(sample, sort_keys=False, allow_unicode=True),
            end="",
            file=sys.stderr,
        )
    print(
        components.render(
            sample,
            web_tools=args.web_tools or args.strict_quotes,
            strict_quotes=args.strict_quotes,
        )
    )


if __name__ == "__main__":
    main()
