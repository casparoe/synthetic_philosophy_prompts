#!/usr/bin/env python3
"""Assemble the meta-prompt: the prompt that asks a model to write a prompt.

The meta-prompt is prompt.j2 rendered with components drawn from the other
files in this directory:

    domains.txt                   philosophical domains; a handful are offered
    task_types.yaml               prompt genres with examples and notes; a few
                                  are offered
    additional_instructions.yaml  extra instructions (length, persona, writing
                                  style, ...) in mutually exclusive groups; each
                                  group contributes at most one option, with a
                                  configurable probability, optionally led in by
                                  a preamble shared by the whole group

One draw is recorded as a *sample*: which domains and task types were offered,
which of each type's examples were shown and in which order (one to five of
them, drawn at random; samples from before batch 046 lack this key and showed
every example in file order), and which additional instruction each group
contributed. Samples use the same keys as the per-prompt .meta.yaml sidecars
and the samples.yaml files under prompts/, so the meta-prompt behind any
existing prompt can be rebuilt from its batch's inputs/ snapshot. (Batches
before 029 predate additional_instructions.yaml; rebuild those with the code at
commit 515faeef.)

The generators in generators/ import this module. Run it directly to print one
assembled meta-prompt:

    .venv/bin/python meta_prompt/assemble.py [--seed N] [--web-tools] [--show-sample]

    # the meta-prompt behind an existing prompt, from its batch's snapshot
    # (add --web-tools / --strict-quotes to match the batch's settings)
    .venv/bin/python meta_prompt/assemble.py --components prompts/batch_NNN/inputs \
        --sample prompts/batch_NNN/prompt_XXXXX.meta.yaml
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
INSTRUCTIONS_FILE = "additional_instructions.yaml"

# Everything the meta-prompt is built from. The generators copy these into
# each batch's inputs/ directory for provenance.
COMPONENT_FILES = [
    TEMPLATE_FILE,
    "domains.txt",
    "task_types.yaml",
    INSTRUCTIONS_FILE,
]

# The record of one draw, in the order the .meta.yaml sidecars use.
SAMPLE_KEYS = [
    "task_types_offered",
    "task_type_examples",
    "additional_instructions",
    "domains_offered",
]
# Keys a sample may lack (older sidecars); render() then falls back to the
# behaviour of the time: every example of a task type, in file order.
OPTIONAL_SAMPLE_KEYS = {"task_type_examples"}
# For each offered task type, how many of its examples are shown: a number
# from 1 to this drawn uniformly, capped by how many examples the type has.
MAX_EXAMPLES_SHOWN = 5


def _load_lines(path):
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


@dataclass
class InstructionGroup:
    """Mutually exclusive alternatives for one kind of additional instruction
    (say, the length instructions). At most one is drawn per prompt."""

    probability: float  # chance that the group contributes an instruction at all
    texts: list  # the alternatives
    weights: list  # relative draw weights, parallel to texts
    preamble: str | None = None  # shown ahead of whichever option is drawn


def _parse_group(spec):
    if not isinstance(spec, dict) or "options" not in spec:
        raise ValueError("expected a mapping with options (and optionally probability)")
    if unknown := set(spec) - {"probability", "options", "preamble"}:
        raise ValueError(f"unknown keys: {', '.join(sorted(map(str, unknown)))}")
    preamble = spec.get("preamble")
    if preamble is not None and (not isinstance(preamble, str) or not preamble.strip()):
        raise ValueError("preamble must be a non-empty string")
    probability = float(spec.get("probability", 1))
    if not 0 <= probability <= 1:
        raise ValueError("probability must be between 0 and 1")
    if not isinstance(spec["options"], list) or not spec["options"]:
        raise ValueError("options must be a non-empty list")
    texts, weights = [], []
    for option in spec["options"]:
        if isinstance(option, str):
            option = {"text": option}
        if not isinstance(option, dict) or set(option) - {"text", "weight"}:
            raise ValueError(
                "each option must be a string or a mapping with text and weight"
            )
        text = option.get("text")
        weight = float(option.get("weight", 1))
        if not isinstance(text, str) or not text.strip() or weight <= 0:
            raise ValueError("each option needs non-empty text and a positive weight")
        texts.append(text.strip())
        weights.append(weight)
    return InstructionGroup(
        probability, texts, weights, preamble.strip() if preamble else None
    )


def _load_instruction_groups(path):
    """Read additional_instructions.yaml: a mapping of group name to
    {options: [...], probability: p, preamble: text}, where an option is a
    string or a mapping with text and weight, and probability and preamble
    are optional. Groups keep the file's order."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found (snapshots of batches before 029 predate it; "
            "rebuild those with the code at commit 515faeef)"
        )
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict) or not data:
        raise ValueError(f"{path}: expected a mapping of instruction groups")
    groups = {}
    for name, spec in data.items():
        try:
            groups[name] = _parse_group(spec)
        except (TypeError, ValueError) as e:
            raise ValueError(f"{path}: group {name!r}: {e}") from None
    return groups


