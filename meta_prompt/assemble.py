#!/usr/bin/env python3
"""Assemble the meta-prompt: the prompt that asks a model to write a prompt.

The meta-prompt is prompt.j2 rendered with components drawn from the other
files in this directory:

    domains/                      philosophical domains in thematic files, each
                                  optionally with URLs of pages about it; a
                                  handful of domains are offered, each with a
                                  random few of its URLs
    task_types/                   prompt genres with examples and notes, one
                                  file per genre; a few are offered
    additional_instructions.yaml  extra instructions (length, persona, writing
                                  style, ...) in mutually exclusive groups; each
                                  group contributes at most one option, with a
                                  configurable probability, optionally led in by
                                  a preamble shared by the whole group or opened
                                  by a prefix written once for all its options

One draw is recorded as a *sample*: which domains and task types were offered,
which of each type's examples were shown and in which order (one to five of
them, drawn at random; samples from before batch 046, except the second half of
batch 044, lack this key and showed every example in file order), which additional instruction each group
contributed, and which URLs were drawn for each offered domain (each of a
domain's URLs with probability URL_PROBABILITY, in file order; samples from
before 2026-10-03 lack this key). The URLs are shown only when the generator
has web tools. Samples use the same keys as the per-prompt .meta.yaml sidecars
and the samples.yaml files under prompts/, so the meta-prompt behind any
existing prompt can be rebuilt from its batch's inputs/ snapshot. (Batches
before 029 predate additional_instructions.yaml; rebuild those with the code at
commit 515faeef.)

A task type is a file NNN_name.yaml in task_types/: a mapping with the genre's
name under type and, optionally, notes (a string) and examples (a list of
strings). The files are read in name order, so a new genre gets the next
number. A batch's inputs/ snapshot holds the same genres joined into one list,
task_types.yaml (also the source's layout before 2026-09-29); load() reads
either layout.

The domains live in domains/, one YAML file per theme (decision_theory.yaml,
fiction_film_and_games.yaml, ...), read in name order. Each file is a list of
mappings with the domain's text under domain and, optionally, a list of URLs
under urls. A snapshot joins the files into one list, domains.yaml. Snapshots
of batches before 2026-10-03 hold domains.txt instead, one domain per line and
no URLs; load() reads all three layouts.

The generators in generators/ import this module. Run it directly to print one
assembled meta-prompt:

    .venv/bin/python meta_prompt/assemble.py [--seed N] [--web-tools] [--show-sample]

    # the meta-prompt behind an existing prompt, from its batch's snapshot
    # (add --web-tools / --strict-quotes to match the batch's settings)
    .venv/bin/python meta_prompt/assemble.py --components prompts/batch_NNN/inputs \
        --sample prompts/batch_NNN/prompt_XXXXX.meta.yaml
"""

import argparse
import collections
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

TASK_TYPES_DIR = "task_types"  # the source: one file per task type
TASK_TYPES_FILE = "task_types.yaml"  # a snapshot: all task types in one list

DOMAINS_DIR = "domains"  # the source: one file per theme
DOMAINS_FILE = "domains.yaml"  # a snapshot: all domains in one list
LEGACY_DOMAINS_FILE = "domains.txt"  # snapshots before 2026-10-03: one per line
# Each URL of an offered domain is shown with this probability, independently.
URL_PROBABILITY = 0.001

# Everything the meta-prompt is built from goes into each batch's inputs/
# directory for provenance: these files copied as they are, plus the task
# types joined into one TASK_TYPES_FILE and the domains into one DOMAINS_FILE
# (see Components.snapshot).
COPIED_FILES = [
    TEMPLATE_FILE,
    INSTRUCTIONS_FILE,
]

# The record of one draw, in the order the .meta.yaml sidecars use.
SAMPLE_KEYS = [
    "task_types_offered",
    "task_type_examples",
    "additional_instructions",
    "domains_offered",
    "domain_urls",
]
# Keys a sample may lack (older sidecars); render() then falls back to the
# behaviour of the time: every example of a task type, in file order, and no
# URLs.
OPTIONAL_SAMPLE_KEYS = {"task_type_examples", "domain_urls"}
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
        raise ValueError(
            "expected a mapping with options (and optionally probability, "
            "preamble, prefix)"
        )
    if unknown := set(spec) - {"probability", "options", "preamble", "prefix"}:
        raise ValueError(f"unknown keys: {', '.join(sorted(map(str, unknown)))}")
    for key in ("preamble", "prefix"):
        value = spec.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"{key} must be a non-empty string")
    preamble = spec.get("preamble")
    prefix = (spec.get("prefix") or "").strip()
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
        # The prefix is written once in the file but stored expanded, so a
        # sample records the complete instruction the model was given.
        texts.append(f"{prefix} {text.strip()}" if prefix else text.strip())
        weights.append(weight)
    return InstructionGroup(
        probability, texts, weights, preamble.strip() if preamble else None
    )


