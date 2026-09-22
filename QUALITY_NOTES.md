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
  a copied structural skeleton rather than a stock phrase. Measured against all
  examples in the batch's own `inputs/` snapshot, although from batch 046 on (and in
  the second half of batch 044) a prompt's generator saw only a random subset of one
  to five examples per offered type (recorded in the sidecar under
  `task_type_examples`).
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
| 031 | Qwen3.8-27B (local) | 958 | 16.3% | 37.0% | 7.4% / 10.4% | adversarial-collaboration example 0, 20; procedure example 0, 17 |
| 032 | DeepSeek V4 Pro (OpenRouter) | 969 | 5.9% | 17.2% | 12.5% / 2.7% | how-to-teach example 0, 10 prompts |
| 033 | DeepSeek V4 Pro (OpenRouter) | 9,931 | 5.7% | 21.0% | 18.4% / 6.3% | classroom-activity example 0, 106; procedure example 0, 85 |
| 034 | GLM-5.3 (OpenRouter) | 1,000 | 5.5% | 21.7% | 11.5% / 2.2% | classroom-activity example 0, 11; procedure example 0, 9 |
| 035 | GLM-5.3 (OpenRouter) | 19,998 | 5.3% | 21.7% | 11.1% / 3.2% | classroom-activity example 0, 230; procedure example 0, 154 |
| 036 | Qwen3.8 2.4T-A95B (OpenRouter) | 999 | 1.7% | 11.8% | 5.6% / 1.8% | classroom-activity example 0, 7; procedure example 0, 5 |
| 037 | Muse Spark 1.3 (OpenRouter, Meta) | 1,000 | 0.7% | 4.2% | 20.5% / 5.1% | classroom-activity example 0, 2 prompts |
| 038 | Qwen3.8 2.4T-A95B (OpenRouter) | 19,997 | 1.7% | 10.5% | 2.8% / 2.1% | classroom-activity example 0, 125; procedure example 0, 88 |
| 039 | DeepSeek V4.1 Flash (OpenRouter) | 488 | 4.7% | 15.6% | 8.2% / 5.2% | classroom-activity example 0, 6; procedure example 0, 4 |
| 040 | Qwen3.8-27B (local) | 442 | 10.4% | 32.4% | 9.8% / 11.3% | classroom-activity example 0, 7; procedure and adversarial-collaboration examples 0, 5 each |
| 041 | DeepSeek V4.1 Flash (OpenRouter) | 39,944 | 4.4% | 16.7% | 7.6% / 5.2% | classroom-activity example 0, 377; procedure example 0, 350 |
| 042 | Inkling (OpenRouter, BaseTen) | 1,000 | 2.5% | 11.2% | 14.1% / 3.0% | exam-question example 0, 3; what-would-count-against example 0, 3 |
| 043 | HY4 preview (OpenRouter, Tencent) | 1,000 | 3.0% | 17.3% | 2.5% / 2.1% | procedure example 0, 10 |
| 044 | Inkling (OpenRouter, BaseTen) | 20,000 | 1.6% | 9.8% | 10.6% / 3.1% | classroom-activity example 0, 43; exam-question example 0, 28 |
| 045 | HY4 preview (OpenRouter, Tencent) | 20,000 | 3.8% | 18.3% | 6.4% / 3.3% | procedure example 0, 161; classroom-activity example 0, 152 |
| 046 | Inkling (OpenRouter, BaseTen) | 100,000 | 1.8% | 9.8% | 10.6% / 2.9% | adjudication example 2, 223; classroom-activity example 0, 189 |
| 047 | Kimi K3 (OpenRouter, BaseTen) | 1,000 | 1.8% | 14.1% | 8.6% / 1.5% | classroom-activity example 0, 7 |
| 049 | DeepSeek V4 Pro 0813 (OpenRouter, Baidu) | 1,000 | 5.1% | 19.9% | 16.0% / 7.0% | classroom-activity example 0, 12; procedure example 0, 9 |
| 050 | Kimi K3 (OpenRouter, BaseTen) | 20,000 | 2.7% | 13.3% | 10.2% / 1.0% | classroom-activity example 0, 205; procedure example 0, 49 |

"Any echo" is the share of prompts with at least one shared eight-word phrase; most
of those share exactly one, typically a request formula such as "who is right about
what here".

## Observations

