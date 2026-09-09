#!/usr/bin/env python3
"""Generate synthetic philosophy prompts via an OpenAI-compatible endpoint.

For self-hosted models, e.g. llama.cpp's llama-server, and for hosted
gateways such as OpenRouter. Same sampling, inputs, and outputs as
generate_prompt.py. Reasoning that arrives inline as <think>...</think>
(llama-server with --reasoning-format none) or in a reasoning_content or
reasoning field goes into the sidecar and is stripped from the saved prompt.

With --web-tools, the model gets web_search (DuckDuckGo via ddgs) and
web_fetch (httpx + trafilatura) as client-executed function calls, looped
until the model stops calling tools -- a poor man's version of the server
tools the Anthropic runs get. llama-server must be launched with --jinja so
tool calls are parsed. Only the final assistant message becomes the prompt,
so mid-loop narration is dropped for free.

Usage:
    .venv/bin/python generators/generate_prompt_oai.py -n 50 --web-tools \
        --base-url http://127.0.0.1:8088 --model qwen3.8-27b

    # OpenRouter: bearer key from a file, an explicit reasoning effort, and
    # (since OpenRouter reports it) each prompt's cost in its sidecar
    .venv/bin/python generators/generate_prompt_oai.py -n 1000 --web-tools \
        --base-url https://openrouter.ai/api --model deepseek/deepseek-v4-pro \
        --api-key-file api_keys/openrouter.txt --reasoning-effort high \
        --quantizations fp8,bf16,fp16 --provider-order streamlake,baidu \
        --provider-ignore z-ai --concurrency 32
"""

import argparse
import json
import re
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import httpx
import trafilatura
import yaml
from ddgs import DDGS

# The meta-prompt components live in meta_prompt/ at the repo root; put the
# root on sys.path so they import when this file runs as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from meta_prompt import assemble  # noqa: E402
from generate_prompt import REPO_ROOT, create_batch_dir, next_output_path  # noqa: E402

THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)

# Tool-call syntax that some models emit as plain text when they want a tool
# they are not allowed to call, or leak into the answer (GLM's
# <tool_call>name<arg_key>k</arg_key><arg_value>v</arg_value></tool_call>);
# such a response is not a prompt.
TOOL_MARKUP_RE = re.compile(
    r"<｜DSML｜|<\|DSML\||</?tool_call|</?arg_key|</?arg_value|</invoke>"
    r"|<function_calls?>|<\|im_start\|"
)
MIN_PROMPT_WORDS = 40  # the batch checker flags shorter prompts; real ones are rarer than fragments

# A model sometimes prefaces the prompt with a note on its own procedure; see
# process_note(). Kept in sync with tools/check_batch.py.
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


# A prompt that role-plays the dataset builder ("I'm building a dataset of
# prompts and I need one on ...") is the meta-task leaking through.
DATASET_FRAMING_RE = re.compile(
    r"dataset of (philosoph[a-z]* )?prompts|prompt for (the|this|your) dataset"
    r"|prompts? (on|about) philosophical (topics|issues)|building a dataset of"
    r"|constructing a dataset",
    re.I,
)

MAX_TOOL_ROUNDS = 8
MAX_ATTEMPTS = 4

# TCP keepalive so that a connection killed while the machine sleeps fails
# within a few minutes of waking instead of hanging until the read timeout.
KEEPALIVE_OPTIONS = [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)]
for _name, _value in (("TCP_KEEPALIVE", 60), ("TCP_KEEPIDLE", 60), ("TCP_KEEPINTVL", 20), ("TCP_KEEPCNT", 6)):
    if hasattr(socket, _name):
        KEEPALIVE_OPTIONS.append((socket.IPPROTO_TCP, getattr(socket, _name), _value))
FETCH_CHAR_LIMIT = 6000

WEB_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web. Returns titles, URLs, and snippets "
            "of the top results. Use only when the prompt genuinely requires "
            "real source material you are not certain of. Snippets are not "
            "reliable for verbatim quotation -- to quote a passage exactly, "
            "follow up with web_fetch on a result.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch a web page by URL and return its main text "
            "content (truncated). Use for reading a specific page, e.g. to "
            "quote a passage verbatim.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
]

# DuckDuckGo dislikes bursts; serialize searches across worker threads.
search_lock = threading.Lock()


def run_web_search(query):
    with search_lock:
        results = DDGS().text(query, max_results=5)
        time.sleep(1.5)
    if not results:
        return "No results."
    return "\n\n".join(
        f"[{i + 1}] {r.get('title', '')}\n{r.get('href', '')}\n{r.get('body', '')}"
        for i, r in enumerate(results)
    )


