#!/usr/bin/env python3
"""Generate synthetic philosophy prompts via the Message Batches API.

Same sampling, inputs, and outputs as generate_prompt.py, but the requests
are submitted as message batches, which are processed server-side at half
price. A batch request can't be resumed mid-turn, so responses that stop
with pause_turn (common with web tools) are continued in follow-up batches,
up to 5 rounds total; requests that error transiently or expire are
resubmitted once.

The script only polls between submissions, and all API calls are retried
on transient failures (laptop sleep/wake cycles break connections). If the
process dies anyway, everything needed to continue is on disk: rerun with

    .venv/bin/python generate_prompt_batch.py --resume prompts/batch_NNN

which re-renders the requests from the batch's own inputs snapshot and
samples.yaml, skips prompts whose files were already written, and picks up
from the last submitted round.

Usage:
    .venv/bin/python generate_prompt_batch.py [-n NUM_PROMPTS]
    .venv/bin/python generate_prompt_batch.py --resume prompts/batch_NNN
"""

import argparse
import random
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import yaml
from jinja2 import Environment, FileSystemLoader

from generate_prompt import (
    INPUT_FILES,
    LEGACY_WEB_TOOLS,
    REPO_ROOT,
    WEB_TOOLS,
    create_batch_dir,
    extract_output,
    load_inputs,
    next_output_path,
    uses_legacy_api,
)

MAX_ROUNDS = 5
RETRY_ATTEMPTS = 10
RETRY_WAIT = 60

# Keep well under the API's 256 MB / 100k-requests per-batch caps.
# Continuation requests carry the whole accumulated conversation
# (including fetched pages), so chunk by estimated size.
CHUNK_BYTES = 150 * 1024 * 1024
CHUNK_REQUESTS = 10_000