def _load_instruction_groups(path):
    """Read additional_instructions.yaml: a mapping of group name to
    {options: [...], probability: p, preamble: text, prefix: text}, where an
    option is a string or a mapping with text and weight; probability,
    preamble, and prefix are optional, and a prefix is prepended (with a
    space) to every option's text. Groups keep the file's order."""
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


TASK_TYPE_KEYS = {"type", "notes", "examples"}


def _load_yaml(path):
    try:
        return yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise ValueError(f"{path}: {e}") from None


def _check_task_type(data, where):
    """One task type: a mapping with the genre's name under type and,
    optionally, notes (a string) and examples (a list of strings)."""
    if not isinstance(data, dict):
        hint = " (a list: the one-file layout?)" if isinstance(data, list) else ""
        raise ValueError(f"{where}: expected a mapping with type, notes, examples{hint}")
    if unknown := set(data) - TASK_TYPE_KEYS:
        raise ValueError(f"{where}: unknown keys: {', '.join(sorted(map(str, unknown)))}")
    if not isinstance(data.get("type"), str) or not data["type"].strip():
        raise ValueError(f"{where}: type must be a non-empty string")
    notes, examples = data.get("notes"), data.get("examples")
    if notes is not None and not isinstance(notes, str):
        raise ValueError(f"{where}: notes must be a string")
    if examples is not None and not (
        isinstance(examples, list) and all(isinstance(e, str) for e in examples)
    ):
        raise ValueError(f"{where}: examples must be a list of strings")
    return data


def _task_type_files(folder):
    """The per-type files of a TASK_TYPES_DIR, in name order."""
    return sorted(
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix in (".yaml", ".yml") and not p.name.startswith(".")
    )


def load_task_types(directory):
    """Read the task types of a components directory: the files of its
    TASK_TYPES_DIR in name order, or else the single list in its
    TASK_TYPES_FILE (the layout of snapshots). Either way a list of mappings
    with type, notes, and examples, checked and free of repeated names."""
    directory = Path(directory)
    folder, single = directory / TASK_TYPES_DIR, directory / TASK_TYPES_FILE
    if folder.is_dir() and single.exists():
        raise ValueError(
            f"{directory} has both {TASK_TYPES_DIR}/ and {TASK_TYPES_FILE}; "
            "the directory is the source, remove the file"
        )
    if folder.is_dir():
        files = _task_type_files(folder)
        if not files:
            raise ValueError(f"{folder}: no task type files (*.yaml)")
        types = [_check_task_type(_load_yaml(f), f) for f in files]
    elif single.exists():
        data = _load_yaml(single)
        if not isinstance(data, list) or not data:
            raise ValueError(f"{single}: expected a list of task types")
        types = [_check_task_type(t, f"{single}, item {i + 1}") for i, t in enumerate(data)]
    else:
        raise FileNotFoundError(
            f"{directory}: no {TASK_TYPES_DIR}/ directory and no {TASK_TYPES_FILE}"
        )
    counts = collections.Counter(t["type"] for t in types)
    if repeated := sorted(name for name, n in counts.items() if n > 1):
        raise ValueError(
            f"{directory}: task types defined more than once: {', '.join(repeated)}"
        )
    return types


