#!/usr/bin/env python
"""Quality report for a prompt batch.

Checks: counts and skips, cost / token / provider mix (where recorded), ID
collisions across all batches, leak scans (tool-call markup, chat preambles, leaked deliberation,
process notes before the prompt, dataset-construction framing, prompts wrapped
in quotes), stray East Asian words and word salad, example echo (prompts
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
import unicodedata

import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "meta_prompt"))
import assemble  # noqa: E402

WORD = re.compile(r"[a-z0-9']+")
MARKUP = re.compile(r"<｜|<\|DSML\||</?tool_call|arg_value|arg_key|</invoke>|<function_calls?>|<\|im_start\||</?think[>:\s]")
PREAMBLE = re.compile(r"^(here is (the|your|my|a) prompt|here's (the|your|my|a) prompt|this looks good|this is my final"
                      r"|i'll rely on|i will rely on|(sure|okay|ok)[,!] here('s| is) (the|your|a) prompt|certainly[,!] here)", re.I)
META = re.compile(r"dataset of (philosoph[a-z]* )?prompts|prompt for (the|this|your) dataset"
                  r"|prompts? (on|about) philosophical (topics|issues)|building a dataset of|constructing a dataset"
                  # the asker saying what the prompt is for, or relaying the meta-prompt's
                  # instructions about the prompt ("Write the prompt in a formal register",
                  # "The asker should not signal ..."), seen at scale in batches 044 and 046
                  r"|\b(?:this is |is )?for (?:a|my|the|this|your) dataset\b|\bthe asker should\b"
                  r"|\bwrite the prompt (?:in|as|from)\b|\bthe prompt should be (?:formal|casual|written|polished|in the)\b", re.I)

# Generator vocabulary that has no place in a user's prompt: the model talking about
# producing "the prompt" / its "final answer", the meta-prompt's own wording quoted back,
# or a thinking block that leaked. Seen with DeepSeek V4 Pro (batches 051, 052), V4.1
# Flash (041) and Tencent HY4 (054, "</think:opensource>"), often with the real prompt
# glued directly onto the last word of the deliberation ("Let me outputSome people ...").
LEAK_VOCAB_RE = re.compile(
    r"\A\s*```|\bassistant reasoning\b|</?think\b|\bprompt text only\b|\b(?:here is|here'?s) the final prompt\b|\bComposing the final prompt\b"
    r"|\b(?:output|produce|write) (?:the |just the |only the )?final prompt\b|\bJust output (?:the )?prompt\b"
    r"|\bI'?ll (?:just |now )?output\b|\bLet me output\b|(?-i:Output now)(?=[A-Z.:])|(?-i:Now output)(?=[A-Z.:])|(?-i:Now final)(?:\.|\s+(?:answer|output|prompt|must))|\bFinal prompt text:"
    r"|\bLet'?s (?:finalize|finalise|produce final)\b|\bLet me (?:produce|craft|write) (?:the )?final (?:prompt|version|answer|text|clean)\b|\bThis is final\b|\bOk,? final\b|\bI'?ll finali[sz]e\b"
    r"|\breasoning tokens,? (?:please )?reply\b|\bThe user wants a prompt\b|\bthe meta-prompt\b|\bhidden conversation\b"
    r"|\bfinal answer (?:with|only|:)\s*(?:the |just the |only the )?prompt\b"
    r"|\bno preamble like\b|\bthe type is\b.{0,40}\bthe domain is\b|\bDomain\s*=.{0,80}\bType\s*="
    # a preamble sentence or a process note ending in "here is the prompt:" on its own line
    r"|\A.{0,600}?\bhere(?: is|'s) the (?:final )?prompt(?: text)?:[ \t]*\n"
    r"|\bOutput the prompt only\b|\bPolish wording\b|\bLength is reasonable\b"
    r"|\bthe (?:text|page|source) I fetched\b|\ba domain and a (?:prompt )?type\b|\bwhether you want only the prompt text\b"
    r"|\bSorry, I can'?t\b.{0,40}\bprompt\b|\bthe final should be (?:just )?the prompt\b|\bLet me ensure no\b|\bprovide (?:the )?final answer now\b"
    r"|\bNo quotation marks used\b|\bType: [^\n]{0,80}\bDomain: |\bDomain: [^\n]{0,80}\bType: "
    # the end of a planning section glued to the prompt's first word ("Final composition.I teach ...", batch 060)
    r"|(?-i:Final composition)\.(?=[A-Z])",
    re.I | re.S,
)
GLUE_RE = re.compile(r"\b(?:final|output|text|prompt|it|only|now|this|version|answer)(?=[A-Z][a-z]{2,})")
MIN_WORDS = 40

# A Chinese word standing in for an English one, glued to the English around it ("a norm of
# belief更新", "agency:她 weighs"): Tencent HY4 did this in 0.4-1.6% of its prompts (batches
# 043, 045, 054, 059), GLM-5.3 and Qwen3.8 2.4T in under 0.1%, DeepSeek V4 Pro and MiMo a
# few times. Quoted terms are set off by a space or a parenthesis ("the Chinese term 道 (dao)",
# "白馬非馬") and do not match.
EAST_ASIAN = "\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af"  # kana, CJK ideographs, Hangul
EAST_ASIAN_RE = re.compile(f"[{EAST_ASIAN}]")
STRAY_EAST_ASIAN_RE = re.compile(f"[A-Za-z][,:;]?[{EAST_ASIAN}]|[{EAST_ASIAN}][A-Za-z]")
# HY4 also set stray words off by a space, a dash or a full stop ("my hunch is the 니 answer",
# "two jobs —機械 ability"); in a prompt that is not about East Asian languages or thought,
# any East Asian characters outside brackets are suspect.
EAST_ASIAN_TOPIC_RE = re.compile(
    r"chinese|japanese|korean|mandarin|cantonese|kanji|\bkana\b|hiragana|katakana|hangul|hanja|pinyin"
    r"|confuci|mencius|mengzi|xunzi|zhuangzi|laozi|lao tzu|daois|taois|mozi|mohis|han fei|legalis"
    r"|gongsun|hui shi|school of names|white horse|wang yangming|zhu xi|analects|dao ?de ?jing"
    r"|tao te ching|yijing|i ching|buddhis|sutra|\bzen\b|sanskrit|china|japan|korea|chengyu"
    r"|nishida|d[oō]gen|watsuji|kyoto school|(?:tang|song|ming|qing) dynasty", re.I)
BRACKETED_EAST_ASIAN_RE = re.compile(f"[(（\\[][^()（）\\[\\]\\n]{{0,40}}[{EAST_ASIAN}][^()（）\\[\\]\\n]{{0,40}}[)）\\]]")
# Word salad: HY4 sometimes ends a prompt with a long run of random words, either from several
# writing systems at once (Latin, Cyrillic, Chinese, Arabic, Hangul; batch 059) or random
# English words without punctuation. Greek and math letters are not counted as scripts.
SCRIPTS = {"CYRILLIC", "ARMENIAN", "HEBREW", "ARABIC", "SYRIAC", "THAANA", "DEVANAGARI", "BENGALI",
           "GURMUKHI", "GUJARATI", "ORIYA", "TAMIL", "TELUGU", "KANNADA", "MALAYALAM", "SINHALA",
           "THAI", "LAO", "TIBETAN", "MYANMAR", "GEORGIAN", "HANGUL", "ETHIOPIC", "CHEROKEE", "KHMER",
           "MONGOLIAN", "CJK", "HIRAGANA", "KATAKANA", "BOPOMOFO"}
FUNCTION_WORDS = set(
    # English, then frequent Spanish, French, German, Italian, Portuguese and Latin ones, so
    # quoted passages in those languages are not taken for word salad
    "the of and to a in is that it for as with on be this are or not by an but at from have was what"
    " which if can i you we they he she do does would should could will my your our their its there"
    " than so about into because when how why who more one no all any"
    " de la que el en y los se del las un por con una su para es al lo como pero sus le ya o este si"
    " et les des du une est pour qui dans par plus pas au sur ne ce il sont avec"
    " der die und den von zu das mit sich auf ist im dem nicht ein eine als auch es er hat aus bei sind"
    " di e il che per non sono i da della do da em um os na ad cum quod ut quae sed ex enim esse nec"
    " vel aut autem".split())

# A note on the generator's own procedure placed before the prompt; kept in
# sync with generators/generate_prompt_oai.py.
PROCESS_NOTE_OPENER_RE = re.compile(
    r"^\s*(?:(?:quick|brief|short) (?:sanity |background |scope )?(?:note|check)"
    r"|(?:sanity|background|scope) (?:note|check)|note to (?:my)?self)\b",
    re.I,
)
PROCESS_NOTE_TOPIC_RE = re.compile(
    r"\b(?:prompt|search(?:es)?|fetch(?:ed)?|quot(?:e|ed|ing|ation)|verbatim|citation"
    r"|attribution|sourc(?:e|ing))\b",
    re.I,
)
PROCESS_NOTE_STRONG_RE = re.compile(
    r"\b(?:no|without) (?:a )?(?:web )?(?:search|fetch)(?:es)? (?:is |are |was |were )?"
    r"(?:needed|necessary|required|warranted)\b"
    r"|\bno tools? (?:is |are )?(?:needed|necessary|required)\b"
    r"|\b(?:the|this) prompt (?:involves|doesn'?t|does not|needs no|requires no|paraphrases"
    r"|quotes|cites|leans on|relies on)\b"
    r"|^\s*(?:here'?s|here is|below is) (?:the|my|your) (?:final )?prompt\b",
    re.I,
)
PROCESS_NOTE_WORDS = 60

# The model's own deliberation leaking into the prompt text, seen with DeepSeek
# V4.1 Flash: the answer opens with planning ("Let me actually settle. I'll pick:
# Domain = ...", "The user wants a prompt only.") or with a fragment of a thought,
# or the prompt is followed by a self-review ("--- Hmm, that's decent. Let me
# check for issues."). Casual openers ("Ok,", "Let's do a role-play", "Let me
# preface this") and "Constraints:" paragraphs are legitimate and not matched.
DELIBERATION_HEAD_RE = re.compile(
    r"^\s*(?:\.\.\.|Let me (?!preface|start by|begin by|explain|be )|Hmm\b|Actually[,:]|Wait\b"
    r"|I'll (?:pick|go with|draft|write the prompt|write it)\b"
    r"|I need to (?:pick|choose|decide|write (?:a |the )?(?:\w+ )?prompt)\b|The user wants\b|Options?:"
    r"|Domain\s*[=:]|Type\s*[=:]|\w+ type[,:] |Now,? let me|First,? let me|Final check|Good\."
    r"|I'm thinking about which|That'?s (?:decent|good|fine)|[:;)\]\-\u2013\u2014,.?!])",
    re.I,
)
SELF_REVIEW_RE = re.compile(
    r"^(?:Hmm\b|Let me (?:check|review|make sure|verify|double-?check|count|re-?read|refine|tighten|trim"
    r"|polish|finalize|reconsider|decide|also make sure|see if|look at the|think about (?:the|which|whether))"
    r"|That'?s (?:decent|pretty good|solid)\b|That'?s (?:good|fine)\. (?:Let me|Now|Length|Check|Final|I'll)"
    r"|Good\.|Check(?:ing|s)?:|Final check|Word count|Length check"
    r"|Now let me (?:check|review|make sure|verify|double-?check|count|re-?read|refine|tighten|trim|polish|finalize|reconsider)"
    r"|OK[,.] (?:let me|that works)|Okay[,.] (?:let me|that works)"
    r"|I (?:should|need to) (?:check|make sure|tighten|trim|double-check)|Wait[,\u2014-] (?:the|I|is|does|let)"
    r"|Actually[,:] (?:let me|I should|I'll|wait|the instruction|the prompt))",
    re.I,
)
PARAGRAPH_START_RE = re.compile(r"(?:^|\n\n|\n---+\n\n?)([^\n]+)")


def leaked_deliberation(prompt_text):
    """Return a short reason if the text carries the model's deliberation, else None."""
    if DELIBERATION_HEAD_RE.match(prompt_text):
        return "deliberation or a fragment before the prompt"
    m = LEAK_VOCAB_RE.search(prompt_text)
    if m:
        return f"generator vocabulary ({m.group(0)[:30]!r})"
    for g in GLUE_RE.finditer(prompt_text):
        # a deliberation word glued to a capitalised prompt start, shortly after generator talk
        if re.search(r"\b(?:prompt|final|output|preamble|quotation marks|tools?)\b", prompt_text[max(0, g.start() - 200):g.start()], re.I):
            return f"prompt glued to deliberation ({prompt_text[max(0, g.start() - 20):g.end() + 20]!r})"
    for m in PARAGRAPH_START_RE.finditer(prompt_text):
        if m.start(1) >= 150 and SELF_REVIEW_RE.match(m.group(1).strip()):
            return "self-review after the prompt"
    return None


