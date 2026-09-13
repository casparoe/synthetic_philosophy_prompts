#!/usr/bin/env python3
"""Generate model responses to prompts of the dataset via an OpenAI-compatible endpoint.

Companion to the prompt generators. Takes a prompt set (a list of prompt IDs,
see tools/make_prompt_set.py), sends every prompt as a single user message to
one model -- no system prompt, no tools -- and stores the reply, the visible
answer plus the chain of thought exactly as the provider returns it, as one
YAML file per response under responses/run_NNN/. Intended for open-weight
models whose licenses permit training on their outputs and which return their
full reasoning rather than a summary (Qwen3.5, gpt-oss, DeepSeek V4, ...).

A run is one model, one prompt set, one sampling configuration; run.yaml
records all of it. Sampling parameters are not defaulted: pass the model
card's recommended values. Runs resume: --resume responses/run_NNN answers
whatever has no file yet, so a crash or a Ctrl-C costs nothing but the
requests in flight.

Usage:
    .venv/bin/python tools/make_prompt_set.py responses/sets/open_1k.txt \
        --generator-model 'qwen|deepseek' --sample 1000 --seed 0
    .venv/bin/python generators/generate_responses.py --prompt-set responses/sets/open_1k.txt \
        --model qwen/qwen3.5-397b-a17b --temperature 0.6 --top-p 0.95 --top-k 20 \
        --api-key-file api_keys/openrouter.txt --provider-order alibaba,deepinfra --concurrency 16
    .venv/bin/python generators/generate_responses.py --resume responses/run_000 \
        --api-key-file api_keys/openrouter.txt
"""

import argparse
import collections
import os
import random
import re
import shlex
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_prompt import PROMPTS_DIR, REPO_ROOT  # noqa: E402

RESPONSES_DIR = REPO_ROOT / "responses"
THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)
RECORD_FILE_RE = re.compile(r"prompt_(\d+)(?:\.(\d+))?\.yaml")
YAML_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
MAX_ATTEMPTS = 6
# A long generation sends nothing back until it is finished, so a connection
# that died (network drop, system sleep) looks just like one still waiting.
# TCP keepalive probes detect the dead ones within a few minutes instead of at
# the read timeout. (Names differ per platform; TCP_KEEPALIVE is macOS's idle
# time, TCP_KEEPIDLE Linux's.)
KEEPALIVE_OPTIONS = [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)]
for _name, _value in (("TCP_KEEPALIVE", 60), ("TCP_KEEPIDLE", 60), ("TCP_KEEPINTVL", 20), ("TCP_KEEPCNT", 6)):
    if hasattr(socket, _name):
        KEEPALIVE_OPTIONS.append((socket.IPPROTO_TCP, getattr(socket, _name), _value))
# Statuses worth retrying: rate limits, timeouts, and provider-side failures.
RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524}
SAMPLING_KEYS = ["temperature", "top_p", "top_k", "min_p", "presence_penalty", "repetition_penalty"]
# The long text fields, written last and as literal blocks so the files read well.
TEXT_FIELDS = ["system_prompt", "prompt", "reasoning", "answer"]
# Settings that define a run; on --resume they come from run.yaml and may not
# be changed on the command line.
RUN_SETTINGS = [
    "prompt_set", "model", "base_url", "system_prompt_file", "reasoning", "max_tokens",
    *SAMPLING_KEYS, "samples_per_prompt", "provider_order", "provider_ignore",
    "quantizations", "no_fallbacks",
]


class FatalRequestError(Exception):
    """An error every request would hit the same way (bad key, no credits,
    unknown model): abort the run instead of retrying prompt by prompt."""


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_prompt_set(path):
    """Prompt IDs listed in a set file, one per line, '#' comments allowed.
    Accepts 'prompt_00042', '42', or a path ending in prompt_00042.txt."""
    ids = []
    for line in Path(path).read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.search(r"(?:^|/)(?:prompt_)?(\d+)(?:\.txt)?$", line)
        if not m:
            raise ValueError(f"{path}: cannot read a prompt ID from {line!r}")
        ids.append(f"prompt_{int(m.group(1)):05d}")
    return ids


def prompt_index():
    """Prompt ID -> path, for every prompt in the dataset."""
    return {p.stem: p for p in PROMPTS_DIR.glob("**/prompt_*.txt")}


