#!/usr/bin/env python
"""Quality report for a prompt batch.

Checks: counts and skips, cost / token / provider mix (where recorded), ID
collisions across all batches, leak scans (tool-call markup, chat preambles,
dataset-construction framing, prompts wrapped in quotes), example echo (prompts
reusing wording from the task-type examples they were shown), verbatim copying
of the additional-instruction text, near-duplicate prompt pairs, the most
repeated eight-word phrases, and whether every sidecar re-renders from the
batch's snapshot. Findings are tracked in QUALITY_NOTES.md.

    tools/check_batch.py prompts/batch_033 [--no-pairs] [--top 10]
"""
import argparse
import collections
import datetime
import glob
import itertools
import pathlib
import re
import statistics as st
import sys

import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "meta_prompt"))

WORD = re.compile(r"[a-z0-9']+")
MARKUP = re.compile(r"<｜DSML｜|<\|DSML\||</?tool_call|arg_value|arg_key|</invoke>|<function_calls?>|<\|im_start\||</?think>")
PREAMBLE = re.compile(r"^(here is (the|your|my|a) prompt|here's (the|your|my|a) prompt|this looks good|this is my final"
                      r"|i'll rely on|i will rely on|(sure|okay|ok)[,!] here('s| is) (the|your|a) prompt|certainly[,!] here)", re.I)
META = re.compile(r"dataset of (philosoph[a-z]* )?prompts|prompt for (the|this|your) dataset"
                  r"|prompts? (on|about) philosophical (topics|issues)|building a dataset of|constructing a dataset", re.I)
MIN_WORDS = 40


def grams(text, n=8):
    w = WORD.findall(text.lower())
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def load_examples(batch):
    """8-gram -> (task type, example index) for the examples this batch was shown."""
    path = batch / "inputs" / "task_types.yaml"
    note = "snapshot"
    if not path.exists():
        path, note = REPO / "meta_prompt" / "task_types.yaml", "CURRENT components (no snapshot in this batch)"
    index = {}
    for t in yaml.safe_load(path.read_text()):
        for i, e in enumerate(t.get("examples") or []):
            for g in grams(e):
                index.setdefault(g, (t["type"], i))
    return index, note


