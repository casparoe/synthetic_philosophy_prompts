#!/usr/bin/env python
"""Report on a link batch: the pages its prompts come with, and how the prompts use them.

Checks, in addition to tools/check_batch.py (which a link batch should pass as
well): pages per prompt and their total length; sources (how the cache fetched
the text), sites, and licenses; that the snapshot store holds every page's text
and that it matches its hash; that every prompt gives its pages' URLs and no
other (generators/attached_pages.url_problem, which generation enforces); how
much of a page the prompt copies (the longest run of words shared with the
page, and the share of the prompt's 8-grams found in it), since the answering
model has the page; and prompts that seem to ask for a whole page to be
reworked (translated, rewritten, summarized throughout) although the page is
not openly licensed, for a manual look.

    tools/check_link_batch.py prompts/batch_NNN [--show 5]
"""
import argparse
import collections
import pathlib
import re
import statistics as st
import sys

import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "generators"))
import attached_pages  # noqa: E402

LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
WORD = re.compile(r"[a-z0-9']+")
# Asking for a whole text to be reworked: a sentence with one of the verbs and
# a word that makes the request cover all of it.
SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
REWORK = re.compile(
    r"\b(?:translat|rewrit|re-writ|paraphras|summari[sz]|condens|abridg|retell|redraft|proofread|copy-?edit)\w*",
    re.I,
)
WHOLE = re.compile(
    r"\b(?:whole|entire|full|in full|complete|section by section|paragraph by paragraph"
    r"|every (?:section|paragraph)|all of (?:it|the (?:post|essay|article|piece|page|text)))\b",
    re.I,
)
COPY_FLAG_WORDS = 40  # a run of this many words copied from a page is worth a look


def dist(values):
    if not values:
        return "n/a"
    values = sorted(values)
    q = lambda p: values[min(len(values) - 1, int(p * len(values)))]  # noqa: E731
    return f"median {st.median(values):,.0f}, p90 {q(0.9):,.0f}, max {values[-1]:,.0f}, mean {st.mean(values):,.0f}"