def join_task_types(directory):
    """The task types of a components directory as the text of one YAML list,
    for a snapshot: the per-type files one after another, each indented into
    a list item the way the one-file layout wrote them (a space and a dash,
    keys at three spaces), so that snapshots diff cleanly across batches. A
    directory that already holds the single file gets that file's text."""
    directory = Path(directory)
    types = load_task_types(directory)
    folder = directory / TASK_TYPES_DIR
    if not folder.is_dir():
        return (directory / TASK_TYPES_FILE).read_text()
    items = []
    for path in _task_type_files(folder):
        lines = path.read_text().splitlines()
        # YAML's optional document markers would not survive the indentation
        if lines and lines[0].rstrip() == "---":
            lines = lines[1:]
        if lines and lines[-1].rstrip() == "...":
            lines = lines[:-1]
        items.append(
            f" - {lines[0]}\n"
            + "".join(f"   {line}\n" if line else "\n" for line in lines[1:])
        )
    text = "".join(items)
    if yaml.safe_load(text) != types:
        raise ValueError(
            f"{folder}: the files do not join into one list unchanged "
            "(a document marker or unusual indentation in one of them?)"
        )
    return text


DOMAIN_KEYS = {"domain", "urls"}


def _check_domain(data, where):
    """One domain: a mapping with its text under domain and, optionally, a
    list of distinct http(s) URLs under urls."""
    if not isinstance(data, dict):
        raise ValueError(f"{where}: expected a mapping with domain and optionally urls")
    if unknown := set(data) - DOMAIN_KEYS:
        raise ValueError(f"{where}: unknown keys: {', '.join(sorted(map(str, unknown)))}")
    text = data.get("domain")
    if not isinstance(text, str) or not text.strip() or text != text.strip() or "\n" in text:
        raise ValueError(f"{where}: domain must be a non-empty one-line string without surrounding spaces")
    urls = data.get("urls")
    if urls is None:
        urls = []
    if not isinstance(urls, list) or not all(
        isinstance(u, str) and u.startswith(("http://", "https://")) and not any(c.isspace() for c in u)
        for u in urls
    ):
        raise ValueError(f"{where}: urls must be a list of http(s) URLs")
    if len(set(urls)) != len(urls):
        raise ValueError(f"{where}: a URL is listed twice")
    return {"domain": text, "urls": urls}


def _domain_files(folder):
    """The theme files of a DOMAINS_DIR, in name order."""
    return sorted(
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix in (".yaml", ".yml") and not p.name.startswith(".")
    )


def load_domains(directory):
    """Read the domains of a components directory: the files of its
    DOMAINS_DIR in name order, else the single list in its DOMAINS_FILE (the
    layout of snapshots), else the lines of LEGACY_DOMAINS_FILE (snapshots
    before 2026-10-03). Either way a list of mappings with domain and urls,
    checked and free of repeated domains."""
    directory = Path(directory)
    folder, single = directory / DOMAINS_DIR, directory / DOMAINS_FILE
    legacy = directory / LEGACY_DOMAINS_FILE
    present = [p.name for p in (folder, single, legacy) if p.exists()]
    if len(present) > 1:
        raise ValueError(
            f"{directory} has {' and '.join(present)}; keep only one "
            f"({DOMAINS_DIR}/ is the source, {DOMAINS_FILE} a snapshot)"
        )
    if folder.is_dir():
        domains = []
        files = _domain_files(folder)
        if not files:
            raise ValueError(f"{folder}: no domain files (*.yaml)")
        for f in files:
            data = _load_yaml(f)
            if not isinstance(data, list) or not data:
                raise ValueError(f"{f}: expected a non-empty list of domains")
            domains += [_check_domain(d, f"{f}, item {i + 1}") for i, d in enumerate(data)]
    elif single.exists():
        data = _load_yaml(single)
        if not isinstance(data, list) or not data:
            raise ValueError(f"{single}: expected a list of domains")
        domains = [_check_domain(d, f"{single}, item {i + 1}") for i, d in enumerate(data)]
    elif legacy.exists():
        domains = [{"domain": line, "urls": []} for line in _load_lines(legacy)]
    else:
        raise FileNotFoundError(
            f"{directory}: no {DOMAINS_DIR}/ directory, {DOMAINS_FILE}, or {LEGACY_DOMAINS_FILE}"
        )
    counts = collections.Counter(d["domain"] for d in domains)
    if repeated := sorted(text for text, n in counts.items() if n > 1):
        raise ValueError(f"{directory}: domains listed more than once: {repeated[:5]}")
    return domains


