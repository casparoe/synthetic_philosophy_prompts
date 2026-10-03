#!/usr/bin/env python
"""Count the domains in each theme file, and how many of them have URLs.

Reads meta_prompt/domains/ by default. Pass another domains directory, or a
batch's joined snapshot (prompts/batch_NNN/inputs/domains.yaml, whose themes
are marked by the "# domains/<file>" comments that snapshots write), to count
that instead.

    .venv/bin/python tools/count_domains.py
    .venv/bin/python tools/count_domains.py --sort name
    .venv/bin/python tools/count_domains.py prompts/batch_NNN/inputs/domains.yaml
"""

import argparse
import pathlib
import re
import sys

import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "meta_prompt"))
import assemble  # noqa: E402

MARKER = re.compile(rf"^# {assemble.DOMAINS_DIR}/(.+?)\.ya?ml\s*$", re.M)


def themes_of_directory(folder):
    """Theme name -> list of domain entries, one theme per file."""
    themes = {}
    for path in assemble._domain_files(folder):
        data = assemble._load_yaml(path) or []
        themes[path.stem] = [assemble._check_domain(d, f"{path}, item {i + 1}") for i, d in enumerate(data)]
    return themes


def themes_of_snapshot(path):
    """Theme name -> list of domain entries, split at the snapshot's file markers."""
    text = path.read_text()
    marks = list(MARKER.finditer(text))
    if not marks:
        raise SystemExit(f"{path}: no '# {assemble.DOMAINS_DIR}/<file>' markers to split themes by")
    themes = {}
    for mark, nxt in zip(marks, marks[1:] + [None]):
        chunk = text[mark.end(): nxt.start() if nxt else len(text)]
        data = yaml.safe_load(chunk) or []
        themes[mark.group(1)] = [assemble._check_domain(d, f"{path}, theme {mark.group(1)}") for d in data]
    return themes


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "source",
        nargs="?",
        default=REPO / "meta_prompt" / assemble.DOMAINS_DIR,
        type=pathlib.Path,
        help="a domains directory or a snapshot's domains.yaml (default: meta_prompt/domains)",
    )
    parser.add_argument(
        "--sort",
        choices=["count", "name"],
        default="count",
        help="order the themes by number of domains (default) or by name",
    )
    args = parser.parse_args()

    themes = themes_of_directory(args.source) if args.source.is_dir() else themes_of_snapshot(args.source)
    rows = [
        (name, len(entries), sum(1 for e in entries if e["urls"]), sum(len(e["urls"]) for e in entries))
        for name, entries in themes.items()
    ]
    if args.sort == "count":
        rows.sort(key=lambda r: (-r[1], r[0]))
    else:
        rows.sort()
    width = max(len("theme"), *(len(r[0]) for r in rows))
    print(f"{'theme':<{width}}  {'domains':>7}  {'with URLs':>9}  {'URLs':>5}")
    for name, n, with_urls, urls in rows:
        print(f"{name:<{width}}  {n:>7}  {with_urls:>9}  {urls:>5}")
    total = (sum(r[1] for r in rows), sum(r[2] for r in rows), sum(r[3] for r in rows))
    label = f"total ({len(rows)} themes)"
    print(f"{label:<{width}}  {total[0]:>7}  {total[1]:>9}  {total[2]:>5}")


if __name__ == "__main__":
    main()
