#!/usr/bin/env python
"""Quality report for a response run.

Coverage against the run's prompt set, finish reasons, missing chains of
thought or answers, <think> tags and tool-call markup left in answers,
refusal phrases, repeated phrases, reasoning and answer lengths, cost, and
the provider mix. Findings are tracked in QUALITY_NOTES.md.

    tools/check_run.py responses/run_000 [--top 5]
"""
import argparse
import collections
import json
import pathlib
import re
import statistics as st
import sys

import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "generators"))
from generate_responses import RECORD_FILE_RE, read_prompt_set  # noqa: E402

LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
WORD = re.compile(r"[a-z0-9']+")
MARKUP = re.compile(r"<｜DSML｜|<\|DSML\||</?tool_call|</invoke>|<function_calls?>|<\|im_start\||<\|channel\|>|<\|end\|>")
THINK_TAG = re.compile(r"</?think>")
REFUSAL = re.compile(
    r"\b(I can(?:'|no)t (?:help|assist|comply|provide|write)|I(?:'m| am) (?:unable|not able) to (?:help|assist|comply|provide)"
    r"|I won(?:'|no)t be able to|as an AI(?: language model)?)\b", re.I)
SHORT_WORDS = 40


def words(text):
    return len(WORD.findall((text or "").lower()))


def pct(k, n):
    return f"{k} ({100 * k / n:.1f}%)" if n else "0"


def dist(values):
    if not values:
        return "n/a"
    values = sorted(values)
    p90 = values[min(len(values) - 1, int(0.9 * len(values)))]
    return f"mean {st.mean(values):,.0f}, median {values[len(values) // 2]:,}, p90 {p90:,}, max {values[-1]:,}"


def load(run_dir):
    records = []
    for path in sorted(run_dir.glob("prompt_*.yaml")):
        if RECORD_FILE_RE.fullmatch(path.name):
            with open(path, encoding="utf-8") as f:
                records.append(yaml.load(f, Loader=LOADER))
    return records


def repeats(text, n=12, times=3):
    w = WORD.findall(text.lower())
    counts = collections.Counter(" ".join(w[i:i + n]) for i in range(len(w) - n + 1))
    return bool(counts) and counts.most_common(1)[0][1] >= times


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run", type=pathlib.Path)
    ap.add_argument("--top", type=int, default=5, help="how many example IDs to list per finding")
    args = ap.parse_args()

    cfg = yaml.safe_load((args.run / "run.yaml").read_text())
    records = load(args.run)
    print(f"== {cfg.get('run')}: {cfg['model']} ({cfg.get('hugging_face_id') or 'no HF id recorded'}) via {cfg['api']}")
    print(f"prompt set {cfg['prompt_set']} ({cfg['num_prompts']} prompts x {cfg['samples_per_prompt']}), "
          f"system prompt: {'yes' if cfg.get('system_prompt') else 'none'}")
    print(f"reasoning {json.dumps(cfg.get('reasoning'))}; max_tokens {cfg.get('max_tokens')}; "
          f"sampling {json.dumps(cfg.get('sampling'))}; provider {json.dumps(cfg.get('provider'))}")
    print(f"created {cfg.get('created_at')}" + (f", resumed {len(cfg['resumed_at'])}x" if cfg.get("resumed_at") else ""))

    n = len(records)
    keys = {(r["id"], r.get("sample_index", 0)) for r in records}
    set_path = REPO / cfg["prompt_set"] if not pathlib.Path(cfg["prompt_set"]).is_absolute() else pathlib.Path(cfg["prompt_set"])
    expected = {(pid, k) for pid in read_prompt_set(set_path) for k in range(cfg["samples_per_prompt"])}
    missing = sorted(expected - keys)
    stray = sorted(keys - expected)
    print(f"\n-- records: {n}; coverage: {len(expected) - len(missing)}/{len(expected)}; missing {len(missing)} "
          f"{[m[0] for m in missing[:args.top]]}" + (f"; {len(stray)} records outside the set" if stray else ""))
    if not n:
        return

    finish = collections.Counter(r.get("finish_reason") for r in records)
    print("\n-- finish reasons: " + ", ".join(f"{k} {pct(v, n)}" for k, v in finish.most_common()))
    kinds = collections.Counter(",".join(r.get("reasoning_detail_types") or []) or "(none)" for r in records)
    print("reasoning detail types: " + ", ".join(f"{k} {pct(v, n)}" for k, v in kinds.most_common()))

    def flag(label, hits):
        print(f"{label}: {pct(len(hits), n)} {[r['id'] for r in hits[:args.top]]}")

    print("\n-- content checks")
    flag("no reasoning", [r for r in records if not r.get("reasoning")])
    flag("empty answer", [r for r in records if not r.get("answer")])
    flag("truncated (finish_reason=length)", [r for r in records if r.get("finish_reason") == "length"])
    flag("finish reason missing or other", [r for r in records if r.get("finish_reason") not in ("stop", "length")])
    flag("<think> tag left in answer", [r for r in records if THINK_TAG.search(r.get("answer") or "")])
    flag("tool/chat markup in answer", [r for r in records if MARKUP.search(r.get("answer") or "")])
    flag("refusal phrase in answer", [r for r in records if REFUSAL.search(r.get("answer") or "")])
    flag(f"answer under {SHORT_WORDS} words", [r for r in records if r.get("answer") and words(r["answer"]) < SHORT_WORDS])
    flag("answer repeats a 12-word phrase 3+ times", [r for r in records if repeats(r.get("answer") or "")])

    print("\n-- lengths")
    comp = [r["completion_tokens"] for r in records if r.get("completion_tokens") is not None]
    reas = [r["reasoning_tokens"] for r in records if r.get("reasoning_tokens") is not None]
    print(f"completion tokens: {dist(comp)}")
    if reas and comp:
        print(f"reasoning tokens: {dist(reas)}; share of completion {100 * sum(reas) / max(sum(comp), 1):.0f}%")
    print(f"reasoning words: {dist([words(r.get('reasoning')) for r in records])}")
    print(f"answer words: {dist([words(r.get('answer')) for r in records])}")
    print(f"prompt tokens: {dist([r['prompt_tokens'] for r in records if r.get('prompt_tokens') is not None])}")

    costs = [r["cost_usd"] for r in records if r.get("cost_usd") is not None]
    if costs:
        print(f"\n-- cost: total ${sum(costs):.2f}; mean ${st.mean(costs):.4f} per response; "
              f"${1000 * st.mean(costs):.2f} per 1000")
    by_provider = collections.defaultdict(list)
    for r in records:
        by_provider[r.get("provider") or "?"].append(r)
    print("-- providers")
    for name, rs in sorted(by_provider.items(), key=lambda kv: -len(kv[1])):
        c = [r["cost_usd"] for r in rs if r.get("cost_usd") is not None]
        t = [r["completion_tokens"] for r in rs if r.get("completion_tokens") is not None]
        trunc = sum(r.get("finish_reason") == "length" for r in rs)
        print(f"   {name:<16} {pct(len(rs), n):>14}  mean {st.mean(t) if t else 0:,.0f} tok  "
              f"mean ${st.mean(c) if c else 0:.4f}  truncated {trunc}")


if __name__ == "__main__":
    main()
