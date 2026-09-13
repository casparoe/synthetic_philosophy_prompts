#!/usr/bin/env python3
"""Write a pair set: the pairs of responses a preference run compares.

A pair set fixes, for a list of prompts, which two responses are compared and
which of them is shown first (A) and which second (B), so that any number of
judges -- a strong model once, weak models many times -- see exactly the same
pairs. The two responses come either from one run that took two samples per
prompt (two answers by the same model, e.g. run_005_imported) or from two
runs (one answer each, e.g. R1 against Qwen on the same prompts). Only
complete pairs qualify: both responses stopped by themselves (finish_reason
stop), have a non-empty answer with no stray <think> tag, and were given the
prompt text as it stands in prompts/. With --complete-in RUN the prompt must
also have complete responses in other runs, so that the same seeded sample of
prompts can be paired for several models. A/B order is a coin flip per pair,
drawn from the same seed.

    tools/make_pair_set.py preferences/pairs/r1_imported_500.yaml --runs responses/run_005_imported \
        --complete-in responses/run_004_imported --sample 500 --seed 0
    tools/make_pair_set.py preferences/pairs/r1_vs_qwen397b_033.yaml --runs responses/run_006,responses/run_007
"""
import argparse
import collections
import pathlib
import random
import re
import shlex
import sys

import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "generators"))
from generate_responses import (  # noqa: E402
    PROMPTS_DIR, YAML_LOADER, now_iso, read_prompt_set, record_path, repo_relative,
)

THINK_TAG = re.compile(r"</?think>")


def load_run(path):
    run_dir = pathlib.Path(path)
    if not (run_dir / "run.yaml").exists():
        raise SystemExit(f"{run_dir}: no run.yaml")
    return run_dir, yaml.safe_load((run_dir / "run.yaml").read_text())


def load_record(path):
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return yaml.load(f, Loader=YAML_LOADER)


def defect(record, prompt_text):
    """Why a response cannot go into a pair, or None if it can."""
    if record is None:
        return "no record"
    if record.get("finish_reason") != "stop":
        return f"finish_reason {record.get('finish_reason')}"
    if not (record.get("answer") or "").strip():
        return "empty answer"
    if THINK_TAG.search(record["answer"]):
        return "<think> tag in answer"
    if (record.get("prompt") or "").strip() != prompt_text:
        return "prompt text differs from the prompt file"
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", help="pair set to write, e.g. preferences/pairs/r1_imported_500.yaml")
    parser.add_argument(
        "--runs", required=True, metavar="RUN[,RUN]",
        help="one run with two samples per prompt (its samples 0 and 1 are paired), or two runs (their first samples are paired)",
    )
    parser.add_argument(
        "--complete-in", metavar="RUN", nargs="*", default=[],
        help="also require complete responses (every sample) in these runs",
    )
    parser.add_argument("--prompt-set", metavar="FILE", help="prompts to draw from (default: the runs' own prompt set)")
    parser.add_argument(
        "--sample", type=int, metavar="N",
        help="walk the prompts in seeded random order and stop after N complete pairs (default: every complete pair, in ID order)",
    )
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    runs = [load_run(p) for p in args.runs.split(",")]
    if len(runs) == 1:
        (run_dir, cfg), = runs
        if cfg["samples_per_prompt"] < 2:
            raise SystemExit(f"{run_dir} has one sample per prompt; pass two runs to pair")
        sources = [(run_dir, cfg, 0), (run_dir, cfg, 1)]
    elif len(runs) == 2:
        sources = [(run_dir, cfg, 0) for run_dir, cfg in runs]
    else:
        parser.error("--runs takes one or two runs")
    extra = [load_run(p) for p in args.complete_in]

    if args.prompt_set:
        candidates = read_prompt_set(args.prompt_set)
    else:
        sets = [set(read_prompt_set(REPO / cfg["prompt_set"])) for _, cfg in runs]
        candidates = sorted(set.intersection(*sets))
    index = {p.stem: p for p in PROMPTS_DIR.glob("**/prompt_*.txt")}

    rng = random.Random(args.seed)
    order = list(candidates)
    if args.sample is not None:
        rng.shuffle(order)
    pairs, skipped, walked = [], collections.Counter(), 0
    for pid in order:
        if args.sample is not None and len(pairs) >= args.sample:
            break
        walked += 1
        if pid not in index:
            skipped["no prompt file"] += 1
            continue
        prompt_text = index[pid].read_text().strip()
        needed = [record_path(run_dir, pid, k, cfg["samples_per_prompt"]) for run_dir, cfg, k in sources]
        for run_dir, cfg in extra:
            needed += [record_path(run_dir, pid, k, cfg["samples_per_prompt"]) for k in range(cfg["samples_per_prompt"])]
        problem = None
        for path in needed:
            problem = defect(load_record(path), prompt_text)
            if problem:
                skipped[f"{problem} ({repo_relative(path.parent)})"] += 1
                break
        if problem:
            continue
        a, b = needed[0], needed[1]
        if rng.random() < 0.5:
            a, b = b, a
        pairs.append({"id": pid, "a": repo_relative(a), "b": repo_relative(b)})
    if args.sample is not None and len(pairs) < args.sample:
        raise SystemExit(f"only {len(pairs)} complete pairs among all {walked} candidates; asked for {args.sample}")
    pairs.sort(key=lambda p: int(p["id"].split("_")[1]))

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    header = {
        "pair_set": repo_relative(out),
        "created_at": now_iso(),
        "command": shlex.join(["tools/make_pair_set.py", *sys.argv[1:]]),
        "runs": [repo_relative(run_dir) for run_dir, _ in runs],
        "complete_in": [repo_relative(run_dir) for run_dir, _ in extra] or None,
        "prompt_set": repo_relative(args.prompt_set) if args.prompt_set else [cfg["prompt_set"] for _, cfg in runs],
        "candidates": len(candidates),
        "walked": walked,
        "skipped": dict(sorted(skipped.items())) or None,
        "sample": args.sample,
        "seed": args.seed,
        "num_pairs": len(pairs),
        "pairs": pairs,
    }
    out.write_text(yaml.safe_dump(header, sort_keys=False, allow_unicode=True))
    print(f"{len(pairs)} pairs from {walked} of {len(candidates)} candidates walked; skipped {dict(skipped) or 'none'}")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