1. **Echo is mostly a property of the generating model.** Sonnet 5 sits at 1-2%
   heavy echo, Muse Spark 1.3 under 1%, Qwen3.8 2.4T at about 2%, Inkling at 2.5%
   and HY4 at 3% in their thousand-prompt test batches, DeepSeek V4.1
   Flash at about 5%, DeepSeek V4 Pro and GLM-5.3 at about 6%, Qwen3.8-27B at about 7% in batch 028 and 10-16% in
   batches 040 and 031, whose task-type snapshots add the adversarial-collaboration, procedure, and
   classroom-activity examples that are the strongest magnets for every model.
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
   recurs. Batch 038, whose generator searched and fetched about twice per prompt,
   has 27 such pairs above 100 shared phrases (33 prompts): Aristotle's *Nicomachean
   Ethics* on proportionate requital, Maimonides again, Polybius on the study of
   history.
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
   paragraph now names explicitly. The line was stripped from both files on
   2026-09-07 (commit 4dcf3b06); the imported response runs 004 and 005, collected
   before that, carry the earlier text in their `prompt` field. Batch 033 also lost
   65 of 10,000 generations to empty or errored responses, which the generator
   skipped; since batch 034 it retries such generations, up to four attempts,
   instead. Batch 031, made on the desktop with the older generator, arrived on
   2026-09-10 with six more dataset-builder prompts (IDs 24015, 24132, 24270,
   24635, 24728, 24753), deleted before the batch was committed, and one prompt
   (24393) that opened with the line "here's a prompt for my dataset:", which was
   stripped; the older generator also skipped 36 defective generations there
   (17 empty or truncated thinking, 13 unfinished tool loops, 6 read timeouts),
   so IDs 24841-24876 were never used.
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
8. **Model deliberation leaking into the prompt.** DeepSeek V4.1 Flash sometimes
   continues thinking in the answer channel: the content opens with planning
   ("Let me actually settle. I'll pick: Domain = ...", "The user wants a prompt
   only.") or with a fragment of a thought, runs for thousands of words, and only
   then gives the prompt; in a second pattern the prompt comes first and a
   self-review follows ("--- Hmm, that's decent. Let me check for issues."). The
   checker's other scans miss both, because they look at a short opening
   paragraph. A sweep on 2026-09-12 found 74 such prompts in batch 041 (0.2%): 57
   deliberation-first texts were deleted, 16 trailing self-reviews were cut off,
   and one prompt was recovered from between two deliberation blocks. The same
   sweep found a few older cases from other models: in batch 033 one deleted
   (26625) and one cut (32063), and label lines such as "Slogan type, social
   construction of kinds." stripped from 033/27152, 035/40299, 035/56072, plus a
   trailing "Word count: 1,181." in 036/57545. Originals are kept outside the
   repository. The checker now scans for deliberation openers, fragment starts,
   and self-review paragraphs, and the OpenAI-compatible generator retries such
   generations.

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
  own figures) understate list price for prompts that used tools. The 20k batch
  038 cost $706 in the sidecars plus about $7 for 302 retried generations and a
  few dollars of requests lost to three sleep pauses; it took 33 hours of running
  time at concurrency 48 (about 10 prompts a minute), and three prompts were given
  up because their meta-prompt sent the model past the 32,768-token budget on all
  four attempts.
- Muse Spark 1.3 (batch 037, proprietary, standard tier, effort high) cost $23 per
  1,000 prompts at 24 prompts a minute, with no defective generation in 1,000. It
  has the lowest example echo of any generator but the highest instruction copying,
  writes the shortest prompts (median 314 words), and used the web tools once in
  1,000 prompts, so its prompts contain no fetched quotations.
- Batch 031 (958 prompts) was generated on a second machine (a Framework desktop)
  with a local llama-server (Qwen3.8-27B at Q8_0, eight parallel slots, 280k
  context) between 2026-09-06 and 2026-09-10: about 240 prompts a day, 10,200
  output tokens per prompt, no API cost. That machine ran the pre-034 generator,
  which retried 135 read timeouts against the slow local server but skipped
  defective generations instead of regenerating them (36 of 1,000) and did not
  screen for preambles or dataset framing; the seven such prompts were curated
  after the batch was copied here (observation 6). Batch 040 (442 prompts) ran on
  the same machine with the current generator and a three-hour read timeout from
  2026-09-11 until it was stopped by hand on 2026-09-12 to free the machine: no
  timeouts, no lost prompts, 20 retried generations (12 over the 24k-token budget,
  6 with empty or truncated thinking, 2 with dataset framing), nothing to curate.