def pct(k, n):
    return f"{k} ({100 * k / n:.1f}%)" if n else "0"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("batch", type=pathlib.Path)
    ap.add_argument("--no-pairs", action="store_true", help="skip the near-duplicate pair search (the slow part)")
    ap.add_argument("--top", type=int, default=8, help="how many repeated phrases / copied examples to list")
    args = ap.parse_args()
    b = args.batch
    texts = {p.name: p.read_text() for p in sorted(b.glob("prompt_*.txt"))}
    metas = {}
    for p in sorted(b.glob("prompt_*.meta.yaml")):
        metas[p.name.replace(".meta.yaml", ".txt")] = yaml.safe_load(p.read_text())
    n = len(texts)
    cfg = yaml.safe_load((b / "batch.yaml").read_text()) if (b / "batch.yaml").exists() else {}
    print(f"# {b}  ({n} prompts, {len(metas)} sidecars)  model={cfg.get('model', '?')}  api={cfg.get('api', '?')}")
    if not n:
        return

    # -- cost, tokens, providers, tools ------------------------------------------------------
    ms = list(metas.values())
    if any("cost_usd" in m for m in ms):
        cost = [m["cost_usd"] for m in ms if "cost_usd" in m]
        print(f"cost: total ${sum(cost):.2f}, mean ${st.mean(cost):.4f}, median ${st.median(cost):.4f}")
    if any("input_tokens" in m for m in ms):
        print(f"tokens: in mean {st.mean(m['input_tokens'] for m in ms if 'input_tokens' in m):.0f}, "
              f"out mean {st.mean(m['output_tokens'] for m in ms if 'output_tokens' in m):.0f}")
    prov = collections.Counter(p for m in ms for p in m.get("providers", []))
    if prov:
        print("providers:", ", ".join(f"{p} {c}" for p, c in prov.most_common()))
    if any("web_searches" in m for m in ms):
        print(f"web: {sum(m.get('web_searches', 0) for m in ms)} searches, {sum(m.get('web_fetches', 0) for m in ms)} fetches")
    if ms and "generated_at" in ms[0]:
        stamps = sorted(str(m["generated_at"]) for m in ms if m.get("generated_at"))
        print(f"generated: {stamps[0][:16]} .. {stamps[-1][:16]}")

    # -- IDs -----------------------------------------------------------------------------------
    ids = collections.Counter(int(re.search(r"prompt_(\d+)\.txt$", p).group(1))
                              for p in glob.glob(str(REPO / "prompts" / "batch_*" / "prompt_*.txt")))
    dups = sorted(i for i, c in ids.items() if c > 1)
    mine = sorted(int(re.search(r"(\d+)", name).group(1)) for name in texts)
    print(f"ids: {mine[0]}..{mine[-1]}, {mine[-1] - mine[0] + 1 - len(mine)} gaps; "
          f"collisions across all batches: {dups[:5] or 'none'}")

    # -- text scans ----------------------------------------------------------------------------
    words = [len(t.split()) for t in texts.values()]
    print(f"words: median {st.median(words):.0f}, min {min(words)}, max {max(words)}; under {MIN_WORDS}: "
          f"{sum(w < MIN_WORDS for w in words)}")
    flag = lambda rx, where=lambda t: t: [name for name, t in texts.items() if rx.search(where(t))]
    print("tool-call markup:", flag(MARKUP)[:5] or "none")
    print("chat preamble at start:", flag(PREAMBLE, lambda t: t.strip())[:5] or "none")
    print("dataset-construction framing leaked:", flag(META)[:8] or "none")
    quoted = [name for name, t in texts.items() if t.strip().startswith(('"', "“")) and t.strip().endswith(('"', "”"))]
    print("wrapped in quotes / pure dialogue:", quoted[:5] or "none")

    # -- example echo --------------------------------------------------------------------------
    ex, note = load_examples(b)
    exset = set(ex)
    shared = {name: grams(t) & exset for name, t in texts.items()}
    counts = {name: len(s) for name, s in shared.items()}
    buckets = collections.Counter("0" if c == 0 else "1" if c == 1 else "2-4" if c < 5 else "5-19" if c < 20 else "20+"
                                  for c in counts.values())
    print(f"example echo (8-grams shared with task-type examples, {note}): " +
          ", ".join(f"{k}: {pct(buckets[k], n)}" for k in ["0", "1", "2-4", "5-19", "20+"]))
    heavy = sum(1 for c in counts.values() if c >= 5)
    print(f"  heavy echo (>=5 shared 8-grams): {pct(heavy, n)}")
    src = collections.Counter()
    for name, s in shared.items():
        if len(s) >= 5:
            src[collections.Counter(ex[g] for g in s).most_common(1)[0][0]] += 1
    for (ttype, i), c in src.most_common(args.top):
        print(f"  {c:4d}  example {i} of: {ttype[:70]}")

    # -- instruction copying -------------------------------------------------------------------
    copied = collections.defaultdict(lambda: [0, 0])
    for name, m in metas.items():
        instr = m.get("additional_instructions")
        if not isinstance(instr, dict):
            instr = {k: m[k] for k in ("length", "persona", "writing_style") if isinstance(m.get(k), str)}
        if not instr or name not in texts:
            continue
        pg = grams(texts[name])
        for group, text in instr.items():
            copied[group][1] += 1
            if grams(text) & pg:
                copied[group][0] += 1
    if copied:
        print("instruction text copied verbatim (>=8 consecutive words) into the prompt: " +
              ", ".join(f"{g} {pct(k, t)}" for g, (k, t) in sorted(copied.items())))

    # -- stock phrases -------------------------------------------------------------------------
    allgrams = {name: grams(t) for name, t in texts.items()}
    freq = collections.Counter(g for s in allgrams.values() for g in s)
    print("most repeated 8-grams (number of prompts):")
    for g, c in freq.most_common(args.top):
        print(f"  {c:4d}  {g}")

    # -- near-duplicate pairs ------------------------------------------------------------------
    if not args.no_pairs and n > 1:
        index = collections.defaultdict(list)
        for name, s in allgrams.items():
            for g in s:
                index[g].append(name)
        pair = collections.Counter()
        for g, names in index.items():
            if 2 <= len(names) <= 30:
                for a, c in itertools.combinations(names, 2):
                    pair[(a, c)] += 1
        for th in (20, 50, 100):
            ps = [p for p, c in pair.items() if c >= th]
            print(f"pairs sharing >= {th} 8-grams: {len(ps)} (prompts involved: {len({x for p in ps for x in p})})")
        for (a, c), k in sorted(pair.items(), key=lambda x: -x[1])[:3]:
            wa = WORD.findall(texts[a].lower())
            pos = [i for i in range(len(wa) - 7) if " ".join(wa[i:i + 8]) in allgrams[c]]
            snippet = " ".join(wa[pos[0]:pos[0] + 14]) if pos else ""
            print(f"  {a} ~ {c}: {k} shared, starting '{snippet} ...'")

    # -- sidecars re-render ---------------------------------------------------------------------
    try:
        import assemble
        comp = assemble.load(b / "inputs")
        bad = 0
        for m in metas.values():
            try:
                comp.render({k: m[k] for k in assemble.SAMPLE_KEYS}, web_tools=True, strict_quotes=True)
            except Exception:
                bad += 1
        print(f"sidecars that fail to re-render from the snapshot: {bad}")
    except Exception as e:  # pre-029 snapshots lack additional_instructions.yaml
        print(f"sidecar re-render skipped ({e.__class__.__name__})")


if __name__ == "__main__":
    main()
