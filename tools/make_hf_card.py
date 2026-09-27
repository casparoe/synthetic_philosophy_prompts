#!/usr/bin/env python
"""Write the dataset card (README.md) for the Hugging Face staging folder.

    python tools/make_hf_card.py --out hf_export --repo casparoe/synthetic_philosophy_prompts

The card combines a Hub-specific opening (what the Parquet shards contain, how to
load them, how the columns relate to the per-file layout of the GitHub repository)
with sections copied verbatim from this repository's README.md, which stays the
single place where batches, runs, and licensing are described: the sections on how
the prompts were generated (with the batch table), on responses (with the run table
and field table), on preference pairs, on quality control, on authorship, and on
licensing and provenance. Row counts come from the shards in the staging folder.
LICENSE-DATA is copied next to the card.
"""

import argparse
import re
import shutil
from pathlib import Path

import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parent.parent
COPIED_SECTIONS = [
    "How the prompts were generated",
    "Responses",
    "Preference pairs",
    "Quality control and known limitations",
    "Authorship",
    "Licensing and provenance",
]

FRONT_MATTER = """---
license: cc-by-4.0
language:
  - en
pretty_name: Synthetic Philosophy Prompts
size_categories:
  - 100K<n<1M
task_categories:
  - text-generation
  - question-answering
tags:
  - philosophy
  - synthetic
  - reasoning
  - chain-of-thought
  - distillation
  - preferences
configs:
  - config_name: prompts
    default: true
    data_files:
      - split: train
        path: data/prompts/*.parquet
  - config_name: responses
    data_files:
      - split: train
        path: data/responses/*.parquet
  - config_name: preferences
    data_files:
      - split: train
        path: data/preferences/*.parquet
---
"""


def readme_sections(text):
    """Map each '## ' heading to its body (without the heading line)."""
    parts = re.split(r"^## (.+)$", text, flags=re.M)
    return {parts[i].strip(): parts[i + 1].strip("\n") for i in range(1, len(parts), 2)}


def count_rows(folder):
    counts = {}
    for kind in ("prompts", "responses", "preferences"):
        files = sorted((folder / "data" / kind).glob("*.parquet"))
        counts[kind] = {f.stem: pq.read_metadata(f).num_rows for f in files}
    return counts


def fmt(n):
    return f"{n:,}"


