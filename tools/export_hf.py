#!/usr/bin/env python
"""Export the dataset to a staging folder for the Hugging Face Hub.

The repository keeps one file per prompt and per response, which suits git and
grep but not the Hub (its guidance is under about 100,000 files per repository
and 10,000 per folder; this dataset has close to two million). The export writes
one Parquet shard per prompt batch, per response run, and per preference run,
with a fixed schema per kind so that every shard of a kind can be loaded as one
table, and copies the small metadata files (batch and run settings, meta-prompt
snapshots, prompt sets, pair sets, judge prompts) unchanged.

    python tools/export_hf.py --out hf_export --exclude-batches 052,054,055 \\
        --exclude-runs run_020,run_021,run_022
    python tools/export_hf.py --out hf_export --verify

Shards whose row count already matches the number of source files are skipped
unless --force is given. --verify re-reads every shard: schema, row count against
the source, an exact comparison of a random sample of rows with their source
files, uniqueness of prompt IDs across batches, and that every response and
judgment refers to an exported prompt.

Normalizations, all documented in the dataset card:
  * prompt `text` is the .txt file content without its single trailing newline;
  * the three separate keys of batches before 029 (length, persona, writing_style)
    are folded into the `additional_instructions` JSON object like later batches;
  * dictionaries (`additional_instructions`, `task_type_examples`) are stored as
    JSON strings; unknown sidecar or record keys go into the `extra` JSON string.
"""

import argparse
import json
import random
import re
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = REPO_ROOT / "prompts"
RESPONSES_DIR = REPO_ROOT / "responses"
PREFERENCES_DIR = REPO_ROOT / "preferences"
Loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

PROMPT_SCHEMA = pa.schema(
    [
        ("prompt_id", pa.int64()),
        ("batch", pa.string()),
        ("prompt_file", pa.string()),
        ("text", pa.large_string()),
        ("model", pa.string()),
        ("effort", pa.string()),
        ("generated_at", pa.string()),
        ("input_tokens", pa.int64()),
        ("output_tokens", pa.int64()),
        ("web_searches", pa.int64()),
        ("web_fetches", pa.int64()),
        ("cost_usd", pa.float64()),
        ("providers", pa.list_(pa.string())),
        ("generation_ids", pa.list_(pa.string())),
        ("domains_offered", pa.list_(pa.string())),
        ("task_types_offered", pa.list_(pa.string())),
        ("additional_instructions", pa.string()),
        ("task_type_examples", pa.string()),
        ("reasoning_summary", pa.large_string()),
        ("custom_id", pa.string()),
        ("extra", pa.string()),
    ]
)
PROMPT_SCALARS = {
    "model", "effort", "generated_at", "input_tokens", "output_tokens",
    "web_searches", "web_fetches", "cost_usd", "reasoning_summary", "custom_id",
}
PROMPT_LISTS = {"providers", "generation_ids", "domains_offered", "task_types_offered"}
PROMPT_JSON = {"additional_instructions", "task_type_examples"}
LEGACY_GROUPS = ("length", "persona", "writing_style")

RESPONSE_SCHEMA = pa.schema(
    [
        ("id", pa.string()),
        ("run", pa.string()),
        ("prompt_id", pa.int64()),
        ("sample_index", pa.int64()),
        ("prompt_file", pa.string()),
        ("model", pa.string()),
        ("provider", pa.string()),
        ("generation_id", pa.string()),
        ("finish_reason", pa.string()),
        ("native_finish_reason", pa.string()),
        ("prompt_tokens", pa.int64()),
        ("completion_tokens", pa.int64()),
        ("reasoning_tokens", pa.int64()),
        ("cost_usd", pa.float64()),
        ("reasoning_detail_types", pa.list_(pa.string())),
        ("created_at", pa.string()),
        ("imported_from", pa.string()),
        ("source_id", pa.string()),
        ("prompt", pa.large_string()),
        ("reasoning", pa.large_string()),
        ("answer", pa.large_string()),
        ("extra", pa.string()),
    ]
)
RESPONSE_SCALARS = {
    "id", "sample_index", "prompt_file", "model", "provider", "generation_id",
    "finish_reason", "native_finish_reason", "prompt_tokens", "completion_tokens",
    "reasoning_tokens", "cost_usd", "created_at", "imported_from", "source_id",
    "prompt", "reasoning", "answer",
}
RESPONSE_LISTS = {"reasoning_detail_types"}