def stray_east_asian(text):
    """True if the text has East Asian characters that look like a stray word rather than a
    quoted term: glued to the English around them, or in a prompt on some other subject and
    not in brackets."""
    if not EAST_ASIAN_RE.search(text):
        return False
    if STRAY_EAST_ASIAN_RE.search(text):
        return True
    return not EAST_ASIAN_TOPIC_RE.search(text) and bool(EAST_ASIAN_RE.search(BRACKETED_EAST_ASIAN_RE.sub("", text)))


def other_scripts(text):
    """The writing systems other than Latin and Greek with at least two letters in the text."""
    letters = collections.Counter()
    for ch in re.findall(r"[^\x00-\x7f]", text):
        if ch.isalpha():
            script = unicodedata.name(ch, "").split(" ", 1)[0]
            if script in SCRIPTS:
                letters["CJK" if script in ("HIRAGANA", "KATAKANA", "BOPOMOFO") else script] += 1
    return sorted(s for s, k in letters.items() if k >= 2)


def word_salad(text, width=40, step=5):
    """The start of the first stretch of `width` words that are nearly all bare words of ASCII
    letters (no punctuation, digits or symbols, so not a formula or a list of names), mostly
    different from each other (not coin flips or a table's labels), with at most two function
    words among them, or None."""
    words = text.split()
    for i in range(0, len(words) - width + 1, step):
        window = words[i:i + width]
        if (sum(w.isascii() and w.isalpha() for w in window) >= 0.9 * width
                and len({w.lower() for w in window}) >= 0.75 * width
                and sum(w.lower() in FUNCTION_WORDS for w in window) <= 0.05 * width):
            return " ".join(window[:8])
    return None


