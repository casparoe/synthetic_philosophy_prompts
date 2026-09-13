#!/usr/bin/env python3
"""Judge pairs of responses with a Claude model: which reply to a prompt is better?

Takes a pair set (tools/make_pair_set.py), renders preferences/judge_prompt.j2
with the prompt and the two answers -- the responders' chains of thought are
not shown -- and asks the judge for one of five verdicts: strongly A, weakly A,
unsure/similar, weakly B, strongly B. One YAML file per pair goes to
preferences/run_NNN/ with the verdict, the judge's visible reasoning, its
summarized thinking, and token usage; run.yaml records the model, effort,
and pair set, and a copy of the template sits next to it.

Two ways to send the requests: --api messages streams them one at a time per
worker (the default: results as they come), --api batches submits them all as
Message Batches (half price, results within hours, and a sleeping laptop can
do no harm) and polls until they have ended. Both resume: --resume
preferences/run_NNN judges whatever has no file yet, first collecting the
results of batches an earlier invocation submitted. Pairs whose judgment the
API kept blocking ("Output blocked by content filtering policy", which sticks
to a few prompts) are listed under given_up in run.yaml and skipped on resume
unless --retry-given-up is passed.

    .venv/bin/python generators/judge_pairs.py --pairs preferences/pairs/r1_imported_500.yaml --limit 3
    .venv/bin/python generators/judge_pairs.py --pairs preferences/pairs/r1_imported_500.yaml --api batches --prices 5,25
    .venv/bin/python generators/judge_pairs.py --resume preferences/run_000
"""

import argparse
import collections
import hashlib
import json
import random
import re
import shlex
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import anthropic
import jinja2
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_responses import (  # noqa: E402
    REPO_ROOT, YAML_LOADER, FatalRequestError, create_run_dir, now_iso, repo_relative, write_record,
)

PREFERENCES_DIR = REPO_ROOT / "preferences"
DEFAULT_TEMPLATE = PREFERENCES_DIR / "judge_prompt.j2"
VERDICTS = ["strongly A", "weakly A", "unsure/similar", "weakly B", "strongly B"]
# The last "Verdict: <option>" in the judge's text; tolerant of markdown
# emphasis and of "unsure" or "similar" alone.
VERDICT_RE = re.compile(
    r"verdict\W{0,8}(strongly\s+a|weakly\s+a|unsure(?:\s*/\s*similar)?|similar|weakly\s+b|strongly\s+b)(?![a-z])",
    re.I,
)
TEXT_FIELDS = ["thinking", "judgment"]
MAX_ATTEMPTS = 3  # defective judgments (no verdict line, budget hit): these cost money
MAX_FAILURES = 8  # request failures: these cost nothing
MAX_ROUNDS = 3  # batch submissions per invocation, for errored, expired, or defective results
POLL_INTERVAL = 60
RETRY_ATTEMPTS = 10
RETRY_WAIT = 60
CHUNK_BYTES = 150 * 1024 * 1024  # well under the API's 256 MB / 100k requests per batch
CHUNK_REQUESTS = 10_000
# Settings that define a run; on --resume they come from run.yaml and may not
# be changed on the command line.
RUN_SETTINGS = ["pairs", "model", "effort", "max_tokens", "template", "api", "prices"]


def failure_pause(n):
    return min(15 * 2 ** (n - 1), 480) * random.uniform(1.0, 1.5)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.load(f, Loader=YAML_LOADER)


def load_pairs(path):
    data = load_yaml(path)
    pairs = data["pairs"]
    ids = [p["id"] for p in pairs]
    if len(set(ids)) != len(ids):
        raise SystemExit(f"{path}: contains duplicate pair IDs")
    return pairs


def record_file(run_dir, pid):
    return run_dir / f"{pid}.yaml"


def load_done(run_dir):
    for tmp in run_dir.glob("*.tmp"):
        tmp.unlink()
    return {p.stem for p in run_dir.glob("prompt_*.yaml")}


def render_pair(template, pair):
    """The judge prompt for a pair: the prompt as the responders saw it and
    their two answers, in the pair set's A/B order."""
    a = load_yaml(REPO_ROOT / pair["a"])
    b = load_yaml(REPO_ROOT / pair["b"])
    if a["prompt"].strip() != b["prompt"].strip():
        raise ValueError(f"{pair['id']}: the two responses answer different prompt texts")
    return template.render(prompt=a["prompt"].strip(), response_a=a["answer"].strip(), response_b=b["answer"].strip())