PREFERENCE_SCHEMA = pa.schema(
    [
        ("id", pa.string()),
        ("run", pa.string()),
        ("prompt_id", pa.int64()),
        ("pair_set", pa.string()),
        ("response_a", pa.string()),
        ("response_b", pa.string()),
        ("judge_model", pa.string()),
        ("effort", pa.string()),
        ("api", pa.string()),
        ("verdict", pa.string()),
        ("preferred", pa.string()),
        ("strength", pa.string()),
        ("stop_reason", pa.string()),
        ("input_tokens", pa.int64()),
        ("output_tokens", pa.int64()),
        ("cost_usd", pa.float64()),
        ("message_id", pa.string()),
        ("attempts", pa.int64()),
        ("created_at", pa.string()),
        ("thinking", pa.large_string()),
        ("judgment", pa.large_string()),
        ("extra", pa.string()),
    ]
)
PREFERENCE_SCALARS = {
    "id", "pair_set", "response_a", "response_b", "judge_model", "effort", "api",
    "verdict", "preferred", "strength", "stop_reason", "input_tokens", "output_tokens",
    "cost_usd", "message_id", "attempts", "created_at", "thinking", "judgment",
}


def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.load(f, Loader=Loader)


def dump_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=False)


def prompt_id_of(name):
    """The prompt number in a file name or path such as prompt_00123.txt,
    prompt_00123.1.yaml, or prompts/batch_009/prompt_00123.txt."""
    m = re.match(r"prompt_(\d+)", Path(name).name)
    return int(m.group(1)) if m else None


def str_or_none(value):
    return None if value is None else str(value)


def int_or_none(value):
    return None if value is None else int(value)


def float_or_none(value):
    return None if value is None else float(value)


def list_of_str(value):
    return None if value is None else [str(v) for v in value]


# --- rows ---------------------------------------------------------------------

def prompt_row(batch, txt_path):
    meta_path = txt_path.with_name(txt_path.stem + ".meta.yaml")
    meta = load_yaml(meta_path) if meta_path.exists() else {}
    text = txt_path.read_text(encoding="utf-8")
    if text.endswith("\n"):
        text = text[:-1]
    row = {name: None for name in PROMPT_SCHEMA.names}
    row.update(prompt_id=prompt_id_of(txt_path.name), batch=batch, prompt_file=txt_path.name, text=text)
    extra = {}
    for key, value in meta.items():
        if key == "prompt_file":
            continue
        if key in PROMPT_SCALARS:
            row[key] = value
        elif key in PROMPT_LISTS:
            row[key] = list_of_str(value)
        elif key in PROMPT_JSON:
            row[key] = dump_json(value) if value is not None else None
        elif key in LEGACY_GROUPS:
            continue
        else:
            extra[key] = value
    if any(k in meta for k in LEGACY_GROUPS) and not meta.get("additional_instructions"):
        row["additional_instructions"] = dump_json({k: meta[k] for k in LEGACY_GROUPS if k in meta})
    for key in ("input_tokens", "output_tokens", "web_searches", "web_fetches"):
        row[key] = int_or_none(row[key])
    row["cost_usd"] = float_or_none(row["cost_usd"])
    for key in ("model", "effort", "generated_at", "reasoning_summary", "custom_id"):
        row[key] = str_or_none(row[key])
    row["extra"] = dump_json(extra) if extra else None
    return row


def response_row(run, path):
    rec = load_yaml(path)
    row = {name: None for name in RESPONSE_SCHEMA.names}
    row["run"] = run
    extra = {}
    for key, value in rec.items():
        if key in RESPONSE_SCALARS:
            row[key] = value
        elif key in RESPONSE_LISTS:
            row[key] = list_of_str(value)
        else:
            extra[key] = value
    row["prompt_id"] = prompt_id_of(path.name)
    for key in ("sample_index", "prompt_tokens", "completion_tokens", "reasoning_tokens"):
        row[key] = int_or_none(row[key])
    row["cost_usd"] = float_or_none(row["cost_usd"])
    for key in RESPONSE_SCALARS - {"sample_index", "prompt_tokens", "completion_tokens", "reasoning_tokens", "cost_usd"}:
        row[key] = str_or_none(row[key])
    row["extra"] = dump_json(extra) if extra else None
    return row


