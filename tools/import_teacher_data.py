#!/usr/bin/env python
"""Import a teacher-data collection from the cr_training sister repo as a run.

Before this repository had responses of its own, the sister repo collected two
independent samples per prompt from self-hosted models (vLLM on Modal, official
fp8 weights) for the first 22,367 prompts. This converts one such collection
(one or more JSONL files, plain or gzipped) into a run directory in the same
per-response YAML layout that generate_responses.py writes, marked as imported
at every level: the directory name ends in `_imported`, run.yaml says
`api: imported` and carries a `source` block, and every record has
`imported_from` and `source_id`.

Source records look like {id, source, messages, teacher, reasoning, answer,
raw_text, finish_reason, prompt_tokens, completion_tokens, sampling}. The id is
`synthphil_prompt_00042`, with a `__s2` suffix for the second sample. raw_text
(reasoning plus answer again) and the `teacher` label (wrong in every source
record) are dropped; the model comes from --model.

    tools/import_teacher_data.py responses/run_004_imported \\
        --model Qwen/Qwen3.5-397B-A17B-FP8 --prompt-set responses/sets/batches_000-021.txt \\
        --source "q397b_synthphil_v1=~/cr_training/teacher_data/q397b_synthphil_v1/completions_*.jsonl" \\
        --source "q397b_synthphil_v2=~/cr_training/teacher_data/q397b_synthphil_v2/completions_*.gz" \\
        --collected "2026-08-22 (q397b_synthphil_v1), 2026-08-28 (q397b_synthphil_v2)" \\
        --temperature 0.6 --top-p 0.95 --max-tokens 16384
"""
import argparse
import collections
import glob
import gzip
import json
import os
import pathlib
import re
import shlex
import sys

import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "generators"))
from generate_responses import (  # noqa: E402
    REPO_ROOT, clean_text, now_iso, prompt_index, read_prompt_set, record_path, write_record,
)

SOURCE_ID_RE = re.compile(r"^synthphil_(prompt_\d+)(__s2)?$")
SERVING = "self-hosted vLLM 0.25 on Modal, 8xH200 (TP=8), official fp8 weights, max_model_len 65536"