def create_run_dir(root):
    existing = [
        int(m.group(1))
        for p in root.glob("run_*")
        if (m := re.fullmatch(r"run_(\d+)(?:_[a-z].*)?", p.name))  # run_004_imported counts too
    ]
    n = max(existing, default=-1) + 1
    while True:
        run_dir = root / f"run_{n:03d}"
        try:
            run_dir.mkdir(parents=True)
            return run_dir
        except FileExistsError:
            n += 1


def record_path(run_dir, pid, sample_index, samples_per_prompt):
    """prompt_00042.yaml, or prompt_00042.K.yaml when a run takes several
    samples per prompt."""
    suffix = f".{sample_index}" if samples_per_prompt > 1 else ""
    return run_dir / f"{pid}{suffix}.yaml"


def load_done(run_dir):
    """(prompt ID, sample index) of every response file in the run. Leftover
    temporary files from an interrupted write are removed."""
    for tmp in run_dir.glob("*.tmp"):
        tmp.unlink()
    done = set()
    for path in run_dir.glob("prompt_*.yaml"):
        m = RECORD_FILE_RE.fullmatch(path.name)
        if m:
            done.add((f"prompt_{int(m.group(1)):05d}", int(m.group(2) or 0)))
    return done


def literal_block(key, text):
    """`key: |-` followed by the text, indented; every line is taken literally."""
    body = "\n".join("  " + line if line else "" for line in text.split("\n"))
    return f"{key}: |-\n{body}\n"


def record_yaml(record, text_fields=TEXT_FIELDS):
    """The record as YAML with the long text fields as literal blocks at the
    end. PyYAML would quote and escape a text that has a tab or a trailing
    space, so the blocks are written by hand and the result is checked by
    loading it back; if anything does not round-trip, the whole record falls
    back to PyYAML's own (less readable, always correct) rendering."""
    head = {k: v for k, v in record.items() if k not in text_fields}
    text = yaml.safe_dump(head, sort_keys=False, allow_unicode=True)
    for key in text_fields:
        if key not in record:
            continue
        value = record[key]
        if isinstance(value, str) and value and value == value.strip():
            text += literal_block(key, value)
        else:
            text += yaml.safe_dump({key: value}, allow_unicode=True)
    try:
        if yaml.load(text, Loader=YAML_LOADER) == record:
            return text
    except yaml.YAMLError:
        pass
    return yaml.safe_dump(record, sort_keys=False, allow_unicode=True)


def write_record(path, record, text_fields=TEXT_FIELDS):
    """Write via a temporary file and rename, so a crash never leaves a
    truncated response file that --resume would mistake for a finished one."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(record_yaml(record, text_fields), encoding="utf-8")
    os.replace(tmp, path)


def reasoning_setting(value):
    """The request's reasoning object for a --reasoning value."""
    if value == "default":
        return None
    if value in ("on", "off"):
        return {"enabled": value == "on"}
    return {"effort": value}


def build_request(cfg, messages):
    request = {"model": cfg["model"], "messages": messages, "max_tokens": cfg["max_tokens"]}
    for key in SAMPLING_KEYS:
        if cfg["sampling"].get(key) is not None:
            request[key] = cfg["sampling"][key]
    if cfg.get("reasoning"):
        request["reasoning"] = cfg["reasoning"]
    if cfg.get("provider"):
        request["provider"] = cfg["provider"]
    if cfg["api"] == "openrouter":
        request["usage"] = {"include": True}
    return request


def parse_message(message):
    """(reasoning, answer, reasoning_detail_types) from an assistant message.

    The chain of thought normally arrives in `reasoning` (OpenRouter, vLLM's
    reasoning_content, ...); reasoning_details says whether that is the full
    text or only a summary. Some servers instead leave it inline as
    <think>...</think>, which is moved out of the answer here."""
    content = message.get("content") or ""
    reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
    details = message.get("reasoning_details") or []
    if not reasoning:
        reasoning = "".join(d.get("text") or "" for d in details if d.get("type") == "reasoning.text")
    if "<think>" in content:
        inline = THINK_RE.findall(content)
        if inline:
            content = THINK_RE.sub("", content)
        else:  # never closed: everything after the tag is cut-off reasoning
            content, _, tail = content.partition("<think>")
            inline = [tail]
        reasoning = "\n\n".join(p for p in [reasoning, *inline] if p.strip())
    kinds = sorted({d.get("type") for d in details if d.get("type")})
    return reasoning.strip() or None, content.strip(), kinds