def preference_row(run, path):
    rec = load_yaml(path)
    row = {name: None for name in PREFERENCE_SCHEMA.names}
    row["run"] = run
    extra = {}
    for key, value in rec.items():
        if key in PREFERENCE_SCALARS:
            row[key] = value
        else:
            extra[key] = value
    row["prompt_id"] = prompt_id_of(row["id"] or path.name)
    for key in ("input_tokens", "output_tokens", "attempts"):
        row[key] = int_or_none(row[key])
    row["cost_usd"] = float_or_none(row["cost_usd"])
    for key in PREFERENCE_SCALARS - {"input_tokens", "output_tokens", "attempts", "cost_usd"}:
        row[key] = str_or_none(row[key])
    row["extra"] = dump_json(extra) if extra else None
    return row


# --- shards -------------------------------------------------------------------

def source_files(kind, name):
    if kind == "prompts":
        return sorted((PROMPTS_DIR / f"batch_{name}").glob("prompt_*.txt"), key=lambda p: prompt_id_of(p.name))
    if kind == "responses":
        return sorted((RESPONSES_DIR / name).glob("prompt_*.yaml"), key=lambda p: (prompt_id_of(p.name), p.name))
    if kind == "preferences":
        return sorted(p for p in (PREFERENCES_DIR / name).glob("prompt_*.yaml"))
    raise ValueError(kind)


SCHEMAS = {"prompts": PROMPT_SCHEMA, "responses": RESPONSE_SCHEMA, "preferences": PREFERENCE_SCHEMA}
ROW_FUNCS = {"prompts": prompt_row, "responses": response_row, "preferences": preference_row}
CHUNK = {"prompts": 5000, "responses": 2000, "preferences": 2000}


def shard_path(out, kind, name):
    return out / "data" / kind / (f"batch_{name}.parquet" if kind == "prompts" else f"{name}.parquet")


def write_shard(args):
    kind, name, out, force = args
    files = source_files(kind, name)
    path = shard_path(out, kind, name)
    if not files:
        return f"{kind}/{name}: no source files, skipped"
    if path.exists() and not force:
        if pq.read_metadata(path).num_rows == len(files):
            return f"{kind}/{name}: up to date ({len(files)} rows)"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    schema, row_func, chunk = SCHEMAS[kind], ROW_FUNCS[kind], CHUNK[kind]
    writer = pq.ParquetWriter(tmp, schema, compression="zstd")
    try:
        for start in range(0, len(files), chunk):
            rows = [row_func(name, p) for p in files[start:start + chunk]]
            writer.write_table(pa.Table.from_pylist(rows, schema=schema))
    finally:
        writer.close()
    tmp.replace(path)
    return f"{kind}/{name}: wrote {len(files)} rows, {path.stat().st_size / 1e6:.1f} MB"


def copy_small_files(out, batches, runs, pref_runs):
    copied = 0
    for b in batches:
        src = PROMPTS_DIR / f"batch_{b}"
        if (src / "batch.yaml").exists():
            dst = out / "metadata" / "batches" / f"batch_{b}.yaml"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / "batch.yaml", dst)
            copied += 1
        if (src / "inputs").is_dir():
            dst = out / "inputs" / f"batch_{b}"
            dst.mkdir(parents=True, exist_ok=True)
            for f in (src / "inputs").iterdir():
                if f.is_file():
                    shutil.copy2(f, dst / f.name)
                    copied += 1
    for r in runs:
        src = RESPONSES_DIR / r / "run.yaml"
        if src.exists():
            dst = out / "metadata" / "runs" / f"{r}.yaml"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
    sets_dst = out / "sets"
    sets_dst.mkdir(parents=True, exist_ok=True)
    for f in sorted((RESPONSES_DIR / "sets").glob("*.txt")):
        shutil.copy2(f, sets_dst / f.name)
        copied += 1
    pref_dst = out / "preferences"
    (pref_dst / "pairs").mkdir(parents=True, exist_ok=True)
    for f in sorted((PREFERENCES_DIR / "pairs").glob("*.yaml")):
        shutil.copy2(f, pref_dst / "pairs" / f.name)
        copied += 1
    if (PREFERENCES_DIR / "judge_prompt.j2").exists():
        shutil.copy2(PREFERENCES_DIR / "judge_prompt.j2", pref_dst / "judge_prompt.j2")
        copied += 1
    for r in pref_runs:
        dst = pref_dst / r
        dst.mkdir(parents=True, exist_ok=True)
        for fname in ("run.yaml", "judge_prompt.j2", "message_batches.txt"):
            if (PREFERENCES_DIR / r / fname).exists():
                shutil.copy2(PREFERENCES_DIR / r / fname, dst / fname)
                copied += 1
    return copied


