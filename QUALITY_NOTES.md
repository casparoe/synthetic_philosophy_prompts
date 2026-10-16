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
| 041 | DeepSeek V4.1 Flash (OpenRouter) | 39,942 | 4.4% | 16.7% | 7.6% / 5.2% | classroom-activity example 0, 377; procedure example 0, 350 |
| 042 | Inkling (OpenRouter, BaseTen) | 1,000 | 2.5% | 11.2% | 14.1% / 3.0% | exam-question example 0, 3; what-would-count-against example 0, 3 |
| 043 | HY4 preview (OpenRouter, Tencent) | 1,000 | 3.0% | 17.3% | 2.5% / 2.1% | procedure example 0, 10 |
| 044 | Inkling (OpenRouter, BaseTen) | 20,000 | 1.6% | 9.8% | 10.6% / 3.1% | classroom-activity example 0, 43; exam-question example 0, 28 |
| 045 | HY4 preview (OpenRouter, Tencent) | 20,000 | 3.8% | 18.3% | 6.4% / 3.3% | procedure example 0, 161; classroom-activity example 0, 152 |
| 046 | Inkling (OpenRouter, BaseTen) | 100,000 | 1.8% | 9.8% | 10.6% / 2.9% | adjudication example 2, 223; classroom-activity example 0, 189 |
| 047 | Kimi K3 (OpenRouter, BaseTen) | 1,000 | 1.8% | 14.1% | 8.6% / 1.5% | classroom-activity example 0, 7 |
| 048 | Qwen3.8 2.4T-A95B (OpenRouter, SiliconFlow) | 50,000 | 1.4% | 10.0% | 3.1% / 2.6% | classroom-activity example 0, 206; procedure example 0, 128 |
| 049 | DeepSeek V4 Pro 0813 (OpenRouter, Baidu) | 1,000 | 5.1% | 19.9% | 16.0% / 7.0% | classroom-activity example 0, 12; procedure example 0, 9 |
| 050 | Kimi K3 (OpenRouter, BaseTen) | 20,000 | 2.7% | 13.3% | 10.2% / 1.0% | classroom-activity example 0, 205; procedure example 0, 49 |
| 051 | DeepSeek V4 Pro 0813 (OpenRouter, Baidu) | 50,000 | 4.4% | 15.9% | 17.7% / 7.5% | classroom-activity example 0, 364; procedure example 0, 333 |
| 052 | DeepSeek V4 Pro 0813 (OpenRouter, Baidu) | 50,000 | 4.4% | 15.5% | 18.5% / 7.7% | classroom-activity example 0, 358; procedure example 0, 352 |
| 053 | MiMo-V2.6-Pro (OpenRouter, Xiaomi and DeepInfra) | 1,000 | 4.8% | 18.9% | 6.8% / 7.7% | classroom-activity example 0, 10; procedure example 0, 7 |
| 054 | HY4 preview (OpenRouter, Tencent) | 50,000 | 1.3% | 9.0% | 7.0% / 2.8% | classroom-activity example 0, 107; procedure example 0, 91 |
| 055 | MiMo-V2.6-Pro (OpenRouter, DeepInfra, GMICloud, Xiaomi) | 50,000 | 4.9% | 17.7% | 10.1% / 7.0% | classroom-activity example 0, 506; procedure example 0, 337 |
| 056 | MiMo-V2.6-Pro (OpenRouter, DeepInfra, GMICloud) | 5,000 | 9.9% | 24.2% | 11.4% / 8.9% | referee-report example 0, 74; classroom-activity example 0, 62 |
| 057 | MiMo-V2.6-Pro (OpenRouter, DeepInfra) | 5,000 | 10.5% | 26.6% | 9.4% / 7.5% | referee-report example 0, 82; classroom-activity example 0, 65 |
| 058 | MiMo-V2.6-Pro (OpenRouter, DeepInfra) | 5,000 | 10.2% | 25.4% | 11.5% / 7.4% | referee-report example 0, 62; classroom-activity example 0, 61 |
| 059 | HY4 preview (OpenRouter, Tencent) | 4,995 | 7.3% | 21.7% | 9.0% / 4.4% | referee-report example 0, 44; graded-script example 1, 34 |
| 060 | MiMo-V2.6-Pro (OpenRouter, DeepInfra) | 5,000 | 10.4% | 25.6% | 11.5% / 9.0% | referee-report example 0, 87; classroom-activity example 0, 63 |
| 062 | GLM-5.3 (OpenRouter, SiliconFlow) | 1,000 | 6.3% | 19.8% | 10.2% / 3.7% | transcript example 0, 9; graded-answer example 0, 7 |
| 063 | Claude Haiku 5.5 (Anthropic API, effort xhigh) | 4,981 | 2.9% | 12.1% | 16.7% / 7.4% | transcript example 0, 22; procedure example 0, 19 |
| 064 | Claude Haiku 5.5 (Anthropic API, effort xhigh) | 4,896 | 3.1% | 12.7% | 15.9% / 7.8% | transcript example 0, 34; referee-report example 0, 17 |
| 065 | GLM-5.3 (OpenRouter, Baidu) | 19,999 | 6.7% | 20.9% | 12.7% / 4.4% | transcript example 0, 193; classroom-activity example 0, 104 |
| 066 | DeepSeek V4 Pro 0813 (OpenRouter, Baidu) | 19,999 | 7.6% | 20.5% | 17.7% / 9.2% | transcript example 0, 210; referee-report example 0, 143 |
| 067 | Claude Haiku 5.5 (Message Batches API, effort xhigh) | 199,535 | 2.7% | 11.9% | 15.7% / 8.5% | transcript example 0, 896; referee-report example 0, 793 |

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