def request_params(cfg, judge_prompt):
    return {
        "model": cfg["model"],
        "max_tokens": cfg["max_tokens"],
        "thinking": {"type": "adaptive", "display": "summarized"},
        "output_config": {"effort": cfg["effort"]},
        "messages": [{"role": "user", "content": judge_prompt}],
    }


def parse_verdict(text):
    matches = VERDICT_RE.findall(text or "")
    if not matches:
        return None
    raw = re.sub(r"\s+", " ", matches[-1].lower()).strip()
    if raw.startswith(("unsure", "similar")):
        return "unsure/similar"
    word, letter = raw.split(" ")
    return f"{word} {letter.upper()}"


def cost(cfg, usage):
    if not cfg.get("prices"):
        return None
    price_in, price_out = cfg["prices"]
    return round((usage.input_tokens * price_in + usage.output_tokens * price_out) / 1e6, 6)


def make_record(cfg, pair, message, attempts):
    thinking = "\n\n".join(b.thinking for b in message.content if b.type == "thinking" and b.thinking).strip()
    judgment = "".join(b.text for b in message.content if b.type == "text").strip()
    verdict = parse_verdict(judgment)
    preferred = strength = None
    if verdict and verdict != "unsure/similar":
        preferred = pair["a"] if verdict.endswith("A") else pair["b"]
        strength = verdict.split()[0].removesuffix("ly")
    return {
        "id": pair["id"],
        "pair_set": cfg["pairs"],
        "response_a": pair["a"],
        "response_b": pair["b"],
        "judge_model": cfg["model"],
        "effort": cfg["effort"],
        "api": cfg["api"],
        "verdict": verdict,
        "preferred": preferred,
        "strength": strength,
        "stop_reason": message.stop_reason,
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
        "cost_usd": cost(cfg, message.usage),
        "message_id": message.id,
        "attempts": attempts,
        "created_at": now_iso(),
        "thinking": thinking or None,
        "judgment": judgment,
    }


def judgment_defect(record):
    """Why a judgment cannot be kept, or None. Refusals are reported
    separately: they are final, the others are worth another attempt."""
    if record["stop_reason"] != "end_turn":
        return f"stop_reason {record['stop_reason']}"
    if not record["verdict"]:
        return "no verdict line"
    return None


def judge_one(client, cfg, template, pair):
    """Stream one judgment. Returns (record, None), or (None, reason) when the
    request keeps failing or the judge never produces a verdict."""
    params = request_params(cfg, render_pair(template, pair))
    attempts = failures = 0
    problem = None
    while True:
        if attempts >= MAX_ATTEMPTS or failures >= MAX_FAILURES:
            return None, problem
        if problem:
            print(
                f"warning: {pair['id']}: {problem}; retry ({attempts} defective of {MAX_ATTEMPTS}, "
                f"{failures} failed of {MAX_FAILURES})",
                file=sys.stderr,
                flush=True,
            )
        try:
            with client.messages.stream(**params) as stream:
                message = stream.get_final_message()
        except anthropic.APIStatusError as e:
            if e.status_code in (401, 402, 403, 404):
                raise FatalRequestError(f"HTTP {e.status_code}: {str(e.message)[:300]}")
            if e.status_code == 400:
                return None, f"request rejected: {str(e.message)[:300]}"
            problem = f"HTTP {e.status_code}"
            failures += 1
            time.sleep(failure_pause(failures))
            continue
        except Exception as e:
            # Broad on purpose: transport errors (e.g. the burst of broken
            # connections when the machine wakes from sleep) are not always
            # wrapped in anthropic.APIError.
            problem = f"request failed ({e.__class__.__name__})"
            failures += 1
            time.sleep(failure_pause(failures))
            continue
        attempts += 1
        record = make_record(cfg, pair, message, attempts)
        if record["stop_reason"] == "refusal":
            return None, "refusal"
        problem = judgment_defect(record)
        if problem is None:
            return record, None


class Totals:
    def __init__(self):
        self.n = self.failed = self.input_tokens = self.output_tokens = 0
        self.cost = 0.0
        self.verdicts = collections.Counter()

    def add(self, record):
        self.n += 1
        self.input_tokens += record["input_tokens"]
        self.output_tokens += record["output_tokens"]
        self.cost += record["cost_usd"] or 0.0
        self.verdicts[record["verdict"]] += 1

    def report(self, total):
        cost = f"; cost ${self.cost:.2f}" if self.cost else ""
        print(
            f"done: {self.n} judgments written, {self.failed} failed, {total} pairs in the set; "
            f"verdicts {dict(self.verdicts)}; tokens in {self.input_tokens:,} out {self.output_tokens:,}"
            + cost,
            flush=True,
        )