def snapshot_domains(directory, dest_dir):
    """Write the domains of a components directory into dest_dir: the theme
    files joined into one DOMAINS_FILE (each file's text after a comment
    naming it, so snapshots diff cleanly), or an existing single file or
    legacy file copied as it is."""
    directory, dest_dir = Path(directory), Path(dest_dir)
    domains = load_domains(directory)
    folder = directory / DOMAINS_DIR
    if not folder.is_dir():
        for name in (DOMAINS_FILE, LEGACY_DOMAINS_FILE):
            if (directory / name).exists():
                shutil.copy2(directory / name, dest_dir / name)
                return
    parts = []
    for path in _domain_files(folder):
        lines = path.read_text().splitlines()
        if any(line.rstrip() in ("---", "...") for line in lines):
            raise ValueError(f"{path}: document markers would not survive joining")
        parts.append(f"# {DOMAINS_DIR}/{path.name}\n" + "\n".join(lines).rstrip("\n") + "\n")
    text = "\n".join(parts)
    joined = [_check_domain(d, DOMAINS_FILE) for d in yaml.safe_load(text)]
    if joined != domains:
        raise ValueError(f"{folder}: the files do not join into one list unchanged")
    (dest_dir / DOMAINS_FILE).write_text(text)


@dataclass
class Components:
    """The component files of one directory, read once, plus the template."""

    source: Path
    domains: list  # the domains' texts, in file order
    domain_urls: dict  # domain text -> its URLs, in file order (often empty)
    task_types: list  # dicts with "type" and optional "examples"/"notes", in file order
    instruction_groups: dict  # group name -> InstructionGroup, in file order
    template: object  # jinja2.Template

    def sample(
        self,
        num_domains=5,
        num_task_types=3,
        rng=random,
        max_examples=MAX_EXAMPLES_SHOWN,
        url_probability=URL_PROBABILITY,
    ):
        """Draw the parameters for one prompt. Pass a seeded random.Random as
        rng for a reproducible draw. For every offered task type, a number of
        examples from 1 to max_examples is drawn, then that many of the type's
        examples (fewer if it has fewer), in random order; task_type_examples
        records their indices into the type's example list. For every offered
        domain, each of its URLs is drawn with probability url_probability;
        domain_urls lists the drawn URLs per offered domain, in the order of
        domains_offered. (The URL draws come last, so the rest of a seeded
        draw is what it was before domains had URLs.)"""
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
            "domains_offered": (
                domains := rng.sample(self.domains, k=min(num_domains, len(self.domains)))
            ),
            "domain_urls": [
                [url for url in self.domain_urls.get(d, []) if rng.random() < url_probability]
                for d in domains
            ],
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
            domain_links=self._links_shown(sample),
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

    def _links_shown(self, sample):
        """The drawn URLs of each offered domain, parallel to domains_offered;
        none for samples that predate domain_urls. Every URL must be one of
        the domain's URLs in these components."""
        domains = sample["domains_offered"]
        links = sample.get("domain_urls")
        if links is None:
            return [[] for _ in domains]
        if not isinstance(links, list) or len(links) != len(domains):
            raise ValueError("sample's domain_urls must be a list parallel to domains_offered")
        for domain, urls in zip(domains, links):
            known = self.domain_urls.get(domain, [])
            if not isinstance(urls, list) or any(u not in known for u in urls):
                raise ValueError(
                    f"sample has URLs for domain {domain[:60]!r} that {self.source} does not list"
                )
        return links

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
        """Write the components into dest_dir (a batch's inputs/): the files
        in COPIED_FILES as they are, the task types joined into one file, and
        the domains joined into one file."""
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        for name in COPIED_FILES:
            shutil.copy2(self.source / name, dest_dir / name)
        (dest_dir / TASK_TYPES_FILE).write_text(join_task_types(self.source))
        snapshot_domains(self.source, dest_dir)


def load(directory=COMPONENTS_DIR):
    """Read the components from a directory, by default this one. Pass a
    batch's inputs/ directory to work from the snapshot a past run used."""
    directory = Path(directory)
    env = Environment(
        loader=FileSystemLoader(directory), trim_blocks=True, lstrip_blocks=True
    )
    domains = load_domains(directory)
    return Components(
        source=directory,
        domains=[d["domain"] for d in domains],
        domain_urls={d["domain"]: d["urls"] for d in domains},
        task_types=load_task_types(directory),
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
    parser.add_argument(
        "--url-probability",
        type=float,
        default=URL_PROBABILITY,
        help=f"chance that each URL of an offered domain is drawn (default: {URL_PROBABILITY})",
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
        sample = components.sample(
            args.num_domains, args.num_task_types, rng, url_probability=args.url_probability
        )
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
