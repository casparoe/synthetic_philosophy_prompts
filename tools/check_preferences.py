#!/usr/bin/env python
"""Report on a preference run: coverage of the pair set, verdicts, position balance, tokens, cost.

With --compare, also the agreement of two runs on the pairs both judged (same
pair set, e.g. a strong judge against a weak one).

    tools/check_preferences.py preferences/run_000 [--compare preferences/run_001]
"""
import argparse
import collections
import pathlib
import statistics as st
import sys

import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "generators"))
from judge_pairs import VERDICTS, load_pairs, load_yaml  # noqa: E402


def pct(k, n):
    return f"{k} ({100 * k / n:.1f}%)" if n else "0"


def dist(values):
    if not values:
        return "n/a"
    values = sorted(values)
    p90 = values[min(len(values) - 1, int(0.9 * len(values)))]
    return f"mean {st.mean(values):,.0f}, median {values[len(values) // 2]:,}, p90 {p90:,}, max {values[-1]:,}"


def load_run(run_dir):
    cfg = yaml.safe_load((run_dir / "run.yaml").read_text())
    records = {r["id"]: r for r in (load_yaml(p) for p in sorted(run_dir.glob("prompt_*.yaml")))}
    return cfg, records


def side(verdict):
    """A, B, or - for a verdict."""
    return "-" if verdict in (None, "unsure/similar") else verdict[-1]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run", type=pathlib.Path)
    ap.add_argument("--compare", type=pathlib.Path, metavar="RUN", help="a second run on the same pair set")
    ap.add_argument("--top", type=int, default=5, help="how many example IDs to list per finding")
    args = ap.parse_args()

    cfg, records = load_run(args.run)
    pairs = load_pairs(REPO / cfg["pairs"])
    n = len(records)
    print(f"== {cfg.get('run')}: {cfg['model']} at effort {cfg['effort']} via {cfg['api']}; template {cfg['template']}")
    print(f"pair set {cfg['pairs']} ({len(pairs)} pairs); created {cfg.get('created_at')}"
          + (f", resumed {len(cfg['resumed_at'])}x" if cfg.get("resumed_at") else ""))
    missing = [p["id"] for p in pairs if p["id"] not in records]
    stray = sorted(set(records) - {p["id"] for p in pairs})
    given_up = cfg.get("given_up") or []
    print(f"\n-- judgments: {n}; coverage {len(pairs) - len(missing)}/{len(pairs)}; missing {len(missing)} {missing[:args.top]}"
          + (f"; {len(stray)} outside the set" if stray else "")
          + (f"; given up on {len(given_up)} (judgment repeatedly blocked or defective): {given_up}" if given_up else ""))
    if not n:
        return

    verdicts = collections.Counter(r["verdict"] for r in records.values())
    print("\n-- verdicts: " + ", ".join(f"{v} {pct(verdicts[v], n)}" for v in VERDICTS + [None] if verdicts[v]))
    sides = collections.Counter(side(r["verdict"]) for r in records.values())
    print(f"position: A preferred {pct(sides['A'], n)}, B preferred {pct(sides['B'], n)}, neither {pct(sides['-'], n)} "
          "(the pair set flips a coin for the order, so A and B should come out about even)")

    def flag(label, hits):
        print(f"{label}: {pct(len(hits), n)} {hits[:args.top]}")

    print("\n-- checks")
    flag("no verdict", [pid for pid, r in records.items() if not r["verdict"]])
    flag("stop reason not end_turn", [pid for pid, r in records.items() if r.get("stop_reason") != "end_turn"])
    flag("took more than one attempt", [pid for pid, r in records.items() if (r.get("attempts") or 1) > 1])
    flag("no thinking", [pid for pid, r in records.items() if not r.get("thinking")])

    print("\n-- lengths")
    print(f"input tokens: {dist([r['input_tokens'] for r in records.values()])}")
    print(f"output tokens: {dist([r['output_tokens'] for r in records.values()])}")
    print(f"judgment words: {dist([len((r.get('judgment') or '').split()) for r in records.values()])}")
    costs = [r["cost_usd"] for r in records.values() if r.get("cost_usd") is not None]
    if costs:
        print(f"\n-- cost: total ${sum(costs):.2f}; mean ${st.mean(costs):.4f} per judgment; ${1000 * st.mean(costs):.2f} per 1000")

    if args.compare:
        cfg2, records2 = load_run(args.compare)
        both = sorted(set(records) & set(records2))
        print(f"\n== agreement with {cfg2.get('run')} ({cfg2['model']} at effort {cfg2['effort']}) on {len(both)} pairs")
        if cfg2["pairs"] != cfg["pairs"]:
            print(f"warning: different pair sets ({cfg2['pairs']})")
        if both:
            exact = sum(records[p]["verdict"] == records2[p]["verdict"] for p in both)
            same_side = sum(side(records[p]["verdict"]) == side(records2[p]["verdict"]) for p in both)
            decided = [p for p in both if side(records[p]["verdict"]) != "-" and side(records2[p]["verdict"]) != "-"]
            opposite = sum(side(records[p]["verdict"]) != side(records2[p]["verdict"]) for p in decided)
            print(f"same verdict {pct(exact, len(both))}; same side (A, B, or neither) {pct(same_side, len(both))}; "
                  f"both decided {len(decided)}, of which opposite sides {pct(opposite, len(decided))}")
            table = collections.Counter((records[p]["verdict"], records2[p]["verdict"]) for p in both)
            width = max(len(v) for v in VERDICTS)
            print(" " * width + "  " + "  ".join(f"{v[:10]:>10}" for v in VERDICTS) + "   (columns: " + cfg2.get("run", "second run") + ")")
            for v1 in VERDICTS:
                print(f"{v1:>{width}}  " + "  ".join(f"{table[(v1, v2)]:>10}" for v2 in VERDICTS))


if __name__ == "__main__":
    main()