# --- verification ---------------------------------------------------------------

def verify(out, sample_size, seed, partial=False):
    rng = random.Random(seed)
    problems = []
    notes = []
    prompt_ids = {}
    for kind in ("prompts", "responses", "preferences"):
        for path in sorted((out / "data" / kind).glob("*.parquet")):
            name = path.stem[len("batch_"):] if kind == "prompts" else path.stem
            files = source_files(kind, name)
            table = pq.read_table(path)
            if not table.schema.equals(SCHEMAS[kind]):
                problems.append(f"{path.name}: schema differs from the canonical {kind} schema")
            if table.num_rows != len(files):
                problems.append(f"{path.name}: {table.num_rows} rows but {len(files)} source files")
            rows_by_key = None
            for i in sorted(rng.sample(range(table.num_rows), min(sample_size, table.num_rows))):
                row = {c: table.column(c)[i].as_py() for c in table.column_names}
                expected = ROW_FUNCS[kind](name, files[i])
                if row != expected:
                    diff = [c for c in table.column_names if row[c] != expected[c]]
                    problems.append(f"{path.name} row {i}: differs from source in {diff}")
            if kind == "prompts":
                for pid in table.column("prompt_id").to_pylist():
                    if pid in prompt_ids:
                        problems.append(f"prompt_id {pid} appears in batch {prompt_ids[pid]} and batch {name}")
                    prompt_ids[pid] = name
            else:
                missing = set(table.column("prompt_id").to_pylist()) - set(prompt_ids)
                if missing:
                    (notes if partial else problems).append(f"{path.name}: {len(missing)} prompt IDs without an exported prompt, e.g. {sorted(missing)[:3]}")
            print(f"checked {path.name}: {table.num_rows} rows")
    print(f"{len(prompt_ids)} distinct prompt IDs")
    for n in notes:
        print("note (partial export):", n)
    for p in problems:
        print("PROBLEM:", p)
    return not problems


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="hf_export", help="staging folder (default: hf_export)")
    parser.add_argument("--batches", help="only these batch numbers, e.g. 009,053")
    parser.add_argument("--runs", help="only these response runs, e.g. run_003,run_024")
    parser.add_argument("--pref-runs", help="only these preference runs, e.g. run_000")
    parser.add_argument("--exclude-batches", default="", help="batch numbers to leave out (still generating)")
    parser.add_argument("--exclude-runs", default="", help="response runs to leave out (still running)")
    parser.add_argument("--force", action="store_true", help="rewrite shards that look up to date")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--verify", action="store_true", help="check the staging folder instead of writing it")
    parser.add_argument("--sample", type=int, default=25, help="rows compared with their source per shard when verifying")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--partial", action="store_true", help="when verifying a partial export, report responses to unexported prompts as notes, not problems")
    args = parser.parse_args()
    out = Path(args.out)
    if not out.is_absolute():
        out = REPO_ROOT / out

    if args.verify:
        ok = verify(out, args.sample, args.seed, args.partial)
        print("VERIFY", "OK" if ok else "FAILED")
        sys.exit(0 if ok else 1)

    excl_b = set(filter(None, args.exclude_batches.split(",")))
    excl_r = set(filter(None, args.exclude_runs.split(",")))
    batches = sorted(p.name[len("batch_"):] for p in PROMPTS_DIR.glob("batch_*") if p.is_dir())
    batches = [b for b in batches if b not in excl_b]
    if args.batches:
        batches = [b for b in batches if b in set(args.batches.split(","))]
    runs = sorted(p.name for p in RESPONSES_DIR.glob("run_*") if p.is_dir())
    runs = [r for r in runs if r not in excl_r]
    if args.runs:
        runs = [r for r in runs if r in set(args.runs.split(","))]
    pref_runs = sorted(p.name for p in PREFERENCES_DIR.glob("run_*") if p.is_dir())
    if args.pref_runs:
        pref_runs = [r for r in pref_runs if r in set(args.pref_runs.split(","))]

    jobs = [("prompts", b, out, args.force) for b in batches]
    jobs += [("responses", r, out, args.force) for r in runs]
    jobs += [("preferences", r, out, args.force) for r in pref_runs]
    print(f"{len(batches)} batches, {len(runs)} response runs, {len(pref_runs)} preference runs -> {out}")
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for msg in pool.map(write_shard, jobs):
            print(msg, flush=True)
    print(f"copied {copy_small_files(out, batches, runs, pref_runs)} metadata files")


if __name__ == "__main__":
    main()