def open_text(path):
    return gzip.open(path, "rt", encoding="utf-8") if str(path).endswith(".gz") else open(path, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir", type=pathlib.Path, help="new run directory, e.g. responses/run_004_imported")
    ap.add_argument("--model", required=True, help="model as served, e.g. Qwen/Qwen3.5-397B-A17B-FP8")
    ap.add_argument("--hugging-face-id", help="default: same as --model")
    ap.add_argument("--prompt-set", required=True, help="set file the records must belong to")
    ap.add_argument("--source", action="append", required=True, metavar="NAME=GLOB",
                    help="a source collection and its JSONL file(s); repeatable")
    ap.add_argument("--source-repo", default="casparoe/cr_training, teacher_data/",
                    help="where the sources came from, for run.yaml")
    ap.add_argument("--collected", required=True, help="when the sources were generated, for run.yaml")
    ap.add_argument("--serving", default=SERVING)
    ap.add_argument("--note", default="", help="free text for run.yaml")
    ap.add_argument("--temperature", type=float, required=True)
    ap.add_argument("--top-p", type=float, required=True)
    ap.add_argument("--max-tokens", type=int, required=True)
    ap.add_argument("--samples-per-prompt", type=int, default=2)
    ap.add_argument("--limit", type=int, help="import only the first N records (for testing)")
    args = ap.parse_args()

    run_dir = args.run_dir
    if run_dir.exists() and any(run_dir.iterdir()):
        sys.exit(f"{run_dir} exists and is not empty")
    if not re.fullmatch(r"run_\d+_imported", run_dir.name):
        sys.exit(f"{run_dir.name}: imported runs are named run_NNN_imported")
    run_dir.mkdir(parents=True, exist_ok=True)

    set_path = pathlib.Path(args.prompt_set)
    wanted = set(read_prompt_set(set_path))
    paths = prompt_index()
    sources = []
    for spec in args.source:
        name, _, pattern = spec.partition("=")
        files = sorted(glob.glob(os.path.expanduser(pattern)))
        if not name or not files:
            sys.exit(f"--source {spec!r}: no files")
        sources.append((name, files))

    stats = collections.Counter()
    seen = set()
    mismatched = []
    per_source = []
    created = now_iso()
    n_written = 0
    for name, files in sources:
        n_source = 0
        for file in files:
            with open_text(file) as f:
                for line in f:
                    if args.limit and n_written >= args.limit:
                        break
                    src = json.loads(line)
                    m = SOURCE_ID_RE.match(src["id"])
                    if not m:
                        stats["unrecognized id"] += 1
                        continue
                    pid, sample_index = m.group(1), 1 if m.group(2) else 0
                    if pid not in wanted or pid not in paths:
                        stats["outside prompt set"] += 1
                        continue
                    if (pid, sample_index) in seen:
                        stats["duplicate (pid, sample)"] += 1
                        continue
                    seen.add((pid, sample_index))
                    prompt = src["messages"][-1]["content"]
                    if prompt.strip() != paths[pid].read_text().strip():
                        mismatched.append(pid)
                    reasoning = clean_text((src.get("reasoning") or "").strip()) or None
                    answer = clean_text((src.get("answer") or "").strip())
                    record = {
                        "id": pid,
                        "sample_index": sample_index,
                        "prompt_file": str(paths[pid].relative_to(REPO_ROOT)),
                        "model": args.model,
                        "provider": "self-hosted vLLM (imported, see run.yaml)",
                        "generation_id": None,
                        "finish_reason": src.get("finish_reason"),
                        "native_finish_reason": None,
                        "prompt_tokens": src.get("prompt_tokens"),
                        "completion_tokens": src.get("completion_tokens"),
                        "reasoning_tokens": None,
                        "cost_usd": None,
                        "reasoning_detail_types": None,
                        "created_at": created,
                        "imported_from": name,
                        "source_id": src["id"],
                        "prompt": clean_text(prompt),
                        "reasoning": reasoning,
                        "answer": answer,
                    }
                    write_record(record_path(run_dir, pid, sample_index, args.samples_per_prompt), record)
                    n_written += 1
                    n_source += 1
                    stats[f"sample {sample_index}"] += 1
                    stats[f"finish {record['finish_reason']}"] += 1
                    if reasoning is None:
                        stats["no reasoning"] += 1
                    if not answer:
                        stats["empty answer"] += 1
                    if n_written % 5000 == 0:
                        print(f"  {n_written} records written", flush=True)
        per_source.append({"name": name, "files": [os.path.relpath(f, os.path.expanduser("~")) for f in files],
                           "records": n_source})

    config = {
        "run": run_dir.name,
        "created_at": created,
        "command": shlex.join([str(pathlib.Path(sys.argv[0]).relative_to(REPO_ROOT)) if pathlib.Path(sys.argv[0]).is_absolute() else sys.argv[0], *sys.argv[1:]]),
        "api": "imported",
        "base_url": None,
        "model": args.model,
        "hugging_face_id": args.hugging_face_id or args.model,
        "prompt_set": str(set_path),
        "num_prompts": len(wanted),
        "samples_per_prompt": args.samples_per_prompt,
        "system_prompt": None,
        "reasoning": {"enabled": True},
        "max_tokens": args.max_tokens,
        "sampling": {"temperature": args.temperature, "top_p": args.top_p},
        "provider": None,
        "source": {
            "repository": args.source_repo,
            "collections": per_source,
            "collected": args.collected,
            "serving": args.serving,
            "records": n_written,
            "prompt_text_mismatches": len(mismatched),
            "note": ("Imported, not generated by generate_responses.py: no gateway metadata "
                     "(generation IDs, costs, reasoning token counts, native finish reasons); "
                     "reasoning is the <think> block as split by the collector; the source "
                     "records' raw_text (reasoning plus answer) and mislabeled teacher field "
                     "were dropped. " + args.note).strip(),
        },
    }
    (run_dir / "run.yaml").write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True))
    print(f"done: {n_written} records -> {run_dir}; " + ", ".join(f"{k} {v}" for k, v in sorted(stats.items())))
    if mismatched:
        print(f"prompt text differs from the current prompt file for {len(mismatched)} records, e.g. {mismatched[:5]}")


if __name__ == "__main__":
    main()