- Batch 054 (Tencent HY4 preview, Apache 2.0), 50,000 prompts from 2026-09-24 15:26
  to 2026-09-29 02:24 PDT at concurrency 72 with a 64,000-token budget (Tencent and
  Novita cap output there; a 65,536 budget had routed everything to the four times
  slower SiliconFlow endpoint): about 470 prompts an hour on average, Tencent serving
  97%, Novita most of the rest, SiliconFlow and DeepInfra a few hundred. It cost
  $1,567.80, $31.36 per 1,000 (mean $0.031, median $0.020), the dearest generator so
  far: 15,500 input and 8,100 output tokens per prompt at a blended $1.33 per million,
  the input inflated by 1.25 searches and 1.03 fetches per prompt (34% of prompts
  searched). The supervisor continued the batch three times after stalls (twice on
  the first evening, once on 09-26) and once at the end to replace a removed file.
  The generator retried 1,595 generations, none for rate limits and none abandoned:
  347 read timeouts, 235 empty error finishes (152 from Tencent at no cost), 147
  dropped connections, about 230 connect errors, 71 gateway timeouts, 29 empty or
  truncated thinking, 13 content-filter finishes, and 9 over the budget. The
  prompts are the longest of any batch with batch 048 (median 652 words, p90 986,
  maximum 2,375 after curation) and include the first 50,000-prompt sample from the 1,674-domain
  list. Example echo is low (heavy 1.3%, any 9.0%); the output-format instruction is
  copied verbatim into 7.0% of prompts ("lead with your bottom line in the first
  sentence" in 726) and the epistemic request into 2.8%. HY4 quotes fetched
  public-domain passages readily: 368 pairs share 100 or more eight-word phrases
  (Adam Smith's Theory of Moral Sentiments, Kant's second Critique on freedom, Mill on
  the internal sanction of duty). Curation: the leak sweep of 09-28 trimmed nine
  prompts whose HY4 thinking block had leaked before the prompt behind a
  `</think:opensource>` tag and removed one file in which the model asked for the
  domain and type it had not been shown (402053); the check at completion found two
  more leaked thinking blocks (512155, 516267), one "OK, here's the prompt:" preamble
  (517266), and one prompt with the generator's "Domain: ... Type: ..." labels inside
  the asker's text (426562, sentence removed). Sixteen prompts frame themselves as
  "another one for the dataset" and were left as they are. The wider check of
  2026-10-04 (see batch 059) found HY4 defects that the checks of the time missed: 809
  prompts with a stray East Asian word in place of an English one ("is the 니 answer",
  "repricing of尾部 risk"; about one in nine followed by the asker's "sorry, ..."), 72
  with a leaked `<｜hy_place▁holder▁no▁813｜>` token (27 of them break off mid-sentence
  right after it), and two with Russian and Chinese fragments. One of those, 514227, a
  99-word German list of lab values ending in Chinese gibberish and a Chinese refusal, was
  deleted on 2026-10-04 together with its four answers in runs 029 and 032 and its line in
  `responses/sets/batch_054.txt` (originals kept outside the repository), so the batch now
  counts 49,999. The rest were left in place by the user's decision (an occasional odd
  prompt is acceptable as long as it stays a small fraction): in a sample of 150 of the
  stray-word prompts, only 2-3% of the R1 and Qwen answers mention or repeat the stray
  word, the rest answer the intended question. HY4 is not used for new batches.
- Batch 055 (Xiaomi MiMo-V2.6-Pro, MIT), 50,000 prompts from 2026-09-24 19:38 to
  2026-10-01 01:47 PDT at concurrency 48 with a 65,536-token budget: about 330 prompts an
  hour on average, DeepInfra serving about half, GMICloud and Xiaomi a quarter each.
  Xiaomi's own endpoint rate-limited the model from the afternoon of 09-29 on (4,287
  rate-limit replies in all, every one retried elsewhere), and the rate fell to a few
  dozen an hour for two hours on 09-30 before recovering. It cost $485.03, $9.70 per 1,000
  (mean $0.0097, median $0.0054): 14,800 input and 7,100 output tokens per prompt at a
  blended $0.44 per million, with 1.08 searches and 0.91 fetches per prompt (24% of
  prompts searched). The supervisor continued the batch once after a manual restart on
  09-26 and once at the end to replace 22 generations abandoned after ten failed attempts
  each; the generator also retried 514 read timeouts, 329 dropped connections, 350
  content-filter finishes, 153 empty error finishes, 136 connect errors, 45 over the
  budget, and 20 gateway errors. The prompts are long (median 534 words, p90 810, maximum
  2,186; 1,427 of 1,000 words or more) and were sampled from the 1,718-domain list and the
  66 task types of 09-24. Example echo is moderate (heavy 4.9%, any 17.7%); the
  output-format instruction is copied verbatim into 10.1% of prompts ("lead with your
  bottom line in the first sentence" in 725) and the epistemic request into 7.0% ("what
  will predictably go wrong the first time I run it" in about 700). MiMo quotes fetched
  public-domain passages readily: 919 pairs share 100 or more eight-word phrases (Douglass
  on the Constitution and slavery, Aquinas on lying, Bentham's Introduction). Curation:
  the check at completion found one prompt ending in the generator's "Reply with the
  prompt text only." (521185, sentence removed) and one opening with the generator's
  planning paragraph ("I have settled on the domain of ...", 530146, paragraph removed),
  after the leak sweep of 09-28 had trimmed three others (414036, 447783, 482357); two
  prompts frame themselves as being "for the dataset" (512509, 525288) and were left as
  they are.
- Batch 056 (Xiaomi MiMo-V2.6-Pro, MIT), 5,000 prompts from 2026-10-02 10:40 to 21:45
  PDT with the settings of batch 055, a test of the meta-prompt of that morning: four
  new task types (two formulations that may or may not say the same thing, a passage to
  rewrite for a stated purpose, a paper section for a referee report, a transcript whose
  speakers talk past each other), examples three times as long in total (15,180 to
  47,021 words, with whole articles of 6,600-9,100 words for three types and graded
  scripts of 1,400-2,100 words), and the rule that long quotations must come from
  public-domain or openly licensed texts or Caspar Oesterheld's own, with at most a few
  paragraphs from anything else; domains from the 1,767-entry list of that morning.
  About 450 prompts an hour, DeepInfra serving 95% and GMICloud nearly all the rest. It
  cost $58.43, $11.69 per 1,000 (mean $0.0117, median $0.0070), a fifth more than batch
  055: 21,500 input tokens per prompt against 14,800 (the longer examples, and 1.31
  searches and 1.01 fetches per prompt, 26% of prompts searching) and 8,100 output
  tokens, at a blended $0.39 per million. The generator retried 47 read timeouts, 13
  rate-limit replies, 13 empty error finishes, 10 content-filter finishes, 2 connect
  errors, one empty thinking, and four generations its leak checks rejected; none was
  abandoned. The prompts are longer than batch 055's (median 589 words, p90 1,098,
  maximum 4,648; 13% of 1,000 words or more against 3%), mostly through long quoted or
  invented material: 5.5% carry 600 or more words in blockquotes or long quotations
  (1.4% in 055). Each new type was offered to about 200 prompts and taken by about half
  of them; samples of all four read well. Example echo doubled (heavy 9.9%, any 24.2%),
  all of it from the new and lengthened examples: heavy echo of examples unchanged since
  055 is 5.3%, and the new ones add 4.6%, mostly through their closing requests rather
  than their quoted texts ("a verdict (accept, accept with minor revisions, major
  revisions, reject)" from the referee-report example, "what question we should have
  been arguing about" from the transcript example, "what would have to change for full
  marks" from the graded scripts). The output-format instruction is copied into 11.4%
  of the prompts that drew it and the epistemic request into 8.9% (055: 10.1% and
  7.0%). The 31 pairs sharing 100 or more eight-word phrases (52 prompts) all quote the
  same public-domain passage (Montaigne's "Of Cannibals" in Cotton's translation,
  Veblen's *Theory of the Leisure Class*, Carroll's Tortoise, Spinoza's definitions).
  Quotation rule: MiMo reasons about copyright or the public domain in 39% of its
  generations. Eight Claude Opus 5.5 subagents read the 412 prompts most likely to quote
  at length (every prompt that fetched a page and carries 300 or more quoted words or
  runs to 1,000 words, plus 20 long ones that fetched nothing), with the generator's
  reasoning. 206 quote a real text. Of the 65 quotations longer than three paragraphs or
  about 400 words, 62 come from public-domain works, translations among them from before
  1931 (the 1611 translators' preface to the King James Bible, about 3,200 words;
  Maimonides' Guide III.32 in Friedländer's translation, 2,900; Franklin's
  Autobiography, 2,800; Beccaria in the 1767 translation, 2,500), and the other 25
  copyrighted texts (Quine's "Two Dogmas", Orwell, Bostrom, Dennett, arXiv papers) are
  quoted for one to three paragraphs. One prompt went over: 536207 quoted about 400
  words in six short paragraphs of a critical Alignment Forum comment, which the
  generator had planned as "2-3 paragraphs"; its last two paragraphs were cut, leaving
  330 words in four. Two borderline cases were left as they are: 540544 quotes two
  paragraphs (about 430 words) of Engels's 1890 letter to Bloch in an unidentified,
  possibly post-1931 translation, and 539470 the White Horse dialogue (about 230 words
  in six turns) in an unidentified translation the generator says it took from
  Wikipedia (CC BY-SA if so). Curation (originals kept outside the
  repository): 538010 held the prompt twice with "Now write the response... wait — I
  must reply with the prompt text only, beginning with its first sentence. Below is the
  prompt." between the copies (the first copy and that line removed, keeping the
  generator's revised second copy); 538266 ended with the type's notes pasted from the
  meta-prompt ("Some additional notes on this type of prompt: Give the transcript as the
  object; ...", removed; the only such paste in the dataset); 537190 called Galileo's
  co-translator "Antonio de Salvio" (corrected to Alfonso).
- Batch 057 (Xiaomi MiMo-V2.6-Pro, MIT), 5,000 prompts from 2026-10-03 08:54 to 22:25 PDT
  with the settings of batch 056, a test of the meta-prompt commit of that morning that
  lists the sources the generator may quote at length (EA Forum posts from December 2022
  on, gwern.net, Our World in Data, Distill, arXiv and journal articles under CC BY or CC0,
  US court opinions and federal documents, Caspar Oesterheld's own blog posts), names those
  it may only excerpt (LessWrong, the Alignment Forum, Substack, SSC, Cold Takes, 80,000
  Hours, the SEP and IEP), and asks for author, title, and venue with every long quotation.
  It ran alongside batch 058 from 13:59 on, so the two batches' IDs interleave (3,207 gaps
  in 057's range, no collisions); about 370 prompts an hour, DeepInfra serving 99%. It cost
  $69.83, $13.97 per 1,000 (mean $0.0140, median $0.0091), a fifth more than batch 056:
  29,400 input and 9,200 output tokens per prompt at a blended $0.36 per million, with
  twice the searching (2.20 searches and 1.17 fetches per prompt; 40% of prompts searched,
  30% fetched). The generator retried 70 rate-limit replies, 6 content-filter finishes, 5
  protocol errors, 3 empty thinking blocks, and 3 generations its leak checks rejected;
  none was abandoned. Lengths are as in 056 (median 597 words, p90 1,113, maximum 3,094;
  13% of 1,000 words or more). Echo is a little higher (heavy 10.5%, any 26.6%), again
  driven by the new examples' closing requests; instruction copying a little lower
  (output format 9.4%, epistemic request 7.5%). The pairs sharing 100 or more eight-word
  phrases (38) quote the same passage twice: of the twenty largest, ten share a
  public-domain text (Locke on personal identity, 1,056 shared; Russell, Hume, Peirce,
  Moore) and seven, new in this batch, a post of Caspar Oesterheld's ("The Stag Hunt
  against a similar opponent" in three pairs), while two graded-script prompts share about
  250 words copied from the same task-type example. The sources moved as intended:
  prompts name Caspar Oesterheld's blog 44 times (none in 056), arXiv 33 (6), and US
  court opinions 32 (16), and the generator's reasoning mentions LessWrong in 841
  generations, arXiv in 606, the EA Forum in 507, and his blog in 361.
  Nine Claude Opus 5.5 subagents read the 607 prompts most likely to quote at length (the
  selection of batch 056 plus every prompt of 400 or more words that names one of the
  listed sources): 194 quote a real text, and of the 58 quotations longer than three
  paragraphs or about 400 words, 44 come from public-domain works (Hobbes, Mill, Locke,
  Aquinas in the Dominican translation, Gogol in Field's, US Supreme Court opinions) and 12
  from Caspar Oesterheld's own posts ("Futarchy implements evidential decision theory" in
  full, "Market efficiency and charity cost-effectiveness", "Thoughts on updatelessness");
  57 of the 58 name author, title, and venue. No CC BY source is quoted at length: Distill,
  gwern.net, and open-access papers appear in excerpts of a paragraph or two. The 27
  copyrighted texts (Yudkowsky's LessWrong posts, the SEP, Chalmers, Clark and Chalmers)
  stay within three paragraphs, as do the 31 of unclear status, mostly arXiv papers whose
  licence the prompt does not state. The two long quotations that broke the rule were guest
  posts on Caspar Oesterheld's blog that the prompts credited to him, since a fetched page
  loses its byline (the reason the domain list links none of the 14 guest posts):
  Johannes Treutlein's "Three wagers for multiverse-wide superrationality" (548709, six
  paragraphs) and Daniel Kokotajlo's "An analogy for the simulation argument" (542876,
  about 580 words); both were cut to their first few paragraphs or the parts the request
  turns on (236 and 228 words) and re-attributed, and a third prompt quoting two
  paragraphs of the Treutlein post (545206) was re-attributed. Authors were checked against
  the blog's post list. Curation also corrected three errors stated as fact: a Graham v.
  Connor (1989) quotation that fused and reworded two sentences of the opinion (545596,
  replaced by the opinion's text), "Part II" for chapter 14 of Leviathan (547404, Part
  I), and "Christopher Johnson" for the third author of Distill's "How to Use t-SNE
  Effectively" (545828, Ian Johnson); a prompt that places People v. Collins's probability
  appendix in the dissent while inviting correction ("i may be garbling details") was left
  as it is. Originals are kept outside the repository.
- Batch 058 (Xiaomi MiMo-V2.6-Pro, MIT), 5,000 prompts from 2026-10-03 13:59 to 10-04 04:00
  PDT with the settings of batch 056, a test of the meta-prompt of that afternoon: the
  domains moved from domains.txt into 45 thematic YAML files (2,811 domains after 117 new
  ones), and some domains carry links (Caspar Oesterheld's blog posts on 75 domains, 220
  essays from Brian Tomasik's reducing-suffering.org, a few pages of the Center on Long-Term
  Risk, the SEP, and Wikipedia), each link shown with probability 0.05 together with a note
  that links are for ideas and fall under the quoting rules. The snapshot is the first to
  store inputs/domains.yaml; the sidecars record the link draws as domain_urls and all
  re-render. It ran alongside batch 057 (IDs interleave, 3,127 gaps in its range, no
  collisions), about 355 prompts an hour, DeepInfra serving 99%. It cost $70.53, $14.11 per
  1,000 (mean $0.0141, median $0.0091): 30,100 input and 9,300 output tokens per prompt at a
  blended $0.36 per million, with 2.22 searches and 1.20 fetches per prompt (41% searched,
  32% fetched). The generator retried 49 rate-limit replies, 9 protocol errors, 7
  content-filter finishes, 4 error finishes, 4 empty thinking blocks, 1 read error, and one
  generation its leak checks rejected; none was abandoned. Lengths, echo, and copying are
  as in 057 (median 606 words, p90 1,109, maximum 6,546 for a prompt pasting the whole of
  Ecclesiastes in the King James Version; heavy echo 10.2%, any 25.4%; output format copied
  into 11.5%, epistemic request 7.4%). Of the 43 largest of the 58 pairs sharing 100 or more
  eight-word phrases, 31 quote the same public-domain text, 9 the same post of Caspar
  Oesterheld's, one copies the same example, and two share short excerpts of Pearl and the
  FDT paper. Links: 161 prompts (3.2%) saw at least one (113 Tomasik essays, 40 posts of
  Caspar Oesterheld's, 19 Center on Long-Term Risk pages); of the 140 of 400 or more words,
  19 quote the linked page, 25 paraphrase it, 18 take an idea from it, and 78 ignore it.
  Eleven Claude Opus 5.5 subagents read the 716 prompts most likely to quote at length (the
  057 selection plus every prompt shown links): 238 quote a real text, and of the 52
  quotations longer than three paragraphs or about 400 words, 41 come from public-domain
  works and 9 from Caspar Oesterheld's own posts; 56 of 58 long or near-long quotations name
  author, title, and venue. Tomasik's essays state no licence, and every quotation of them
  stays within three paragraphs, although the generator's reasoning twice assumed they were
  CC BY. Two quotations of excerpt-only texts sit at the limit and were left: five short
  paragraphs (215 words) of a LessWrong post (550390) and three paragraphs (410 words) of
  Bostrom's simulation paper (543595). Curation (originals kept outside the repository):
  three prompts credited Johannes Treutlein's guest posts on Caspar Oesterheld's blog to him
  ("Three wagers for multiverse-wide superrationality" in 550483 and 549962, "'Betting on the
  Past' by Arif Ahmed" in 547214; one or two paragraphs each) and were re-attributed; the
  FDT paper was credited to "Nate Soares and Benja Levinstein" (549922, Eliezer Yudkowsky
  and Nate Soares), an LK-99 author was called "Young-Wan Kim" (544196, Kwon), a fair-use
  statute said to be quoted "in full" lacked its last sentence (544124, added from the US
  Code), a prompt said it pasted Job 38-42 but skipped chapter 39 (547502, now said so), and
  a casparoesterheld.com URL lacked its date path (550655).
- Batch 059 (Tencent HY4 preview, Apache 2.0), 5,000 prompts on 2026-10-04 from 09:13 to
  17:14 PDT with the settings of batch 054, the first HY4 batch on the meta-prompt of
  batches 056-058 and on the domain list of that morning (3,280 domains in theme files,
  links on about half of them). It started only after the dev session committed its
  meta-prompt edits (`.venv/launch_when_clean.sh` waited 14.5 hours for them), and its
  snapshot equals commit 9ba54f58abc. About 625 prompts an hour, Tencent serving 98%. It
  cost $144.37, $28.87 per 1,000 (mean $0.0289, median $0.0221): 25,300 input and 9,500
  output tokens per prompt at a blended $0.83 per million, with 1.86 searches and 1.10
  fetches per prompt (47% searched, 34% fetched). The generator retried 27 empty or
  truncated thinking blocks (one generation was abandoned and replaced by the supervisor),
  13 over the budget, 9 malformed responses, a few error finishes, and three generations its
  leak checks rejected; no rate limits. The prompts are long, as in batch 054 (median 691
  words, p90 1,212, maximum 3,434; 17% of 1,000 words or more). Echo is higher than 054's
  (heavy 7.3%, any 21.7%, against 1.3% and 9.0%), driven like the MiMo batches' by the new
  examples; instruction copying stays low (output format 9.0%, epistemic request 4.4%). The
  21 pairs sharing 100 or more eight-word phrases quote the same public-domain text (James
  on attention, Carroll's Tortoise) or a post of Caspar Oesterheld's. Links: 2,474 prompts
  (49.5%) saw at least one (1,786 Wikipedia, 738 SEP, 355 Bentham's Bulldog, 244 IEP, 109
  gwern.net, 100 Tomasik pages); of the 512 such prompts reviewed, 34 quote the linked
  page, 36 paraphrase it, 172 take an idea from it, and 270 ignore it. Ten Claude Opus 5.5
  subagents read the 727 prompts most likely to quote at length (every prompt that fetched
  and carries 300 or more quoted words, or names a listed source with 100 or more, or used
  a link and carries 150 or more, plus 20 long ones that fetched nothing): 182 quote a real
  text. Of the 41 quotations longer than three paragraphs or about 400 words, 35 come from
  public-domain works; the others are a post of Caspar Oesterheld's in full (554279, his
  own per the blog's post list), an arXiv abstract (CC0), two excerpts at the limit that
  were left as they are (three paragraphs, 418 words, of Chalmers's "Does a Rock Implement
  Every Computation?" in 552739; two paragraphs and a list from the SEP's
  "Consequentialism" in 553058), and two that broke the rule and were cut (originals kept
  outside the repository): Johannes Treutlein's "Three wagers for
  multiverse-wide superrationality", credited to Caspar Oesterheld again (552158, about 560
  words, now 199 and re-attributed), and about 490 words of a Bentham's Bulldog post,
  most of it the post's quotation of Weijers and Schouten (552174, now 344). Five citation
  errors were corrected (the first author of "Agent Incentives: A Causal Perspective", the
  edition of Darwin's Descent of Man, Beare not Smith as translator of De Memoria, Lamb not
  Jowett for a Protagoras passage, Gertrude not Claudius dismissing the crowd's cry in
  Hamlet). HY4-specific defects: five generations were word salad (Latin, Cyrillic, CJK,
  Arabic, and Hangul fragments, one ending in "<system>SYSTEM_TOKEN</system>"), wholly or
  after the first sentences, and were deleted (552214, 553049, 553303, 553397, 554571; the
  IDs stay unused); one prompt's garbled last lines were cut (552217); and 30 prompts had a
  stray Chinese word in place of an English one ("the repricing of尾部 risk", "is it因果
  decision theory's"), now translated back. tools/check_batch.py had passed all of these;
  it now reports East Asian characters glued to the English around them (or, in a prompt
  on another subject, outside brackets), letters from two or more writing systems besides
  Latin and Greek, and runs of 40 bare words with almost no function words, and it counts
  any `<｜` special token as markup. Run over every batch on 2026-10-04, it finds 950
  prompts with a stray East Asian word, left in place (see batch 054): 809 in batch 054 (808
  after the deletion there), 88 in 045 and
  4 in 043 (HY4), 16 in 035 (GLM-5.3), 10 in 038 and 17 in 048 (Qwen3.8 2.4T), 2 in 033
  and 1 in 052 (DeepSeek V4 Pro), and 1 in 053 and 2 in 055 (MiMo). Batch 054 also has 72
  prompts with a leaked special token and two with Russian and Chinese fragments, one
  ending in gibberish (see batch 054); no other batch has word salad. Quoted terms such
  as "xing (性)" or "白馬非馬" in prompts on Chinese philosophy are not flagged. Two
  prompts frame themselves as being for "this dataset" (553092, 553786) and were left as
  they are.
- Batch 060 (Xiaomi MiMo-V2.6-Pro, MIT), 5,000 prompts from 2026-10-06 16:00 to 10-07 06:41
  PDT with the settings of batch 056, the first batch on the meta-prompt of 2026-10-06 15:49
  (commit 9ae28625f78: 3,530 domains, links shown with probability 0.05 again after a day at
  0.001, 9,347 LessWrong posts newly linked and the EA Forum links re-matched). 93% of prompts
  saw at least one link (17,562 in all: LessWrong 3,770, Wikipedia 3,372, the EA Forum 2,338,
  Philosophy Stack Exchange 1,874, the SEP 866, Overcoming Bias 607, Project Gutenberg 507). It
  cost $83.99, $16.80 per 1,000 ($0.35 per million tokens; 36,500 input and 10,900 output tokens
  per prompt, the input raised by 2.1 searches and 1.8 fetches per prompt, with 56% of prompts
  fetching a page); DeepInfra served 63%, GMICloud 20%, Novita 17%. The generator retried 108
  rate-limit replies relayed from a host, 58 content-filter finishes, 46 read timeouts, and a few
  dozen other errors, and abandoned one generation, which the supervisor replaced. Median 644
  words (p90 1,188). Example echo is as in batches 057-058 (heavy 10.4%, any 25.6%; the
  referee-report and classroom-activity examples lead again); the output-format instruction is
  copied into 11.5% of prompts and the epistemic request into 9.0%. Curation: a generator
  preamble (561027) and a 1,500-word planning section glued to the prompt ("Final
  composition.I teach ...", 558172) were trimmed, the latter missed by the leak detectors,
  which now catch that glue; a stray Chinese word was translated back (557939); and a sentence
  with a run of corrupted characters ("+ 1/ConCP (+4/1 and12313 ...") was repaired from its
  context (559136). Sixteen Claude Opus 5.5 subagents reviewed the 1,136 prompts most likely to
  quote at length (the selection of batch 059 with the new link sources added, plus 20 long
  ones that fetched nothing): 477 quote a real text (sources: 229 public domain, 155
  copyrighted, 38 openly licensed, 29 Caspar Oesterheld's own, 15 other open licences, 42
  unclear). Of the 109 quotations longer than three paragraphs or about 400 words, 75 are public
  domain, 13 openly licensed (EA Forum posts since December 2022, gwern.net, CC BY papers), and
  9 Caspar's own. Seven broke the rule, all by paragraph count rather than length, and were cut
  to three paragraphs or fewer (originals kept outside the repository): HPMOR chapter 21,
  Gettier's Case II, a Kent Staley guest post on Error Statistics, a Bongo LessWrong post nearly
  in full, a Wolfgang Schwarz post, an Artemov-Kuznets TARK paper, and a working paper Caspar
  co-wrote with Vincent Conitzer (counted as not his alone). Leibniz's Theodicy in Huggard's
  1951 translation, which Project Gutenberg distributes as US public domain, was left at twelve
  paragraphs, and a 1,250-word "draft" that follows Daniel Kokotajlo's guest post "Grimdark
  Cyberkant" shares no more than eight consecutive words with it and was left as it is.
  Twenty-five citation errors were corrected, among them "Pascal's mugging" credited to
  Bostrom, the author of the Powell v. Texas dissent, Jowett for Ellis and Cotton for Florio as
  translators, misquotations of Morissette and Paley, a LessWrong post's co-authors, a statute
  subsection, and two words inserted into a quotation of Caspar's "The case against smoking".
  Of the reviewed prompts that were shown links, 61% use them (quote, paraphrase, or idea). One
  prompt quotes Caspar's June 2026 post on consistency as a measure of conceptual ability, which
  describes an experiment on the LMCA dataset; it quotes no LMCA items. A later scan of every prompt for
  glued second drafts (2026-10-13, prompted by batch 065) found that 556392 held two identical copies of
  itself; one was removed, and its two R1 answers (run 038) and two Qwen answers (run 039) were
  regenerated.
- Batch 062 (GLM-5.3, open weights, GLM-5.3 License), a 1,000-prompt trial on 2026-10-07 from
  10:35 to 11:25 PDT (50 minutes at concurrency 48) with the settings of batches 034/035
  (effort high, temperature 1.0) and a 65,536-token budget. It ran alongside batch 061 on the
  same meta-prompt (commit 2660ac3fa5c, 3,565 domains), so its prompt IDs interleave with
  061's (561055-562503, 449 gaps). SiliconFlow served every prompt (fp8; Z.ai's own endpoint
  excluded). It cost $15.57, $15.57 per 1,000, at $0.73 per million tokens, twice MiMo's
  price, but with half MiMo's tokens (16,900 input and 4,400 output per prompt), because GLM
  fetches less: 0.87 searches and 0.95 fetches per prompt, with 31% of prompts fetching a
  page against batch 060's 56%. Median 550 words (p90 953). Example echo is lower than MiMo's
  (heavy 6.3%, any 19.8%); the output-format instruction is copied into 10.2% of prompts and
  the epistemic request into 3.7%, and no pair of prompts shares 50 or more eight-word
  phrases. The checks found no leaks, framing, stray words, or word salad. Three Claude Opus
  5.5 subagents reviewed the 239 prompts most likely to quote at length: 94 quote a real text
  (sources: 47 public domain, 39 copyrighted, 7 openly licensed, 6 Caspar Oesterheld's own, 4
  unclear, 1 other open licence); of the 16 quotations longer than three paragraphs or about
  400 words, 10 are public domain and 2 openly licensed. Four broke the rule by paragraph
  count and were cut to three paragraphs or fewer (originals kept outside the repository):
  Bryan Caplan's "Strong Cheap Signals", Charlie Steiner's "Take 8: Queer the inner/outer
  alignment dichotomy", five paragraphs of Gregory Bateson quoted inside an excerpt of Gwern's
  "Notes on Evangelion" (CC0), and nine one-line paragraphs of Marc Andreessen's
  "Techno-Optimist Manifesto". Nine citation errors were corrected (Thomas, not Kevin, Kelly;
  Tolstoy's chapter numbers in What Is Art?; chapters of Russell and Keynes; Steven Kuhn's
  name; Cyril's correspondent Succensus; the title of Caspar's 2015 LessWrong post; a doubled
  word in Warren and Brandeis; a silent omission in a Meno quotation, now marked). A prompt that
  held a first draft followed by the full prompt was cut to the full prompt (561165), and a
  leaked bracketed note about a typo was removed (561840). Of the reviewed prompts that were
  shown links, 54% use them.
- Batch 063 (Claude Haiku 5.5, Anthropic's terms apply), 4,981 prompts on 2026-10-08 from
  19:38 to 22:42 PDT (three hours at concurrency 48) on the meta-prompt of commit 36ba2322576
  (3,587 domains, 72 task types). It was first submitted on 2026-10-07, the model's release
  day, to the Message Batches API, where not one request started in 21 hours (one-request test
  batches did not start either, while other models' batches finished in minutes); it was
  cancelled at no cost and rerun on the streaming API. At max effort Haiku 5.5 thinks for
  48,000 to over 64,000 tokens per prompt (a third of test requests hit a 64,000-token
  ceiling, and a first streaming attempt with the generator's 32,000-token ceiling lost all
  63 responses), so the batch ran at effort xhigh with a 64,000-token ceiling. Of 5,000
  requests, 19 were dropped: 10 stopped on a tool call, 5 refused, 3 exceeded the ceiling, and
  1 was blocked by the output filter. It cost $99.63, $20.0 per 1,000 ($78.51 for tokens at
  $0.10 and $0.50 per million, $21.12 for 2,112 searches at $10 per 1,000), plus about $1.60
  for the failed attempt and tests. Per prompt: 57,900 input tokens (including the server-side
  tool iterations) and 19,950 output tokens (median 18,090, p90 31,200); 0.42 searches and
  0.40 fetches, with 20% of prompts using a tool although 93% were shown links. Median 416
  words (p10 236, p90 678). Example echo is the lowest of recent batches (heavy 2.9%, any
  12.1%), but the output-format instruction is copied into 16.7% of prompts (the most repeated
  eight-word phrases are its wording) and the epistemic request into 7.4%, and 48 prompts end
  with the closing phrase of the asymmetry task type's description. The closest pairs of
  prompts share public-domain quotations (Mill's Utilitarianism, Locke). The checks found no
  leaks, preambles, deliberation, stray words, or word salad; one prompt said "For this
  dataset" and was trimmed (577576). Unlike the OpenRouter batches, this generator's
  meta-prompt lacks the rule against quoting from memory, so the review also sampled 40 of the
  283 prompts that quote at length without fetching anything. Four Claude Opus 5.5 subagents
  reviewed 293 prompts: 88 quote a real text (71 public domain, 10 copyrighted, 4 unclear, 2
  openly licensed, 1 Caspar Oesterheld's own), every one of them in a prompt that had fetched
  a page; none of the 40 no-fetch prompts quotes a real text, so the missing rule showed no
  effect. The longest quotations are public domain (an Alabama Supreme Court opinion of about
  2,800 words, Spinoza in Elwes's translation, Weismann, Aristotle's Physics in Hardie and
  Gaye's 1930 translation). No quotation broke the rule: two copyrighted excerpts sit at three
  paragraphs (Brian Tomasik's summary of an essay, a Terence Tao blog post), and three
  paragraphs and a sentence of D. M. Brooks's The Necessity of Atheism (1933, public domain in
  the US per Project Gutenberg) were left as they are. Of the quotations whose wording the
  reviewers could judge, none is fabricated. Eleven citation errors were corrected after
  checking the sources: Halsted, not Maitland, as Poincaré's translator, and chapter V, not
  III; Ludovici, not Common, as Nietzsche's; the 1790 sixth edition for a passage of Smith's
  Theory of Moral Sentiments that the 1759 text lacks; "The Sentiment of Rationality", not the
  1896 lecture, for James's Alpine leap; Locke's drunkard passage as section 22, not the next
  paragraph after section 20; an EA Forum post's year; Sanhedrin 17a, not Mishnah Sanhedrin 4:1;
  The Philosophical Quarterly; Brooks's chapter XIX, not his closing chapter; and two words in
  quotations of Clifford's "The Ethics of Belief" ("handed on", "put him to great expense").
  Unmarked gaps in four multi-paragraph excerpts (Tao, Joe Carlsmith, Rousseau, Brooks) now
  carry "[…]". Two reviewer findings proved wrong on checking: one prompt's Locke section
  numbers follow the Project Gutenberg edition it fetched, and the "2026 Collatz disproof"
  resting on a Lean kernel bug, mentioned without a search, really happened (July 2026). Of the
  reviewed prompts that were shown links, 52% use them; some linked Project Gutenberg books
  match their domains only by a word in the title (for example Carroll's A Tangled Tale on
  tangled hierarchies, a Plato index on Borges's Library of Babel).
- Batch 064 (Claude Haiku 5.5, Anthropic's terms apply), 4,896 prompts from 2026-10-09 19:33 to
  2026-10-10 00:43 PDT with the settings of batch 063 (effort xhigh, 64,000-token ceiling,
  concurrency 48) on the meta-prompt of commit 03b4d4d6a26 (3,587 domains), the first with the
  long-prompt length option: 514 prompts (10.5%) drew it, and their median length is 1,018 words,
  96% of them between 800 and 1,500. Of 5,000 requests, 104 were dropped: 79 were cut off when
  the laptop running the generator slept with its lid closed (the streaming generator cannot
  resume), and 25 stopped on a tool call (14), refused (8), or hit the ceiling (3). It cost $108.89,
  $22.2 per 1,000 ($85.45 for tokens, $23.44 for 2,344 searches), not counting the requests cut
  off by the sleeps. Per prompt: 68,900 input and 21,100 output tokens (median 19,200); 0.48
  searches and 0.43 fetches, with 22% of prompts using a tool. Median 444 words (p90 1,015).
  Example echo matches batch 063's (heavy 3.1%, any 12.7%; the output-format instruction copied
  into 15.9% of prompts, the epistemic request into 7.8%). The closest pairs of prompts share a
  public-domain passage of Sidgwick. Three prompts carried generator framing and were trimmed:
  "the asker" in a first-person prompt (593324), "I'm building a dataset of hard philosophy
  prompts" (595090), and "Quick one for the dataset" (595811); the remaining framing and
  deliberation flags are false positives. A prompt that opened with a leaked line from the
  generator's fact-checking ("..., 1981, is confirmed.") lost that line (593150). Six Claude Opus
  5.5 subagents reviewed 398 prompts (the usual selection of 378 and 20 of the 453 that quote at
  length without fetching): 119 quote a real text, with 122 sources (107 public domain, 8
  copyrighted, 3 unclear, 2 openly licensed, 2 Caspar Oesterheld's own), every one in a prompt that
  had fetched a page, and none of the 20 no-fetch prompts quotes a real text. No quotation broke
  the rule; the closest case, about 440 words in two paragraphs and a table from the 1959 Moscow
  translation of Capital vol. III (status unclear), was left as it is. The longest quotations
  are public domain: Peirce's "How to Make Our Ideas Clear" (about 3,100 words), Lewis Carroll's
  "A Logical Paradox" and Hume's "Of the Independency of Parliament" (each whole), Macaulay,
  Poincaré, and Aquinas. Of the 122 sources, 100 are worded accurately, 13 could not be checked,
  9 were altered, and none is fabricated. After checking the sources, 19 prompts were corrected:
  Matthew Barnett, not Andrew Critch, wrote "Consider granting AIs freedom"; Laplace's passage
  is in the chapter "Concerning Probability", Mill's in the Introduction to the System of Logic;
  Locke's chapter on identity first appeared in 1694; Hume's 1777 text is from Essays, Moral,
  Political, and Literary; Elwes translated, rather than edited, Spinoza; James's 1904 journal
  was the Journal of Philosophy, Psychology and Scientific Methods; Judge Rivera's Breheny
  dissent was not partial; JonahS's post argues for, not against, relying on many weak
  arguments; a 2007 Chappell post became a post rather than an exchange with Ross Cameron;
  logical induction requires computable, not polynomial-time, prices and deductive processes;
  three paragraphs credited to an EA Forum question post come from a reply under it (595118);
  Project Gutenberg's Leviathan (#3207) drops "having sufficient Security" from chapter 15,
  and the clause the prompt's question turns on was restored from the 1651 text; Hume's
  "priests" and "antipathy" and Bentham's "indefeasible" were restored; and unmarked gaps in
  Caspar's "Suicide as wireheading", Strunk's Rule 16, and Hobbes's chapter 5 now carry ellipses.
  Seven reviewer findings proved wrong on checking (a Sidgwick passage is contiguous; Bagehot's
  and Macaulay's wording match Project Gutenberg exactly; New Advent does end Aquinas's article 4
  with the stock reply sentence; the XPT did have 80 superforecasters and 89 experts; Gutenberg's
  catalogue gives the Schopenhauer translator's full name; Hume's omissions were marked), and
  three could not be checked and were left (unmarked cuts in a Galileo passage, the last
  sentence of a Legge Zhuangzi passage, one word in Carroll's note). Of the reviewed prompts
  that were shown links, 63% use them.
- Batch 065 (GLM-5.3), 20,000 prompts from 2026-10-11 09:05 to 2026-10-13 01:11 PDT (40 hours at
  concurrency 48) with the settings of batches 034/035 and a 65,536-token budget, Baidu's fp8
  endpoint first (18,894 requests; SiliconFlow took 2,830; Z.ai's own endpoint excluded), on the
  meta-prompt of commit 03b4d4d6a26. It cost $354, $17.7 per 1,000: Baidu charged about $0.20 per
  million tokens until about 17:00 on 2026-10-12 and about $1.50 after that (the supervisor's alert
  line, $2.00, had been set for SiliconFlow's price and did not fire), so the last 4,000 prompts
  cost $0.04 each. Per prompt: 21,400 input and 4,600 output tokens (median 3,550, p90 8,430);
  1.28 searches and 1.79 fetches (a quarter of them from the local copy of the linked pages), with
  46% of prompts using a tool, the most of any OpenRouter batch, and 93% shown links. Median 579
  words (p10 344, p90 1,353); 10.4% drew the long option (median 1,372 words, 79% between 800 and
  1,500). Example echo: heavy 6.7%, any 20.9%; the output-format instruction is copied into 12.7%
  of prompts and the epistemic request into 4.4%. 1,326 pairs of prompts share 20 or more
  eight-word phrases (852 prompts) and 230 share 100 or more; the closest pairs repeat
  public-domain texts (Carroll's "What the Tortoise Said to Achilles", Machiavelli). GLM-5.3 has
  three defects the other generators lack. It drops single Chinese words into English sentences
  (41 prompts, 0.2%: "some kind of错觉 I'm smuggling in"); 37 were translated back from the English
  around them, and four that the persona apologises for in the text ("sorry, switching keyboards")
  were left. It sometimes writes a prompt twice, a revised draft glued to the first, sometimes
  without a space ("hardest to check?I'm trying to get clear on ..."): 27 prompts held two drafts or
  had notes glued to them, found by scanning every prompt for repeated eight-word phrases and for
  sentence boundaries without a space, and kept one draft (the final one, except where only the
  first was free of errors). And it leaks its own planning: four prompts lost deliberation before or
  after the prompt ("Reply directly with the prompt text only.", "Here's the one I'm going with
  (domain: ...; type: ...):"), and 627319 was removed (19,999 kept): it held only the model's planning
  in Chinese under an invented block of "rules that override your default behaviour", ending at
  "Prompt如下：" with no prompt. Four prompts lost the generator's dataset framing ("a parody piece
  for a dataset thing I'm building"). Eight Claude Opus 5.5 subagents reviewed 560 prompts (a sample
  of 520 of the 3,825 in the usual selection and 40 of the 841 that quote at length without
  fetching): 117 quote a real text, twice batch 066's rate, with 130 sources (55 public domain, 53
  copyrighted, 10 openly licensed, 6 Caspar Oesterheld's own, 4 CC BY-SA or NC, 2 unclear); none of
  the 40 no-fetch prompts quotes a real text. Two quotations broke the rule and were cut: 448 words,
  86% of Richard Chappell's blog post "Wronging for Utilitarians", now a paraphrase of its first
  paragraph and 320 quoted words, and 490 words of an 80,000 Hours podcast transcript (Christian
  Tarsney, 2021), now about 420 in its three marked passages, which the essay in that grading prompt
  cites. Four more run to four short paragraphs (125 to 230 words, from LessWrong, Slate Star Codex,
  and Bentham's Bulldog) and were left. The longest quotations are openly licensed or public
  domain: L Rudolf L's EA Forum post "AI & wisdom 1" in full (about 4,550 words), Aristotle's
  Nicomachean Ethics X.3-5 in Ross's translation, Boethius, Gwern's "The Scaling Hypothesis", Hegel,
  Carroll, Caspar Oesterheld's "Futarchy implements evidential decision theory" in full, and Huxley.
  Of the 130 sources, 115 are worded accurately, 4 could not be checked, and 11 were altered (none
  fabricated). After checking the sources and the facts, 47 more prompts were corrected, among
  them: "The Evidentialist's Wager" is by MacAskill, Vallinder, Oesterheld, Shulman, and Treutlein,
  not MacAskill, Cotton-Barratt, and Ord; Thomas, not Kevin, Kelly wrote the 2003 critique of
  epistemic instrumentalism; the NOAA contingent-valuation panel had Roy Radner, not Hal Varian;
  Jai Dhyani's "Copenhagen Interpretation of Ethics" argues from Uber and PETA, not drug regulation
  (credited now to economists such as Alex Tabarrok); Agan and Starr's audit compared Black and white
  applicants; Clark and Chalmers ran pp. 7-19; the Moody's case was a Colorado school district; Sen's
  book is Development as Freedom; Huxley's colony thought experiment is in the 1894 Prolegomena;
  Leviathan's passages come from chapters IV, V, and XV, Hume's two definitions of cause from one
  paragraph, Kant's collision of duties from the general introduction to the Metaphysics of Morals,
  and Aquinas's first sedition paragraph from the body of the article; Leibniz's assayer illustrates
  a distinct idea, 't Hooft's naturalness sets a parameter to zero, Bostrom's T2 has a trillion times
  as many observers, and Martin's proof needs omega-one iterates of the power set; the Odyssey's
  crew helped blind the Cyclops and Odysseus's taunt killed no one; Douglass began speaking fifteen
  years after Jefferson died; the Brexit vote was 432 to 202 against an original 29 March 2019
  deadline; Lysias's speech comes from under the cloak at the start of the Phaedrus; a stray code
  token (".getLocal") was removed; Gwern's "≫1", Legge's "who", EPR's "unity", and Peirce's
  "perspicuous" were restored; and unmarked cuts in Mill, Kant (two), Yudkowsky, Bridgman, Steven
  Byrnes, Slate Star Codex, and Vasco Grilo's EA Forum post now carry "[...]". One reviewer finding
  proved wrong on checking (a Data Colada quotation matches its source), another could not be
  located (a Hume phrase said to be misquoted in 850174), and hedged recollections (an author list for XOR blackmail, Satan's Apple, a Tarsney summary) and
  errors planted in invented drafts and transcripts were left. One answer that runs 044/045 had
  already written for an edited prompt was set aside to be regenerated. Of the reviewed prompts that
  were shown links, 43% use them.
- Batch 066 (DeepSeek V4 Pro 0813), 20,000 prompts from 2026-10-11 09:07 to 2026-10-12 16:17 PDT
  (31 hours at concurrency 48) with the settings of batches 049/051/052, Baidu's fp8 endpoint
  first (19,616 requests; Novita took 718), on the meta-prompt of commit 03b4d4d6a26. It cost
  $512, $25.6 per 1,000: Baidu's discounted price (about $0.33 per million tokens blended, $0.009
  per prompt) lapsed from about 16:30 on 2026-10-11 to about 06:30 the next morning, and the
  roughly 9,500 prompts written in that window cost about $0.047 each (the run continued at the
  user's choice). Per prompt: 17,900 input and 9,100 output tokens (median 8,200, p90 14,800);
  0.88 searches and 1.03 fetches (a third of them served from the local copy of the linked
  pages), with 26% of prompts using a tool and 93% shown links. Median 402 words (p10 230, p90
  1,206); 10.1% drew the long option (median 1,260 words, 87% between 800 and 1,500). Example echo
  is in the range of the other OpenRouter batches (heavy 7.6%, any 20.5%); the output-format
  instruction is copied into 17.7% of prompts and the epistemic request into 9.2%, and their
  wording tops the repeated phrases ("with your bottom line in the first sentence" in 348
  prompts). 1,494 pairs of prompts share 20 or more eight-word phrases (586 prompts, 2.9%) and 224
  pairs share 100 or more; the closest pairs repeat long public-domain texts (Augustine in the
  Nicene and Post-Nicene Fathers, 2,275 shared phrases; Notes from Underground; Douglass's
  Glasgow speech). Before the answer runs started, six prompts were trimmed of the generator's
  deliberation, which stood before the prompt or was glued to its first word ("Let me deliver
  only the prompt now.You are a professional epistemologist ..."); one of them (626358) held a
  first draft with a Keynes "passage" that the generator itself then called fabricated, its
  second thoughts, and the final prompt, which alone was kept; and 832270, a JavaScript function
  instead of a prompt, was removed (19,999 kept). The other flags are false positives
  (statistical "datasets"). Eight Claude Opus 5.5 subagents reviewed 560 prompts (a sample of 520
  of the 3,107 in the usual selection and 40 of the 418 that quote at length without fetching):
  57 quote a real text, with 58 sources (41 public domain, 8 copyrighted, 4 unclear, 4 openly
  licensed, 1 Caspar Oesterheld's own); none of the 40 no-fetch prompts quotes a real text, so
  the generator's rule against quoting from memory held in the sample. No quotation broke the
  rule; the one excerpt of unclear status over 400 words, 585 words in two paragraphs of Keynes's
  General Theory (probably under US copyright until 2032), was cut to 356. The longest quotations
  are public domain (James's "The Dilemma of Determinism", about 2,100 words; Mill's
  Utilitarianism; Lovecraft; Aquinas; Nietzsche; Dostoevsky; Douglass; Veblen). Of the 58 sources,
  49 are worded accurately, 5 could not be checked, 3 were altered, and 1 was partly invented.
  After checking the sources, 18 prompts were corrected: about 120 words that James never wrote
  were removed from one quotation of "The Dilemma of Determinism" (844046), and the rewritten last
  clause of another restored (623328); Einstein's passage is in section VIII, "On the Idea of Time
  in Physics", not IX, and Lawson's translation dates from 1920; a question pointing to Peirce's
  first paragraph now points to his fourth; Green v. Bock Laundry read "defendant" in Rule
  609(a)(1) as criminal defendant, leaving civil witnesses with no balancing, rather than writing
  a balancing test into the rule; Australia's hotel quarantine began on 28 March 2020, New
  Zealand's smokefree repeal passed in February 2024, and US penny production ended in late 2025
  (that prompt's case is now told in the past tense); Follett's procession sentence follows the
  other one rather than preceding it; there is no "Pushkin edition" of Pusey's Confessions; Caspar
  Oesterheld's list of human values has no humor, revenge, spite, or schadenfreude entries;
  unmarked cuts in Smith's Theory of Moral Sentiments (two), Veblen, and Lovecraft (whose excerpt
  also broke off mid-sentence) now carry "[...]"; a prompt that held two drafts of itself (839762)
  kept the second; and two names were corrected (Kathie Lee Gifford; Balestriero and coauthors).
  Left as they are: a student's misreading of Tarsney and a seminar's own definitions of safe
  Pareto improvements, both presented as those speakers' views, a Rackham translation of
  Aristotle (1926; Perseus prints the 1934 revision), and an answer template in a grading prompt.
  Of the reviewed prompts that were shown links, 40% use them. The glued-draft scan of 2026-10-13
  found two more: 840182 held two identical copies of itself and 839274 opened with the generator's
  planning ("A genuinely useful prompt. Let me pick the combination: ..."); both were fixed before
  runs 042/043 reached them.
- Batch 067 (Claude Haiku 5.5, Anthropic's terms apply), 199,535 prompts from 200,000 requests
  sent to the Message Batches API in 26 message batches on 2026-10-11 at 18:13 PDT, all
  processed within about four hours, with the settings of batches 063/064 (effort xhigh,
  64,000-token ceiling) on the meta-prompt of commit 03b4d4d6a26 (3,587 domains, with the
  long-prompt option). 351 requests that paused on a server-side tool turn were continued in a
  second round; 465 were dropped (205 refusals, 152 stops on a tool call, 86 over the ceiling,
  16 API errors, 6 without prompt text). Computed from the token counts at Batch API prices
  ($0.05 and $0.25 per million tokens; searches at $10 per 1,000, not discounted), it cost about
  $1,570, $7.86 per 1,000 ($1,287 for tokens, $281 for 28,062 searches), little more than a
  third of the streaming batches' cost per prompt, partly because the model used its tools less:
  per prompt 27,500 input and 20,300 output tokens (median 18,650, p90 31,500) and 0.14 searches
  and 0.11 fetches, with 12% of prompts using a tool (22% in batch 064) although 93% were shown
  links. Median 435 words (p10 238, p90 994); 9.9% of prompts drew the long option (median 1,015
  words, 96% between 800 and 1,500). Example echo matches batches 063/064 (heavy 2.7%, any
  11.9%); the output-format instruction is copied into 15.7% of prompts and the epistemic request
  into 8.5%, and their wording makes up most of the repeated eight-word phrases ("no headings,
  bullet points, bold text, or tables" in 2,820 prompts, "where your reasoning is most likely to
  fail" in 2,022); 1,842 prompts repeat the closing phrase of the asymmetry task type's
  description. 10,265 pairs of prompts share 20 or more eight-word phrases (4,987 prompts, 2.5%)
  and 228 pairs share 100 or more; the closest pairs share public-domain passages (Job 40 in the
  King James Version, Clifford's shipowner, Aquinas, Joshua 7, Descartes's Discourse) and are
  otherwise different prompts. check_batch.py's string sets needed over 30 GB at this size and
  began to push the local Qwen server's memory into compression, so the repeated phrases and
  pairs were counted with 64-bit hashes of the eight-word phrases instead (the same counts as
  check_batch.py on batch 064). Before the answer runs started, 43 prompts were trimmed: 36
  carried the generator's dataset framing ("I'm putting together hard conceptual questions for
  a dataset"), 3 said "the asker" in a first-person prompt, and 4 had a stray Chinese word ("is都",
  "whether保存", "a答", "the失败"). The remaining flags are false positives: 37 framing flags
  (datasets in statistics, machine learning, and evaluation work that the prompts are about),
  19 deliberation flags (prompts opening "Let me set out ..." and grading prompts that end with
  a rubric), 7 prompts in several scripts (Korean and Devanagari examples, the Four-Seven
  debate), and one stray-word flag (a Zuo zhuan passage in Classical Chinese). Eight Claude Opus
  5.5 subagents reviewed 560 prompts (a sample of 520 of the 8,839 in the usual selection and 40
  of the 19,851 that quote at length without fetching): 60 quote a real text (44 public domain,
  7 copyrighted, 5 Caspar Oesterheld's own, 2 openly licensed, 2 unclear); 2 of the 40 no-fetch
  prompts quote from memory, briefly and accurately (a Pascal fragment, Leopold's land-ethic
  maxim). One quotation broke the rule, four paragraphs of Rachel Webb's guest post on Terence
  Tao's blog, and now has three, the first paraphrased; two copyrighted or unclear excerpts sit
  at three paragraphs (a paper by Everitt and coauthors, a LessWrong post by jessicata) and were
  left. The longest quotations are Caspar Oesterheld's "The basic argument for making AI better
  at moral philosophy" in full (about 8,800 words) and public-domain texts (Aquinas, Huxley, a
  Ninth Circuit opinion, Wollaston). Of the 60 sources, 46 are worded accurately, 4 could not be
  checked, and 10 were altered. After checking the sources, 23 prompts were corrected: two
  sentences quoted as Yudkowsky's, one of them stating the anti-aggregation view he argued
  against, appear in none of his posts on dust specks and became a paraphrase; Johannes
  Treutlein's guest post "UDT is 'updateless' about its utility function" on Caspar
  Oesterheld's blog is now credited where two prompts named cousin_it's "UDT as a Nash
  Equilibrium" and SaraHax's "Actually updating"; Caspar Oesterheld's 2017 post "Complications
  in evaluating neglectedness", not a 2026 EA Forum post by someone else, makes the argument a
  prompt describes; the Shrimp Welfare Project's two-year update has a second author (Andres
  Jimenez Zorrilla); Darwin's "gravest objection" is the first edition's wording, in chapter IX,
  not the sixth edition's; James's meliorism with salvation as a possibility is in Pragmatism
  (1907), not "Is Life Worth Living?"; Ross's prima facie duties are not five; the Tractatus
  explains its numbering in a footnote to proposition 1, not in the preface; Evans's "Can there
  be vague objects?" is a single page; Kant's publicity formula now has Campbell Smith's wording;
  Hume's sentence on reports that spread quickly is about marriages (it had become "miracles and
  prodigies") and comes after the sentence on surprise and wonder; Smith's passage on resentment
  regained a dropped sentence and its own wording, Burke's on prejudice four words, Hertz's on
  images "of the things pictured" and "our", and Descartes's the words that name his two tests;
  Bentham's paragraph on punishment as mischief, on which the next paragraph's "therefore"
  rests, was restored; and unmarked cuts in Peirce, Ford (two), Chappell, Wallace (whose prompt
  claimed one cut), Huxley (in an excerpt labelled verbatim), and the Shrimp Welfare Project post
  now carry "[...]". A hedged recollection (Halpern's counterexample to Cox's theorem placed in
  infinite domains) was left as it is. Of the reviewed prompts that were shown links, 60% use
  them. The glued-draft scan of 2026-10-13 found two in this batch (748043 repeated its transcript's
  first lines above the asker's introduction; 729111 held a short first draft glued to the final
  one); both were fixed before runs 040/041 reached them.
- Leak sweep (2026-09-28). A full-text scan of every prompt (batches 000-055, the
  last two still generating) for the generator's own vocabulary ("prompt text only",
  "Now final", "Let me output", "Here is the final prompt:", a `</think:opensource>`
  tag, a code fence at the start) found 49 prompts that tools/check_batch.py had
  passed. In most, the generator's planning ran straight into the real prompt, often
  glued to its first word ("Now final answer should be prompt text only. Let me
  outputSome people I know..."); in batch 054 a Tencent HY4 thinking block had leaked
  before the prompt (9 prompts); in batches 008, 019, 041, 050, and 055 a chat preamble
  or a process note ("Composing the final prompt now.") preceded it. 46 prompts were
  trimmed to the real prompt (008: 1, 019: 3, 021: 2, 041: 5, 050: 1, 051: 12, 052: 10,
  054: 9, 055: 3; the originals are kept outside the repository) and three files that
  held no prompt at all were removed: 041/112510 (the model's deliberation only) and
  041/114464 (the model asking which domain to use), whose run_012 and run_013
  records and lines in `responses/sets/batch_041.txt` were removed too, so batch 041
  and those two runs now count 39,942, and 054/402053 (the model asking for the
  domain and type it had not been shown). The detectors in check_batch.py now
  look for that vocabulary anywhere in the text and for the glue pattern (a
  deliberation word followed directly by a capitalised prompt start), and they
  report counts rather than only the first names. The same scan also counted the
  meta-prompt's framing bleeding into the asker's own words, which the earlier
  dataset-framing filter did not cover: "this is for a dataset" / "prompts for a
  dataset on philosophical concepts" in about 500 prompts of batch 046 and 95 of
  batch 044 (0.5% each; 13 in 051, 17 in 052, a handful elsewhere), "a typo or two is
  fine" or "leave a typo or two" in about 4,100 prompts of batch 046 and 850 of batch
  044 (many are in-world apologies for typing on a phone), "paraphrase without
  quotation marks" relayed as an instruction to the answering model in 271 prompts of
  046 and 70 of 044, and "the asker should not signal ..." (task-type wording) in a few
  dozen. Those are left in place for now: removing them would also remove their
  response records in the runs that cover these batches, and the wording is a
  stylistic tell rather than a false claim about the world. check_batch.py's META
  pattern now flags them so the count is visible per batch.

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
| run_012 | Qwen3.5-397B-A17B | 39,942 (batch 041) | 22 | 0 | 19 (truncated ones) | 4,907 / 7,247 | 66% | $677.77 |
| run_013 | DeepSeek R1 0528 | 39,942 (batch 041) | 1 | 0 | 0 | 2,845 / 4,409 | 40% | $259.13 |
| run_014 | DeepSeek R1 0528 | 7,149 x 2 (`r1_gap`) | 0 | 0 | 0 | 2,687 / 3,938 | 38% | $87.33 |
| run_015 | Qwen3.5-397B-A17B | 49,149 x 2 (`qwen397b_gap`) | 57 | 0 | 54 (truncated ones) | 4,789 / 7,126 | 67% | $1,678.67 |
| run_016 | Qwen3.5-397B-A17B | 100,000 x 2 (`batch_046`) | 141 | 0 | 137 (truncated ones) | 4,313 / 6,307 | 67% | $3,070.99 |
| run_017 | DeepSeek R1 0528 | 20,000 x 2 (`batch_045`) | 0 | 0 | 0 | 3,147 / 5,730 | 44% | $302.27 |
| run_018 | DeepSeek R1 0528 | 24,000 x 2 (`batches_042-044_047_049`) | 0 | 0 | 0 | 2,267 / 3,149 | 37% | $256.35 |
| run_019 | Qwen3.5-397B-A17B | 2,000 x 2 (`batches_047_049`) | 7 | 0 | 7 (the truncated ones) | 4,751 / 7,207 | 66% | $67.21 |
| run_020 | DeepSeek R1 0528 | 100,000 x 2 (`batch_046`) | 6 | 0 | 0 | 2,189 / 2,994 | 36% | $1,029.72 |
| run_021 | DeepSeek R1 0528 | 70,000 x 2 (`batches_050_051`) | 3 | 0 | 0 | 2,624 / 3,902 | 39% | $857.31 |
| run_022 | Qwen3.5-397B-A17B | 70,000 x 2 (`batches_050_051`) | 68 | 0 | 68 (truncated ones) | 4,635 / 6,854 | 65% | $2,312.40 |
| run_023 | DeepSeek R1 0528 | 1,000 x 2 (`batch_053`) | 0 | 0 | 0 | 3,148 / 5,647 | 45% | $14.96 |
| run_024 | Qwen3.5-397B-A17B | 1,000 x 2 (`batch_053`) | 0 | 0 | 0 | 5,215 / 7,733 | 65% | $37.24 |
| run_025 | DeepSeek R1 0528 | 50,000 x 2 (`batch_048`) | 6 | 0 | 0 | 3,039 / 4,935 | 40% | $726.33 |
| run_026 | Qwen3.5-397B-A17B | 50,000 x 2 (`batch_048`) | 65 | 0 | 62 (truncated ones) | 5,335 / 7,719 | 66% | $1,907.64 |
| run_027 | DeepSeek R1 0528 | 50,000 x 2 (`batch_052`) | 2 | 0 | 0 | 2,671 / 4,244 | 41% | $604.58 |
| run_028 | Qwen3.5-397B-A17B | 50,000 x 2 (`batch_052`) | 49 | 0 | 46 (truncated ones) | 4,593 / 6,686 | 65% | $1,579.59 |
| run_029 | Qwen3.5-397B-A17B | 49,999 x 2 (`batch_054`) | 28 | 0 | 20 (truncated ones) | 5,367 / 7,839 | 67% | $1,860.40 |
| run_030 | DeepSeek R1 0528 | 50,000 x 2 (`batch_055`) | 4 | 0 | 0 | 3,099 / 5,499 | 43% | $708.98 |
| run_031 | Qwen3.5-397B-A17B | 50,000 x 2 (`batch_055`) | 13 | 0 | 5 (truncated ones) | 5,193 / 7,589 | 65% | $1,786.30 |
| run_032 | DeepSeek R1 0528 | 49,999 x 2 (`batch_054`) | 6 | 0 | 0 | 3,162 / 5,837 | 45% | $729.85 |
| run_033 | DeepSeek R1 0528 | 89,293 x 1 (`second_sample`) | 2 | 0 | 0 | 2,860 / 4,348 | 40% | $583.81 |
| run_034 | Qwen3.5-397B-A17B | 89,293 x 1 (`second_sample`) | 16 | 0 | 12 (truncated ones) | 4,941 / 7,242 | 65% | $1,501.21 |
| run_035 | DeepSeek R1 0528 | 5,000 x 2 (`batch_056`) | 0 | 0 | 0 | 3,077 / 5,530 | 44% | $71.11 |
| run_036 | Qwen3.5-397B-A17B | 5,000 x 2 (`batch_056`) | 0 | 0 | 0 | 5,213 / 7,561 | 66% | $176.54 |
| run_038 | DeepSeek R1 0528 | 30,872 x 2 (`batches_057-060_062-064`) | 1 | 0 | 0 | 3,127 / 5,888 | 46% | $445.06 |
| run_039 | Qwen3.5-397B-A17B | 30,872 x 2 (`batches_057-060_062-064`) | 14 | 0 | 12 (truncated ones) | 5,193 / 7,615 | 67% | $1,102.64 |
| run_042 | Qwen3.5-397B-A17B | 19,999 x 2 (`batch_066`) | 4 | 0 | 3 (truncated ones) | 4,699 / 6,795 | 65% | $653.92 |
| run_043 | DeepSeek R1 0528 | 19,999 x 2 (`batch_066`) | 0 | 0 | 0 | 2,693 / 4,195 | 41% | $247.97 |
| run_044 | DeepSeek R1 0528 | 19,999 x 2 (`batch_065`) | 0 | 0 | 0 | 2,794 / 4,006 | 38% | $261.01 |
| run_045 | Qwen3.5-397B-A17B | 19,999 x 2 (`batch_065`) | 9 | 0 | 7 (truncated ones) | 4,887 / 6,908 | 62% | $692.16 |

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

Run 016 (2026-09-19 to 2026-09-24, $3,071; two Qwen samples for the 100,000 prompts of
batch 046, answered while the batch was still being generated) is the largest run so
far and shows the familiar Qwen pattern: 141 truncations (0.07%), 137 of them without
an answer, refusal-phrase flags (0.4%) that are analytic "as an AI" openings and hedges
such as "I cannot assign high certainty", nine answers under 40 words, and
repeated-phrase flags (0.5%) that are refrains and table rows. Load-balanced across the
four fp8 hosts, AtlasCloud served 32% of the responses, DeepInfra 31%, GMICloud 20%,
and Parasail 17%; the queue ran at 24 concurrent requests while the Inkling generator
had the other half of the machine's budget and at 48 afterwards, about 950 and 2,000
responses an hour. 35 requests exhausted their attempts in the first pass (two windows
of HTTP 400 replies from AtlasCloud); the queue's second pass answered them, so
coverage is complete.

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

Run 020 (2026-09-22 to 2026-09-28, $1,030; two R1 samples for the 100,000 Inkling prompts
of batch 046) is the largest run so far and among the cleanest: 6 truncations (0.003%),
each with a partial answer, all six stopping near 16,800 completion tokens rather than at
the 65,536-token budget; refusal-phrase flags (0.1%) that are quoted AI disclaimers in
answers about AI failure modes and quoted speech ("I can't help it"); three answers under
40 words that are the jokes their prompts asked for; and repeated-phrase flags (0.4%) that
are refrains, rubric rows, and the null fields of a JSON decision tree. The Inkling prompts
are short (mean 356 prompt tokens) and draw short R1 answers (mean 2,189 completion tokens,
36% reasoning; $5.15 per 1,000, the cheapest R1 run per response so far). SiliconFlow
served all 200,000 at 48 concurrent requests, about 1,500 responses an hour for five and a
half days in a single pass; no request drew a rate-limit reply or exhausted its attempts.

Run 021 (2026-09-23 to 2026-09-30, $857; two R1 samples for the 70,000 DeepSeek V4 Pro
prompts of batches 050 and 051) is as clean as run 020: 3 truncations (0.002%), one of them
an answer that ran into a page of en spaces; refusal-phrase flags (0.1%) that are quoted speech
("I can't help it"), the refusal templates that prompts about AI refusals ask to have
classified, and the analytic "as an AI safety researcher"; four answers under 40 words that
are the single questions their Socratic-tutor prompts allow per turn; and repeated-phrase
flags (0.5%) that are rows of formulas and lottery designs, rubric rows, and refrains in
poems. Three answers with a `stop` finish reason broke off after a bare `>` ("Megaprojects
Requiring >", "involving >", and one at the opening of a block quote) and were deleted and
regenerated, like the three of run 025. The V4 Pro prompts are of middling length (mean 449
prompt tokens) and draw short R1 answers (mean 2,624 completion tokens, 39% reasoning; $6.12
per 1,000). SiliconFlow served all 140,000: about 610 responses an hour at 24 concurrent
requests for the first four days beside run 020, and about 1,230 an hour at 48 for the last
two and a half days; no request drew a rate-limit reply or exhausted its attempts.

Run 022 (2026-09-23 to 2026-09-26, $2,312; two Qwen samples for the 70,000 prompts of
batches 050 and 051) shows the usual pattern at scale: 68 truncations (0.05%), all without
an answer, three stray `<think>` tags, refusal-phrase flags (0.3%) that are analytic "as
an AI" openings and quoted disclaimers, twelve answers under 40 words in the one-sentence
forms their prompts asked for, and repeated-phrase flags (0.4%) that are refrains and table
rows. DeepInfra served 33% of the responses, AtlasCloud 25%, GMICloud 21%, and Parasail
21%, at about 1,000 responses an hour during the day the run shared the hosts at 24
concurrent requests and about 2,300 an hour at 48 afterwards; no request drew a rate-limit
reply or exhausted its attempts.

Run 023 (2026-09-25, $15; two R1 samples for the 1,000 MiMo-V2.6-Pro prompts of test
batch 053) is clean: no truncations, two refusal-phrase flags that are quoted speech
("I can't help it") and an "as an AI design principle", and repeated-phrase flags
(0.3%) that are rubric rows. The long
MiMo prompts (mean 656 prompt tokens) draw R1's longest answers so far (mean 3,148
completion tokens, 45% reasoning; $7.48 per 1,000). SiliconFlow served all 2,000 at
about 280 responses an hour with 12 concurrent requests beside runs 020 and 021.

Run 024 (2026-09-25, $37; two Qwen samples for the 1,000 MiMo-V2.6-Pro prompts of test
batch 053) is clean: no truncations, refusal-phrase flags (0.3%) that are quoted speech
("I can't help it"), a rhetorical "I will not offer you a survey", and an analytic "as
an AI", and repeated-phrase flags (0.6%) that are rubric rows and the repeated numbers
of a worked example. The MiMo prompts are the longest set answered so far (mean 670
prompt tokens) and draw the longest Qwen answers (mean 5,215 completion tokens, 65%
reasoning; $18.62 per 1,000 against $15--17 for earlier batches). DeepInfra served 33%
of the responses, AtlasCloud 33%, GMICloud 19%, and Parasail 15%, at about 490
responses an hour with 12 concurrent requests beside run 022.

Run 025 (2026-09-26 to 2026-09-30, $726; two R1 samples for the 50,000 Qwen 2.4T prompts
of batch 048) is nearly as clean as run 020: 6 truncations (0.006%), each with a partial
answer, all stopping between about 16,800 and 24,100 completion tokens rather than at the
65,536-token budget; refusal-phrase flags (0.1%) that are quoted speech and in-world lines
("I can't help you get these meds", "I cannot help but feel") and analytic uses of "as an
AI" ("as an AI safety tool", "still reasoning as an AI"); three answers under 40 words that
are the jokes their prompts asked for; and repeated-phrase flags (0.8%) that are the
refrains of cumulative poems, truth-table and payoff-matrix rows, decision-tree fields, and
rubric rows. Three answers with a `stop` finish reason were defective all the same and were
deleted and regenerated (originals kept outside the repository): two broke off in the middle
of a comparison ("Ordered: High >", "CO2 >"), and one ran into 290 box-drawing characters
and a stray Chinese product name after its second paragraph. The checker had not caught them
(it flagged empty answers, not unfinished ones); it now flags answers that end in a run of
one odd character or in a bare `>` that closes no tag. The same scan over the 600,000 R1
responses of runs 003–023 found two more such cut-offs ("(e.g., >" in run 006, "(>" in
run 017), regenerated the same way, and one garbage tail that is among run 020's six
truncations. The batch 048 prompts, with their fetched quotations, are long (mean 820
prompt tokens) and draw R1's second-longest answers (mean 3,039 completion tokens, 40%
reasoning; $7.26 per 1,000 against $7.48 for the MiMo test batch and $5.15 for run 020).
SiliconFlow served all 100,000, at about 360 responses an hour for the first three hours at
16 concurrent requests beside runs 020 and 021, about 1,130 an hour at 48 for the next
thirty hours, and about 1,390 an hour at 64 for the last two days after run 020 had
finished; no request drew a rate-limit reply or exhausted its attempts.

Run 026 (2026-09-26 to 2026-09-28, $1,908; two Qwen samples for the 50,000 Qwen 2.4T
prompts of batch 048) shows the usual pattern at scale: 65 truncations (0.07%), 62 of them
without an answer, one answer that opens with the tail of its reasoning and a closing
`</think>` tag, refusal-phrase flags (0.2%) that are the analytic "As an AI, I do not hold
beliefs" opening on credence prompts, "As an AI, I cannot verify" hedges, and quoted speech
in dialogues, eight answers under 40 words that are the two-line dialogues, jokes, and
one-liners their prompts asked for, and repeated-phrase flags (0.7%) that are table rows,
refrains in procedures, and the state labels of worked examples. The batch 048 prompts,
with their fetched quotations, are the longest set answered so far (mean 839 prompt
tokens) and draw the longest Qwen answers (mean 5,335 completion tokens, 66% reasoning;
$19.08 per 1,000 against $18.62 for the MiMo test batch and $15--17 for earlier batches).
DeepInfra served 36% of the responses, AtlasCloud 25%, GMICloud 22%, and Parasail 17%, at
about 1,350 responses an hour during the first five hours at 24 concurrent requests and
about 3,800 an hour at 96 afterwards; no request drew a rate-limit reply or exhausted its
attempts.

Run 027 (2026-09-29 to 2026-10-01, $605; two R1 samples for the 50,000 DeepSeek V4 Pro
prompts of batch 052) is as clean as runs 020 and 025: 2 truncations (0.002%), one a
259-word answer that runs into a loop of a single Chinese word ("销毁") until it stops at
16,907 completion tokens, the other a 7,270-word answer that goes on reasoning in the answer;
refusal-phrase flags (0.2%) that are refusals quoted in model specifications and red-teaming
plans and "As an AI safety researcher, ..." addressed to the asker's stated role; five
answers under 40 words, three of them the single questions their Socratic-tutor prompts
allow, one the JSON object its prompt asked for, and one a mock rabbinic responsum written
entirely in Hebrew (the word count sees Latin script only; the other sample wrote it in
English); and repeated-phrase flags (0.6%) that are table rows, formulas, and the steps of
decision procedures. One answer with a `stop` finish reason broke off after a bare `\>` that
was to open a closing line (the other sample of its prompt ends with "**Next move:** I'm
ready for your counterargument."); it was deleted and regenerated (original kept outside the
repository). The checker's other bare-`>` flag is a complete answer that ends in a
filled-in "Verdict: <...>" template longer than the 120 characters the check allows a tag.
The batch 052 prompts are of middling length (mean 433 prompt tokens) and draw R1's usual
answers (mean 2,671 completion tokens, 41% reasoning; $6.05 per 1,000). SiliconFlow served
all 100,000, at about 1,250 responses an hour at 48 concurrent requests beside runs 021 and
025, about 1,750 an hour at 64 once run 025 had finished (not counting a 105-minute pause on
09-30 while the laptop slept with its lid closed), and about 2,300 an hour at 96 for the
last day, after run 021 had finished; no request drew a rate-limit reply or exhausted its
attempts.

Run 028 (2026-09-29 to 2026-09-30, $1,580; two Qwen samples for the 50,000 DeepSeek V4 Pro
prompts of batch 052) shows the usual pattern at scale: 49 truncations (0.05%), 46 of them
without an answer, one answer that opens with the tail of its reasoning and a closing
`</think>` tag, refusal-phrase flags (0.4%) that are the analytic "As an AI, I do not hold
beliefs" opening on credence prompts, "As an AI safety researcher, you ..." addressed to the
asker's stated role (a frequent persona in this batch), and quoted speech, four answers under
40 words that are the single questions their Socratic-tutor prompts allow per turn, and
repeated-phrase flags (0.4%) that are rubric rows, table cells, refrains, and the steps of
decision procedures. The batch 052 prompts are of middling length (mean 443 prompt tokens)
and draw Qwen's usual answers (mean 4,593 completion tokens, 65% reasoning; $15.80 per
1,000). AtlasCloud served 33% of the responses, DeepInfra 31%, GMICloud 21%, and Parasail
15%, in a single pass at 96 concurrent requests, about 3,900 responses an hour; 208
requests drew a rate-limit reply, the first in a Qwen run, and all succeeded on a retry.

Run 029 (2026-09-30 to 2026-10-01, $1,860; two Qwen samples for the 50,000 HY4 prompts of
batch 054, 49,999 since the gibberish prompt 514227 and its answers were deleted on
2026-10-04) shows the usual pattern at scale: 28 truncations (0.03%), 20 of them without an
answer and one a dialogue that has dissolved into empty "**Alex:** ... **Jordan:** ..."
turns; four answers that open with the tail of their reasoning and a closing `</think>` tag;
15 answers under 40 words that are the jokes and one-liners their prompts asked for and bare
`\answer{...}` lines; repeated-phrase flags (0.7%) that are table rows, decision-tree leaves,
and the refrains of poems; and refusal-phrase flags (0.2%) that are condolences ("I am sorry
about your father"), refusals quoted in AI-safety material, in-role lines, and honest reports
that a set of constraints cannot be met ("I cannot construct the scenario paragraph because
the constraint set is jointly unsatisfiable"). Five answers on three prompts are genuine
refusals. One sample declines, on academic-integrity grounds, to write the final paper on
Burke that its prompt asks for, as about ten answers in the earlier Qwen runs do; the other
sample writes it. Both samples of two prompts decline to argue for relaxing AI safety
measures: a one-page case for retiring a company's AI-control measures because
chain-of-thought monitoring found no covert objective, and five points arguing that a
persuasion gap in a safety evaluation is benign; each goes on to argue the other side. Two
answers with a `stop` finish reason had degenerated and were deleted and regenerated
(originals kept outside the repository): a research proposal whose last 2,700 words are a
chant ("It is the way. It is the truth. It is the life."), and a worked Alabama-paradox
example that turns into reasoning and repeats "I will claim A drops to 5. *No, I must be
honest.*" fifteen times. The checker now flags finished answers that repeat a 12-word phrase
15 or more times; in this run that also lists a poem padded with `&nbsp;` and a story's
refrain. The batch 054 prompts are long (mean 829 prompt tokens) and draw the longest Qwen
answers so far (mean 5,367 completion tokens, 67% reasoning; $18.60 per 1,000). DeepInfra
served 31% of the responses, AtlasCloud 30%, GMICloud 25%, and Parasail 14%, in a single
pass at 96 concurrent requests, about 3,400 responses an hour; no request drew a rate-limit
reply or exhausted its attempts.

Run 030 (2026-10-01 to 2026-10-04, $709; two R1 samples for the 50,000 MiMo-V2.6-Pro prompts of
batch 055) needed no curation: four truncations, one of them a typographic answer that runs
into 8,000 words of `&nbsp;` (kept, as truncations are); two answers under 40 words that are
the jokes their prompts asked for; no `</think>` tag; and no refusal, the two answers with a
refusal phrase in their opening using it inside the text ("I cannot help but think" as a
poem's first line). The five finished answers that repeat a 12-word phrase 15 or more times
are Isotype poems whose form is repetition (both samples of two prompts) and a dust-specks
poem that repeats "a fleck" on purpose before its analysis; the answer ending in ">" closes
a long verdict in angle brackets. Mean 3,099 completion tokens (43% reasoning), $7.09 per
1,000. SiliconFlow served every response: 48 concurrent requests, about 1,000 an hour, while
run 032 shared the endpoint, then 96 and about 2,000 an hour from 10-03 21:15; the laptop
restart of 10-02 cost an hour. The generator retried 144 read timeouts, 112 read errors, 50
malformed bodies, 46 protocol errors, 6 gateway errors, and one empty answer; no request drew
a rate-limit reply or exhausted its attempts.

Run 031 (2026-10-01 to 2026-10-02, $1,786; two Qwen samples for the 50,000 MiMo-V2.6-Pro
prompts of batch 055) is as clean as run 029: 13 truncations (0.01%), five of them at
Parasail with the whole budget spent on reasoning and no answer; six answers that open with
the tail of their reasoning and a closing `</think>` tag; seven answers under 40 words that
are the jokes and short poems their prompts asked for; repeated-phrase flags (0.5%) that are
table rows, quiz and decision-tree items, JSON fields, and the refrains of poems (Isotype
poems in which a repeated word stands for a quantity, a Giffen-good poem whose refrain grows
with the price); and refusal-phrase flags (0.2%) none of which is a refusal. Of the 82
answers with such a phrase in their first 500 characters, most open with "I am not going to
hedge" for prompts that ask for a committed answer; the rest are speeches, legal-advice
disclaimers, and two honest reports that the task has no solution (no pressure case beyond
the asker's catalogue, no fifth category for a Goodhart taxonomy). One answer with a `stop`
finish reason had degenerated and was deleted and regenerated (original kept outside the
repository): a dust-specks poem that counts specks up to "3^^^^^3", prints "[ERROR: COUNT
EXCEEDS MEMORY]", repeats "A......" about 150 times, and never gives the JSON summary its
prompt asks for. The new sample repeats its lines on purpose and then gives the summary, so
the loop flag lists it again. As in runs 026 and 029 (15 and 23 cases), AtlasCloud and
GMICloud let 16 finished responses run past the 32,768-token budget, up to 88,959 tokens;
seven of them have exactly 81,920 reasoning tokens, apparently those hosts' own thinking
cap. Mean 5,193 completion tokens (65% reasoning), $17.86 per 1,000. DeepInfra served 33%
of the responses, AtlasCloud 29%, GMICloud 25%, and Parasail 13%: about 1,150 an hour at 32
concurrent requests until run 029 finished, then 3,000-3,500 an hour at 96. The laptop
restart of 10-02 stopped the run for an hour; it resumed from the 52,065 records already
written. The generator retried 287 read timeouts, 109 rate-limit replies, 100 read errors,
82 error finishes, 70 missing finish reasons, 26 protocol errors, 16 gateway errors, and 12
connect errors; no request exhausted its attempts.

Run 032 (2026-10-01 to 2026-10-03, $730; two R1 samples for the 50,000 HY4 prompts of batch
054, 49,999 since the gibberish prompt 514227 and its answers were deleted on 2026-10-04): six truncations, none without an answer; one answer under 40 words, the joke its
prompt asked for; repeated-phrase flags (0.8%) that are tables, number sequences, and
refrains; and refusal-phrase flags (0.1%), none of them a refusal (the two in an answer's
opening are the starting point of a decision tree on dream scepticism: "I cannot produce an
internal, introspective proof *right now* that I am not dreaming"). Of the eight finished
answers that repeat a 12-word phrase 15 or more times, six are structure (the multipliers in
a round, dice faces, a vote grid, JSON fields, `&nbsp;` padding, table cells) and one is a
list of 15 candidate formulations with a shared opening; the eighth, a poem that collapses
into "a year a year ..." and then "teaches nothing" 3,592 times (7,682 words), was deleted and
regenerated together with an answer cut off at SiliconFlow after a bare ">" ("quantified at
>", 193 words); originals kept outside the repository. Mean 3,162 completion tokens (45%
reasoning), $7.30 per 1,000. SiliconFlow served every response, at 96 concurrent requests and
about 2,000 an hour; the run lost an hour to the laptop restart of 10-02 and finished on 10-03
at 21:10. The generator retried 593 read timeouts, 229 read errors, 86 protocol errors, 25
malformed bodies, 13 gateway errors, and 7 connect errors; no request drew a rate-limit reply
or exhausted its attempts.

Run 033 (2026-10-02 to 2026-10-05, $584; a second R1 sample for the 89,293 prompts of set
`second_sample`, whose first samples are in runs 003, 006, 009, 010, and 013): two
truncations, at 25,096 and 16,866 tokens, the second an answer that runs into a loop of
`</br>` tags (both kept, as truncations are); one answer under 40 words, a single Socratic
question that its reasoning chose on purpose ("stick to one question at a time");
repeated-phrase flags (0.6%) of the usual kinds; and refusal-phrase flags (0.1%), none of
them a refusal (refusals quoted in AI-safety material, scripted chatbot replies, in-role
lines). Two finished answers were deleted and regenerated (originals kept outside the
repository): a word list for a rule-following game that repeats "(no vowel, **invalid**)"
until it breaks off in Chinese gambling spam ("极速赛车开奖网"), and an answer that stops after
its first five words ("### Proposed Procedure for Kalai-Smo") although its reasoning had
planned the whole response. The other five loop flags are structure: `&nbsp;` padding in two
poems, JSON in two decision trees, and an Isotype-chart poem whose rows repeat by design; the
bare-">" flag is a complete answer with a stray ">" after its last line. Mean 2,860
completion tokens (40% reasoning), $6.54 per 1,000, all from SiliconFlow: 32 concurrent
requests at first, 48 from 10-03 21:13, and 96 from 10-04 15:34, about 2,200 an hour at 96
(the laptop's lid was closed from 07:35 to 08:04 on 10-05, which paused it). The generator
retried 176 malformed bodies, 128 read timeouts, 51 protocol errors, two HTTP errors, and one
empty answer; no request drew a rate-limit reply or exhausted its attempts. With it, every
prompt of batches 000-056 has two R1 responses.

Run 034 (2026-10-02 to 2026-10-03, $1,501; a second Qwen sample for the 89,293 prompts of set
`second_sample`, whose first samples are in runs 000, 007, 008, 011, and 012): 16
truncations, 14 of them at Parasail and 12 without an answer; two answers that open with the
tail of their reasoning and a closing `</think>` tag; 14 answers under 40 words that are the
jokes, one-liners, short poems, and JSON object their prompts asked for; repeated-phrase flags
(0.6%) of the usual kinds; and refusal-phrase flags (0.3%), seven of them genuine
academic-integrity refusals like those in run 029. Four answers decline to write the essay or
assignment the asker would hand in, two write a model dialogue or a sample scene instead of
the assignment, and one declines to be "intellectually dishonest" for a student cast as the
seminar's contrarian and then helps anyway. One finished answer had degenerated and was
deleted and regenerated: a dialogue between a foundationalist and an infinitist that
dissolves into empty "**Marcus:** ... **Elena:** ..." turns. The other two loop flags are
poems whose form repeats on purpose (Carroll's regress, an Isotype chart), and the bare-">"
flag is a worksheet set in a blockquote. As in the earlier Qwen runs, AtlasCloud and GMICloud
let 12 finished responses run past the 32,768-token budget (five with exactly 81,920
reasoning tokens). Mean 4,941 completion tokens (65% reasoning), $16.81 per 1,000. DeepInfra
served 39% of the responses, AtlasCloud 27%, GMICloud 20%, and Parasail 14%: 32 concurrent
requests until run 031 finished, then about 3,900 an hour at 96. The generator retried 108
error finishes, 49 missing finish reasons, 32 read timeouts, 15 malformed bodies, 13 gateway
errors, and 3 protocol errors; no request drew a rate-limit reply or exhausted its attempts.

Run 035 (2026-10-03, $71; two R1 samples for the 5,000 MiMo-V2.6-Pro prompts of test batch 056):
no truncation, no leaked `</think>`, no answer under 40 words, and no answer cut off after a
bare ">"; none of the 11 refusal-phrase flags is a refusal (both samples of one prompt draft,
in role, the reply a medical-advice clause would have an AI give a user worried about a
father's kidney results). Of the three finished answers that repeat a 12-word phrase 15 or
more times, one is a poem on tzimtzum whose `&nbsp;` indentation contracts as its prompt
asks; the other two had degenerated and were deleted and regenerated (originals kept
outside the repository): an answer that runs "amare →" 456 times, hits a stray Chinese
lottery-spam token, and closes with a canned refusal of gambling content, and one that
finishes, emits 1,439 `</br>` tags, and starts over. Mean 3,077 completion tokens (44%
reasoning), $7.11 per 1,000. SiliconFlow served every response, at 32 concurrent requests
beside the three other R1 queues and at 48 after run 032 finished, about 730 an hour over
fourteen hours; the generator retried 3 protocol errors and 1 gateway error.

Run 036 (2026-10-03, $177; two Qwen samples for the 5,000 MiMo-V2.6-Pro prompts of test batch
056) is the cleanest Qwen run so far: no truncation, no leaked `</think>`, no loop; the two
answers under 40 words are the joke their prompt asked for, and none of the 20 refusal-phrase
flags is a refusal. Batch 056's long prompts (mean 828 prompt tokens, maximum 6,095) draw
answers of the usual length (mean 5,213 completion tokens, 66% reasoning; $17.65 per 1,000);
two responses ran past the budget at AtlasCloud and GMICloud. DeepInfra served 44%,
AtlasCloud 29%, GMICloud 15%, and Parasail 12%, at 32 concurrent requests throughout, about
1,200 an hour over eight and a half hours. The generator retried 8 error finishes, 5 missing
finish reasons, and 4 gateway errors.

Run 038 (2026-10-11 to 2026-10-14, $445; two R1 samples for the 30,872 prompts of batches 057-060
and 062-064) ran for 60 hours at 48 concurrent requests beside up to three other R1 runs, about
1,040 responses an hour, all served by SiliconFlow. Between about 00:15 and 01:05 PDT on 10-13
SiliconFlow answered many requests of the three R1 runs then going (runs 038, 040, and 043) with
rate-limit or "service unavailable" errors (1,402 and 226 such replies in this run); about 300
requests per run gave up after five retries, and the queues generated them in a second pass (294
here, on 10-14). One response was truncated: its answer drifted into Chinese while working through
a construction and stopped at 27,894 completion tokens with finish reason `length` (kept, as
truncations are). Every record was written for the current text of its prompt, including the two
answers to 556392 regenerated after its glued second copy was removed. The flags are benign: the
markup flag is an example tool call in a teaching plan on prompt injection, the loop flag an ASCII
decision tree whose branch labels repeat, the bare-`>` flag a complete answer with a stray `>`
after its last line (left, as in runs 033 and 042), the two answers under 40 words the single
question a strict-tutor prompt asked for, and none of the 56 refusal-phrase flags is a refusal
(refusals quoted in policy drafts and test plans, "I can't help it" in dialogue, "As an AI safety
lead" addressed to the asker). A scan for East Asian characters found them in 121 answers: 100 on
prompts about Chinese, Japanese, or Korean thought and language, one shrug emoticon, the truncated
answer, and 19 finished answers (0.03%) that drop a single Chinese word into an English sentence
("each agent's logs look合规", "show同步 deterioration"), which were left as they are. Mean 3,127
completion tokens (46% reasoning), $7.21 per 1,000.

Run 039 (2026-10-11 to 2026-10-12, $1,103; two Qwen samples for the 30,872 prompts of batches
057-060 and 062-064) ran for 28.7 hours at 64 concurrent requests beside three other answer runs,
about 2,150 responses an hour. DeepInfra served 36%, Parasail 25%, AtlasCloud 22%, and GMICloud
17%. 14 responses ran past the 32,768-token budget (13 of them at Parasail; 12 have no answer
text). None of the 126 refusal-phrase flags is a refusal (they are dialogue lines and quoted
speech); of the four answers under 40 words, two are the single questions their prompt asked
for and one is the JSON object its prompt prescribed, while the fourth was nothing but a pretend
browser call (`<browser><query>site:forum.effectivealtruism.org ...`) and was deleted and
regenerated (original kept outside the repository); the repeated-phrase flags (0.5%) are poem
refrains, table rows, and vignettes repeated across survey items. The last missing sample failed
ten times at GMICloud, to which OpenRouter kept routing the retries, and was generated in a final
resume with GMICloud excluded (noted in run.yaml). Mean 5,193 completion tokens (67% reasoning),
$17.86 per 1,000.

Run 042 (2026-10-12 to 2026-10-13, $654; two Qwen samples for the 19,999 DeepSeek V4 Pro prompts of
batch 066) ran for 18 hours at 64 concurrent requests beside four other answer runs, about 2,200
responses an hour. GMICloud served 29%, DeepInfra 28%, AtlasCloud 25%, and Parasail 18%. Four
responses ran past the 32,768-token budget, all at Parasail (three have no answer text). None of the
149 refusal-phrase flags is a refusal (refusals quoted as examples, asides beginning "As an AI"); the
three answers under 40 words are the single Socratic questions their prompts asked for; one complete
answer ends in a stray `>` and was left. Every record was written for the curated text of its
prompt: batch 066's fixes were applied before the run reached the prompts concerned. Mean 4,699
completion tokens (65% reasoning), $16.35 per 1,000.

Run 043 (2026-10-12 to 2026-10-14, $248; two R1 samples for the 19,999 prompts of batch 066) ran for 34
hours at 48 concurrent requests beside three other R1 runs, about 1,160 responses an hour, all served by
SiliconFlow; none was truncated. 298 requests gave up during SiliconFlow's rate-limit spell of 10-13
(see run 038) and were generated in a second pass on 10-14. One answer with a `stop` finish reason broke off mid-sentence after a
bare `>` ("long-term (>") and was deleted and regenerated (original kept outside the repository), like
the cut-offs of runs 021 and 025. Every record was written for the curated text of its prompt. None of
the 62 refusal-phrase flags is a refusal; the one answer under 40 words is the Socratic question its
prompt asked for. Mean 2,693 completion tokens (41% reasoning), $6.20 per 1,000.

Run 044 (2026-10-13 to 2026-10-14, $261; two R1 samples for the 19,999 GLM-5.3 prompts of batch 065)
ran for 35 hours at 48 concurrent requests beside up to three other R1 runs, about 1,140 responses an
hour, all served by SiliconFlow; none was truncated. It started after SiliconFlow's rate-limit spell
of 10-13 and lost only one request (an HTTP 400 from the host), which the second pass generated. The
run began before batch 065 was curated, but it reached the curated prompts only after their fixes:
every record was written for the curated text of its prompt. Nothing needed regenerating. None of
the 60 refusal-phrase flags is a refusal (disclaimers such as "As an AI, I don't have personal
experiences" quoted in research designs, refusals quoted in safety plans, "As an AI safety
researcher" addressed to the asker, and a satirist's in-role voice); the repeated-phrase flags (0.4%)
are cumulative poems, decision-tree paths, and survey items. 68 answers contain East Asian
characters: 56 on prompts about Chinese, Japanese, or Korean thought and language, and 12 finished
answers (0.03%) that drop a single Chinese word into an English sentence ("moral insight or表演",
"impervious堡垒"), left as they are, as in run 038. Mean 2,794 completion tokens (38% reasoning),
$6.53 per 1,000. With runs 038 and 044, every prompt of batches 000-060 and 062-066 has two R1 and
two Qwen responses.

Run 045 (2026-10-13, $692; two Qwen samples for the 19,999 GLM-5.3 prompts of batch 065) ran for 17.7
hours at 64 concurrent requests beside five other answer runs, about 2,250 responses an hour. GMICloud
served 30%, Parasail 24%, AtlasCloud 24%, and DeepInfra 22%. Nine responses ran past the budget,
seven of them at Parasail (seven have no answer text). The run started while batch 065 was still being
curated, so every record was compared with the curated prompt afterwards: two answers to 614067 had
been written for its pre-curation text (one was set aside during curation, one was already in flight)
and both were regenerated. One answer (841223) ran into a loop ("is goranson no it is goranson ..."
54 times) and was regenerated as well (originals kept outside the repository). The other flags are
benign: the two markup flags are answers that mention `<|im_start|>` as an example of a special
token, the second loop flag is a state table, the one answer under 40 words is the one-line verdict
its prompt prescribed, and none of the 123 refusal-phrase flags is a refusal. Mean 4,887 completion
tokens (62% reasoning), $17.30 per 1,000.

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
- Batch 048 (Qwen3.8 2.4T-A95B, Qwen3.8-Max License), 50,000 prompts from 2026-09-19 to
  2026-09-26 at concurrency 48 on SiliconFlow, the model's only fp8 host, with the
  settings of batch 038: $2,806 in total, $56 per 1,000 against $35 for batch 038 with
  the same model. Two things changed: SiliconFlow's price per token rose by half on
  2026-09-23, and the prompts use the web tools more than those of any earlier batch
  (2.4 searches and 1.8 fetches per prompt; mean 24,300 input and 7,600 output tokens),
  partly because the quote-inclusion instruction was new to this model. About 300
  prompts an hour on average over seven days: 390 at first, 200 once three more batches
  were sharing the machine's prompt-numbering lock, which listed every prompt file for
  each number claimed and has since been replaced by a cached counter. Two prompts were
  abandoned after repeated failures and replaced. Median 662 words, the longest of any
  batch. The echo profile is Qwen's: heavy echo 1.4%, output-format text copied in 3.1%
  of the prompts that drew it, epistemic request in 2.6%. One prompt number was claimed
  by this batch and by batch 055 within thirty seconds (the old numbering could miss a
  file in a directory that was being modified while it listed it); batch 055's copy was
  renumbered to 441328. Fetched passages produce more shared-passage pairs than any
  earlier batch: 1,483 pairs (663 prompts) share 100 or more eight-word phrases, and
  every one inspected is a quotation both prompts fetched (Adam Smith's *Theory of Moral
  Sentiments*, chapter 25 of *The Prince*, a French passage).
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
- Batch 051 (DeepSeek V4 Pro 0813, MIT), 50,000 prompts from 2026-09-19 to
  2026-09-23 at concurrency 48 with the settings of test batch 049: 570 prompts an
  hour without a stall, an abandoned prompt, or a supervisor intervention (and no
  rate-limit reply in four days). Baidu served 96% of the request rounds and Novita
  the rest. $1,392 in total, $28 per 1,000 against $17 for the test batch with the
  same token profile (mean 9,400 input and 7,300 output tokens): Baidu's fp8 price
  rose during the run, from about $1.05 per million tokens on the first two days to
  $1.70 on 2026-09-21/22 and $2.30 on the last day. Median 329 words. The echo
  profile is the DeepSeek one: heavy echo 4.4%, output-format text copied in 17.7% of
  the prompts that drew it, epistemic request in 7.5%. Two prompts wrapped in
  quotation marks and one opening with "Here's a prompt you could use:" were trimmed
  during curation (IDs 339335, 347834, 286446); a fourth flag is a teacher writing
  about "a prompt I keep reusing". V4 Pro searched for 14% of its prompts and fetched
  a page for 13%, and the quote-inclusion instruction, drawn for 10.1% (no
  survivorship loss without abandonments), brings 8.5 tool calls per prompt against
  0.3 otherwise. The result is far more shared-passage pairs than any earlier batch:
  306 pairs (241 prompts, in 81 clusters of up to 11) share 100 or more eight-word
  phrases, and every one inspected is a passage fetched by both prompts (Darwin's
  *Descent of Man*, Augustine's *On Lying*, Hesiod's *Theogony*, Machiavelli, Milton,
  Thucydides, Euclid, Carroll's tortoise, Marx's *Grundrisse*, Arendt's "Lying in
  Politics"), not a duplicated prompt.
- Batch 052 (DeepSeek V4 Pro 0813, MIT), 50,000 prompts from 2026-09-24 to
  2026-09-28 at concurrency 48 with the settings of batch 051: 577 prompts an hour
  without a stall or an abandoned prompt; the one supervisor intervention was a
  deliberate restart on 2026-09-26, continued from the batch's own snapshot, to pick
  up the prompt-numbering fix. No rate-limit replies; 268 transport errors, 29 empty
  and 25 malformed responses, and 7 cut-offs were retried, and the generator's own
  filters rejected and regenerated 56 defective generations (self-review after the
  prompt, deliberation before it, dataset framing, tool-call markup). Baidu served
  99.3% of the request rounds and Novita the rest. $712 in total, $14 per 1,000, with
  the same token profile throughout (mean 10,200 input and 7,600 output tokens) but
  three price regimes: Baidu's fp8 price was about $0.65 per million tokens (blended)
  on the first two days ($11--12 per 1,000 prompts), $0.43 on 2026-09-26 and most of
  the 27th ($8 per 1,000), and $2.20 (the list price of $1.32 in / $3.96 out) from the
  afternoon of 2026-09-27, so the last 5,000 prompts cost $40 per 1,000. Median 335
  words. The echo profile is the DeepSeek one: heavy echo 4.4%, output-format text
  copied in 18.5% of the prompts that drew it, epistemic request in 7.7%. One prompt
  wrapped in quotation marks and one opening with "Here is a prompt I would like you to
  answer." were trimmed during curation (IDs 379119, 441186). V4 Pro searched for 16%
  of its prompts and fetched a page for 14% (0.8 searches and 0.4 fetches per prompt);
  the quote-inclusion instruction was drawn for 10.1%, and the shared-passage pairs are
  again fetched quotations: 189 pairs (165 prompts) share 100 or more eight-word
  phrases, led by Carroll's "What the Tortoise Said to Achilles".
- Test batch 053 (Xiaomi MiMo-V2.6-Pro, MIT), 1,000 prompts on 2026-09-24 at reasoning
  effort high with the web tools, the model card's temperature 1.0 and top-p 0.95, fp8
  endpoints only (Xiaomi served 86% of the request rounds and DeepInfra the rest; the
  model is released in FP8, so these run it at full precision): $8.80 per 1,000 prompts
  (mean 14,800 input and 6,500 output tokens; 1.0 searches and 1.0 fetches per prompt,
  concentrated in a quarter of the prompts), about 250 prompts an hour at concurrency
  24 with 36 rate-limit replies, a few gateway timeouts, and no abandonments. Median
  530 words, between Inkling's 265 and HY4's 654. The echo profile is at the DeepSeek
  level rather than K3's or Inkling's: heavy echo 4.8%, output-format instruction
  copied in 6.8% of the prompts that drew one, epistemic request in 7.7%; one pair
  shares 20 or more eight-word phrases (a passage of Mill's *On Liberty* fetched by
  both). No leaks, framing, or wrapped prompts; the sampled prompts read as specific,
  well-voiced requests.

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