def run_web_fetch(url):
    response = httpx.get(
        url, timeout=20.0, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (research script)"},
    )
    response.raise_for_status()
    text = trafilatura.extract(response.text) or ""
    if not text:
        return "Could not extract text content from that page."
    if len(text) > FETCH_CHAR_LIMIT:
        text = text[:FETCH_CHAR_LIMIT] + "\n[truncated]"
    return text


def run_tool(name, arguments):
    try:
        args = json.loads(arguments or "{}")
        if name == "web_search":
            return run_web_search(args["query"])
        if name == "web_fetch":
            return run_web_fetch(args["url"])
        return f"Unknown tool: {name}"
    except Exception as e:
        return f"Tool error: {e!r}"


def generation_defect(result):
    """Why a finished conversation cannot be saved as a prompt, or None.

    Some hosts return generations cut off without a finish reason; a model
    may also truncate at the token budget, answer with nothing, or leak
    tool-call markup. All of these are sampling failures worth retrying."""
    if result is None:
        return f"still calling tools after {MAX_TOOL_ROUNDS} rounds"
    hosts = ",".join(sorted(result["providers"])) or "server"
    where = f"from {hosts}, ${result['cost']:.3f} spent"
    finish = result["choice"].get("finish_reason")
    if finish != "stop":
        return f"finish_reason={finish!r} ({where})"
    prompt_text = THINK_RE.sub("", result["content"]).strip()
    if "<think>" in prompt_text or not prompt_text:
        return f"empty or truncated-thinking response ({where})"
    if TOOL_MARKUP_RE.search(prompt_text):
        return f"tool-call markup in the response ({where})"
    if len(prompt_text.split()) < MIN_PROMPT_WORDS:
        return f"implausibly short response ({where})"
    if process_note(prompt_text):
        return f"process note before the prompt ({where})"
    if DATASET_FRAMING_RE.search(prompt_text):
        return f"dataset-construction framing in the prompt ({where})"
    return None


