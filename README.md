# Synthetic Philosophy Prompts

A dataset of (currently) about 160,000 synthetic user prompts on philosophical and
conceptual topics — decision theory, formal epistemology, philosophy of science,
mind, and language, ethics, metaphysics, history of philosophy, AI alignment as a
conceptual topic, and more, with a smaller share of non-Western and historical
traditions. Each prompt is written as if by a real person (a grad student, a
retired physicist, a novelist, a committee member, ...) in one of forty-nine genres
(explanations, essay requests, grading tasks, dialogues, adjudications of
disagreements, committee memos, interview questions, speeches for occasions,
rankings, ...).

The prompts are deliberately "in the weeds": specific enough that a model cannot
answer by regurgitating a canned summary, while remaining answerable for a model
without web access. Alongside the prompts, `responses/` collects responses to
subsets of them from open-weight models, each with the model's full chain of
thought (see [Responses](#responses)), and `preferences/` collects pairwise judgments
of such responses by a strong model (see [Preference pairs](#preference-pairs)).

## Layout

```
prompts/batch_NNN/
  prompt_XXXXX.txt        the prompt text (IDs are globally unique across batches;
                          five digits up to 99999, six from 100000 on)
  prompt_XXXXX.meta.yaml  per-prompt metadata (see below)
  batch.yaml              batch-level settings (model, API, sampling parameters)
  inputs/                 snapshot of the meta-prompt components used for this batch
responses/
  sets/NAME.txt           a prompt set: the IDs of the prompts a response run answers
  run_NNN/                a response run (run_NNN_imported/ if converted from the sister repo, see below)
    run.yaml              run-level settings (model, sampling parameters, provider preferences, prompt set)
    prompt_XXXXX.yaml     one file per response: the prompt as sent, chain of thought, answer, usage
preferences/
  judge_prompt.j2         the judge prompt: which of two responses to the same prompt is better, five options
  pairs/NAME.yaml         a pair set: which two responses are compared for which prompts, in which A/B order
  run_NNN/                a preference run: one judge over one pair set
    run.yaml              judge model, effort, pair set, prices used for the cost field
    judge_prompt.j2       the template as it was when the run started
    prompt_XXXXX.yaml     one file per pair: verdict, the judge's visible reasoning and summarized thinking, usage
meta_prompt/              the meta-prompt: the prompt that asks a model to write a prompt
  assemble.py             samples the components and renders the template (also a CLI)
  prompt.j2               the meta-prompt template
  domains.txt             753 philosophical domains sampled from
  task_types.yaml         49 prompt genres, with examples and notes
  additional_instructions.yaml
                          extra instructions (length, persona, writing style) in
                          mutually exclusive groups, each drawn with a set probability
generators/
  generate_prompt.py        generator: Anthropic API, streaming
  generate_prompt_batch.py  generator: Anthropic Message Batches API
  generate_prompt_oai.py    generator: OpenAI-compatible endpoints (self-hosted models, OpenRouter)
  generate_responses.py     model responses to a prompt set (OpenAI-compatible endpoints, OpenRouter)
  judge_pairs.py            preference judgments over a pair set (Anthropic API, streamed or as Message Batches)
tools/
  check_batch.py            quality report for a batch: leaks, example echo, near-duplicates, cost
  make_prompt_set.py        writes a prompt set: filter by batch or generating model, seeded sample
  check_run.py              quality report for a response run: coverage, truncation, missing reasoning, cost
  import_teacher_data.py    converts the cr_training sister repo's teacher-data collections into imported runs
  make_pair_set.py          writes a pair set: complete response pairs from one run (two samples) or two runs, seeded sample
  check_preferences.py      report for a preference run: coverage, verdicts, position balance, cost; agreement of two runs
QUALITY_NOTES.md          known quality issues and per-batch measurements
```

Per-prompt metadata includes the generating model, the domains and task types
offered during sampling (from batch 046 on, and for the second half of batch 044, also
which of each type's examples were shown, in which order, under `task_type_examples`),
the additional instructions drawn (persona, writing style,
length, and from batch 029 on further groups such as epistemic and output-format
requests; recorded as one `additional_instructions` mapping from batch 029 on and as
separate `length`/`persona`/`writing_style` keys before), token counts, the number
of web searches and page fetches the generator performed, a summary of the
generator's reasoning, and a timestamp.

## How the prompts were generated

For each prompt, the pipeline samples a handful of domains, three candidate
genres, and additional instructions (a persona, a writing style, and a length
instruction; from batch 029 on, `meta_prompt/additional_instructions.yaml` defines
the groups, which also include epistemic requests, output-format requests,
prompt-engineering phrasing, and, in batches generated from 2026-09-19 on, an
occasional request to build the prompt around a verbatim passage from a primary
source, each drawn with its own probability), renders them into the meta-prompt (`meta_prompt/prompt.j2`), and asks
a model to write one prompt. Each offered genre comes with example prompts of that
genre; from batch 046 on, only a random subset of them is shown (a number from one to
five is drawn, that many examples are sampled without replacement, and they appear in
random order), so that no single example shapes every prompt of a genre. Earlier
batches showed every example in file order, except that the 10,617 prompts of batch
044 generated after its pause already used the subsets (their sidecars carry
`task_type_examples`). The generating models had web search and page
fetching available for fact-checking and verbatim quotation.

| Batches | Model | Notes |
|---|---|---|
| 000–009, 013–017, 030 | claude-sonnet-5 | Anthropic API, streaming |
| 010–012 | claude-haiku-4-5 | Anthropic API, streaming |
| 018–021 | claude-sonnet-5 | Anthropic Message Batches API |
| 022–029, 031, 040 | Qwen 3.8 27B | self-hosted llama.cpp (batch 040 stopped by hand after 442 prompts); client-executed web tools (DuckDuckGo search + page fetch) |
| 032–033 | DeepSeek V4 Pro | OpenRouter, fp8 providers only; client-executed web tools (DuckDuckGo search + page fetch) |
| 034–035 | GLM-5.3 | OpenRouter, fp8 providers only, Z.ai's own endpoint excluded; client-executed web tools (DuckDuckGo search + page fetch) |
| 036, 038 | Qwen3.8 2.4T-A95B | OpenRouter, fp8 provider only (SiliconFlow); client-executed web tools (DuckDuckGo search + page fetch) |
| 037 | Muse Spark 1.3 (Meta, proprietary) | OpenRouter, Meta's own endpoint, standard tier; client-executed web tools offered but almost never used |
| 039 | DeepSeek V4.1 Flash | OpenRouter, fp8 provider (Novita), Io Net and GMICloud excluded; stopped by hand after 488 prompts; client-executed web tools (DuckDuckGo search + page fetch) |
| 041 | DeepSeek V4.1 Flash | OpenRouter, fp8 hosts load-balanced (Novita, Morph, Venice, Parasail, DeepInfra), Io Net and GMICloud excluded; client-executed web tools (DuckDuckGo search + page fetch) |
| 042 | Thinking Machines Inkling | OpenRouter, fp8 provider (BaseTen; DeepInfra excluded because its tool-call grammar rejects the web tools); 1,000-prompt test batch; client-executed web tools (DuckDuckGo search + page fetch) |
| 043 | Tencent HY4 preview | OpenRouter, fp8 provider (Tencent); 1,000-prompt test batch, temperature 0.9 and top-p 1.0 as the model card recommends; client-executed web tools (DuckDuckGo search + page fetch) |
| 044 | Thinking Machines Inkling | OpenRouter, fp8 provider (BaseTen; DeepInfra excluded); 20,000 prompts; paused for six hours during a BaseTen outage and continued from the batch's own snapshot; client-executed web tools (DuckDuckGo search + page fetch) |
| 045 | Tencent HY4 preview | OpenRouter, fp8 provider (Tencent); 20,000 prompts, temperature 0.9 and top-p 1.0 as the model card recommends; client-executed web tools (DuckDuckGo search + page fetch) |

The exact model for every prompt is recorded in its `.meta.yaml`. From batch 026
on, the runs through the OpenAI-compatible generator (self-hosted Qwen, then
DeepSeek and GLM via OpenRouter) enforce a strict sourcing rule: the generator may not
quote real texts from memory — verbatim quotations must be copied from a fetched
page, and load-bearing titles, dates, and attributions must be verified by search.

## Responses

`responses/` holds model responses to subsets of the prompts, for experiments that
need answers rather than questions: distilling a strong open model's reasoning into
a small one, testing whether a weak judge can tell a weak model's answer from a
strong model's, and the like. Two rules decide which models are used: the weights
are open under a license that permits training on the model's outputs (Apache 2.0,
MIT), and the API returns the model's complete chain of thought rather than a
summary. That rules out the Claude models most of the prompts were written with.

A *run* answers one prompt set with one model under one sampling configuration.
`tools/make_prompt_set.py` writes a prompt set (all prompts, some batches, or the
prompts written by a given generating model, optionally a seeded random sample);
`generators/generate_responses.py` sends every prompt as a single user message,
with no system prompt and no tools, and writes one YAML file per response
(`prompt_XXXXX.yaml`, or `prompt_XXXXX.K.yaml` when a run takes several samples
per prompt). Reasoning is requested with the model's default budget
(`reasoning: {enabled: true}` on OpenRouter) unless `run.yaml` says otherwise;
sampling parameters follow the model card's recommendation for thinking mode and
are recorded in `run.yaml`; the completion budget is 32,768 tokens unless
`run.yaml` says otherwise. On OpenRouter, routing is restricted to endpoints that
declare 8-bit or higher precision (fp8, int8, bf16, fp16), which excludes
endpoints of undisclosed precision; the endpoint that served each response is in
its `provider` field. Responses
that hit that budget are kept with `finish_reason: length` so that consumers can
decide for themselves. Nothing else is filtered or edited, except that a chain of
thought a server returns inline as `<think>...</think>` is moved out of the answer,
and line endings are normalized. `tools/check_run.py` reports coverage,
truncation, missing reasoning, refusals, lengths, cost, and provider mix for a
run; findings go to `QUALITY_NOTES.md`.

Each response file has:

| Field | Meaning |
|---|---|
| `id`, `sample_index`, `prompt_file` | prompt ID as in `prompts/`; sample index for runs with several responses per prompt; path of the prompt |
| `model`, `provider`, `generation_id` | model as requested; the OpenRouter provider that served it; OpenRouter's generation ID |
| `finish_reason`, `native_finish_reason` | `stop` or `length`, as normalized by OpenRouter and as reported by the provider |
| `prompt_tokens`, `completion_tokens`, `reasoning_tokens`, `cost_usd` | usage as reported by the API; completion tokens include the reasoning |
| `reasoning_detail_types` | OpenRouter's classification of the reasoning: `reasoning.text` is the full text, `reasoning.summary` would be a summary |
| `created_at` | when the response was generated (for imported runs: when the record was converted) |
| `imported_from`, `source_id` | only in `run_NNN_imported/` runs: the sister-repo collection the record came from and its ID there |
| `prompt` | exactly what was sent, as the single user message (a `system_prompt` field appears only if a run used one) |
| `reasoning`, `answer` | the chain of thought as returned, and the visible answer |

Runs so far:

| Run | Model | Prompt set | Responses | Sampling (from the model card) | Notes |
|---|---|---|---|---|---|
| run_000 | Qwen3.5-397B-A17B (Apache 2.0) | `open_1k` | 1,000 | temperature 0.6, top-p 0.95, top-k 20 | fp8 endpoints: DeepInfra, AtlasCloud, GMICloud; one response truncated at the budget |
| run_001 | Qwen3.5-122B-A10B (Apache 2.0) | `open_1k` | 1,000 | temperature 1.0, top-p 0.95, top-k 20, presence penalty 1.5 | fp8 endpoints: SiliconFlow, AtlasCloud |
| run_002 | DeepSeek V4 Pro 0813 (MIT) | `open_1k_sub100` | 100 | temperature 1.0, top-p 1.0; reasoning effort high; 65,536-token budget | fp8 endpoints: Baidu, GMICloud |
| run_003 | DeepSeek R1 0528 (MIT) | `open_1k` | 1,000 | temperature 0.6, top-p 0.95; 65,536-token budget | fp8 endpoint: SiliconFlow; one of the two R1 checkpoints whose reasoning traces trained Olmo 3 Think |
| run_004_imported | Qwen3.5-397B-A17B-FP8 (Apache 2.0) | `batches_000-021` | 44,734 (2 per prompt) | temperature 0.6, top-p 0.95; 16,384-token budget | **imported**, not generated here: the sister repo's teacher collections of 2026-08-22 and 2026-08-28, self-hosted vLLM on Modal with the official fp8 weights |
| run_005_imported | DeepSeek R1 0528 (MIT) | `batches_000-021` | 44,734 (2 per prompt) | temperature 0.6, top-p 0.95; 16,384-token budget | **imported**: the sister repo's collection of 2026-08-29, self-hosted vLLM on Modal, fp8 weights |
| run_006 | DeepSeek R1 0528 (MIT) | `batch_033` | 9,930 | temperature 0.6, top-p 0.95; 65,536-token budget | fp8 endpoint: SiliconFlow |
| run_007 | Qwen3.5-397B-A17B (Apache 2.0) | `batch_033` | 9,930 | temperature 0.6, top-p 0.95, top-k 20 | fp8 endpoints load-balanced: DeepInfra, AtlasCloud, Parasail, GMICloud; 5 responses truncated at the budget |
| run_008 | Qwen3.5-397B-A17B (Apache 2.0) | `batch_035` | 19,998 | temperature 0.6, top-p 0.95, top-k 20 | same endpoints; 10 truncated |
| run_009 | DeepSeek R1 0528 (MIT) | `batch_035` | 19,998 | temperature 0.6, top-p 0.95; 65,536-token budget | fp8 endpoint: SiliconFlow |
| run_010 | DeepSeek R1 0528 (MIT) | `batch_038` | 19,997 | temperature 0.6, top-p 0.95; 65,536-token budget | fp8 endpoint: SiliconFlow |
| run_011 | Qwen3.5-397B-A17B (Apache 2.0) | `batch_038` | 19,997 | temperature 0.6, top-p 0.95, top-k 20 | same endpoints; 13 truncated |
| run_012 | Qwen3.5-397B-A17B (Apache 2.0) | `batch_041` | 39,944 | temperature 0.6, top-p 0.95, top-k 20 | same endpoints; 22 truncated |
| run_013 | DeepSeek R1 0528 (MIT) | `batch_041` | 39,944 | temperature 0.6, top-p 0.95; 65,536-token budget | fp8 endpoint: SiliconFlow; 1 truncated |
| run_014 | DeepSeek R1 0528 (MIT) | `r1_gap` | 14,298 (2 per prompt) | temperature 0.6, top-p 0.95; 65,536-token budget | fp8 endpoint: SiliconFlow; two independent samples per prompt |
| run_015 | Qwen3.5-397B-A17B (Apache 2.0) | `qwen397b_gap` | 98,298 (2 per prompt) | temperature 0.6, top-p 0.95, top-k 20 | fp8 endpoints load-balanced: DeepInfra, AtlasCloud, GMICloud, Parasail; two independent samples per prompt; 57 truncated |

`open_1k` is a seed-0 sample of 1,000 prompts from those written by the open-weight
generators (batches 022–029 and 032–033), so that the responses can be used to train
models without inheriting the Anthropic provenance notice below; `open_1k_sub100` is
a seed-0 sample of 100 of those. The two Qwen runs follow each model card's own
recommended thinking-mode settings, which differ between the two models. Run 003
answers the same set with DeepSeek R1 0528 so that distillation into Olmo 3 can be
compared against one of that model's original reasoning teachers.

Runs 006 through 013 answer the four large open-weight batches (sets `batch_033`,
`batch_035`, `batch_038`, and `batch_041`, one line per prompt of the batch, minus a
prompt deleted during curation) once each with both models, so that every prompt of
those batches has one DeepSeek R1 0528 response and one Qwen3.5-397B-A17B response.
Set `r1_gap` lists the 7,149 prompts of batches 022–040 that had no R1 response after
that (`tools/make_prompt_set.py --without-response`); run 014 answered them twice with
R1, so that, as for batches 000–021, two independent R1 samples exist for them. Every
prompt of batches 000–041 now has at least one R1 response.
Set `qwen397b_gap` lists the 49,149 prompts of batches 022–045 that had no
Qwen3.5-397B-A17B response after runs 007–012 (42,000 of them in the Inkling and HY4
batches 042–045); run 015 answered them twice with Qwen. Every prompt of batches
000–045 now has at least one Qwen3.5-397B-A17B response, and all but the prompts of
batches 033, 035, 038, and 041 and the `open_1k` prompts (which keep their single
run 000 response) have two.

**Imported runs.** The two runs whose directory names end in `_imported` were not
produced by `generate_responses.py`. They are the teacher-data collections of the
sister repo [cr_training](https://github.com/casparoe/cr_training), converted by
`tools/import_teacher_data.py`, and are the only copy now that the sister repo drops
them. Both sampled the first 22,367 prompts of this dataset (all of them
Claude-written, batches 000–021, the set `batches_000-021`) twice, independently, at
identical settings, from models the author served himself with vLLM 0.25 on Modal
(8×H200, official fp8 weights). Their records use the same layout as the other runs,
with `prompt_XXXXX.0.yaml` and `.1.yaml` for the two samples, but `generation_id`,
`native_finish_reason`, `reasoning_tokens`, `cost_usd`, and `reasoning_detail_types`
are null (no gateway metadata exists), the chain of thought is the `<think>` block as
split by the collector, and every record names its source collection and original
ID. Each `run.yaml` says `api: imported` and carries a `source` block with the
collection files, dates, and serving setup.

## Preference pairs

`preferences/` holds pairwise judgments: which of two responses to the same prompt is
the better reply. The first use is a small evaluation of weak judges against a strong
one (asked many times and for confidence estimates, does a weak model recover the
preferences of a strong one?), so the strong judge is a Claude model at maximum
reasoning effort, while the responses being judged remain the open-weight models'.

A *pair set* (`preferences/pairs/NAME.yaml`, written by `tools/make_pair_set.py`)
fixes which two responses are compared for which prompts and which one is shown first
(A) and which second (B), so that every judge sees exactly the same pairs. Pairs come
either from one run with two samples per prompt (two answers by the same model) or
from two runs (one answer each). Only complete pairs qualify: both responses have
`finish_reason: stop`, a non-empty answer without a stray `<think>` tag, and the prompt
text as it stands in `prompts/`. The A/B order is a coin flip per pair, drawn from the
set's seed.

`generators/judge_pairs.py` renders `preferences/judge_prompt.j2` with the prompt and
the two answers (the responders' chains of thought are not shown), asks the judge to
think it through and end with one of five verdicts (strongly A, weakly A,
unsure/similar, weakly B, strongly B), and writes one YAML file per pair to
`preferences/run_NNN/`. Requests are streamed one at a time per worker or submitted as
Message Batches (half price). A judgment that ends without a verdict line or is cut
off by the output budget is retried; nothing is edited. `tools/check_preferences.py`
reports coverage, the verdict distribution, the balance between A and B (a position
bias check, since the order is a coin flip), token usage and cost, and the agreement
between two runs on the same pair set.

Each judgment file has:

| Field | Meaning |
|---|---|
| `id`, `pair_set`, `response_a`, `response_b` | prompt ID; the pair set; the two response files, in the order shown to the judge |
| `judge_model`, `effort`, `api` | the judge, its reasoning effort, and whether the request was streamed (`messages`) or batched (`message_batches`) |
| `verdict` | one of the five options, as parsed from the judge's final line |
| `preferred`, `strength` | the preferred response file (null for unsure/similar) and `strong` or `weak` |
| `stop_reason`, `input_tokens`, `output_tokens`, `cost_usd`, `message_id`, `attempts` | API metadata; cost at the per-token prices recorded in `run.yaml`; how many judgments it took to get a verdict |
| `thinking`, `judgment` | the judge's thinking as the API returns it (a summary) and its visible reasoning, ending in the verdict line |

Pair sets and runs so far:

| Pair set | Pairs | Responses compared | Runs |
|---|---|---|---|
| `r1_imported` | 4,100 | the two DeepSeek R1 0528 samples of run_005_imported, for a seed-0 sample of prompts of batches 000–021 whose responses are complete in both imported runs | run_000: Claude Fable 5.1, effort max, via Message Batches; 4,065 judgments |
| `qwen397b_imported` | 4,100 | the two Qwen3.5-397B-A17B samples of run_004_imported, for the same 4,100 prompts | run_001: Claude Fable 5.1, effort max, via Message Batches; 4,068 judgments |

Both sets were drawn as 500 prompts and grown to 4,100 in three steps by re-running the
tool with a larger sample, which continues the same seeded walk and leaves the earlier
pairs unchanged. The API blocked the judge's output ("Output blocked by content
filtering policy") on every attempt for 34 and 30 pairs, 19 of them the same prompts in
both runs; these are listed under `given_up` in each `run.yaml`. The judge shows a clear
position bias in both runs, preferring the response shown second in about 60% of the
decided pairs although the order is a coin flip; and for most judgments of the third
extension the API returned no thinking summary (`thinking: null`), although the
judgment text and verdict are complete; see `QUALITY_NOTES.md`.

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
- **Data** (everything under `prompts/` and `responses/`): Creative Commons
  Attribution 4.0 (CC BY 4.0) — see `LICENSE-DATA`.

**Provenance notice.** Most prompts (batches 000–021 and 030) are outputs of Anthropic
Claude models. If you use them, you are responsible for complying with
[Anthropic's terms and usage policies](https://www.anthropic.com/legal) as they
apply to Claude outputs — in particular, restrictions on using outputs to train
models that compete with Anthropic. Batch 037 is the output of Muse Spark 1.3, a
proprietary Meta model accessed through the standard tier of the
[Meta Model API](https://developer.meta.com/ai/products/meta-model-api/) via
OpenRouter; its use is subject to Meta's terms for that API. Batches 022–029, 031, and 040 were generated with Qwen
3.8 27B, an open-weights model released under Apache 2.0; via OpenRouter, batches
032–033 with DeepSeek V4 Pro and batches 039 and 041 with DeepSeek V4.1 Flash,
open-weights models released under the MIT license, batches 042 and 044 with Thinking
Machines' Inkling and batches 043 and 045 with Tencent's HY4 preview, both open-weights
models released under Apache 2.0, and batches 034–035 with GLM-5.3, an open-weights model released under Z.ai's GLM-5.3
License (MIT terms plus a security-review condition for model-as-a-service operators
above $10 billion in annual revenue; it places no restrictions on the use of
outputs). Batches 036 and 038 were generated with Qwen3.8 2.4T-A95B, an open-weights model
released under the Qwen3.8-Max License (MIT terms plus an attribution requirement
for products above 100 million monthly users or $20 million in monthly revenue, and
a separate-license requirement for model-as-a-service businesses above $50 million
in annual revenue; no restrictions on the use of outputs). Responses under `responses/` come only from open-weights models whose
licenses (Apache 2.0, MIT) place no restrictions on the use of outputs; the model
behind every record is named in its `model` field and in the run's `run.yaml`. A
record also contains the prompt it answers, so records answering prompts from the
Claude-written batches carry the notice above with them.

## Reproducing or extending

```
pip install -r requirements.txt
python meta_prompt/assemble.py        # print one sampled meta-prompt (no API needed)
export ANTHROPIC_API_KEY=...          # for the Anthropic generators
python generators/generate_prompt.py -n 10
python generators/generate_prompt_batch.py -n 1000
python generators/generate_prompt_oai.py -n 10 --web-tools --base-url http://127.0.0.1:8088
python generators/generate_prompt_oai.py -n 10 --web-tools --base-url https://openrouter.ai/api \
    --model z-ai/glm-5.3 --api-key-file api_keys/openrouter.txt --reasoning-effort high \
    --temperature 1.0 --quantizations fp8,bf16,fp16 --provider-order io-net,siliconflow \
    --provider-ignore z-ai

# responses: build a prompt set, answer it with an open-weight model, check the run
python tools/make_prompt_set.py responses/sets/open_1k.txt --generator-model 'qwen|deepseek' --sample 1000 --seed 0
python generators/generate_responses.py --prompt-set responses/sets/open_1k.txt \
    --model qwen/qwen3.5-397b-a17b --temperature 0.6 --top-p 0.95 --top-k 20 \
    --api-key-file api_keys/openrouter.txt --quantizations fp8,int8,bf16,fp16 \
    --provider-order deepinfra,parasail --concurrency 16
python tools/check_run.py responses/run_000

# preference pairs: fix the pairs, judge them with a Claude model, check the run
python tools/make_pair_set.py preferences/pairs/r1_imported.yaml --runs responses/run_005_imported \
    --complete-in responses/run_004_imported --sample 4100 --seed 0
python generators/judge_pairs.py --pairs preferences/pairs/r1_imported.yaml --api batches --prices 5,25
python tools/check_preferences.py preferences/run_000
```

The OpenAI-compatible generator expects a llama.cpp `llama-server` (launched with
`--jinja` so tool calls are parsed) or any other OpenAI-compatible endpoint; with
`--api-key-file` it works against hosted gateways such as OpenRouter, where
`--quantizations` restricts routing to providers serving the model at the listed
precisions.
`meta_prompt/additional_instructions.yaml` controls which extra instructions are
drawn and how often. Each batch directory snapshots the exact inputs used, so past
batches remain reproducible even as the input lists evolve.
