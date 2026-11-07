#!/usr/bin/env python
"""Report on a link run: how the answers use the pages attached to their prompts.

Checks, in addition to tools/check_run.py (which a link run should pass as
well): how much of each answer and of its reasoning is copied word for word
from a page attached to the prompt (the longest run of words shared with the
page, as tools/check_link_batch.py measures it for prompts), with the page's
site and license; and four signs of a broken answer that check_run.py misses,
each listed worst first for a manual look: the later part of an answer
repeating the earlier part (an answer written out twice, or in several
drafts), page text stitched into the answer (the share of its 8-grams found in
the pages), one sentence opening repeated many times, and an answer much
longer than the other sample of the same prompt. In the first trial link run
(Qwen3.5 397B, 1,000 answers), these found four broken answers: a page pasted
out verbatim; an answer far longer than its other sample, with 391 sentences
that open "We agree that" and go on with fragments of the page; and two answers
whose later part repeated 99% and 90% of the earlier part's 12-grams. Good
answers reach 20-40% there, with a refrain, the bands of a rubric, or a quoted
original.

    tools/check_link_answers.py responses/run_NNN [--show 5]
"""
import argparse
import collections
import pathlib
import re
import sys

import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "generators"))
sys.path.insert(0, str(REPO / "tools"))
import attached_pages  # noqa: E402
from check_link_batch import COPY_FLAG_WORDS, LOADER, WORD, dist, longest_shared_run  # noqa: E402

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
REPEAT_GRAM = 12  # words per shingle when comparing the later part of an answer with the earlier part
CUTS = (0.33, 0.5, 0.67)  # where an answer is split into an earlier and a later part


def copy_report(records, store, show):
    """The longest run of words that each answer, and its reasoning, share with
    a page attached to the prompt."""
    pages, words = {}, {}

    def page_info(rec):
        # [(sha256, site, license)] of the attached pages, from the prompt's sidecar
        if rec["id"] not in pages:
            meta = yaml.load((REPO / rec["prompt_file"]).with_suffix(".meta.yaml").read_text(), Loader=LOADER)
            pages[rec["id"]] = [(p["sha256"], p.get("site"), p.get("license")) for p in meta["attached_pages"]]
        return pages[rec["id"]]

    def page_words(sha):
        if sha not in words:
            words[sha] = WORD.findall(store.get(sha).lower())
        return words[sha]

    rows = []
    for name, rec in records:
        for part in ("answer", "reasoning"):
            text_words = WORD.findall((rec.get(part) or "").lower())
            best = (0, None, None)
            for sha, site, lic in page_info(rec):
                n = longest_shared_run(text_words, page_words(sha))
                if n > best[0]:
                    best = (n, site, lic)
            rows.append((name, part, *best))
    for part in ("answer", "reasoning"):
        runs = [r[2] for r in rows if r[1] == part]
        print(f"{part}: {len(runs)} records; longest copied run {dist(runs)}; "
              f">={COPY_FLAG_WORDS} words: {sum(n >= COPY_FLAG_WORDS for n in runs)}, "
              f">=100: {sum(n >= 100 for n in runs)}, >=300: {sum(n >= 300 for n in runs)}")
        by_site = collections.Counter((r[3], r[4]) for r in rows if r[1] == part and r[2] >= COPY_FLAG_WORDS)
        for (site, lic), c in by_site.most_common(8):
            print(f"   {c:4d}  {site}  [{lic}]")
        for r in sorted((r for r in rows if r[1] == part), key=lambda r: -r[2])[:show]:
            print(f"   {r[2]:5d} words  {r[0]}  {r[3]}  [{r[4]}]")


def broken_report(records, store, show):
    """Signs of a broken answer that tools/check_run.py misses, worst first."""
    grams = {}
    rows, length = [], collections.defaultdict(dict)
    for name, rec in records:
        name = name[len("prompt_"):-len(".yaml")]
        answer = rec.get("answer") or ""
        w = WORD.findall(answer.lower())
        page_grams = set()
        for p in rec["attached_pages"]:
            if p["sha256"] not in grams:
                pw = WORD.findall(store.get(p["sha256"]).lower())
                grams[p["sha256"]] = {tuple(pw[i:i + 8]) for i in range(len(pw) - 7)}
            page_grams |= grams[p["sha256"]]
        g = [tuple(w[i:i + 8]) for i in range(len(w) - 7)]
        from_pages = 100 * sum(x in page_grams for x in g) / len(g) if g else 0
        openers = collections.Counter(
            " ".join(s.lower().split()[:3]) for s in SENTENCE_END.split(answer) if len(s.split()) >= 3)
        opener, opener_n = openers.most_common(1)[0] if openers else ("", 0)
        # the share of the later part's 12-grams that occur in the earlier part, at the cut that gives most
        ws = re.findall(r"\S+", answer.lower())
        repeat = 0
        for cut in CUTS:
            k = int(len(ws) * cut)
            early = {tuple(ws[i:i + REPEAT_GRAM]) for i in range(max(0, k - REPEAT_GRAM + 1))}
            later = [tuple(ws[i:i + REPEAT_GRAM]) for i in range(k, len(ws) - REPEAT_GRAM + 1)]
            if later:
                repeat = max(repeat, 100 * sum(x in early for x in later) / len(later))
        rows.append((name, len(w), from_pages, opener, opener_n, repeat))
        pid, sample = name.split(".")
        length[pid][sample] = len(w)
    print("  later part repeating the earlier part (share of 12-grams):")
    for x in sorted(rows, key=lambda x: -x[5])[:show]:
        print(f"    {x[0]}  {x[5]:5.1f}%  {x[1]:,} words")
    print("  highest share of answer 8-grams found in the pages:")
    for x in sorted(rows, key=lambda x: -x[2])[:show]:
        print(f"    {x[0]}  {x[2]:5.1f}%  {x[1]:,} words")
    print("  most repeated sentence opener:")
    for x in sorted(rows, key=lambda x: -x[4])[:show]:
        print(f"    {x[0]}  x{x[4]} '{x[3]}'  ({x[1]:,} words)")
    ratios = sorted(((max(v.values()) / max(1, min(v.values())), pid, v)
                     for pid, v in length.items() if len(v) == 2), reverse=True)
    print("  largest length ratio between a prompt's two samples:")
    for x in ratios[:show]:
        print(f"    {x[1]}  {x[0]:.1f}x  {x[2]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run", type=pathlib.Path)
    parser.add_argument("--show", type=int, default=5, help="worst cases to list per finding (default: 5)")
    args = parser.parse_args()
    cfg = yaml.load((args.run / "run.yaml").read_text(), Loader=LOADER)
    if not cfg.get("snapshots"):
        raise SystemExit(f"{args.run} is not a link run (run.yaml names no snapshot store)")
    store = attached_pages.SnapshotStore(REPO / cfg["snapshots"])
    records = [(p.name, yaml.load(p.read_text(), Loader=LOADER)) for p in sorted(args.run.glob("prompt_*.yaml"))]
    print(f"# {args.run}: {len(records)} answers; page format {cfg.get('page_format')}; store {cfg['snapshots']}")
    print("## copied from the pages (longest run of words shared with an attached page)")
    copy_report(records, store, args.show)
    print("## signs of a broken answer")
    broken_report(records, store, args.show)


if __name__ == "__main__":
    main()