- DeepSeek V4.1 Flash (batch 039, released the same day, MIT weights) cost $12 per
  1,000 prompts at reasoning effort high via Novita's fp8 endpoint (mean $0.012,
  median $0.010): about 8,600 output tokens per prompt and 16,000 input tokens,
  the latter because it fetches a page for most prompts (1.4 searches and 0.9
  fetches per prompt). It ran at 13 prompts a minute at concurrency 24 with a
  single retry (one generation hit the 65,536-token budget). The batch was
  stopped by hand after 488 prompts to judge the quality before deciding on a
  larger batch; `batch.yaml` records the stop. The 40k batch 041 that followed
  (2026-09-10 to 2026-09-12, about 47 hours of wall time including two sleeps and
  five restarts) cost $412 in the sidecars (mean $0.010, median $0.008) plus about
  $4 for 504 regenerated defective answers and a few dollars of requests abandoned
  at the restarts; 24 prompts were lost in one twelve-minute outage before the
  retry budget existed. Load-balanced across the fp8 hosts, Novita served 63% of
  the rounds, Morph 35%, Venice 12%, Parasail 3%, DeepInfra 2% (a prompt's rounds
  can land on several hosts). The leak filters regenerated 30 dataset-framing and
  31 truncated-thinking answers; nothing needed curation afterwards. Shared long
  quotations (Tocqueville on equality, Augustine on lying, Machiavelli's dedication)
  give 118 prompt pairs with 100 or more shared 8-grams among 40,000 prompts.
- A self-hosted server needs a longer read timeout. With eight slots busy, the
  desktop's llama-server generates about 4.6 tokens a second per slot, so an
  answer above roughly 16,000 tokens takes longer than the generator's one-hour
  read timeout; the client then gives up and regenerates while the server
  finishes the abandoned answer anyway. Batch 031 hit this 135 times and lost six
  prompts to it. The generator has had `--read-timeout` since 2026-09-11; batch
  040 ran with three hours (recorded in `batch.yaml`) and saw no timeout.
- Throughput on OpenRouter is bounded by the providers, not by the client. For
  DeepSeek V4.1 Flash (batch 041) doubling the concurrency from 24 to 48 changed
  nothing (13 prompts a minute either way) because every request went to Novita
  first, which answered a share of them with HTTP 429; letting OpenRouter balance
  across all fp8 hosts and raising the concurrency further helped modestly. Since
  2026-09-11 the generator keeps two budgets per prompt: four paid attempts for
  defective generations, and ten free retries for connection errors, HTTP 429/5xx,
  and error bodies returned in place of choices, with pauses growing from 15
  seconds to eight minutes, so that an outage of most of an hour costs retries
  rather than prompts (the earlier fixed one-minute pause lost 24 prompts of
  batch 041 in one twelve-minute outage).

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
| run_004_imported | Qwen3.5-397B-A17B-FP8 (imported, see README) | 22,367 x 2 | 29 | 0 | 0 | 3,936 / 5,405 | about 55% by words | none (self-hosted) |
| run_005_imported | DeepSeek R1 0528 (imported) | 22,367 x 2 | 18 | 0 | 5 (all truncated inside the reasoning) | 2,349 / 3,091 | about 34% by words | none (self-hosted) |
| run_006 | DeepSeek R1 0528 | 9,930 (batch 033) | 0 | 0 | 0 | 2,656 / 3,894 | 38% | $59.71 |
| run_007 | Qwen3.5-397B-A17B | 9,930 (batch 033) | 5 | 0 | 5 (the truncated ones) | 4,510 / 6,627 | 62% | $152.95 |
| run_008 | Qwen3.5-397B-A17B | 19,998 (batch 035) | 10 | 0 | 10 (the truncated ones) | 4,795 / 6,997 | 64% | $329.62 |
| run_009 | DeepSeek R1 0528 | 19,998 (batch 035) | 0 | 0 | 0 | 2,790 / 3,967 | 38% | $127.37 |
| run_010 | DeepSeek R1 0528 | 19,997 (batch 038) | 0 | 0 | 0 | 3,065 / 5,030 | 41% | $141.57 |
| run_011 | Qwen3.5-397B-A17B | 19,997 (batch 038) | 13 | 0 | 12 (truncated ones) | 5,363 / 7,738 | 66% | $371.74 |
| run_012 | Qwen3.5-397B-A17B | 39,944 (batch 041) | 22 | 0 | 19 (truncated ones) | 4,907 / 7,247 | 66% | $677.77 |
| run_013 | DeepSeek R1 0528 | 39,944 (batch 041) | 1 | 0 | 0 | 2,845 / 4,409 | 40% | $259.13 |
| run_014 | DeepSeek R1 0528 | 7,149 x 2 (`r1_gap`) | 0 | 0 | 0 | 2,687 / 3,938 | 38% | $87.33 |
| run_015 | Qwen3.5-397B-A17B | 49,149 x 2 (`qwen397b_gap`) | 57 | 0 | 54 (truncated ones) | 4,789 / 7,126 | 67% | $1,678.67 |
| run_017 | DeepSeek R1 0528 | 20,000 x 2 (`batch_045`) | 0 | 0 | 0 | 3,147 / 5,730 | 44% | $302.27 |
| run_018 | DeepSeek R1 0528 | 24,000 x 2 (`batches_042-044_047_049`) | 0 | 0 | 0 | 2,267 / 3,149 | 37% | $256.35 |
| run_019 | Qwen3.5-397B-A17B | 2,000 x 2 (`batches_047_049`) | 7 | 0 | 7 (the truncated ones) | 4,751 / 7,207 | 66% | $67.21 |

No refusals: the refusal-phrase flags were memos quoting AI disclaimers,
hypothetical objections ("if I cannot provide..."), and a style pattern worth
knowing about: on prompts that ask for the model's own credences or intuitions,
both Qwen models sometimes open with "As an AI, I do not hold beliefs" and then
answer anyway (4 of 1,000 for 397B, 3 of 1,000 for 122B, none of 100 for
DeepSeek V4 Pro, none of 1,000 for R1 0528). The repeated-phrase flags were refrains, rubric rows, and table cells.
The one truncated response (run 000, prompt 32085, on Solomonoff induction) spent
its whole 32,768-token budget reasoning and never reached an answer; it is kept
with `finish_reason: length` and an empty `answer`.

Runs 006–014 (2026-09-12 to 2026-09-16, $2,207 in total) show the same pattern. The
refusal-phrase flags (0.1–0.6% per run) are "as an AI" used analytically ("As an AI,
I am biased toward formal consistency"), "AI safety mechanism", and quoted
disclaimers; the repeated-phrase flags (0.3–0.8%) are refrains, rubric rows, and
probability tables, with one genuine degenerate loop: run 012's response to a sestina
prompt (100372) repeats its refrain 73 times until the 32,768-token budget, and is
kept with `finish_reason: length` like the other 22 truncated Qwen responses of that
run. The Qwen runs truncate 0.1% of the time (5, 10, 13, and 22 responses), the R1
runs almost never (one response in 90,000). SiliconFlow rate-limited R1 for stretches
of the night of 2026-09-14/15, and 49 prompts of run 013 exhausted their six attempts;
the resume-until-complete queue answered them in a second pass, so coverage is
complete everywhere.

Run 015 (2026-09-16 to 2026-09-18, $1,679; two Qwen samples for the 49,149 prompts
that had none) shows the same pattern at a larger scale: 57 truncations (0.06%), 54
of them without an answer, four answers with a stray `<think>` tag, refusal-phrase
flags (0.3%) that are analytic "as an AI" openings and quoted disclaimers, and
repeated-phrase flags (0.5%) that are refrains and table rows. Load-balanced across
the four fp8 hosts, DeepInfra served 31% of the responses, AtlasCloud 28%, GMICloud
23%, and Parasail 17%, at about 1,900 responses an hour with 48 concurrent requests.
The run paused twice with the laptop (a lid-close sleep and a change of network,
about half an hour each) and resumed on its own; one request that GMICloud ended
without a finish reason exhausted its attempts and was answered in the queue's second
pass.

Run 017 (2026-09-19 to 2026-09-21, $302; two R1 samples for the 20,000 prompts of
batch 045) is as clean as the earlier R1 runs: no truncations, refusal-phrase flags
(0.1%) that are quoted speech ("you know I can't help it"), three answers under 40
words that are the one-line joke or the role-played prediction the prompt asked for,
and repeated-phrase flags (0.7%) that are repeated utility formulas and table rows in
responses that finished normally. SiliconFlow served all 40,000 at about 1,100
responses an hour with 48 concurrent requests, sharing the endpoint with run 018 on
its second day. 48 requests exhausted their attempts in the first pass (rate limits at
SiliconFlow); the queue's second pass answered them, so coverage is complete.

Run 018 (2026-09-19 to 2026-09-22, $256; two R1 samples for the 24,000 prompts of
batches 042–044, 047, and 049) is the cheapest R1 run per response so far ($5.34 per
1,000) because these prompts draw shorter responses: mean 2,267 completion tokens
against 3,147 for batch 045. No truncations; refusal-phrase flags (0.1%) are quoted
refusals in answers about AI refusal and in role-play scripts, and "I won't" in
answers scoping what they will not cover; the one answer under 40 words is the
four-field JSON object the prompt asked for; repeated-phrase flags (0.3%) are the
branch labels of decision trees, quizzes, and JSON schemas in responses that finished
normally. SiliconFlow served all 48,000. The run started at 24 concurrent requests
while run 017 held 48 on the same endpoint; the combined load drew rate-limit replies
overnight and 24 prompts were abandoned, all before run 017 finished, after which the
queue resumed at 48 and ran at 1,300 to 1,800 responses an hour without further
abandonments. The second pass answered the 24.

Run 019 (2026-09-20, $67; two Qwen samples for the 2,000 prompts of the test batches
047 and 049) matches: 7 truncations (0.2%, all without an answer), refusal-phrase
flags (0.5%) that are the analytic "As an AI, I don't have beliefs" opening on
prompts asking for the model's own credence, and repeated-phrase flags (0.4%) that
are refrains and table rows in responses that finished normally. DeepInfra served
36% of the responses, AtlasCloud 29%, Parasail 20%, and GMICloud 15%, at about 1,100
responses an hour with 24 concurrent requests.

The two imported runs were checked the same way, and their flags are artifacts of
the source collection rather than generation defects. 30 (Qwen) and 24 (R1) answers
contain a `<think>` tag: the collector split each output at the first `</think>`,
and the model had either emitted a second closing tag, so that the answer begins
with the tail of the reasoning, or written the tag inside its answer. 22 and 4
records have no reasoning; R1's 5 empty answers are all records truncated inside
the reasoning. The 148 and 48 refusal-phrase hits are dialogue lines ("I can't
write down the formula") and quoted phrases, and Qwen's 130 answers under 40 words
are 93 JSON-only answers and 37 requested one-liners. The records were imported as
they were; consumers should filter on `finish_reason` and on a `<think>` tag in the
answer, as with the other runs.
- Test batches 042 (Thinking Machines Inkling, 975B/41B MoE, Apache 2.0) and 043
  (Tencent HY4 preview, Apache 2.0), 1,000 prompts each on 2026-09-15, both at
  reasoning effort high with the web tools, fp8 endpoints only: Inkling via BaseTen
  ($17 per 1,000 prompts; mean 4,300 input and 3,500 output tokens; 0.4 searches
  and 0.03 fetches per prompt; 16 prompts a minute at concurrency 24; median prompt
  254 words, the shortest of any batch), HY4 via Tencent's endpoint ($22 per 1,000;
  10,400 input and 7,400 output tokens; 0.9 searches and 0.4 fetches per prompt; 10
  a minute; median 666 words, the longest). HY4's card asks for temperature 0.9 and
  top-p 1.0, so the OpenAI-compatible generator gained `--top-p` (default 0.95, the
  value every earlier batch used). DeepInfra cannot serve Inkling with the web
  tools: its tool-call grammar rejects the definitions ("Failed to compile
  structural_tag grammar: unknown name: web_search"), so every request errored until
  the provider was excluded.
- The 20,000-prompt batches 044 (Inkling) and 045 (HY4 preview) ran side by side on
  2026-09-15/16 at concurrency 48: Inkling at 26–43 prompts a minute, HY4 at 10–20,
  $343 and $431 in total ($17 and $22 per 1,000). BaseTen, Inkling's only fp8 host,
  failed for six and a half hours from about 20:00 PDT (rate limits, gateway
  timeouts, "overloaded"); the batch was paused by hand at 9,383 prompts after four
  had been abandoned, a watcher probed the host every five minutes, and at 02:37 the
  batch was continued with `--continue-batch` from its own snapshot to 20,000. The
  continuation ran under the example-subsetting code (below), so the 10,617 prompts
  after the pause carry `task_type_examples` while the first 9,383 saw every example.
  With two to four examples per type in the snapshot the two halves are
  indistinguishable: heavy echo 1.5% against 1.6%, any echo 9.7% against 9.9%, median
  267 words in both; the subsets will only bite once the types have more examples.
  HY4 fetched a page for 38% of its prompts and quotes public-domain passages more
  often, which shows up as 13 pairs sharing 100 or more eight-word phrases (Euclid's
  common notions, Aristotle on exchange in the Nicomachean Ethics, Adam Smith's Theory
  of Moral Sentiments), the same pattern as batch 041's Tocqueville and Augustine
  pairs; its most repeated phrase, "what will predictably go wrong the first time I
  run it", comes from the procedure type's own description and appears in 348
  prompts.
- Two generators on one machine used to be able to take the same prompt number.
  Each computed "highest existing number plus one" by listing all prompts (about a
  second with 120,000 files), so two processes finishing within that window wrote
  the same ID into different batches. Batches 042 and 043, generated at the same
  time on 2026-09-15, collided 131 times in 2,000 prompts; the HY4 copies were
  renumbered to 122870–123000 (sidecars updated, texts unchanged), which is why
  batch 043 has a second ID range. `next_output_path` now serializes the claim
  across processes with a lock file (`prompts/.numbering.lock`, ignored by git) and
  creates the file while holding it. Batches on different machines still need
  `--first-id`.
- Test batch 047 (Moonshot Kimi K3, 2.8T/104B MoE, Kimi K3 License), 1,000 prompts on
  2026-09-19 at reasoning effort high with the web tools, 8-bit endpoints only: BaseTen
  is the only such host (the model is trained in MXFP4, so its fp8 endpoint serves the
  released precision), and it enforces top-p 0.95 for this model, rejecting a first
  attempt at the card's agentic value of 1.0 with "Cannot override enforced sampling
  params". $46 per 1,000 prompts (mean 6,200 input and 2,200 output tokens); about 740
  rate-limit replies at concurrency 24, five to six prompts a minute, 14 prompts
  abandoned after ten failures and regenerated afterwards with `--continue-batch`. K3
  hardly touches the tools unless an instruction requires it: 0.1 tool calls per prompt
  without the new quote-inclusion instruction, 7.6 with it. That made the quote
  instruction under-represented while the batch ran (4.7% of finished prompts against
  a 10% draw rate), since its prompts need many more request rounds and so finished
  later and were likelier to be abandoned; it ended at 8.5% once the slow and
  regenerated prompts came in. Median 413 words; heavy echo 1.8%; two pairs share a
  long quotation (Nietzsche's preface to the Genealogy), the pattern of batches 041
  and 045.
- Test batch 049 (DeepSeek V4 Pro 0813, MIT), 1,000 prompts on 2026-09-19 at reasoning
  effort high with the web tools, fp8 endpoints only with Baidu first (Io Net and
  GMICloud excluded, as for V4.1 Flash): $17 per 1,000 prompts (mean 9,600 input and
  7,400 output tokens; 0.7 searches and 0.4 fetches per prompt, far more tool use than
  K3), about 500 prompts an hour at concurrency 48 with four transient connection
  errors and no rate limiting or abandonments. Median 332 words. The echo profile is
  that of the earlier DeepSeek batches rather than of Inkling or K3: heavy echo 5.1%,
  output-format instruction copied in 16% of the prompts that drew one, epistemic
  request in 7%; four pairs share 20 or more eight-word phrases, three of them real
  quotations (Darwin, Douglass, Hume) fetched by both prompts.
- Batch 046 (Thinking Machines Inkling, Apache 2.0), 100,000 prompts from
  2026-09-16 to 2026-09-22 at concurrency 48 on BaseTen, the model's only fp8 host:
  $1,720 in total ($17 per 1,000; mean 3,400 input and 3,500 output tokens), 13
  prompts a minute over five days, 54,500 rate-limit replies, and 590 prompts
  abandoned after ten failures, regenerated at the end with `--continue-batch` in 40
  minutes. It is the first whole batch under the example subsetting (a random subset
  of each type's examples, recorded in `task_type_examples`), and its echo profile is
  that of batch 044, which ran half with and half without it: heavy echo 1.8% against
  1.6%, any echo 9.8% in both, median 265 words against 267. The most repeated
  eight-word phrases are the output-format instructions themselves ("do not provide
  bibliographies, reading lists, or citations" in 1,165 prompts), copied into 10.6%
  of the prompts that drew one. 13 pairs share 100 or more eight-word phrases, all
  quotations fetched by both prompts (Carroll's tortoise and Achilles; Augustine's
  *On Lying*, in three prompts). Inkling searched the web for 11% of its prompts and
  fetched a page for 1%; the batch predates the quote-inclusion instruction. Run 016
  (two Qwen3.5-397B-A17B samples per prompt) has been answering the batch since
  2026-09-19, while it was still being generated.
- Batch 050 (Moonshot Kimi K3, Kimi K3 License), 20,000 prompts from 2026-09-19 to
  2026-09-21 at concurrency 48 on BaseTen with the settings of test batch 047: $901
  in total ($45 per 1,000; mean 5,400 input and 2,200 output tokens), six prompts a
  minute, 27,300 rate-limit replies, and 778 prompts abandoned after ten failures.
  The supervisor killed the generator three times after 45 minutes without a new
  prompt (at 4,297 prompts during a BaseTen outage, and twice at the tail of a pass
  when only rate-limited stragglers were in flight) and continued the batch with
  `--continue-batch`, so the abandoned prompts were regenerated in passes of 15,703,
  622, and 11. Median 414 words. Heavy echo 2.7% (classroom-activity example 0 in 205
  prompts); the procedure type's "what will predictably go wrong the first time I run
  it" appears in 380 prompts. The quote-inclusion instruction ended at 7.3% of the
  prompts against its 10% draw rate: its prompts make 6.8 tool calls on average
  against 0.09 for the rest, so they were the likeliest to be abandoned, and their
  replacements drew afresh. Those quotations also produce more shared-passage pairs
  than any earlier batch: 33 pairs (48 prompts) share 100 or more eight-word phrases,
  every one a passage fetched by both prompts (Darwin's *Descent of Man* in five
  prompts; Smith's *Theory of Moral Sentiments*, Marx's 1859 preface, and Hume's "Of
  Miracles" in three each; Mill, Beccaria, Moore, Maxwell's demon, the White Horse
  dialogue).

## Preference pairs

Preference runs (`preferences/run_NNN/`) are checked with

    .venv/bin/python tools/check_preferences.py preferences/run_NNN [--compare preferences/run_MMM]

which reports coverage of the pair set, the verdict distribution, the balance between
A and B, judgments without a verdict line or with a stop reason other than `end_turn`,
retries, token usage, and cost, and, with `--compare`, the agreement of two runs on the
same pair set. Things to track per run:

- **Position balance.** The pair set decides by a coin flip which response is shown as
  A, so a judge without position bias should prefer A and B about equally often; a
  clear tilt toward A or B is a bias of the judge, not of the responses.
- **Missing verdicts.** The judge is asked to end with `Verdict: <option>`. A judgment
  without a parseable verdict line, or cut off by the output budget, is retried up to
  three times and otherwise dropped, so records with a null verdict should not exist.
- **Refusals** (`stop_reason: refusal`) are dropped without retry and would show up as
  missing coverage.
- **Cost.** Claude Fable 5.1 costs $10 per million input and $50 per million output
  tokens on the Messages API and half of that through Message Batches. A judgment at
  maximum effort reads 2,500–9,000 tokens (the prompt and two answers) and writes
  8,000–13,000 (mostly thinking), so it costs about $0.40–0.75 streamed and half that
  batched (pilot of 6 pairs, 2026-09-13).

### Runs (2026-09-13 to 2026-09-17)

Both pair sets hold the same 4,100 prompts: a seed-0 sample of the 22,367 prompts of
batches 000–021 that have complete responses in both imported runs. 500 were drawn on
2026-09-13, 10 more the same day, 1,020 more on 2026-09-14, and 2,570 more on
2026-09-17, each time by re-running the tool with a larger `--sample`, which continues
the same seeded walk and leaves the earlier pairs unchanged. Each pair is two samples
of the same model for the same prompt; the judge is Claude Fable 5.1 at effort max,
sent as Message Batches (a round of 500 requests took about ten minutes, one of 1,020
about seventy, one of 2,570 about two and a half hours).

| Run | Pairs | Judgments | Strongly A / weakly A / unsure / weakly B / strongly B | A vs B among decided | Output tokens (mean / p90) | Cost |
|---|---|---|---|---|---|---|
| run_000 | `r1_imported` (DeepSeek R1 0528 x 2) | 4,065 of 4,100 | 319 / 1,234 / 70 / 1,863 / 579 | 39% vs 61% | 11,772 / 17,046 | $1,320 |
| run_001 | `qwen397b_imported` (Qwen3.5-397B x 2) | 4,068 of 4,100 | 214 / 1,377 / 108 / 2,014 / 355 | 40% vs 60% | 12,041 / 17,366 | $1,340 |

- **Position bias.** The order of the two responses is a coin flip per pair, yet the
  judge preferred the response shown second (B) in 61% (R1) and 60% (Qwen) of the
  decided pairs (z of 14.1 and 12.4 over about 4,000 decided pairs each). Split by
  which sample was shown first, the tilt toward B is the same either way, and the
  preferred *sample* (first or second draw of the model) is close to balanced (1,941 vs
  2,054, and 1,964 vs 1,996), so this is a bias for the second position, not a
  difference between the samples. The bias is stronger among the "strongly" verdicts
  (579 strongly B against 319 strongly A for R1; 355 against 214 for Qwen). Consumers
  who need order-free judgments should judge each pair in both orders and combine, at
  twice the cost; a run on the same pair sets with A and B swapped would do.
- **Verdicts.** Same-model pairs are close calls: the judge said "unsure/similar" for
  only 2–3% of the pairs and "weakly" for 76% (R1) and 83% (Qwen); "strongly" for 22%
  and 14%. Every judgment that came back ended with a parseable verdict line; the
  records with `attempts` above 1 (40 and 34) are pairs whose earlier attempts the
  content filter blocked, not malformed judgments.
- **Content-filter blocks.** The API rejected some requests with `Output blocked by
  content filtering policy` (an `invalid_request_error` in the batch results): 13 of
  500 R1 pairs and 14 of 500 Qwen pairs in the first round of the first 500, 18 and 16
  of the 1,020 added on 2026-09-14, and about 40 of the 2,570 added on 2026-09-17.
  About half pass when resubmitted; the rest are blocked on all three attempts and
  given up on: 34 pairs in the R1 run and 30 in the Qwen run, 19 of them the same
  prompts in both. The prompts are innocuous philosophy, but the early ones clustered
  on a few texts and debates: Turing's 1950 "Computing Machinery and
  Intelligence" (seven different prompts: 00891, 01012, 05575, 07820, 08668, 10548,
  11411), von Neumann's 1955 "Can We Survive Technology?" (06003, 17300), Popper on
  falsifiability and evolution (02904, 04884, 10013), Hobbes's Leviathan on authors and
  actors (08742), Keynes's 1930 "Economic Possibilities for our Grandchildren" (18087),
  Frederick Douglass's constitutional theory (08654), Aquinas and double effect (21044),
  Pascal on justice and force (02484), Du Bois and Locke on Black art (18024), the FIRE
  movement (08135), and a novel about a housing dispute (01916). The filter evidently
  reacts to something in the judge's own output about these texts, and the same prompt
  tends to trip it for both models' pairs. The pairs are listed under `given_up` in
  each `run.yaml`; `judge_pairs.py --resume` skips them unless `--retry-given-up` is
  passed.
- **Missing thinking summaries.** The requests ask for `display: summarized`
  thinking, and the first 3,031 judgments came back with a summary in all but three
  cases (run_000, prompts 12758 and 15779; run_001, prompt 10080). Of the 5,102
  judgments of the 2026-09-17 extension, 71% (R1) and 66% (Qwen) came back with
  `thinking: null`: the thinking blocks had empty text, as under `display: omitted`,
  although the output-token counts (mean 11,300 for those records against 12,700 for
  the ones with a summary) show that the judge thought as much as before and was
  billed for it. Nothing changed on our side between the rounds. The judgment text
  and verdict are complete in every record; consumers of the `thinking` field should
  expect it to be null for about 45% of the records overall.
- **Cost and length.** $0.33 per judgment through Message Batches ($5/$25 per million
  tokens): about 6,000 input tokens (the prompt and two answers) and 12,000 output
  tokens, of which the visible judgment is about 470 words. The pilot of six pairs
  through the streamed Messages API cost $0.60 per judgment.