def print_progress(totals, record, of):
    cost = f" ${record['cost_usd']:.3f}" if record["cost_usd"] is not None else ""
    print(
        f"[{totals.n + totals.failed}/{of}] {record['id']} {record['verdict']} "
        f"({record['input_tokens']} in, {record['output_tokens']} out{cost})",
        flush=True,
    )


def run_messages(client, cfg, run_dir, template, pending, concurrency):
    totals = Totals()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(judge_one, client, cfg, template, pair): pair for pair in pending}
        try:
            for future in as_completed(futures):
                pair = futures[future]
                record, problem = future.result()
                if record is None:
                    totals.failed += 1
                    print(f"warning: {pair['id']}: giving up ({problem})", file=sys.stderr, flush=True)
                    continue
                write_record(record_file(run_dir, pair["id"]), record, TEXT_FIELDS)
                totals.add(record)
                print_progress(totals, record, len(pending))
        except FatalRequestError as e:
            executor.shutdown(wait=False, cancel_futures=True)
            raise SystemExit(f"fatal: {e}")
        except BaseException:
            executor.shutdown(wait=False, cancel_futures=True)
            raise
    return totals


def with_retries(fn, what):
    """Retry transient failures; a sleeping laptop breaks connections."""
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return fn()
        except anthropic.APIStatusError as e:
            if e.status_code in (400, 401, 402, 403, 404):
                raise SystemExit(f"fatal: {what}: HTTP {e.status_code}: {str(e.message)[:300]}")
            problem = f"HTTP {e.status_code}"
        except Exception as e:
            problem = e.__class__.__name__
        print(f"warning: {what} failed ({problem}), retry {attempt + 1}/{RETRY_ATTEMPTS} in {RETRY_WAIT}s", file=sys.stderr, flush=True)
        time.sleep(RETRY_WAIT)
    raise RuntimeError(f"{what} kept failing after {RETRY_ATTEMPTS} attempts")


def submit_chunked(client, requests):
    batch_ids = []
    chunk, size = [], 0

    def flush():
        nonlocal chunk, size
        if chunk:
            body = chunk
            batch = with_retries(lambda: client.messages.batches.create(requests=body), "batch create")
            batch_ids.append(batch.id)
            chunk, size = [], 0

    for request in requests:
        est = len(json.dumps(request))
        if chunk and (size + est > CHUNK_BYTES or len(chunk) >= CHUNK_REQUESTS):
            flush()
        chunk.append(request)
        size += est
    flush()
    return batch_ids


def poll_until_ended(client, batch_ids):
    remaining = set(batch_ids)
    first = True
    while remaining:
        if not first:
            time.sleep(POLL_INTERVAL)
        first = False
        agg = collections.Counter()
        try:
            for bid in sorted(remaining):
                batch = client.messages.batches.retrieve(bid)
                for key in ("processing", "succeeded", "errored", "expired", "canceled"):
                    agg[key] += getattr(batch.request_counts, key)
                if batch.processing_status == "ended":
                    remaining.remove(bid)
        except Exception as e:
            print(f"warning: poll failed ({e.__class__.__name__}), will retry", file=sys.stderr, flush=True)
            continue
        print(
            f"[{now_iso()[11:16]}] batches left: {len(remaining)} | "
            + " ".join(f"{k}={v}" for k, v in agg.items()),
            flush=True,
        )


