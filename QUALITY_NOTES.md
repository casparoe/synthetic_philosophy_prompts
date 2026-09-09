# Quality notes

Known quality issues in the generated prompts, how they are measured, and the
numbers per batch. None of these is treated as urgent; the point is to track them
across models and template changes. Measure a batch with

    .venv/bin/python tools/check_batch.py prompts/batch_NNN

and add a row below. The checker also scans for leaked tool-call markup, chat
preambles, dataset-construction framing, ID collisions, and sidecars that no longer
re-render from the batch's snapshot; those should simply be zero.

## Definitions

- **Example echo.** The meta-prompt shows the generator a few example prompts per
  task type. A generated prompt *echoes* an example when it shares at least one
  eight-word phrase with it (case- and punctuation-insensitive). *Heavy echo* means
  five or more shared eight-word phrases, which in practice is a copied sentence or
  a copied structural skeleton rather than a stock phrase. Measured against the
  examples in the batch's own `inputs/` snapshot.
- **Instruction copying.** The additional instructions (output format, epistemic
  request, persona, ...) are meant to be realized in the prompt, not pasted into it.
  A prompt *copies* an instruction when it shares eight consecutive words with the
  instruction text it was given. Reported per instruction group, as a share of the
  prompts that drew that group.
- **Near-duplicate pairs.** Pairs of prompts in the same batch sharing 20, 50, or
  100 eight-word phrases. Pairs above 100 have so far always been two prompts
  quoting the same public-domain passage, not duplicated prompts.

## Measurements (taken 2026-09-07)

| Batch | Model | Prompts | Heavy echo | Any echo | Copies output_format / epistemic_request | Most copied example |
|---|---|---|---|---|---|---|
| 009 | Sonnet 5 (streaming) | 954 | 0.0% | 0.4% | n/a (groups did not exist) | none |
| 016 | Sonnet 5 (streaming) | 1,864 | 1.4% | 4.6% | n/a | adjudication example 2 (extended warranty), 23 prompts |
| 021 | Sonnet 5 (Message Batches) | 9,977 | 1.7% | 4.6% | n/a | adjudication example 2, 134 prompts |
| 028 | Qwen3.8-27B (local) | 944 | 7.4% | 14.6% | n/a | interview-questions example 0, 19; adjudication examples, 28 |
| 030 | Sonnet 5 (streaming) | 93 | 1.1% | 5.4% | 0% / 0% | classroom-activity example 0, 1 prompt |
| 032 | DeepSeek V4 Pro (OpenRouter) | 969 | 5.9% | 17.2% | 12.5% / 2.7% | how-to-teach example 0, 10 prompts |
| 033 | DeepSeek V4 Pro (OpenRouter) | 9,931 | 5.7% | 21.0% | 18.4% / 6.3% | classroom-activity example 0, 106; procedure example 0, 85 |
| 034 | GLM-5.3 (OpenRouter) | 1,000 | 5.5% | 21.7% | 11.5% / 2.2% | classroom-activity example 0, 11; procedure example 0, 9 |
| 035 | GLM-5.3 (OpenRouter) | 19,998 | 5.3% | 21.7% | 11.1% / 3.2% | classroom-activity example 0, 230; procedure example 0, 154 |
| 036 | Qwen3.8 2.4T-A95B (OpenRouter) | 999 | 1.7% | 11.8% | 5.6% / 1.8% | classroom-activity example 0, 7; procedure example 0, 5 |
| 037 | Muse Spark 1.3 (OpenRouter, Meta) | 1,000 | 0.7% | 4.2% | 20.5% / 5.1% | classroom-activity example 0, 2 prompts |

"Any echo" is the share of prompts with at least one shared eight-word phrase; most
of those share exactly one, typically a request formula such as "who is right about
what here".

## Observations

1. **Echo is mostly a property of the generating model.** Sonnet 5 sits at 1-2%
   heavy echo, Muse Spark 1.3 under 1%, Qwen3.8 2.4T at about 2%, DeepSeek V4 Pro
   and GLM-5.3 at about 6%, Qwen3.8-27B at about 7%.
   Within a model the rate is stable across batch sizes (032 vs. 033, 034 vs. 035).