def longest_shared_run(words, page_words):
    """The longest run of consecutive words of `words` that also occurs in
    page_words, by extending matches of 8-word shingles."""
    if len(words) < 8:
        return 0
    grams = {}
    for i in range(len(page_words) - 7):
        grams.setdefault(tuple(page_words[i:i + 8]), []).append(i)
    best, i = 0, 0
    while i <= len(words) - 8:
        starts = grams.get(tuple(words[i:i + 8]))
        if not starts:
            i += 1
            continue
        run = 8
        for s in starts:
            k = 8
            while i + k < len(words) and s + k < len(page_words) and words[i + k] == page_words[s + k]:
                k += 1
            run = max(run, k)
        best = max(best, run)
        i += max(1, run - 7)
    return best


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("batch", type=pathlib.Path)
    parser.add_argument("--show", type=int, default=5, help="examples to list per finding (default: 5)")
    args = parser.parse_args()
    b = args.batch
    cfg = yaml.load((b / "batch.yaml").read_text(), Loader=LOADER)
    if not cfg.get("link_prompts"):
        raise SystemExit(f"{b} is not a link batch (batch.yaml has no link_prompts)")
    store = attached_pages.SnapshotStore(REPO / cfg["snapshots"])
    metas = {}
    for path in sorted(b.glob("prompt_*.meta.yaml")):
        metas[path.name.split(".")[0]] = yaml.load(path.read_text(), Loader=LOADER)
    texts = {pid: (b / f"{pid}.txt").read_text() for pid in metas if (b / f"{pid}.txt").exists()}
    print(f"# {b}: {len(texts)} link prompts; page format {cfg.get('page_format')}; "
          f"store {cfg['snapshots']}; {cfg.get('attachable_pages')} pages could be attached")

    def show(label, items):
        print(f"{label}: {len(items)}" + (f"  e.g. {', '.join(items[:args.show])}" if items else ""))

    # -- the pages
    records = {pid: m.get("attached_pages") or [] for pid, m in metas.items()}
    show("prompts without attached_pages", [pid for pid, rs in records.items() if not rs])
    counts = collections.Counter(len(rs) for rs in records.values())
    print("pages per prompt: " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    print(f"characters of page text per prompt: {dist([sum(r['chars'] for r in rs) for rs in records.values()])}")
    pages = [r for rs in records.values() for r in rs]
    distinct = {r["sha256"] for r in pages}
    print(f"pages attached: {len(pages)} ({len(distinct)} distinct texts)")
    for label, key in (("fetched as", "fetch_method"), ("sites", "site")):
        c = collections.Counter(r.get(key) or "?" for r in pages)
        print(f"{label}: " + ", ".join(f"{k} {v} ({v / len(pages):.0%})" for k, v in c.most_common(10)))
    licenses = collections.Counter(r.get("license") or "none stated" for r in pages)
    print("licenses: " + ", ".join(f"{k} {v}" for k, v in licenses.most_common(8)))
    print(f"openly licensed (whole-page reworkings allowed): "
          f"{sum(attached_pages.open_license(r.get('license')) for r in pages)} of {len(pages)}")

    # -- the choice (batches after 073: the model picks pages from those listed)
    choosing = {pid: m for pid, m in metas.items() if "pages_offered" in m}
    if choosing:
        offered = [r for m in choosing.values() for rs in m["pages_offered"] for r in rs]
        read = [len(m.get("pages_read") or []) for m in choosing.values()]
        print(f"pages listed per prompt: {dist([sum(map(len, m['pages_offered'])) for m in choosing.values()])}; "
              f"read per prompt: {dist(read)}; prompts reading none: {sum(1 for n in read if not n)}")
        spread = collections.Counter(
            len({i for i, rs in enumerate(m["pages_offered"]) for r in rs if r["sha256"] in {a["sha256"] for a in m["attached_pages"]}})
            for m in choosing.values()
        )
        print("domains the attached pages come from: " + ", ".join(f"{k}: {v}" for k, v in sorted(spread.items())))
        kind = lambda r: r.get("fetch_method") or "?"  # noqa: E731
        listed_share = collections.Counter(kind(r) for r in offered)
        chosen_share = collections.Counter(kind(r) for r in pages)
        print("attached vs listed, by source: " + ", ".join(
            f"{k} {chosen_share[k] / len(pages):.0%} vs {v / len(offered):.0%}" for k, v in listed_share.most_common(7)))

    # -- the store
    missing = store.missing(distinct)
    show("page texts missing from the store", missing)
    damaged = []
    page_text = {}
    for sha in distinct - set(missing):
        try:
            page_text[sha] = store.get(sha)
        except ValueError:
            damaged.append(sha)
    show("page texts that do not match their hash", damaged)

    # -- the prompts
    show("URL problems", [f"{pid} ({p})" for pid in texts
                          if (p := attached_pages.url_problem(texts[pid].strip(), records[pid]))])
    runs, shares, copied = {}, [], []
    for pid, text in texts.items():
        words = WORD.findall(text.lower())
        page_words = [WORD.findall(page_text.get(r["sha256"], "").lower()) for r in records[pid]]
        runs[pid] = max((longest_shared_run(words, pw) for pw in page_words), default=0)
        grams = [tuple(words[i:i + 8]) for i in range(len(words) - 7)]
        page_grams = {tuple(pw[i:i + 8]) for pw in page_words for i in range(len(pw) - 7)}
        shares.append(100 * sum(g in page_grams for g in grams) / len(grams) if grams else 0)
        if runs[pid] >= COPY_FLAG_WORDS:
            copied.append(f"{pid} ({runs[pid]} words)")
    print(f"longest run of words copied from a page: {dist(list(runs.values()))}")
    print(f"share of the prompt's 8-grams found in its pages (%): {dist(shares)}")
    show(f"prompts copying {COPY_FLAG_WORDS}+ consecutive words from a page", sorted(copied, key=lambda s: -int(s.split("(")[1].split()[0])))
    rework = [
        pid for pid, text in texts.items()
        if any(REWORK.search(s) and WHOLE.search(s) for s in SENTENCE.split(text))
        and not all(attached_pages.open_license(r.get("license")) for r in records[pid])
    ]
    show("asking for a rework of a whole page that is not openly licensed? (look at these)", rework)

    # -- the generator's own tool use, which the pages should make rare
    searches = [m.get("web_searches", 0) for m in metas.values()]
    fetches = [m.get("web_fetches", 0) for m in metas.values()]
    print(f"web searches: {sum(searches)} in {sum(1 for s in searches if s)} prompts; "
          f"fetches: {sum(fetches)} in {sum(1 for f in fetches if f)} prompts")


if __name__ == "__main__":
    main()
