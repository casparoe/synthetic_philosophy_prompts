#!/usr/bin/env python3
"""Write a prompt set: the list of prompt IDs a response run answers.

Starts from every prompt under prompts/, optionally keeps only some batches
or only prompts whose sidecar names a generating model matching a regex (e.g.
'qwen|deepseek' for the prompts written by open-weight models), drops the IDs
of any --exclude sets and the prompts that already have a response in any
--without-response run, and optionally takes a seeded random sample. The file
opens with comment lines that record how it was made; IDs follow, sorted.

    tools/make_prompt_set.py responses/sets/open_1k.txt --generator-model 'qwen|deepseek' --sample 1000 --seed 0
    tools/make_prompt_set.py responses/sets/all.txt
    tools/make_prompt_set.py responses/sets/open_1k_sub100.txt --from responses/sets/open_1k.txt --sample 100
    tools/make_prompt_set.py responses/sets/r1_gap.txt --batches 022-040 \
        --without-response responses/run_003 responses/run_006 responses/run_009 responses/run_010
"""
import argparse
import pathlib
import random
import re
import shlex
import sys
from datetime import datetime, timezone

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "generators"))
from generate_responses import PROMPTS_DIR, RECORD_FILE_RE, read_prompt_set  # noqa: E402

MODEL_LINE = re.compile(r"^model:\s*(.+?)\s*$", re.M)


def parse_batches(spec):
    """'022-029,032' -> {22, ..., 29, 32}"""
    batches = set()
    for part in spec.split(","):
        lo, _, hi = part.partition("-")
        batches.update(range(int(lo), int(hi or lo) + 1))
    return batches


def answered_in(run_dir):
    """Prompt IDs that have at least one response file in a run."""
    ids = set()
    for path in pathlib.Path(run_dir).glob("prompt_*.yaml"):
        m = RECORD_FILE_RE.fullmatch(path.name)
        if m:
            ids.add(f"prompt_{int(m.group(1)):05d}")
    return ids


def generating_model(prompt_path):
    sidecar = prompt_path.with_suffix(".meta.yaml")
    if not sidecar.exists():
        return ""
    m = MODEL_LINE.search(sidecar.read_text())
    return m.group(1).strip("'\"") if m else ""


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", help="set file to write, e.g. responses/sets/open_1k.txt")
    parser.add_argument("--batches", metavar="SPEC", help="only these batches, e.g. 022-029,032-033")
    parser.add_argument(
        "--generator-model", metavar="REGEX",
        help="only prompts whose sidecar's model matches (case-insensitive), e.g. 'qwen|deepseek'",
    )
    parser.add_argument("--from", dest="from_set", metavar="SET", help="choose only among the IDs of this set file (for a subset)")
    parser.add_argument("--exclude", metavar="SET", nargs="*", default=[], help="drop the IDs in these set files")
    parser.add_argument(
        "--without-response", metavar="RUN", nargs="*", default=[],
        help="drop the prompts that already have a response file in these run directories",
    )
    parser.add_argument("--sample", type=int, metavar="N", help="random sample of N prompts (default: all)")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    paths = sorted(PROMPTS_DIR.glob("**/prompt_*.txt"))
    total = len(paths)
    if args.batches:
        wanted = parse_batches(args.batches)
        paths = [p for p in paths if (m := re.fullmatch(r"batch_(\d+)", p.parent.name)) and int(m.group(1)) in wanted]
    if args.generator_model:
        pattern = re.compile(args.generator_model, re.I)
        paths = [p for p in paths if pattern.search(generating_model(p))]
    if args.from_set:
        allowed = set(read_prompt_set(args.from_set))
        paths = [p for p in paths if p.stem in allowed]
    excluded = set()
    for set_file in args.exclude:
        excluded.update(read_prompt_set(set_file))
    answered = set()
    for run_dir in args.without_response:
        answered.update(answered_in(run_dir))
    n_before = len(paths)
    paths = [p for p in paths if p.stem not in excluded]
    n_excluded = n_before - len(paths)
    n_before = len(paths)
    paths = [p for p in paths if p.stem not in answered]
    n_answered = n_before - len(paths)
    candidates = len(paths)
    if args.sample is not None:
        if args.sample > candidates:
            raise SystemExit(f"asked for {args.sample} prompts but only {candidates} qualify")
        paths = sorted(random.Random(args.seed).sample(paths, args.sample))

    filters = []
    if args.from_set:
        filters.append(f"within {args.from_set}")
    if args.batches:
        filters.append(f"batches {args.batches}")
    if args.generator_model:
        filters.append(f"generator model ~ /{args.generator_model}/")
    if args.exclude:
        filters.append(f"minus {n_excluded} in {', '.join(args.exclude)}")
    if args.without_response:
        filters.append(f"minus {n_answered} already answered in {', '.join(args.without_response)}")
    header = [
        f"# prompt set written {datetime.now(timezone.utc).isoformat(timespec='seconds')} by "
        + shlex.join(["tools/make_prompt_set.py", *sys.argv[1:]]),
        f"# {len(paths)} prompts"
        + (f", sampled with seed {args.seed}" if args.sample is not None else "")
        + f" from {candidates} candidates ({'; '.join(filters) or 'all prompts'}; {total} prompts in the dataset)",
    ]
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(header + [p.stem for p in paths]) + "\n")
    print("\n".join(header))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