def process_note(prompt_text):
    """True if a short opening paragraph is a note on the generator's own
    procedure ("Quick sanity check: the prompt paraphrases rather than quotes,
    so no fetch is needed") or a chat preamble ("Here's the prompt:") rather
    than part of the prompt."""
    opening = prompt_text.strip().split("\n\n", 1)[0]
    if len(opening.split()) > PROCESS_NOTE_WORDS:
        return False
    return bool(
        PROCESS_NOTE_STRONG_RE.search(opening)
        or (PROCESS_NOTE_OPENER_RE.search(opening) and PROCESS_NOTE_TOPIC_RE.search(opening))
    )


def grams(text, n=8):
    w = WORD.findall(text.lower())
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def load_examples(batch):
    """8-gram -> (task type, example index) for the examples this batch was shown."""
    try:
        types, note = assemble.load_task_types(batch / "inputs"), "snapshot"
    except FileNotFoundError:
        types, note = assemble.load_task_types(assemble.COMPONENTS_DIR), "CURRENT components (no snapshot in this batch)"
    index = {}
    for t in types:
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
    markup = flag(MARKUP)
    print(f"tool-call markup or special tokens: {len(markup)}", markup[:5] or "none")
    print("chat preamble at start:", flag(PREAMBLE, lambda t: t.strip())[:5] or "none")
    notes = [name for name, t in texts.items() if process_note(t)]
    print("process note before the prompt:", notes[:8] or "none")
    leaks = [name for name, t in texts.items() if leaked_deliberation(t)]
    print(f"model deliberation before or after the prompt: {len(leaks)}", leaks[:8] or "none")
    framing = flag(META)
    print(f"dataset-construction framing or relayed instructions: {len(framing)}", framing[:8] or "none")
    quoted = [name for name, t in texts.items() if t.strip().startswith(('"', "“")) and t.strip().endswith(('"', "”"))]
    print("wrapped in quotes / pure dialogue:", quoted[:5] or "none")
    stray = [name for name, t in texts.items() if stray_east_asian(t)]
    print(f"East Asian characters: {len(flag(EAST_ASIAN_RE))}; a stray word (glued to the English around it, "
          f"or off-topic and unbracketed): {len(stray)}", stray[:8] or "none")
    mixed = {name: s for name, t in texts.items() if len(s := other_scripts(t)) >= 2}
    print(f"letters from two or more writing systems besides Latin and Greek: {len(mixed)}",
          [f"{name} ({'/'.join(s)})" for name, s in list(mixed.items())[:5]] or "none")
    salad = [name for name, t in texts.items() if word_salad(t)]
    print(f"word salad (40 bare words with at most two function words): {len(salad)}", salad[:5] or "none")

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
        comp = assemble.load(b / "inputs")
        store = None
        if cfg.get("link_prompts"):  # a link batch: the pages' texts are in the snapshot store
            sys.path.insert(0, str(REPO / "generators"))
            import attached_pages
            store = attached_pages.SnapshotStore(REPO / cfg["snapshots"])
        bad = 0
        for m in metas.values():
            try:
                sample = {k: m[k] for k in assemble.SAMPLE_KEYS if k in m or k not in assemble.OPTIONAL_SAMPLE_KEYS}
                pages = attached_pages.render_blocks(sample["attached_pages"], store) if store else None
                comp.render(sample, web_tools=True, strict_quotes=True, pages=pages)
            except Exception:
                bad += 1
        print(f"sidecars that fail to re-render from the snapshot: {bad}")
    except Exception as e:  # pre-029 snapshots lack additional_instructions.yaml
        print(f"sidecar re-render skipped ({e.__class__.__name__})")


if __name__ == "__main__":
    main()