@dataclass
class Components:
    """The component files of one directory, read once, plus the template."""

    source: Path
    domains: list
    task_types: list  # dicts with "type" and optional "examples"/"notes"
    instruction_groups: dict  # group name -> InstructionGroup, in file order
    template: object  # jinja2.Template

    def sample(self, num_domains=5, num_task_types=3, rng=random, max_examples=MAX_EXAMPLES_SHOWN):
        """Draw the parameters for one prompt. Pass a seeded random.Random as
        rng for a reproducible draw. For every offered task type, a number of
        examples from 1 to max_examples is drawn, then that many of the type's
        examples (fewer if it has fewer), in random order; task_type_examples
        records their indices into the type's example list."""
        offered = rng.sample(self.task_types, k=min(num_task_types, len(self.task_types)))
        shown = {}
        for t in offered:
            n = len(t.get("examples") or [])
            k = min(rng.randint(1, max_examples), n)
            shown[t["type"]] = rng.sample(range(n), k) if k else []
        return {
            "task_types_offered": [t["type"] for t in offered],
            "task_type_examples": shown,
            "additional_instructions": {
                name: rng.choices(group.texts, weights=group.weights)[0]
                for name, group in self.instruction_groups.items()
                if rng.random() < group.probability
            },
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
        chosen = sample["additional_instructions"]
        unknown = [name for name in chosen if name not in self.instruction_groups]
        if unknown:
            raise ValueError(
                f"sample has additional instructions from groups unknown to "
                f"{self.source}: {', '.join(unknown)}"
            )
        return self.template.render(
            domains=sample["domains_offered"],
            task_types=[
                self._task_type_shown(by_name[name], sample.get("task_type_examples"))
                for name in sample["task_types_offered"]
            ],
            # In the components' group order, however the sample was stored.
            additional_instructions=[
                self._with_preamble(name, chosen[name])
                for name in self.instruction_groups
                if name in chosen
            ],
            web_tools=web_tools,
            strict_quotes=strict_quotes,
        )

    def _task_type_shown(self, task_type, shown):
        """The task type with only the examples the sample shows, in the
        sample's order; every example in file order for samples that predate
        task_type_examples."""
        examples = task_type.get("examples") or []
        if shown is None:
            return task_type
        if task_type["type"] not in shown:
            raise ValueError(
                f"sample records no examples for task type {task_type['type']!r}"
            )
        indices = shown[task_type["type"]]
        if not all(isinstance(i, int) and 0 <= i < len(examples) for i in indices):
            raise ValueError(
                f"sample has example indices out of range for task type "
                f"{task_type['type']!r} in {self.source}: {indices}"
            )
        return {**task_type, "examples": [examples[i] for i in indices]}

    def _with_preamble(self, name, text):
        """The group's preamble, if it has one, ahead of the drawn option; the
        option goes on its own indented line so the bullet reads as a lead-in
        followed by the instruction."""
        preamble = self.instruction_groups[name].preamble
        return f"{preamble}\n  {text}" if preamble else text

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
        task_types=yaml.safe_load((directory / "task_types.yaml").read_text()),
        instruction_groups=_load_instruction_groups(directory / INSTRUCTIONS_FILE),
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

    try:
        components = load(args.components)
    except (FileNotFoundError, ValueError) as e:
        parser.error(str(e))
    if args.sample:
        data = yaml.safe_load(Path(args.sample).read_text())
        missing = [key for key in SAMPLE_KEYS if key not in data and key not in OPTIONAL_SAMPLE_KEYS]
        if missing:
            hint = " (a pre-029 sidecar; see commit 515faeef)" if "length" in data else ""
            parser.error(f"{args.sample} lacks sample keys: {', '.join(missing)}{hint}")
        sample = {key: data[key] for key in SAMPLE_KEYS if key in data}
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