def iter_results(client, bid):
    """Yield each result once, restarting the stream on transient failures."""
    seen = set()
    for attempt in range(RETRY_ATTEMPTS):
        try:
            for result in client.messages.batches.results(bid):
                if result.custom_id not in seen:
                    seen.add(result.custom_id)
                    yield result
            return
        except Exception as e:
            print(
                f"warning: results of {bid} failed ({e.__class__.__name__}), retry {attempt + 1}/{RETRY_ATTEMPTS} in {RETRY_WAIT}s",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(RETRY_WAIT)
    raise RuntimeError(f"results of {bid} kept failing")


def collect(client, cfg, run_dir, by_id, bid, attempts, refused, totals):
    """Write the good judgments of one batch; return the IDs to resubmit."""
    redo = []
    for result in iter_results(client, bid):
        pid = result.custom_id
        pair = by_id.get(pid)
        if pair is None or record_file(run_dir, pid).exists():
            continue
        if result.result.type == "succeeded":
            attempts[pid] += 1
            record = make_record(cfg, pair, result.result.message, attempts[pid])
            if record["stop_reason"] == "refusal":
                refused.add(pid)
                totals.failed += 1
                print(f"warning: {pid}: refusal; giving up", file=sys.stderr, flush=True)
                continue
            problem = judgment_defect(record)
            if problem is None:
                write_record(record_file(run_dir, pid), record, TEXT_FIELDS)
                totals.add(record)
                print_progress(totals, record, len(by_id))
                continue
        elif result.result.type == "errored":
            problem = f"errored: {json.dumps(result.result.error.model_dump())[:200]}"
            if "content filtering" in problem:
                # The judge's output was blocked by the API's content filter. That is
                # partly random (about half pass on a second try) but sticks to a few
                # prompts, so it counts as an attempt and the rounds cap bounds it.
                attempts[pid] += 1
        else:
            problem = result.result.type
        print(f"warning: {pid}: {problem}", file=sys.stderr, flush=True)
        redo.append(pid)
    return redo


def run_batches(client, cfg, run_dir, template, pending, limit):
    totals = Totals()
    by_id = {pair["id"]: pair for pair in pending}
    attempts = collections.Counter()
    refused = set()

    def save():
        (run_dir / "run.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))

    # Results of batches an earlier invocation submitted come first.
    known = list(cfg.get("message_batches") or [])
    if known:
        print(f"collecting {len(known)} batch(es) submitted earlier", flush=True)
        poll_until_ended(client, known)
        for bid in known:
            collect(client, cfg, run_dir, by_id, bid, attempts, refused, totals)
    remaining = [p for p in pending if not record_file(run_dir, p["id"]).exists() and p["id"] not in refused]
    if limit is not None:
        remaining = remaining[:limit]
    for round_no in range(1, MAX_ROUNDS + 1):
        if not remaining:
            break
        over = [p["id"] for p in remaining if attempts[p["id"]] >= MAX_ATTEMPTS]
        for pid in over:
            totals.failed += 1
            print(f"warning: {pid}: {attempts[pid]} defective or blocked judgments; giving up", file=sys.stderr, flush=True)
        if over:
            cfg["given_up"] = sorted(set(cfg.get("given_up") or []) | set(over))
            save()
        remaining = [p for p in remaining if p["id"] not in over]
        if not remaining:
            break
        requests = [{"custom_id": p["id"], "params": request_params(cfg, render_pair(template, p))} for p in remaining]
        batch_ids = submit_chunked(client, requests)
        cfg.setdefault("message_batches", []).extend(batch_ids)
        save()
        with (run_dir / "message_batches.txt").open("a") as f:
            f.write("".join(f"{now_iso()} {bid} {len(requests)} requests\n" for bid in batch_ids))
        print(f"round {round_no}: {len(requests)} requests submitted as {len(batch_ids)} batch(es): {', '.join(batch_ids)}", flush=True)
        poll_until_ended(client, batch_ids)
        redo = set()
        for bid in batch_ids:
            redo.update(collect(client, cfg, run_dir, by_id, bid, attempts, refused, totals))
        remaining = [p for p in remaining if p["id"] in redo]
    for p in remaining:
        totals.failed += 1
        print(f"warning: {p['id']}: still no judgment after {MAX_ROUNDS} rounds", file=sys.stderr, flush=True)
    if remaining and all(attempts[p["id"]] >= MAX_ATTEMPTS for p in remaining):
        cfg["given_up"] = sorted(set(cfg.get("given_up") or []) | {p["id"] for p in remaining})
        save()
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pairs", metavar="FILE", help="pair set to judge (tools/make_pair_set.py)")
    parser.add_argument("--model", help="judge model (default: claude-fable-5-1)")
    parser.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"], help="reasoning effort (default: max)")
    parser.add_argument("--max-tokens", type=int, help="output budget incl. thinking (default: 64000)")
    parser.add_argument("--template", metavar="FILE", help=f"judge prompt template (default: {repo_relative(DEFAULT_TEMPLATE)})")
    parser.add_argument("--api", choices=["messages", "batches"], help="streamed requests (default) or Message Batches")
    parser.add_argument(
        "--prices", metavar="IN,OUT",
        help="USD per million input and output tokens, to record a cost per judgment (e.g. 10,50; 5,25 for batches)",
    )
    parser.add_argument("--api-key-file", metavar="FILE", help="Anthropic API key (default: the ANTHROPIC_API_KEY environment variable)")
    parser.add_argument("--out-dir", metavar="DIR", help="where run_NNN/ directories go (default: preferences/)")
    parser.add_argument("--resume", metavar="RUN_DIR", help="continue an existing run; settings come from its run.yaml")
    parser.add_argument("--concurrency", type=int, default=4, help="parallel requests with --api messages (default: 4)")
    parser.add_argument("--limit", type=int, metavar="N", help="judge at most N pairs this invocation")
    parser.add_argument(
        "--retry-given-up", action="store_true",
        help="on --resume, try again the pairs run.yaml lists under given_up (repeatedly blocked or defective)",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the first judge prompt and request instead of sending anything")
    args = parser.parse_args()

    if args.resume:
        run_dir = Path(args.resume)
        given = [name for name in RUN_SETTINGS if getattr(args, name) is not None]
        if given or args.out_dir:
            parser.error("--resume takes the run's settings from run.yaml; do not pass "
                         + ", ".join("--" + n.replace("_", "-") for n in given + (["out_dir"] if args.out_dir else [])))
        cfg = yaml.safe_load((run_dir / "run.yaml").read_text())
        template_path = run_dir / "judge_prompt.j2"
    else:
        if not args.pairs:
            parser.error("--pairs is required (or --resume RUN_DIR)")
        template_path = Path(args.template) if args.template else DEFAULT_TEMPLATE
        prices = [float(x) for x in args.prices.split(",")] if args.prices else None
        if prices is not None and len(prices) != 2:
            parser.error("--prices takes two numbers: input and output price per million tokens")
        cfg = {
            "run": None,
            "created_at": now_iso(),
            "command": shlex.join([repo_relative(sys.argv[0]), *sys.argv[1:]]),
            "api": args.api or "messages",
            "model": args.model or "claude-fable-5-1",
            "effort": args.effort or "max",
            "max_tokens": args.max_tokens or 64000,
            "thinking": {"type": "adaptive", "display": "summarized"},
            "template": repo_relative(template_path),
            "template_sha256": sha256(template_path),
            "pairs": repo_relative(args.pairs),
            "num_pairs": None,
            "prices": prices,
        }

    pairs = load_pairs(REPO_ROOT / cfg["pairs"])
    cfg["num_pairs"] = len(pairs)
    template = jinja2.Template(template_path.read_text(), undefined=jinja2.StrictUndefined)

    if args.dry_run:
        params = request_params(cfg, render_pair(template, pairs[0]))
        print(params["messages"][0]["content"])
        print("---")
        print(yaml.safe_dump({k: v for k, v in params.items() if k != "messages"}, sort_keys=False))
        return

    key = Path(args.api_key_file).read_text().strip() if args.api_key_file else None
    client = anthropic.Anthropic(api_key=key, max_retries=4)

    if args.resume:
        cfg.setdefault("resumed_at", []).append(now_iso())
    else:
        run_dir = create_run_dir(Path(args.out_dir) if args.out_dir else PREFERENCES_DIR)
        cfg["run"] = run_dir.name
        shutil.copyfile(template_path, run_dir / "judge_prompt.j2")
    (run_dir / "run.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))

    done = load_done(run_dir)
    skip = set() if args.retry_given_up else set(cfg.get("given_up") or [])
    pending = [pair for pair in pairs if pair["id"] not in done and pair["id"] not in skip]
    if cfg["api"] == "messages" and args.limit is not None:
        pending = pending[: args.limit]
    print(
        f"{cfg['model']} at effort {cfg['effort']} via {cfg['api']}: {len(pairs)} pairs in {cfg['pairs']}; "
        f"{len(done)} already judged, {len(pending)} to do"
        + (f" ({len(skip)} given up on earlier, see run.yaml)" if skip else "") + f" -> {repo_relative(run_dir)}",
        flush=True,
    )
    if cfg["api"] == "messages":
        totals = run_messages(client, cfg, run_dir, template, pending, args.concurrency)
    else:
        totals = run_batches(client, cfg, run_dir, template, pending, args.limit)
    totals.report(len(pairs))


if __name__ == "__main__":
    main()