def with_retries(fn, what):
    """Retry transient failures; a sleeping laptop breaks connections."""
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return fn()
        except Exception as e:
            print(
                f"warning: {what} failed ({e.__class__.__name__}), "
                f"retry {attempt + 1}/{RETRY_ATTEMPTS} in {RETRY_WAIT}s",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(RETRY_WAIT)
    raise RuntimeError(f"{what} kept failing after {RETRY_ATTEMPTS} attempts")


def submit_chunked(client, sized_requests):
    """Submit (request, estimated_bytes) pairs as one or more batches."""
    batch_ids = []
    chunk, size = [], 0

    def flush():
        nonlocal chunk, size
        if chunk:
            requests = chunk
            batch = with_retries(
                lambda: client.messages.batches.create(requests=requests),
                "batch create",
            )
            batch_ids.append(batch.id)
            chunk, size = [], 0

    for request, est in sized_requests:
        if chunk and (size + est > CHUNK_BYTES or len(chunk) >= CHUNK_REQUESTS):
            flush()
        chunk.append(request)
        size += est
    flush()
    return batch_ids


def poll_until_ended(client, batch_ids, interval):
    remaining = set(batch_ids)
    while remaining:
        time.sleep(interval)
        agg = {"processing": 0, "succeeded": 0, "errored": 0, "expired": 0}
        try:
            for bid in list(remaining):
                batch = client.messages.batches.retrieve(bid)
                counts = batch.request_counts
                for key in agg:
                    agg[key] += getattr(counts, key)
                if batch.processing_status == "ended":
                    remaining.remove(bid)
        except Exception as e:
            # Treat as still processing; the next cycle retries.
            print(
                f"warning: poll failed ({e.__class__.__name__}), will retry",
                file=sys.stderr,
                flush=True,
            )
            continue
        now = datetime.now(timezone.utc).strftime("%H:%M")
        print(
            f"[{now}] batches left: {len(remaining)} | processing={agg['processing']} "
            f"succeeded={agg['succeeded']} errored={agg['errored']} expired={agg['expired']}",
            flush=True,
        )


def iter_results(client, bid):
    """Yield each result once, restarting the stream on transient failures."""
    processed = set()
    for attempt in range(RETRY_ATTEMPTS):
        try:
            for result in client.messages.batches.results(bid):
                if result.custom_id in processed:
                    continue
                processed.add(result.custom_id)
                yield result
            return
        except Exception as e:
            print(
                f"warning: results stream for {bid} failed "
                f"({e.__class__.__name__}), retry {attempt + 1}/{RETRY_ATTEMPTS} "
                f"in {RETRY_WAIT}s",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(RETRY_WAIT)
    raise RuntimeError(f"results stream for {bid} kept failing")


def render_meta_prompt(template, sample, task_types_by_name, length_instructions, web_tools):
    return template.render(
        domains=sample["domains_offered"],
        task_types=[task_types_by_name[name] for name in sample["task_types_offered"]],
        length_instruction=length_instructions[sample["length"]],
        prompt_persona=sample["persona"],
        prompt_writing_style=sample["writing_style"],
        web_tools=web_tools,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-n", "--num-prompts", type=int, default=1)
    parser.add_argument("--num-domains", type=int, default=5)
    parser.add_argument("--num-task-types", type=int, default=3)
    parser.add_argument("--model", default="claude-sonnet-5")
    parser.add_argument(
        "--effort", default="max", choices=["low", "medium", "high", "xhigh", "max"]
    )
    parser.add_argument("--no-web-tools", action="store_true")
    parser.add_argument("--poll-interval", type=int, default=60)
    parser.add_argument(
        "--resume",
        metavar="BATCH_DIR",
        help="continue an interrupted run from its batch directory",
    )
    args = parser.parse_args()
    client = anthropic.Anthropic()

    start_round = 1
    resume_ids = None

    if args.resume:
        batch_dir = Path(args.resume).resolve()
        config = yaml.safe_load((batch_dir / "batch.yaml").read_text())
        args.model = config["model"]
        args.effort = config["effort"] or args.effort
        web_tools_on = config["web_tools"]
        legacy = uses_legacy_api(args.model)
        effort = None if legacy else args.effort
        # Re-render the requests from the batch's own inputs snapshot so the
        # reconstructed user messages match what the server already saw.
        inputs_dir = batch_dir / "inputs"
        task_types = yaml.safe_load((inputs_dir / "task_types.yaml").read_text())
        task_types_by_name = {t["type"]: t for t in task_types}
        length_instructions = yaml.safe_load(
            (inputs_dir / "prompt_length.yaml").read_text()
        )
        env = Environment(
            loader=FileSystemLoader(inputs_dir), trim_blocks=True, lstrip_blocks=True
        )
        template = env.get_template("prompt.j2")
        samples = yaml.safe_load((batch_dir / "samples.yaml").read_text())
        done = set()
        for meta_path in batch_dir.glob("prompt_*.meta.yaml"):
            cid = yaml.safe_load(meta_path.read_text()).get("custom_id")
            if cid:
                done.add(cid)
        pending = {}
        for cid, sample in samples.items():
            if cid in done:
                continue
            meta_prompt = render_meta_prompt(
                template, sample, task_types_by_name, length_instructions, web_tools_on
            )
            pending[cid] = {
                "messages": [{"role": "user", "content": meta_prompt}],
                "blocks": [],
                "input_tokens": 0,
                "output_tokens": 0,
                "retries": 0,
                "est_bytes": len(meta_prompt.encode()) + 2000,
            }
        rounds = {}
        for line in (batch_dir / "message_batches.txt").read_text().splitlines():
            round_no, bid = line.replace("round ", "").split(": ")
            rounds.setdefault(int(round_no), []).append(bid)
        start_round = max(rounds)
        resume_ids = rounds[start_round]
        print(
            f"resuming {batch_dir.name} at round {start_round}: "
            f"{len(pending)} prompts open, {len(done)} already written",
            flush=True,
        )
    else:
        legacy = uses_legacy_api(args.model)
        effort = None if legacy else args.effort
        web_tools_on = not args.no_web_tools
        domains, personas, writing_styles, task_types, length_instructions = (
            load_inputs()
        )
        task_types_by_name = {t["type"]: t for t in task_types}
        env = Environment(
            loader=FileSystemLoader(REPO_ROOT), trim_blocks=True, lstrip_blocks=True
        )
        template = env.get_template("prompt.j2")

        batch_dir = create_batch_dir()
        inputs_dir = batch_dir / "inputs"
        inputs_dir.mkdir()
        for name in INPUT_FILES:
            shutil.copy2(REPO_ROOT / name, inputs_dir / name)
        (batch_dir / "batch.yaml").write_text(
            yaml.safe_dump(
                {
                    "batch": batch_dir.name,
                    "started_at": datetime.now(timezone.utc).isoformat(
                        timespec="seconds"
                    ),
                    "api": "message_batches",
                    "model": args.model,
                    "effort": effort,
                    "web_tools": web_tools_on,
                    "num_prompts": args.num_prompts,
                    "num_domains": args.num_domains,
                    "num_task_types": args.num_task_types,
                },
                sort_keys=False,
            )
        )
        print(f"writing batch to {batch_dir.relative_to(REPO_ROOT)}", flush=True)

        samples = {}
        pending = {}
        for i in range(args.num_prompts):
            cid = f"p{i:05d}"
            sample = {
                "task_types_offered": [
                    t["type"]
                    for t in random.sample(
                        task_types, k=min(args.num_task_types, len(task_types))
                    )
                ],
                "length": random.choice(list(length_instructions)),
                "persona": random.choice(personas),
                "writing_style": random.choice(writing_styles),
                "domains_offered": random.sample(
                    domains, k=min(args.num_domains, len(domains))
                ),
            }
            meta_prompt = render_meta_prompt(
                template, sample, task_types_by_name, length_instructions, web_tools_on
            )
            samples[cid] = sample
            pending[cid] = {
                "messages": [{"role": "user", "content": meta_prompt}],
                "blocks": [],
                "input_tokens": 0,
                "output_tokens": 0,
                "retries": 0,
                "est_bytes": len(meta_prompt.encode()) + 2000,
            }
        (batch_dir / "samples.yaml").write_text(
            yaml.safe_dump(samples, sort_keys=True, allow_unicode=True)
        )

    # Higher ceiling than the streaming script: with no pause_turn to split
    # the turn, thinking + searches + drafting must all fit in one response.
    request_base = {"model": args.model, "max_tokens": 64000}
    if legacy:
        request_base["thinking"] = {"type": "enabled", "budget_tokens": 16000}
    else:
        request_base["thinking"] = {"type": "adaptive", "display": "summarized"}
        request_base["output_config"] = {"effort": args.effort}
    tools = None
    if web_tools_on:
        tools = LEGACY_WEB_TOOLS if legacy else WEB_TOOLS

    def finalize(cid, state):
        prompt_text, reasoning_summary, tool_calls = extract_output(state["blocks"])
        if not prompt_text:
            print(f"warning: {cid} produced no prompt text, skipping", file=sys.stderr)
            return
        out_path = next_output_path(batch_dir)
        out_path.write_text(prompt_text + "\n")
        metadata = {
            "prompt_file": out_path.name,
            "custom_id": cid,
            "model": args.model,
            "effort": effort,
            "web_searches": tool_calls.count("web_search"),
            "web_fetches": tool_calls.count("web_fetch"),
            "input_tokens": state["input_tokens"],
            "output_tokens": state["output_tokens"],
            **samples[cid],
            "reasoning_summary": reasoning_summary or None,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        out_path.with_suffix(".meta.yaml").write_text(
            yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True)
        )

    finalized = skipped = 0
    for round_no in range(start_round, MAX_ROUNDS + 1):
        if resume_ids is not None:
            batch_ids = resume_ids
            resume_ids = None
            print(f"round {round_no}: resuming with {len(batch_ids)} batch(es)", flush=True)
        else:
            sized_requests = []
            for cid, state in pending.items():
                params = {**request_base, "messages": state["messages"]}
                if tools:
                    params["tools"] = tools
                sized_requests.append(
                    ({"custom_id": cid, "params": params}, state["est_bytes"])
                )
            batch_ids = submit_chunked(client, sized_requests)
            with (batch_dir / "message_batches.txt").open("a") as f:
                for bid in batch_ids:
                    f.write(f"round {round_no}: {bid}\n")
            print(
                f"round {round_no}: submitted {len(pending)} requests "
                f"in {len(batch_ids)} batch(es)",
                flush=True,
            )
        poll_until_ended(client, batch_ids, args.poll_interval)

        next_pending = {}
        for bid in batch_ids:
            for result in iter_results(client, bid):
                cid = result.custom_id
                state = pending.get(cid)
                if state is None:
                    continue  # already finalized before a resume
                outcome = result.result
                if outcome.type != "succeeded":
                    error_type = getattr(
                        getattr(outcome, "error", None), "type", outcome.type
                    )
                    retryable = outcome.type == "expired" or (
                        outcome.type == "errored" and error_type != "invalid_request"
                    )
                    if retryable and state["retries"] < 1:
                        state["retries"] += 1
                        next_pending[cid] = state
                    else:
                        print(
                            f"warning: {cid} {outcome.type} ({error_type}), skipping",
                            file=sys.stderr,
                        )
                        skipped += 1
                    continue
                message = outcome.message
                state["input_tokens"] += message.usage.input_tokens
                state["output_tokens"] += message.usage.output_tokens
                state["blocks"] = state["blocks"] + list(message.content)
                if message.stop_reason == "pause_turn" and round_no < MAX_ROUNDS:
                    state["messages"] = [
                        state["messages"][0],
                        {"role": "assistant", "content": state["blocks"]},
                    ]
                    state["est_bytes"] = 2000 + 5 * (
                        message.usage.input_tokens + message.usage.output_tokens
                    )
                    next_pending[cid] = state
                elif message.stop_reason == "end_turn":
                    finalize(cid, state)
                    finalized += 1
                else:
                    print(
                        f"warning: {cid} stop_reason={message.stop_reason!r}, skipping",
                        file=sys.stderr,
                    )
                    skipped += 1
        pending = next_pending
        print(
            f"round {round_no} done: {finalized} finalized, {skipped} skipped, "
            f"{len(pending)} to continue",
            flush=True,
        )
        if not pending:
            break
    if pending:
        print(
            f"warning: {len(pending)} prompts still unfinished after "
            f"{MAX_ROUNDS} rounds, dropped",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