2. **A few examples act as magnets.** For Sonnet it is the extended-warranty
   adjudication example (its closing "adjudicate move by move" formula). For
   DeepSeek it is the classroom-activity example ("tell me what will predictably go
   wrong the first time I run it", in over 100 prompts of batch 033), the
   procedure example, the objections-prep example, and the commitments examples.
   Rewording those few examples would remove most heavy echo.
3. **The anti-echo sentence in `prompt.j2` did not help at scale.** The line "They
   only illustrate the type: don't reuse their openings, wording, or structure"
   (commit a836f7c7) cut echo from 10% to 6% in a 100-prompt trial, but batch 033,
   generated with it, shows the same heavy-echo rate as batch 032 without it.
4. **Instruction text gets pasted.** Output-format instructions are copied verbatim
   into 6-20% of the prompts that draw them (Qwen3.8 2.4T 6%, GLM-5.3 11%, DeepSeek
   V4 Pro 18%, Muse Spark 1.3 20%), so "lead with your bottom line in the
   first sentence, with no preamble and no restating of the question" recurs
   hundreds of times. Epistemic requests are copied in 3-6%. Persona and writing
   style are essentially never copied. This is the largest source of repeated
   phrasing in the DeepSeek batches.
5. **Near-duplicates are shared quotations.** The most similar prompt pairs in
   batch 033 (up to 274 shared eight-word phrases) quote the same passage of
   Carroll's Tortoise dialogue, Maimonides' Guide III.32, or Machiavelli's chapter
   25. That is expected from the passage-understanding type when the same domain
   recurs.
6. **Defective prompts removed.** Batch 033 originally had three prompts that
   role-played the dataset builder ("I'm building a dataset of philosophy prompts
   and I need one ...": IDs 27747, 28529, 32852) and one dialogue with no request
   (34596). They were deleted before the batch was committed, leaving those IDs
   unused. Batch 035 lost two prompts the same way: one of the dataset-builder kind
   (ID 42705) and a 36-word fragment that stopped mid-sentence (ID 56338); the
   generator now retries dataset framing and anything under 40 words. A scan of all 34,773 committed prompts found no other dataset framing,
   tool-call markup, or request-less dialogues; the only leaks are two batch 009
   prompts (IDs 01002 and 01201) that begin with the line "This is my final
   answer." before an otherwise normal prompt, the leak the template's closing
   paragraph now names explicitly. They are still in place. Batch 033 also lost
   65 of 10,000 generations to empty or errored responses, which the generator
   skipped; since batch 034 it retries such generations, up to four attempts,
   instead.
7. **Process notes before the prompt.** GLM-5.3 sometimes opens with a note on its
   own procedure ("Quick sanity check before I write this: the prompt involves
   Aumann's agreement theorem, but doesn't quote any text or lean on specific
   works/dates, so no search is needed." or just "Here's the prompt:") followed by
   an otherwise normal prompt: 3 of 1,000 in batch 034 (IDs 35845, 36690, 36769) and
   8 of 20,000 in batch 035 (IDs 39290, 40479, 42827, 43669, 45653, 46223, 47199,
   50439). Those openings were removed during curation; the prompts are otherwise
   untouched. The checker flags a short opening paragraph of this kind and the
   OpenAI-compatible generator retries it (it caught several more during the second
   half of batch 035). No Sonnet, Qwen, or DeepSeek batch shows the pattern.

## Possible mitigations (not done)

- Reword or replace the magnet examples listed above.
- Show each render a random subset of a type's examples instead of all of them.
- Add "phrase the request in your own words" to the output_format and
  epistemic_request preambles in `additional_instructions.yaml`.
- Reject and regenerate at generation time when a prompt shares five or more
  eight-word phrases with an example or an instruction (cheap to check).

## Related operational notes

- Cost on OpenRouter depends on which host serves the request. Batch 033 cost
  $174 against a $52 projection from batch 032 because routing shifted from
  StreamLake to Novita and Alibaba; Novita's endpoint both charged more and
  returned about twice the output tokens per prompt. All hosts were fp8 as
  requested. A provider order (StreamLake, Baidu first) would have kept the cost
  near the projection. The generator has had `--provider-order` and
  `--provider-ignore` flags since batch 034; both are recorded in `batch.yaml`.
- Hosts differ in reliability, not only in price. In the first attempt at batch
  034, Io Net returned 20 of 95 GLM-5.3 generations cut off without a finish reason,
  the failure GMICloud showed for DeepSeek V4 Pro in response run 002. That attempt
  (73 prompts, about $1.20) was discarded; the batch was regenerated with SiliconFlow
  first, which served 989 of the 1,000 prompts without a single defective
  generation, at a mean of $0.018 per prompt. Batch 035 (20,000 prompts, $360, the
  same mean) ran 98.5% on SiliconFlow at concurrency 48; 95 defective generations
  (mostly SiliconFlow mid-stream errors and empty responses, about $0.80 in total)
  were retried and none was lost.
- Sleep stalls a run. Batch 035 stalled for 80 minutes when the laptop lid was
  closed on battery: `caffeinate -i` prevents idle sleep only, the in-flight
  requests died, and the generator waited for its read timeout. The run was killed
  and finished with `--continue-batch prompts/batch_035`, which appends to an
  existing batch from its own snapshot and records the continuation in
  `batch.yaml`; the generator now also sets TCP keepalive so dead connections fail
  within minutes of a wake.
- Qwen3.8 2.4T-A95B (batch 036) cost $36 per 1,000 prompts, twice GLM-5.3, because
  its thinking cannot be disabled and averages 7,200 output tokens per prompt; it
  also ran at only six prompts a minute at concurrency 24 and used about two web
  searches per prompt. SiliconFlow is its only host with a disclosed precision.
  That endpoint ends tool-calling rounds without a finish reason, and OpenRouter
  records those rounds at zero cost, so the sidecar costs (which are OpenRouter's
  own figures) understate list price for prompts that used tools.
- Muse Spark 1.3 (batch 037, proprietary, standard tier, effort high) cost $23 per
  1,000 prompts at 24 prompts a minute, with no defective generation in 1,000. It
  has the lowest example echo of any generator but the highest instruction copying,
  writes the shortest prompts (median 314 words), and used the web tools once in
  1,000 prompts, so its prompts contain no fetched quotations.

## Responses

Response runs (`responses/run_NNN/`) are checked with

    .venv/bin/python tools/check_run.py responses/run_NNN

which reports coverage of the prompt set, finish reasons, missing chains of thought,
truncated or empty answers, `<think>` tags or tool-call markup left in answers,
refusal phrases, repeated phrases, length distributions, cost, and the provider mix.
Things to track per run:

- **Truncation** (`finish_reason: length`): the response hit the 32,768-token
  budget. Such records stay in the data; consumers should filter on `finish_reason`.
- **Degenerate loops**: an answer that repeats a twelve-word phrase three or more
  times. Seen so far only together with truncation, on a small model: its
  deliberation continued past the end of the chain of thought and looped until the
  budget ran out.
- **Missing reasoning**: a record without a chain of thought although one was
  requested, or a `reasoning_detail_types` other than `reasoning.text` (a summary
  instead of the full text).
- **Refusals and empty answers**: should be zero for philosophical prompts.
- **Incomplete responses without a finish reason.** One host (GMICloud, serving
  DeepSeek V4 Pro 0813 in run 002) returned generations cut off mid-sentence with
  no `finish_reason` and, in four of five cases, no answer at all, on 5 of its 33
  requests; the other hosts never did. The generator now retries any response
  whose finish reason is not `stop` or `length`, or whose answer is empty without
  the budget having been hit, and the checker flags any that slip through. The
  five records were deleted and regenerated.

### Trial measurements (2026-09-07; 12 prompts each, not committed)

The same twelve prompts (seed-0 sample of the prompts written by open-weight
generators), reasoning enabled with the model's default budget, the provider's
default sampling parameters, 32,768-token budget, no precision filter (Alibaba's
precision is undisclosed). The committed runs use the model cards' sampling
parameters and 8-bit-or-better endpoints only.

| Model | Provider | Truncated | Loops | Completion tokens (mean / p90) | Reasoning share | Answer words (median) | Cost per 1000 |
|---|---|---|---|---|---|---|---|
| Qwen3.5-397B-A17B | Alibaba | 0/12 | 0 | 4,257 / 5,192 | 65% | 1,151 | $10.12 |
| Qwen3.5-9B | SiliconFlow (fp8) | 1/12 | 1 | 7,617 / 9,226 | 54% | 1,251 | $1.18 |
| gpt-oss-120b (effort high) | DeepInfra (bf16) | 0/12 | 0 | 9,929 / 16,539 | 77% | 1,635 | $1.70 |

### Committed runs (model-card sampling, fp8-or-better endpoints)

| Run | Model | Prompts | Truncated | Missing finish reason | Empty answers | Completion tokens (mean / p90) | Reasoning share | Cost |
|---|---|---|---|---|---|---|---|---|
| run_000 | Qwen3.5-397B-A17B | 1,000 | 1 | 0 | 1 (the truncated one) | 4,400 / 6,273 | 63% | $13.52 |
| run_001 | Qwen3.5-122B-A10B | 1,000 | 0 | 0 | 0 | 4,477 / 6,637 | 64% | $10.10 |
| run_002 | DeepSeek V4 Pro 0813, effort high | 100 | 0 | 0 (five regenerated, see above) | 0 | 12,423 / 19,717 | 86% | $4.15 |
| run_003 | DeepSeek R1 0528 | 1,000 | 0 | 0 | 0 | 2,605 / 3,809 | 37% | $5.89 |

No refusals: the refusal-phrase flags were memos quoting AI disclaimers,
hypothetical objections ("if I cannot provide..."), and a style pattern worth
knowing about: on prompts that ask for the model's own credences or intuitions,
both Qwen models sometimes open with "As an AI, I do not hold beliefs" and then
answer anyway (4 of 1,000 for 397B, 3 of 1,000 for 122B, none of 100 for
DeepSeek V4 Pro, none of 1,000 for R1 0528). The repeated-phrase flags were refrains, rubric rows, and table cells.
The one truncated response (run 000, prompt 32085, on Solomonoff induction) spent
its whole 32,768-token budget reasoning and never reached an answer; it is kept
with `finish_reason: length` and an empty `answer`.