def clean_text(text):
    """Normalize line endings; the response files are YAML block scalars,
    which cannot carry a carriage return."""
    return text.replace("\r\n", "\n").replace("\r", "\n") if text else text


def make_record(cfg, pid, path, sample_index, messages, data):
    choice = data["choices"][0]
    reasoning, answer, kinds = parse_message(choice.get("message") or {})
    usage = data.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    record = {
        "id": pid,
        "sample_index": sample_index,
        "prompt_file": str(path.relative_to(REPO_ROOT)),
        "model": cfg["model"],
        "provider": data.get("provider"),
        "generation_id": data.get("id"),
        "finish_reason": choice.get("finish_reason"),
        "native_finish_reason": choice.get("native_finish_reason"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "reasoning_tokens": details.get("reasoning_tokens"),
        "cost_usd": round(float(usage["cost"]), 6) if usage.get("cost") is not None else None,
        "reasoning_detail_types": kinds,
        "created_at": now_iso(),
    }
    if cfg.get("system_prompt"):
        record["system_prompt"] = messages[0]["content"]
    record["prompt"] = messages[-1]["content"]
    record["reasoning"] = clean_text(reasoning)
    record["answer"] = clean_text(answer)
    return record


def answer_one(client, cfg, pid, path, sample_index):
    """Ask the model to answer one prompt. Returns (record, None) on success
    and (None, reason) when the request keeps failing or is rejected."""
    messages = []
    if cfg.get("system_prompt"):
        messages.append({"role": "system", "content": cfg["system_prompt"]})
    messages.append({"role": "user", "content": path.read_text().strip()})
    request = build_request(cfg, messages)
    delay = 10
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.post("/v1/chat/completions", json=request)
        except httpx.HTTPError as e:
            problem = e.__class__.__name__
        else:
            if response.status_code in (401, 402, 403, 404):
                raise FatalRequestError(f"HTTP {response.status_code}: {response.text[:300]}")
            if response.status_code != 200 and response.status_code not in RETRY_STATUS:
                # The server rejected the request itself; it would reject it again.
                return None, f"HTTP {response.status_code}: {response.text[:300]}"
            if response.status_code != 200:
                problem = f"HTTP {response.status_code}"
            else:
                try:
                    data = response.json()
                    if not isinstance(data, dict):
                        raise ValueError("body is not a JSON object")
                except ValueError as e:
                    # a 200 with a truncated or non-JSON body (seen from SiliconFlow):
                    # retry like any other transient failure instead of crashing
                    data = None
                    problem = f"malformed body ({e.__class__.__name__})"
                choices = (data.get("choices") or [{}]) if data else [{}]
                error = (data.get("error") or (choices[0].get("error") if isinstance(choices[0], dict) else None)) if data else None
                if data is None:
                    pass
                elif error:
                    problem = f"provider error {error.get('code')}: {str(error.get('message'))[:200]}"
                elif not data.get("choices"):
                    problem = "no choices in response"
                else:
                    try:
                        record = make_record(cfg, pid, path, sample_index, messages, data)
                    except (KeyError, TypeError, IndexError, AttributeError) as e:
                        record = None
                        problem = f"unexpected response shape ({e!r})"
                    # A response is complete only if the model stopped by itself
                    # or hit the budget; some hosts return a cut-off generation
                    # with no finish reason and no answer at all.
                    if record is None:
                        pass
                    elif record["finish_reason"] not in ("stop", "length"):
                        problem = f"finish_reason={record['finish_reason']!r} from {record['provider']}"
                    elif not record["answer"] and record["finish_reason"] != "length":
                        problem = f"empty answer from {record['provider']}"
                    else:
                        return record, None
        if attempt == MAX_ATTEMPTS:
            return None, problem
        print(
            f"warning: {pid}: {problem}; retry {attempt}/{MAX_ATTEMPTS - 1} in {delay}s",
            file=sys.stderr,
            flush=True,
        )
        time.sleep(delay + random.uniform(0, delay / 2))
        delay = min(delay * 2, 240)


def openrouter_model(client, model):
    """OpenRouter's listing for the model (it names the open-weights repository
    under hugging_face_id). Exits if OpenRouter does not know the model, since
    every request would fail the same way."""
    try:
        entries = client.get("/v1/models").json().get("data", [])
    except (httpx.HTTPError, ValueError) as e:
        raise SystemExit(f"cannot list OpenRouter models: {e!r}")
    for entry in entries:
        if entry.get("id") == model:
            return entry
    raise SystemExit(f"OpenRouter has no model {model!r}; check the ID at https://openrouter.ai/models")


def repo_relative(path):
    path = Path(path).resolve()
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--prompt-set", metavar="FILE", help="prompt IDs to answer (tools/make_prompt_set.py)")
    parser.add_argument("--model", help="model name sent with each request, e.g. qwen/qwen3.5-397b-a17b")
    parser.add_argument("--base-url", help="OpenAI-compatible endpoint (default: https://openrouter.ai/api)")
    parser.add_argument("--api-key-file", metavar="FILE", help="send the key in FILE as a bearer token")
    parser.add_argument("--system-prompt-file", metavar="FILE", help="system prompt to send (default: none)")
    parser.add_argument(
        "--reasoning",
        choices=["default", "on", "off", "low", "medium", "high", "xhigh"],
        help="reasoning request: 'on' asks for the model's default chain of thought "
        "(default), 'off' disables it on hybrid models, an effort level sets it, "
        "'default' sends nothing",
    )
    parser.add_argument("--max-tokens", type=int, help="completion budget incl. reasoning (default: 32768)")
    sampling = parser.add_argument_group(
        "sampling", "sent only when given; use the model card's recommended values for thinking mode"
    )
    sampling.add_argument("--temperature", type=float)
    sampling.add_argument("--top-p", type=float)
    sampling.add_argument("--top-k", type=int)
    sampling.add_argument("--min-p", type=float)
    sampling.add_argument("--presence-penalty", type=float)
    sampling.add_argument("--repetition-penalty", type=float)
    parser.add_argument("--samples-per-prompt", type=int, help="responses per prompt (default: 1)")
    parser.add_argument(
        "--provider-order", metavar="LIST",
        help="OpenRouter: try these provider slugs first, comma-separated, e.g. alibaba,deepinfra",
    )
    parser.add_argument("--provider-ignore", metavar="LIST", help="OpenRouter: never use these provider slugs")
    parser.add_argument(
        "--quantizations", metavar="LIST",
        help="OpenRouter: only providers serving the model at one of these precisions, e.g. fp8,bf16",
    )
    parser.add_argument("--no-fallbacks", action="store_true", default=None, help="OpenRouter: only the providers in --provider-order")
    parser.add_argument("--out-dir", metavar="DIR", help="where run_NNN/ directories go (default: responses/)")
    parser.add_argument("--resume", metavar="RUN_DIR", help="continue an existing run; settings come from its run.yaml")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--limit", type=int, metavar="N", help="answer at most N prompts this invocation")
    parser.add_argument("--dry-run", action="store_true", help="print the first request instead of sending anything")
    args = parser.parse_args()

    if args.resume:
        run_dir = Path(args.resume)
        given = [name for name in RUN_SETTINGS if getattr(args, name) is not None]
        if given or args.out_dir:
            parser.error("--resume takes the run's settings from run.yaml; do not pass "
                         + ", ".join("--" + n.replace("_", "-") for n in given + (["out_dir"] if args.out_dir else [])))
        cfg = yaml.safe_load((run_dir / "run.yaml").read_text())
        set_path = REPO_ROOT / cfg["prompt_set"] if not Path(cfg["prompt_set"]).is_absolute() else Path(cfg["prompt_set"])
    else:
        if not args.prompt_set or not args.model:
            parser.error("--prompt-set and --model are required (or --resume RUN_DIR)")
        set_path = Path(args.prompt_set)
        base_url = args.base_url or "https://openrouter.ai/api"
        provider = {}
        if args.provider_order:
            provider["order"] = args.provider_order.split(",")
        if args.provider_ignore:
            provider["ignore"] = args.provider_ignore.split(",")
        if args.quantizations:
            provider["quantizations"] = args.quantizations.split(",")
        if args.no_fallbacks:
            provider["allow_fallbacks"] = False
        cfg = {
            "run": None,
            "created_at": now_iso(),
            "command": shlex.join([repo_relative(sys.argv[0]), *sys.argv[1:]]),
            "api": "openrouter" if "openrouter.ai" in base_url else "openai_compatible",
            "base_url": base_url,
            "model": args.model,
            "hugging_face_id": None,
            "prompt_set": repo_relative(set_path),
            "num_prompts": None,
            "samples_per_prompt": args.samples_per_prompt or 1,
            "system_prompt": Path(args.system_prompt_file).read_text() if args.system_prompt_file else None,
            "reasoning": reasoning_setting(args.reasoning or "on"),
            "max_tokens": args.max_tokens or 32768,
            "sampling": {key: getattr(args, key) for key in SAMPLING_KEYS if getattr(args, key) is not None},
            "provider": provider or None,
        }

    ids = read_prompt_set(set_path)
    if len(set(ids)) != len(ids):
        raise SystemExit(f"{set_path}: contains duplicate prompt IDs")
    index = prompt_index()
    missing = [pid for pid in ids if pid not in index]
    if missing:
        raise SystemExit(f"{set_path}: {len(missing)} prompts not found under prompts/, e.g. {missing[:5]}")
    cfg["num_prompts"] = len(ids)

    headers = {}
    if args.api_key_file:
        headers["Authorization"] = "Bearer " + Path(args.api_key_file).read_text().strip()
    client = httpx.Client(
        base_url=cfg["base_url"],
        headers=headers,
        timeout=httpx.Timeout(2400.0, connect=30.0),
        transport=httpx.HTTPTransport(retries=2, socket_options=KEEPALIVE_OPTIONS),
    )

    if args.dry_run:
        first = ids[0]
        messages = ([{"role": "system", "content": cfg["system_prompt"]}] if cfg.get("system_prompt") else [])
        messages.append({"role": "user", "content": index[first].read_text().strip()})
        print(yaml.safe_dump(build_request(cfg, messages), sort_keys=False, allow_unicode=True))
        return

    if args.resume:
        cfg.setdefault("resumed_at", []).append(now_iso())
    else:
        if cfg["api"] == "openrouter":
            cfg["hugging_face_id"] = openrouter_model(client, cfg["model"]).get("hugging_face_id") or None
        run_dir = create_run_dir(Path(args.out_dir) if args.out_dir else RESPONSES_DIR)
        cfg["run"] = run_dir.name
    (run_dir / "run.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))

    done = load_done(run_dir)
    items = [
        (pid, k)
        for pid in ids
        for k in range(cfg["samples_per_prompt"])
        if (pid, k) not in done
    ]
    if args.limit is not None:
        items = items[: args.limit]
    print(
        f"{cfg['model']}: {len(ids)} prompts x {cfg['samples_per_prompt']} sample(s); "
        f"{len(done)} already done, {len(items)} to do -> {repo_relative(run_dir)}",
        flush=True,
    )

    totals = {"n": 0, "failed": 0, "cost": 0.0, "completion_tokens": 0}
    finish = collections.Counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = {
            executor.submit(answer_one, client, cfg, pid, index[pid], k): (pid, k) for pid, k in items
        }
        try:
            for future in as_completed(futures):
                pid, k = futures[future]
                record, problem = future.result()
                if record is None:
                    totals["failed"] += 1
                    print(f"warning: {pid}: giving up ({problem})", file=sys.stderr, flush=True)
                    continue
                write_record(record_path(run_dir, pid, k, cfg["samples_per_prompt"]), record)
                totals["n"] += 1
                totals["cost"] += record["cost_usd"] or 0.0
                totals["completion_tokens"] += record["completion_tokens"] or 0
                finish[record["finish_reason"]] += 1
                cost = f" ${record['cost_usd']:.4f}" if record["cost_usd"] is not None else ""
                sample = f"#{k}" if cfg["samples_per_prompt"] > 1 else ""
                print(
                    f"[{totals['n'] + totals['failed']}/{len(items)}] {pid}{sample} "
                    f"{record['provider'] or ''} {record['completion_tokens'] or '?'} tok{cost} "
                    f"{record['finish_reason']}",
                    flush=True,
                )
        except FatalRequestError as e:
            executor.shutdown(wait=False, cancel_futures=True)
            raise SystemExit(f"fatal: {e}")
        except BaseException:
            executor.shutdown(wait=False, cancel_futures=True)
            raise
    mean_tokens = totals["completion_tokens"] / totals["n"] if totals["n"] else 0
    print(
        f"done: {totals['n']} responses written, {totals['failed']} failed; "
        f"finish reasons {dict(finish)}; mean {mean_tokens:,.0f} completion tokens; "
        f"cost ${totals['cost']:.2f}",
        flush=True,
    )


if __name__ == "__main__":
    main()