def opening(repo, counts):
    n_prompts = sum(counts["prompts"].values())
    n_batches = len(counts["prompts"])
    n_responses = sum(counts["responses"].values())
    n_runs = len(counts["responses"])
    n_judgments = sum(counts["preferences"].values())
    n_pref_runs = len(counts["preferences"])
    github = "https://github.com/casparoe/synthetic_philosophy_prompts"
    return f"""# Synthetic Philosophy Prompts

{fmt(n_prompts)} synthetic user prompts on philosophical and conceptual topics — decision
theory, formal epistemology, philosophy of science, mind, and language, ethics,
metaphysics, history of philosophy, AI alignment as a conceptual topic, and more, with a
smaller share of non-Western and historical traditions — in {n_batches} batches written by
a dozen generating models, plus {fmt(n_responses)} responses to subsets of them from
open-weight reasoning models in {n_runs} runs, each with the model's complete chain of
thought, and {fmt(n_judgments)} pairwise preference judgments of such responses by a strong
model in {n_pref_runs} runs. Each prompt is written as if by a real person (a grad student, a
retired physicist, a novelist, a committee member, ...) in one of the genres listed in
the meta-prompt's task types (explanations, essay requests, grading tasks, dialogues,
adjudications of disagreements, committee memos, interview questions, speeches for
occasions, rankings, ...). The prompts are deliberately "in the weeds": specific enough
that a model cannot answer by regurgitating a canned summary, while remaining
answerable for a model without web access.

The generation code, the meta-prompt, the quality reports (`QUALITY_NOTES.md`), and the
same data in its original one-file-per-prompt form (up to the point where that
repository stopped taking data) live in the GitHub repository
[{repo.split('/')[-1]}]({github}). This Hub repository is where new batches and runs are
added. Paths such as `prompts/batch_009/` or `meta_prompt/prompt.j2` in the copied
sections below refer to that repository's layout; the mapping to this one is given next.

## Layout on the Hub

```
data/prompts/batch_NNN.parquet       one row per prompt of batch NNN (config `prompts`)
data/responses/run_NNN.parquet       one row per response of run NNN (config `responses`)
data/preferences/run_NNN.parquet     one row per judgment of preference run NNN (config `preferences`)
metadata/batches/batch_NNN.yaml      batch-level settings (model, API, sampling parameters)
metadata/runs/run_NNN.yaml           run-level settings (model, sampling, provider preferences, prompt set)
inputs/batch_NNN/                    snapshot of the meta-prompt components used for the batch
sets/NAME.txt                        prompt sets: the prompt IDs a response run answers
preferences/pairs/NAME.yaml          pair sets: which two responses are compared, in which A/B order
preferences/judge_prompt.j2          the judge prompt (and per run, the template as it was when the run started)
preferences/run_NNN/run.yaml         judge model, effort, pair set, prices used for the cost field
LICENSE-DATA                         CC BY 4.0
```

```python
from datasets import load_dataset
prompts = load_dataset("{repo}", "prompts", split="train")
responses = load_dataset("{repo}", "responses", split="train")
preferences = load_dataset("{repo}", "preferences", split="train")
```

Every shard of a config has the same schema, so a config loads as one table. Rows are
one-to-one with the files of the GitHub layout, with these normalizations:

- **prompts**: `prompt_id` is the number in the file name (`prompt_00123.txt` → 123),
  globally unique across batches; `text` is the prompt file's content without its
  trailing newline; the sidecar's fields keep their names (`model`, `effort`,
  `generated_at`, `input_tokens`, `output_tokens`, `web_searches`, `web_fetches`,
  `cost_usd`, `providers`, `generation_ids`, `domains_offered`, `task_types_offered`,
  `reasoning_summary`, `custom_id`); the two mappings `additional_instructions` (the
  instruction group → its text) and `task_type_examples` are stored as JSON strings;
  batches before 029, whose sidecars recorded `length`, `persona`, and `writing_style`
  as separate keys, have those folded into `additional_instructions` like later
  batches; any other sidecar key lands in the JSON string `extra`. Fields a batch does
  not have are null.
- **responses**: one row per response file, with the run in `run`, the prompt number in
  `prompt_id` (from the response file's name) and the prompt's path in the GitHub layout
  in `prompt_file`; all record fields keep their names (see the field table under
  Responses); the prompt as sent is included in `prompt`.
- **preferences**: one row per judgment file, with the run in `run` and the prompt
  number in `prompt_id`; fields keep their names (`response_a` and `response_b` are the
  paths of the two response files in the GitHub layout).

Per-shard row counts: {'; '.join(f'{k} {fmt(v)}' for k, v in counts['prompts'].items())}
(prompts); {'; '.join(f'{k} {fmt(v)}' for k, v in counts['responses'].items())} (responses);
{'; '.join(f'{k} {fmt(v)}' for k, v in counts['preferences'].items())} (preferences).
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="hf_export")
    parser.add_argument("--repo", default="casparoe/synthetic_philosophy_prompts")
    args = parser.parse_args()
    out = Path(args.out)
    if not out.is_absolute():
        out = REPO_ROOT / out
    sections = readme_sections((REPO_ROOT / "README.md").read_text(encoding="utf-8"))
    missing = [s for s in COPIED_SECTIONS if s not in sections]
    if missing:
        raise SystemExit(f"README.md lacks sections: {missing}")
    counts = count_rows(out)
    body = [opening(args.repo, counts)]
    for name in COPIED_SECTIONS:
        body.append(f"## {name}\n\n{sections[name]}\n")
    (out / "README.md").write_text(FRONT_MATTER + "\n" + "\n".join(body), encoding="utf-8")
    shutil.copy2(REPO_ROOT / "LICENSE-DATA", out / "LICENSE-DATA")
    print(f"wrote {out / 'README.md'} ({(out / 'README.md').stat().st_size / 1e3:.0f} kB) and LICENSE-DATA; "
          f"{sum(counts['prompts'].values()):,} prompts, {sum(counts['responses'].values()):,} responses, "
          f"{sum(counts['preferences'].values()):,} judgments")


if __name__ == "__main__":
    main()