def served_model_name(client, requested):
    """Name of the loaded model as the server reports it; also verifies
    connectivity. A gateway lists many models, in which case the requested
    one is returned if it is among them."""
    data = client.get("/v1/models").json()
    for key, name_key in (("data", "id"), ("models", "name")):
        if data.get(key):
            names = [m.get(name_key) for m in data[key]]
            return requested if requested in names else names[0]
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-n", "--num-prompts", type=int, default=1)
    parser.add_argument("--num-domains", type=int, default=5)
    parser.add_argument("--num-task-types", type=int, default=3)
    parser.add_argument("--base-url", default="http://127.0.0.1:8088")
    parser.add_argument(
        "--model",
        default="qwen3.8-27b",
        help="model name sent with each request and recorded in the sidecars "
        "(llama-server ignores it; gateways route on it)",
    )
    parser.add_argument(
        "--api-key-file",
        metavar="FILE",
        help="send the key in FILE as a bearer token (hosted services such as OpenRouter)",
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=["low", "medium", "high", "xhigh"],
        help="request this much reasoning via the reasoning.effort field "
        "(OpenRouter and compatible servers); default: the model's own default",
    )
    parser.add_argument(
        "--quantizations",
        metavar="LIST",
        help="OpenRouter only: route only to providers serving the model at one "
        "of these quantizations, comma-separated, e.g. fp8,bf16,fp16 (default: "
        "any, including 4-bit and undisclosed)",
    )
    parser.add_argument(
        "--provider-order",
        metavar="LIST",
        help="OpenRouter only: try these providers first, comma-separated "
        "slugs from OpenRouter's endpoint list, e.g. gmicloud,streamlake; "
        "others remain as fallbacks",
    )
    parser.add_argument(
        "--provider-ignore",
        metavar="LIST",
        help="OpenRouter only: never route to these providers, comma-separated "
        "slugs, e.g. z-ai (whose own API terms restrict the use of outputs)",
    )
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=24576)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument(
        "--top-k",
        type=int,
        help="top-k sampling, sent only when given (some model cards ask for 20)",
    )
    parser.add_argument(
        "--web-tools",
        action="store_true",
        help="give the model client-executed web search/fetch tools",
    )
    parser.add_argument(
        "--continue-batch",
        metavar="DIR",
        help="append -n more prompts to this existing batch instead of starting a "
        "new one, rendering from the batch's own inputs/ snapshot (for a run that "
        "was killed, e.g. after the machine slept); other settings should match",
    )
    parser.add_argument(
        "--first-id",
        type=int,
        default=1,
        metavar="N",
        help="never number a prompt below N, to stay clear of a batch being "
        "generated concurrently on another machine (default: 1, no effect)",
    )
    args = parser.parse_args()
    quantizations = args.quantizations.split(",") if args.quantizations else None
    # OpenRouter routing preferences, sent as the request's provider object.
    provider = {}
    if quantizations:
        provider["quantizations"] = quantizations
    if args.provider_order:
        provider["order"] = args.provider_order.split(",")
    if args.provider_ignore:
        provider["ignore"] = args.provider_ignore.split(",")
    # OpenRouter reports the cost and the serving provider of each request.
    openrouter = "openrouter.ai" in args.base_url

    continuing = Path(args.continue_batch).resolve() if args.continue_batch else None
    components = assemble.load(continuing / "inputs") if continuing else assemble.load()
    headers = {}
    if args.api_key_file:
        headers["Authorization"] = "Bearer " + Path(args.api_key_file).read_text().strip()
    client = httpx.Client(
        base_url=args.base_url,
        headers=headers,
        timeout=httpx.Timeout(3600.0, connect=30.0),
        transport=httpx.HTTPTransport(retries=2, socket_options=KEEPALIVE_OPTIONS),
    )
    served = served_model_name(client, args.model)  # fails fast if the server is down

    if continuing:
        batch_dir = continuing
        config = yaml.safe_load((batch_dir / "batch.yaml").read_text())
        config.setdefault("continued", []).append(
            {
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "num_prompts": args.num_prompts,
                "concurrency": args.concurrency,
            }
        )
        (batch_dir / "batch.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
        print(f"continuing {batch_dir.relative_to(REPO_ROOT)} with {args.num_prompts} more prompts", flush=True)
    else:
        batch_dir = create_batch_dir()
        components.snapshot(batch_dir / "inputs")
    config = config if continuing else {
        "batch": batch_dir.name,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "api": "openai_compatible",
        "base_url": args.base_url,
        "model": args.model,
        "served_model": served,
        "reasoning_effort": args.reasoning_effort,
        "quantizations": quantizations,
        "temperature": args.temperature,
        "top_p": 0.95,
        "top_k": args.top_k,
        "max_tokens": args.max_tokens,
        "web_tools": args.web_tools,
        "num_prompts": args.num_prompts,
        "concurrency": args.concurrency,
        "num_domains": args.num_domains,
        "num_task_types": args.num_task_types,
    }
    if provider.get("order"):
        config["provider_order"] = provider["order"]
    if provider.get("ignore"):
        config["provider_ignore"] = provider["ignore"]
    if args.first_id > 1:
        config["first_id"] = args.first_id
    (batch_dir / "batch.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    print(f"writing batch to {batch_dir.relative_to(REPO_ROOT)}", flush=True)

    path_lock = threading.Lock()

    def generate_one(sample):
        meta_prompt = components.render(
            sample, web_tools=args.web_tools, strict_quotes=args.web_tools
        )

        def attempt_turns():
            """Run one full tool-round conversation. Returns a dict with the
            final choice and content plus the run's counters, or None if the
            model still returned tool calls on the last round, when it is told
            not to use tools."""
            messages = [{"role": "user", "content": meta_prompt}]
            stats = {
                "searches": 0,
                "fetches": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0,
                "providers": set(),
                "generation_ids": [],
                "reasoning_parts": [],
            }
            for round_no in range(MAX_TOOL_ROUNDS):
                request = {
                    "model": args.model,
                    "messages": messages,
                    "max_tokens": args.max_tokens,
                    "temperature": args.temperature,
                    "top_p": 0.95,
                }
                if args.top_k is not None:
                    request["top_k"] = args.top_k
                if args.web_tools:
                    request["tools"] = WEB_TOOL_SCHEMAS
                    if round_no == MAX_TOOL_ROUNDS - 1:
                        # Last round: tell the model to stop searching and
                        # forbid further tool calls, so one that keeps searching
                        # writes the prompt instead of being dropped.
                        messages.append(
                            {
                                "role": "user",
                                "content": "You have used up the tool budget. Do "
                                "not call any more tools; write the prompt now "
                                "from what you already know, following all the "
                                "instructions above.",
                            }
                        )
                        request["tool_choice"] = "none"
                if args.reasoning_effort:
                    request["reasoning"] = {"effort": args.reasoning_effort}
                if openrouter:
                    request["usage"] = {"include": True}
                if provider:
                    request["provider"] = provider
                response = client.post("/v1/chat/completions", json=request)
                response.raise_for_status()
                data = response.json()
                choice = data["choices"][0]
                message = choice["message"]
                usage = data.get("usage") or {}
                stats["input_tokens"] += usage.get("prompt_tokens", 0)
                stats["output_tokens"] += usage.get("completion_tokens", 0)
                stats["cost"] += float(usage.get("cost") or 0)
                if data.get("provider"):
                    stats["providers"].add(data["provider"])
                if openrouter and data.get("id"):
                    stats["generation_ids"].append(data["id"])
                content = message.get("content") or ""
                stats["reasoning_parts"] += THINK_RE.findall(content)
                for key in ("reasoning_content", "reasoning"):
                    if message.get(key):
                        stats["reasoning_parts"].append(message[key])
                tool_calls = message.get("tool_calls") or []
                if not tool_calls:
                    return {"choice": choice, "content": content, **stats}
                # Echo the assistant turn (thinking stripped) plus results.
                # Gateways that return reasoning_details expect them echoed
                # back so the model keeps its train of thought across rounds.
                assistant = {
                    "role": "assistant",
                    "content": THINK_RE.sub("", content).strip() or None,
                    "tool_calls": tool_calls,
                }
                if message.get("reasoning_details"):
                    assistant["reasoning_details"] = message["reasoning_details"]
                messages.append(assistant)
                for tool_call in tool_calls:
                    function = tool_call.get("function") or {}
                    name = function.get("name", "")
                    if name == "web_search":
                        stats["searches"] += 1
                    elif name == "web_fetch":
                        stats["fetches"] += 1
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.get("id"),
                            "content": run_tool(name, function.get("arguments")),
                        }
                    )
            return None

        # A failed request (server restart, network blip; a minute's pause
        # before the next try) or a defective generation (see
        # generation_defect) is retried, the whole conversation restarting
        # from scratch; after MAX_ATTEMPTS the prompt is skipped.
        problem = None
        for attempt in range(MAX_ATTEMPTS):
            if problem:
                print(
                    f"warning: {problem}; retry {attempt}/{MAX_ATTEMPTS - 1}",
                    file=sys.stderr,
                    flush=True,
                )
            try:
                result = attempt_turns()
            except httpx.HTTPError as e:
                problem = f"request failed ({e.__class__.__name__})"
                time.sleep(60)
                continue
            except (KeyError, IndexError, TypeError, ValueError) as e:
                # a 200 response without the expected shape, e.g. a gateway
                # error object in place of choices
                problem = f"malformed response ({e!r})"
                time.sleep(10)
                continue
            except Exception as e:
                print(
                    f"warning: unexpected error, skipping this prompt: {e!r}",
                    file=sys.stderr,
                    flush=True,
                )
                return
            problem = generation_defect(result)
            if problem is None:
                break
        else:
            print(
                f"warning: {problem}; giving up on this prompt",
                file=sys.stderr,
                flush=True,
            )
            return
        prompt_text = THINK_RE.sub("", result["content"]).strip()
        reasoning_summary = "\n\n".join(
            p.strip() for p in result["reasoning_parts"] if p.strip()
        )

        # Writing the .txt reserves the number, so both happen under the lock.
        with path_lock:
            out_path = next_output_path(batch_dir, args.first_id)
            out_path.write_text(prompt_text + "\n")
        metadata = {
            "prompt_file": out_path.name,
            "model": args.model,
            "effort": args.reasoning_effort,
            "web_searches": result["searches"],
            "web_fetches": result["fetches"],
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
        }
        if openrouter:
            metadata["cost_usd"] = round(result["cost"], 6)
            metadata["providers"] = sorted(result["providers"])
            # one per round, for auditing costs against OpenRouter's records
            metadata["generation_ids"] = result["generation_ids"]
        metadata.update(sample)
        metadata["reasoning_summary"] = reasoning_summary or None
        metadata["generated_at"] = datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        )
        out_path.with_suffix(".meta.yaml").write_text(
            yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True)
        )
        offered = " / ".join(sample["task_types_offered"])
        extras = ", ".join(sample["additional_instructions"]) or "none"
        cost = f" ${result['cost']:.3f}" if openrouter else ""
        print(
            f"[{offered} | {extras}]{cost} -> {out_path.relative_to(REPO_ROOT)}",
            flush=True,
        )

    samples = [
        components.sample(args.num_domains, args.num_task_types)
        for _ in range(args.num_prompts)
    ]
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(generate_one, sample) for sample in samples]
        try:
            for future in as_completed(futures):
                future.result()
        except BaseException:
            executor.shutdown(wait=False, cancel_futures=True)
            raise


if __name__ == "__main__":
    main()
