# Synthetic Philosophy Prompts

A dataset of (currently) about 24,000 synthetic user prompts on philosophical and
conceptual topics — decision theory, formal epistemology, philosophy of science,
mind, and language, ethics, metaphysics, history of philosophy, AI alignment as a
conceptual topic, and more, with a smaller share of non-Western and historical
traditions. Each prompt is written as if by a real person (a grad student, a
retired physicist, a novelist, a committee member, ...) in one of forty-eight genres
(explanations, essay requests, grading tasks, dialogues, adjudications of
disagreements, committee memos, interview questions, speeches for occasions,
rankings, ...).

The prompts are deliberately "in the weeds": specific enough that a model cannot
answer by regurgitating a canned summary, while remaining answerable for a model
without web access. They are prompts only — no responses are included.

## Layout

```
prompts/batch_NNN/
  prompt_XXXXX.txt        the prompt text (IDs are globally unique across batches)
  prompt_XXXXX.meta.yaml  per-prompt metadata (see below)
  batch.yaml              batch-level settings (model, API, sampling parameters)
  inputs/                 snapshot of the meta-prompt components used for this batch
meta_prompt/              the meta-prompt: the prompt that asks a model to write a prompt
  assemble.py             samples the components and renders the template (also a CLI)
  prompt.j2               the meta-prompt template
  domains.txt             684 philosophical domains sampled from
  task_types.yaml         48 prompt genres, with examples and notes
  additional_instructions.yaml
                          extra instructions (length, persona, writing style) in
                          mutually exclusive groups, each drawn with a set probability
generators/
  generate_prompt.py        generator: Anthropic API, streaming
  generate_prompt_batch.py  generator: Anthropic Message Batches API
  generate_prompt_oai.py    generator: OpenAI-compatible endpoints (self-hosted models, OpenRouter)
```

Per-prompt metadata includes the generating model, the domains and task types
offered during sampling, the additional instructions drawn (persona, writing style,
length, and from batch 029 on further groups such as epistemic and output-format
requests; recorded as one `additional_instructions` mapping from batch 029 on and as
separate `length`/`persona`/`writing_style` keys before), token counts, the number
of web searches and page fetches the generator performed, a summary of the
generator's reasoning, and a timestamp.

## How the prompts were generated

For each prompt, the pipeline samples a handful of domains, three candidate
genres, and additional instructions (a persona, a writing style, and a length
instruction; from batch 029 on, `meta_prompt/additional_instructions.yaml` defines
the groups, which also include epistemic requests, output-format requests, and
prompt-engineering phrasing, each drawn with its own probability), renders them into the meta-prompt (`meta_prompt/prompt.j2`), and asks
a model to write one prompt. The generating models had web search and page
fetching available for fact-checking and verbatim quotation.

| Batches | Model | Notes |
|---|---|---|
| 000–009, 013–017, 030 | claude-sonnet-5 | Anthropic API, streaming |
| 010–012 | claude-haiku-4-5 | Anthropic API, streaming |
| 018–021 | claude-sonnet-5 | Anthropic Message Batches API |
| 022–029 | Qwen 3.8 27B | self-hosted llama.cpp; client-executed web tools (DuckDuckGo search + page fetch) |
| 032 | DeepSeek V4 Pro | OpenRouter, fp8 providers only; client-executed web tools (DuckDuckGo search + page fetch) |

The exact model for every prompt is recorded in its `.meta.yaml`. From batch 026
on, the runs through the OpenAI-compatible generator (self-hosted Qwen, then
DeepSeek via OpenRouter) enforce a strict sourcing rule: the generator may not
quote real texts from memory — verbatim quotations must be copied from a fetched
page, and load-bearing titles, dates, and attributions must be verified by search.

## Quality control and known limitations

- Every recent batch was swept for meta-commentary leaking into the prompt text
  (generator narration like "Here is the prompt:"); prompts found leaking were
  trimmed or deleted.
- For several batches (011, 023, 026, 027, 028), all quotations of real texts were
  verified word-for-word against primary sources, and factual attributions were
  spot-checked; defective prompts were emended or deleted. Deletions are why ID
  numbering has occasional gaps.
- Batches without full quote verification should be expected to contain a small
  residual rate of misquotation or misattribution (verification of comparable
  batches suggests on the order of 1–3% of prompts before fixes).
- Some prompts contain errors *by design*: several genres present a student
  answer to grade or a disagreement to adjudicate, and the quoted "student" or
  "discussant" content may include deliberate mistakes for the model to catch.
  Typos and informal spelling are intentional persona features, not corruption.
- Batch 016 was accidentally generated twice from one set of sampled parameters,
  so it contains pairs of prompts generated from identical sampling draws (the
  prompt texts differ).

## Authorship

This repository was built largely by AI: the generation scripts, the meta-prompt
template, and this README were written by Claude (Anthropic's Claude Code) under
the author's direction, and parts of the input lists — domains, task-type
definitions and their example prompts — are model-written as well, with the
author contributing, reviewing, and deciding throughout. Dataset curation (leak
sweeps, quote verification against primary sources, and the resulting fixes) was
also performed by Claude models; where a prompt was emended after verification,
the corrected wording is written by the curating model rather than the
generating model named in its sidecar. The prompts themselves are model outputs
by design (see the table above).

## Licensing and provenance

- **Code** (generation scripts, template, input lists): MIT — see `LICENSE`.
- **Data** (everything under `prompts/`): Creative Commons Attribution 4.0
  (CC BY 4.0) — see `LICENSE-DATA`.

**Provenance notice.** Most prompts (batches 000–021 and 030) are outputs of Anthropic
Claude models. If you use them, you are responsible for complying with
[Anthropic's terms and usage policies](https://www.anthropic.com/legal) as they
apply to Claude outputs — in particular, restrictions on using outputs to train
models that compete with Anthropic. Batches 022–029 were generated with Qwen
3.8 27B, an open-weights model released under Apache 2.0, and batch 032 with
DeepSeek V4 Pro, an open-weights model released under the MIT license, via
OpenRouter.

## Reproducing or extending

```
pip install -r requirements.txt
python meta_prompt/assemble.py        # print one sampled meta-prompt (no API needed)
export ANTHROPIC_API_KEY=...          # for the Anthropic generators
python generators/generate_prompt.py -n 10
python generators/generate_prompt_batch.py -n 1000
python generators/generate_prompt_oai.py -n 10 --web-tools --base-url http://127.0.0.1:8088
python generators/generate_prompt_oai.py -n 10 --web-tools --base-url https://openrouter.ai/api \
    --model deepseek/deepseek-v4-pro --api-key-file api_keys/openrouter.txt \
    --reasoning-effort high --quantizations fp8,bf16,fp16
```

The OpenAI-compatible generator expects a llama.cpp `llama-server` (launched with
`--jinja` so tool calls are parsed) or any other OpenAI-compatible endpoint; with
`--api-key-file` it works against hosted gateways such as OpenRouter, where
`--quantizations` restricts routing to providers serving the model at the listed
precisions.
`meta_prompt/additional_instructions.yaml` controls which extra instructions are
drawn and how often. Each batch directory snapshots the exact inputs used, so past
batches remain reproducible even as the input lists evolve.
