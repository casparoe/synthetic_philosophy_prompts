# Synthetic Philosophy Prompts

A dataset of (currently) about 810,000 synthetic user prompts on philosophical and
conceptual topics — decision theory, formal epistemology, philosophy of science,
mind, and language, ethics, metaphysics, history of philosophy, AI alignment as a
conceptual topic, and more, with a smaller share of non-Western and historical
traditions. Each prompt is written as if by a real person (a grad student, a
retired physicist, a novelist, a committee member, ...) in one of eighty genres
(explanations, essay requests, grading tasks, dialogues, adjudications of
disagreements, committee memos, interview questions, speeches for occasions,
rankings, ...).

The prompts are deliberately "in the weeds": specific enough that a model cannot
answer by regurgitating a canned summary, while remaining answerable for a model
without web access. Alongside the prompts, `responses/` collects responses to
subsets of them from open-weight models, each with the model's full chain of
thought (see [Responses](#responses)), and `preferences/` collects pairwise judgments
of such responses by a strong model (see [Preference pairs](#preference-pairs)).
Link prompts are a kind of their own: each comes with one to three web pages that the
answering model reads along with it (see [Link prompts](#link-prompts)).

**Where the data lives.** Since 2026-09-26 the dataset is published on the Hugging Face Hub as
[casparoe/synthetic_philosophy_prompts](https://huggingface.co/datasets/casparoe/synthetic_philosophy_prompts):
one Parquet shard per prompt batch, response run, and preference run, with the same fields as
the files described below (the dataset card gives the mapping). New batches and runs are added
there only. This repository keeps the code, the meta-prompt, and this documentation up to date,
and holds the data in its one-file-per-prompt form as of September 2026 (prompts through batch
050, responses through run 019, preference runs 000 and 001); the tables and notes here and in
`QUALITY_NOTES.md` describe the whole dataset, including the batches and runs that exist only on
the Hub. `tools/export_hf.py` builds the shards from this layout, `tools/make_hf_card.py` the
dataset card, and `tools/upload_hf.py` uploads them.

## Layout

```
prompts/batch_NNN/
  prompt_XXXXX.txt        the prompt text (IDs are globally unique across batches;
                          five digits up to 99999, six from 100000 on)
  prompt_XXXXX.meta.yaml  per-prompt metadata (see below)
  batch.yaml              batch-level settings (model, API, sampling parameters)
  inputs/                 snapshot of the meta-prompt components used for this batch
                          (the task types joined into one task_types.yaml)
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
  domains/                3,862 philosophical domains sampled from, in 46 thematic
                          YAML files; a domain may list URLs of pages about it,
                          each shown to web-enabled generators with probability 0.05,
                          and under stable_urls stable links, which only link
                          prompts attach
  task_types/             80 prompt genres, one file per genre (NNN_name.yaml, read in
                          name order), each with examples and notes
  additional_instructions.yaml
                          extra instructions (length, persona, writing style) in
                          mutually exclusive groups, each drawn with a set probability
generators/
  generate_prompt.py        generator: Anthropic API, streaming
  generate_prompt_batch.py  generator: Anthropic Message Batches API
  generate_prompt_oai.py    generator: OpenAI-compatible endpoints (self-hosted models, OpenRouter)
  link_cache.py             the local copies of the domain links that generate_prompt_oai.py's
                            web_fetch serves instead of the live pages, long ones in parts
  attached_pages.py         the web pages a link prompt comes with: drawn from the link cache,
                            frozen, and shown to the generating and the answering model
  generate_responses.py     model responses to a prompt set (OpenAI-compatible endpoints, OpenRouter)
  judge_pairs.py            preference judgments over a pair set (Anthropic API, streamed or as Message Batches)
tools/
  check_batch.py            quality report for a batch: leaks, stray words and word salad, example echo, near-duplicates, cost
  make_prompt_set.py        writes a prompt set: filter by batch or generating model, seeded sample
  build_link_cache.py       fetches every domain link once, politely, into link_cache/
  arxiv_latexml.py          renders an arXiv paper's source with LaTeXML, in a sandbox (--self-test)
  install_latexml.sh        installs the pinned LaTeXML and TeX Live 2025 that arxiv_latexml.py uses, into .venv
  add_stable_links.py       adds stable versions of the domains' links under stable_urls
                            (Wikipedia articles as permanent links to a revision, arXiv
                            papers as links to a version)
  check_link_batch.py       report for a link batch: pages, sources, licenses, URL problems, copying
  check_run.py              quality report for a response run: coverage, truncation, missing reasoning, cost
  import_teacher_data.py    converts the cr_training sister repo's teacher-data collections into imported runs
  make_pair_set.py          writes a pair set: complete response pairs from one run (two samples) or two runs, seeded sample
  check_preferences.py      report for a preference run: coverage, verdicts, position balance, cost; agreement of two runs
QUALITY_NOTES.md          known quality issues and per-batch measurements
link_cache/               the linked pages' text (git-ignored and never uploaded: most
                          of it is under copyright), snapshots.sqlite, the frozen
                          texts of the pages attached to link prompts, and the arXiv
                          sources with LaTeXML's logs (arxiv_source/, arxiv_logs/)
```

Per-prompt metadata includes the generating model, the domains and task types
offered during sampling (from batch 046 on, and for the second half of batch 044, also
which of each type's examples were shown, in which order, under `task_type_examples`),
the additional instructions drawn (persona, writing style,
length, and from batch 029 on further groups such as epistemic and output-format
requests; recorded as one `additional_instructions` mapping from batch 029 on and as
separate `length`/`persona`/`writing_style` keys before), token counts, the number
of web searches and page fetches the generator performed (from 2026-10-05 also how
many fetches the link cache answered, `web_fetches_cached`), a summary of the
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
| 043 | Tencent HY4 preview | OpenRouter, fp8 provider (Tencent); 1,000-prompt test batch, temperature 0.9 and top-p 1.0 as the model card recommends; 4 prompts carry a stray Chinese word, left in place (see known limitations); client-executed web tools (DuckDuckGo search + page fetch) |
| 044 | Thinking Machines Inkling | OpenRouter, fp8 provider (BaseTen; DeepInfra excluded); 20,000 prompts; paused for six hours during a BaseTen outage and continued from the batch's own snapshot; client-executed web tools (DuckDuckGo search + page fetch) |
| 045 | Tencent HY4 preview | OpenRouter, fp8 provider (Tencent); 20,000 prompts, temperature 0.9 and top-p 1.0 as the model card recommends; 88 prompts (0.4%) carry a stray Chinese word, left in place (see known limitations); client-executed web tools (DuckDuckGo search + page fetch) |
| 046 | Thinking Machines Inkling | OpenRouter, fp8 provider (BaseTen; DeepInfra excluded); 100,000 prompts over five days at concurrency 48; 590 prompts abandoned under rate limiting and regenerated with `--continue-batch`; the first whole batch run with the example subsetting described below; client-executed web tools (DuckDuckGo search + page fetch) |
| 047 | Moonshot Kimi K3 | OpenRouter, fp8 provider (BaseTen, the only 8-bit host; the model is trained in MXFP4); 1,000-prompt test batch; temperature 1.0 and top-p 0.95 (BaseTen enforces 0.95 for this model), reasoning effort high; 14 prompts abandoned under rate limiting and regenerated with `--continue-batch`; client-executed web tools (DuckDuckGo search + page fetch) |
| 048 | Qwen3.8 2.4T-A95B | OpenRouter, fp8 provider only (SiliconFlow); 50,000 prompts over seven days at concurrency 48 with the settings of batch 038; two prompts abandoned and replaced; the first Qwen 2.4T batch with the quote-inclusion instruction; client-executed web tools (DuckDuckGo search + page fetch) |
| 049 | DeepSeek V4 Pro 0813 | OpenRouter, fp8 provider (Baidu first; Io Net and GMICloud excluded); 1,000-prompt test batch; temperature 1.0 and top-p 1.0 from the model card, reasoning effort high; client-executed web tools (DuckDuckGo search + page fetch) |
| 050 | Moonshot Kimi K3 | OpenRouter, fp8 provider (BaseTen, the only 8-bit host); 20,000 prompts; temperature 1.0 and top-p 0.95 (BaseTen enforces 0.95 for this model), reasoning effort high; 778 prompts abandoned under rate limiting and regenerated with `--continue-batch` in three passes; client-executed web tools (DuckDuckGo search + page fetch) |
| 051 | DeepSeek V4 Pro 0813 | OpenRouter, fp8 provider (Baidu first; Io Net and GMICloud excluded); 50,000 prompts; temperature 1.0 and top-p 1.0 from the model card, reasoning effort high; no prompt abandoned in four days; client-executed web tools (DuckDuckGo search + page fetch) |
| 052 | DeepSeek V4 Pro 0813 | OpenRouter, fp8 provider (Baidu first; Io Net and GMICloud excluded); 50,000 prompts over four days at concurrency 48 with the settings of batch 051; no prompt abandoned; continued once from the batch's own snapshot after a deliberate restart; client-executed web tools (DuckDuckGo search + page fetch) |
| 053 | Xiaomi MiMo-V2.6-Pro | OpenRouter, fp8 providers load-balanced (Xiaomi, DeepInfra; the model is released in FP8); 1,000-prompt test batch; temperature 1.0 and top-p 0.95 from the model card, reasoning effort high; client-executed web tools (DuckDuckGo search + page fetch) |
| 054 | Tencent HY4 preview | OpenRouter, fp8 providers (Tencent first, then Novita; SiliconFlow and DeepInfra took a few); 50,000 prompts over four and a half days at concurrency 72, temperature 0.9 and top-p 1.0 as the model card recommends, 64,000-token budget; continued three times from the batch's own snapshot after stalls and once to replace a removed file; flaws left in place (see known limitations): 808 prompts (1.6%) carry a stray Chinese or Korean word and 72 a leaked `<｜hy_place▁holder▁no▁813｜>` token, 27 of them breaking off mid-sentence there; one gibberish prompt deleted on 2026-10-04 (49,999 kept); client-executed web tools (DuckDuckGo search + page fetch) |
| 055 | Xiaomi MiMo-V2.6-Pro | OpenRouter, fp8 providers load-balanced (DeepInfra, GMICloud, Xiaomi; the model is released in FP8); 50,000 prompts over six days at concurrency 48, temperature 1.0 and top-p 0.95 from the model card, reasoning effort high, 65,536-token budget; continued once from the batch's own snapshot after a supervisor restart and once to replace 22 abandoned generations; client-executed web tools (DuckDuckGo search + page fetch) |
| 056 | Xiaomi MiMo-V2.6-Pro | OpenRouter, fp8 providers load-balanced (DeepInfra; GMICloud took about 5%; the model is released in FP8); 5,000-prompt test batch of the meta-prompt of 2026-10-02 (four new task types, longer examples including whole articles and graded scripts, and the rule that long quotations must come from public-domain, openly licensed, or Caspar Oesterheld's texts); the settings of batch 055 (temperature 1.0, top-p 0.95, reasoning effort high, 65,536-token budget, concurrency 48); no prompt abandoned in eleven hours; client-executed web tools (DuckDuckGo search + page fetch) |
| 057 | Xiaomi MiMo-V2.6-Pro | OpenRouter, fp8 providers (DeepInfra; GMICloud and Novita took a few dozen); 5,000-prompt test batch of the meta-prompt of 2026-10-03 morning, which lists the sources that may be quoted at length (EA Forum posts from December 2022 on, gwern.net, Our World in Data, Distill, CC BY arXiv and journal articles, US court and federal documents, Caspar Oesterheld's blog posts) and those that may only be excerpted; the settings of batch 056; ran alongside batch 058, so the two batches' IDs interleave; no prompt abandoned; client-executed web tools (DuckDuckGo search + page fetch) |
| 058 | Xiaomi MiMo-V2.6-Pro | OpenRouter, fp8 providers (DeepInfra; Novita, GMICloud, and Xiaomi took a few dozen); 5,000-prompt test batch of the meta-prompt of 2026-10-03 afternoon: the domains moved into 45 thematic files (2,811 domains), some with links (Caspar Oesterheld's blog posts on 75 domains, 220 essays from Brian Tomasik's reducing-suffering.org, a few others), each link shown with probability 0.05, so 3.2% of prompts saw one; the settings of batch 056; ran alongside batch 057; no prompt abandoned; client-executed web tools (DuckDuckGo search + page fetch) |
| 059 | Tencent HY4 preview | OpenRouter, fp8 providers (Tencent first, then Novita); 5,000 prompts with the settings of batch 054 (concurrency 72, temperature 0.9, top-p 1.0, 64,000-token budget), for comparison with the MiMo test batches on the meta-prompt of 2026-10-04 morning (3,280 domains, links on about half of them: Wikipedia, the SEP and IEP, Bentham's Bulldog, gwern.net, Brian Tomasik, Caspar Oesterheld); one generation abandoned and replaced; five word-salad prompts deleted and 30 stray Chinese words translated back during curation (4,995 kept); client-executed web tools (DuckDuckGo search + page fetch) |
| 060 | Xiaomi MiMo-V2.6-Pro | OpenRouter, fp8 and bf16 providers (DeepInfra 63%, GMICloud 20%, Novita 17%); 5,000 prompts with the settings of batch 056 on the meta-prompt of 2026-10-06 15:49 (3,530 domains; each linked page shown with probability 0.05, so 93% of prompts saw at least one link, most often to LessWrong, Wikipedia, the EA Forum, Philosophy Stack Exchange, the SEP, Overcoming Bias, or Project Gutenberg); one generation abandoned and replaced; client-executed web tools (DuckDuckGo search + page fetch) |
| 062 | GLM-5.3 | OpenRouter, fp8 provider (SiliconFlow; Z.ai's own endpoint excluded); 1,000-prompt trial with the settings of batches 034/035 (effort high, temperature 1.0) and a 65,536-token budget, on the meta-prompt of batch 061 and run alongside it, so the two batches' prompt IDs interleave; client-executed web tools (DuckDuckGo search + page fetch) |
| 063 | claude-haiku-5-5 | Anthropic API, streaming at concurrency 48; effort xhigh with a 64,000-token ceiling, because at max effort Haiku 5.5 thought for 48,000 to over 64,000 tokens per prompt; 5,000 prompts requested and 4,981 written (19 dropped: 10 stopped on a tool call, 5 refusals, 3 over the ceiling, 1 blocked by the output filter); first submitted to the Message Batches API on the model's release day, where it never started in 21 hours and was cancelled; Anthropic's server-side web tools; unlike the OpenRouter batches, its meta-prompt lacks the rule against quoting from memory |
| 064 | claude-haiku-5-5 | Anthropic API, streaming at concurrency 48 with the settings of batch 063 (effort xhigh, 64,000-token ceiling), on the meta-prompt of 2026-10-09 19:20, the first with the long-prompt length option; 5,000 prompts requested and 4,896 written (79 lost to requests cut off while the computer slept, 25 dropped for tool-call stops, refusals, or the ceiling); Anthropic's server-side web tools; like batch 063, no rule against quoting from memory |
| 065 | GLM-5.3 | OpenRouter, fp8 providers (Baidu first, SiliconFlow took 13% of requests; Z.ai's own endpoint excluded); 20,000 prompts over 40 hours at concurrency 48 with the settings of batches 034/035 (effort high, temperature 1.0, top-p 0.95) and a 65,536-token budget, on the meta-prompt of 2026-10-09 19:20 (with the long-prompt option); no prompt abandoned; Baidu's price rose about sixfold for the last eight hours; during curation four prompts lost dataset framing and four leaked deliberation, 27 that held two drafts of themselves (or notes glued to the prompt) kept one, 37 stray Chinese words were translated back, and one non-prompt (the model's own planning in Chinese) was removed (19,999 kept); client-executed web tools (DuckDuckGo search + page fetch, linked pages served from a local copy) |
| 066 | DeepSeek V4 Pro 0813 | OpenRouter, fp8 provider (Baidu first, Novita took 4% of requests; Io Net and GMICloud excluded); 20,000 prompts over 31 hours at concurrency 48 with the settings of batches 049/051/052 (reasoning effort high, temperature 1.0, top-p 1.0, 32,768-token budget) on the meta-prompt of 2026-10-09 19:20 (with the long-prompt option); no prompt abandoned; six prompts trimmed of the generator's deliberation and one non-prompt (a JavaScript function) removed during curation (19,999 kept); client-executed web tools (DuckDuckGo search + page fetch, linked pages served from a local copy) |
| 067 | claude-haiku-5-5 | Anthropic Message Batches API at effort xhigh with a 64,000-token ceiling, on the meta-prompt of 2026-10-09 (with the long-prompt option); 200,000 requests in 26 message batches submitted on 2026-10-11 at 18:13 PDT, all processed within about four hours (on the model's release day a smaller batch had not started in 21 hours); 199,535 prompts written, 465 dropped (205 refusals, 152 tool-call stops, 86 over the ceiling, 16 API errors, 6 without prompt text), 351 continued in a second round after pausing; Anthropic's server-side web tools; like batches 063/064, no rule against quoting from memory |

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
| `attached_pages` | link prompts only: the URL and SHA-256 hash of each page that preceded the prompt in the user message (see [Link prompts](#link-prompts)) |
| `prompt` | exactly what was sent, as the single user message (a `system_prompt` field appears only if a run used one); for a link prompt, the prompt text without the pages before it |
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
| run_012 | Qwen3.5-397B-A17B (Apache 2.0) | `batch_041` | 39,942 | temperature 0.6, top-p 0.95, top-k 20 | same endpoints; 22 truncated |
| run_013 | DeepSeek R1 0528 (MIT) | `batch_041` | 39,942 | temperature 0.6, top-p 0.95; 65,536-token budget | fp8 endpoint: SiliconFlow; 1 truncated |
| run_014 | DeepSeek R1 0528 (MIT) | `r1_gap` | 14,298 (2 per prompt) | temperature 0.6, top-p 0.95; 65,536-token budget | fp8 endpoint: SiliconFlow; two independent samples per prompt |
| run_015 | Qwen3.5-397B-A17B (Apache 2.0) | `qwen397b_gap` | 98,298 (2 per prompt) | temperature 0.6, top-p 0.95, top-k 20 | fp8 endpoints load-balanced: DeepInfra, AtlasCloud, GMICloud, Parasail; two independent samples per prompt; 57 truncated |
| run_016 | Qwen3.5-397B-A17B (Apache 2.0) | `batch_046` | 200,000 (2 per prompt) | temperature 0.6, top-p 0.95, top-k 20 | fp8 endpoints load-balanced: AtlasCloud, DeepInfra, GMICloud, Parasail; two independent samples per prompt; 141 truncated |
| run_017 | DeepSeek R1 0528 (MIT) | `batch_045` | 40,000 (2 per prompt) | temperature 0.6, top-p 0.95; 65,536-token budget | fp8 endpoint: SiliconFlow; two independent samples per prompt |
| run_018 | DeepSeek R1 0528 (MIT) | `batches_042-044_047_049` | 48,000 (2 per prompt) | temperature 0.6, top-p 0.95; 65,536-token budget | fp8 endpoint: SiliconFlow; two independent samples per prompt |
| run_019 | Qwen3.5-397B-A17B (Apache 2.0) | `batches_047_049` | 4,000 (2 per prompt) | temperature 0.6, top-p 0.95, top-k 20 | fp8 endpoints load-balanced: DeepInfra, AtlasCloud, Parasail, GMICloud; two independent samples per prompt; 7 truncated |
| run_020 | DeepSeek R1 0528 (MIT) | `batch_046` | 200,000 (2 per prompt) | temperature 0.6, top-p 0.95; 65,536-token budget | fp8 endpoint: SiliconFlow; two independent samples per prompt; 6 truncated |
| run_021 | DeepSeek R1 0528 (MIT) | `batches_050_051` | 140,000 (2 per prompt) | temperature 0.6, top-p 0.95; 65,536-token budget | fp8 endpoint: SiliconFlow; two independent samples per prompt; 3 truncated |
| run_022 | Qwen3.5-397B-A17B (Apache 2.0) | `batches_050_051` | 140,000 (2 per prompt) | temperature 0.6, top-p 0.95, top-k 20 | fp8 endpoints load-balanced: DeepInfra, AtlasCloud, GMICloud, Parasail; two independent samples per prompt; 68 truncated |
| run_023 | DeepSeek R1 0528 (MIT) | `batch_053` | 2,000 (2 per prompt) | temperature 0.6, top-p 0.95; 65,536-token budget | fp8 endpoint: SiliconFlow; two independent samples per prompt |
| run_024 | Qwen3.5-397B-A17B (Apache 2.0) | `batch_053` | 2,000 (2 per prompt) | temperature 0.6, top-p 0.95, top-k 20 | fp8 endpoints load-balanced: DeepInfra, AtlasCloud, GMICloud, Parasail; two independent samples per prompt |
| run_025 | DeepSeek R1 0528 (MIT) | `batch_048` | 100,000 (2 per prompt) | temperature 0.6, top-p 0.95; 65,536-token budget | fp8 endpoint: SiliconFlow; two independent samples per prompt; 6 truncated |
| run_026 | Qwen3.5-397B-A17B (Apache 2.0) | `batch_048` | 100,000 (2 per prompt) | temperature 0.6, top-p 0.95, top-k 20 | fp8 endpoints load-balanced: DeepInfra, AtlasCloud, GMICloud, Parasail; two independent samples per prompt; 65 truncated |
| run_027 | DeepSeek R1 0528 (MIT) | `batch_052` | 100,000 (2 per prompt) | temperature 0.6, top-p 0.95; 65,536-token budget | fp8 endpoint: SiliconFlow; two independent samples per prompt; 2 truncated |
| run_028 | Qwen3.5-397B-A17B (Apache 2.0) | `batch_052` | 100,000 (2 per prompt) | temperature 0.6, top-p 0.95, top-k 20 | fp8 endpoints load-balanced: DeepInfra, AtlasCloud, GMICloud, Parasail; two independent samples per prompt; 49 truncated |
| run_029 | Qwen3.5-397B-A17B (Apache 2.0) | `batch_054` | 99,998 (2 per prompt) | temperature 0.6, top-p 0.95, top-k 20 | fp8 endpoints load-balanced: DeepInfra, AtlasCloud, GMICloud, Parasail; two independent samples per prompt; 28 truncated; the answers to prompt 514227, deleted from batch 054, removed |
| run_030 | DeepSeek R1 0528 (MIT) | `batch_055` | 100,000 (2 per prompt) | temperature 0.6, top-p 0.95; 65,536-token budget | fp8 endpoint: SiliconFlow; two independent samples per prompt; 4 truncated |
| run_031 | Qwen3.5-397B-A17B (Apache 2.0) | `batch_055` | 100,000 (2 per prompt) | temperature 0.6, top-p 0.95, top-k 20 | fp8 endpoints load-balanced: DeepInfra, AtlasCloud, GMICloud, Parasail; two independent samples per prompt; 13 truncated |
| run_032 | DeepSeek R1 0528 (MIT) | `batch_054` | 99,998 (2 per prompt) | temperature 0.6, top-p 0.95; 65,536-token budget | fp8 endpoint: SiliconFlow; two independent samples per prompt; 6 truncated; the answers to prompt 514227, deleted from batch 054, removed |
| run_033 | DeepSeek R1 0528 (MIT) | `second_sample` | 89,293 (1 per prompt) | temperature 0.6, top-p 0.95; 65,536-token budget | fp8 endpoint: SiliconFlow; the second sample for prompts that had one; 2 truncated |
| run_034 | Qwen3.5-397B-A17B (Apache 2.0) | `second_sample` | 89,293 (1 per prompt) | temperature 0.6, top-p 0.95, top-k 20 | fp8 endpoints load-balanced: DeepInfra, AtlasCloud, GMICloud, Parasail; the second sample for prompts that had one; 16 truncated |
| run_035 | DeepSeek R1 0528 (MIT) | `batch_056` | 10,000 (2 per prompt) | temperature 0.6, top-p 0.95; 65,536-token budget | fp8 endpoint: SiliconFlow; two independent samples per prompt; none truncated |
| run_036 | Qwen3.5-397B-A17B (Apache 2.0) | `batch_056` | 10,000 (2 per prompt) | temperature 0.6, top-p 0.95, top-k 20 | fp8 endpoints load-balanced: DeepInfra, AtlasCloud, GMICloud, Parasail; two independent samples per prompt; none truncated |
| run_038 | DeepSeek R1 0528 (MIT) | `batches_057-060_062-064` | 61,744 (2 per prompt) | temperature 0.6, top-p 0.95; 65,536-token budget | fp8 endpoint: SiliconFlow; two independent samples per prompt; 1 truncated |
| run_039 | Qwen3.5-397B-A17B (Apache 2.0) | `batches_057-060_062-064` | 61,744 (2 per prompt) | temperature 0.6, top-p 0.95, top-k 20 | fp8 endpoints load-balanced: DeepInfra, Parasail, AtlasCloud, GMICloud; two independent samples per prompt; 14 truncated; one answer (a pretend browser call) regenerated |
| run_042 | Qwen3.5-397B-A17B (Apache 2.0) | `batch_066` | 39,998 (2 per prompt) | temperature 0.6, top-p 0.95, top-k 20 | fp8 endpoints load-balanced: GMICloud, DeepInfra, AtlasCloud, Parasail; two independent samples per prompt; 4 truncated |
| run_043 | DeepSeek R1 0528 (MIT) | `batch_066` | 39,998 (2 per prompt) | temperature 0.6, top-p 0.95; 65,536-token budget | fp8 endpoint: SiliconFlow; two independent samples per prompt; none truncated; one answer cut off at the host regenerated |
| run_044 | DeepSeek R1 0528 (MIT) | `batch_065` | 39,998 (2 per prompt) | temperature 0.6, top-p 0.95; 65,536-token budget | fp8 endpoint: SiliconFlow; two independent samples per prompt; none truncated |
| run_045 | Qwen3.5-397B-A17B (Apache 2.0) | `batch_065` | 39,998 (2 per prompt) | temperature 0.6, top-p 0.95, top-k 20 | fp8 endpoints load-balanced: GMICloud, Parasail, AtlasCloud, DeepInfra; two independent samples per prompt; 9 truncated; two answers regenerated (one written for a prompt's pre-curation text, one stuck in a loop) |

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
Set `batch_045` lists the 20,000 prompts of batch 045; run 017 answered them twice with
R1, so batch 045 too has two R1 samples per prompt.
Set `batches_042-044_047_049` lists the 24,000 prompts of the Inkling and HY4 batches
042–044 and of the test batches 047 and 049; run 018 answered them twice with R1, so
every prompt of batches 000–045, 047, and 049 has an R1 response, and all but the
prompts of batches 033, 035, 038, and 041 and the `open_1k` prompts (which keep their
single run 003 response) have two.
Set `qwen397b_gap` lists the 49,149 prompts of batches 022–045 that had no
Qwen3.5-397B-A17B response after runs 007–012 (42,000 of them in the Inkling and HY4
batches 042–045); run 015 answered them twice with Qwen. Every prompt of batches
000–045 now has at least one Qwen3.5-397B-A17B response, and all but the prompts of
batches 033, 035, 038, and 041 and the `open_1k` prompts (which keep their single
run 000 response) have two.
Set `batches_047_049` lists the 2,000 prompts of the test batches 047 and 049; run 019
answered them twice with Qwen3.5-397B-A17B, so the same holds for batches 000–045, 047,
and 049.
Set `batch_046` lists the 100,000 prompts of batch 046; run 016 answered them twice with
Qwen3.5-397B-A17B while the batch was still being generated (the queue refreshed the set
as prompts arrived), so every prompt of batches 000–047 and 049 has a Qwen3.5-397B-A17B
response, and all but the prompts of batches 033, 035, 038, and 041 and the `open_1k`
prompts have two. Run 020 answered the same 100,000 prompts twice with R1, so every
prompt of batches 000–047, 049, and 053 has an R1 response, and all but the prompts of
batches 033, 035, 038, and 041 and the `open_1k` prompts have two.
Set `batches_050_051` lists the 70,000 prompts of batches 050 and 051; run 022 answered them
twice with Qwen3.5-397B-A17B, so every prompt of batches 000–047, 049–051, and 053 has a
Qwen3.5-397B-A17B response, and all but the prompts of batches 033, 035, 038, and 041 and
the `open_1k` prompts have two.
Run 021 answered the same 70,000 prompts twice with R1, so every prompt of batches 000–051
and 053 has an R1 response, and all but the prompts of batches 033, 035, 038, and 041 and
the `open_1k` prompts have two.
Set `batch_053` lists the 1,000 prompts of the MiMo-V2.6-Pro test batch; runs 023 and 024
answered them twice each with R1 and with Qwen3.5-397B-A17B.
Set `batch_048` lists the 50,000 prompts of batch 048; run 026 answered them twice with
Qwen3.5-397B-A17B, so every prompt of batches 000–051 and 053 has a Qwen3.5-397B-A17B
response, and all but the prompts of batches 033, 035, 038, and 041 and the `open_1k`
prompts have two.
Run 025 answered the same 50,000 prompts twice with R1, so every prompt of batches 000–049
and 053 has an R1 response, and all but the prompts of batches 033, 035, 038, and 041 and
the `open_1k` prompts have two.
Set `batch_052` lists the 50,000 prompts of batch 052; run 028 answered them twice with
Qwen3.5-397B-A17B, so every prompt of batches 000–053 has a Qwen3.5-397B-A17B response,
and all but the prompts of batches 033, 035, 038, and 041 and the `open_1k` prompts have
two.
Run 027 answered the same 50,000 prompts twice with R1, so every prompt of batches 000–053
has an R1 response, and all but the prompts of batches 033, 035, 038, and 041 and the
`open_1k` prompts have two.
Set `batch_054` lists the 49,999 prompts of batch 054; run 029 answered them twice with
Qwen3.5-397B-A17B, so every prompt of batches 000–054 has a Qwen3.5-397B-A17B response,
and all but the prompts of batches 033, 035, 038, and 041 and the `open_1k` prompts have
two.
Set `batch_055` lists the 50,000 prompts of batch 055; run 031 answered them twice with
Qwen3.5-397B-A17B, so every prompt of batches 000–055 has a Qwen3.5-397B-A17B response,
and all but the prompts of batches 033, 035, 038, and 041 and the `open_1k` prompts have
two.
Run 032 answered the 49,999 prompts of set `batch_054` twice with R1, so every prompt of
batches 000–054 has an R1 response, and all but the prompts of batches 033, 035, 038, and
041 and the `open_1k` prompts have two.
Run 030 answered the 50,000 prompts of set `batch_055` twice with R1, so every prompt of
batches 000–055 has an R1 response.
Set `second_sample` lists the 89,293 prompts of batches 000–053 that had one response per
model: nearly all of batches 033, 035, 038, and 041, plus 213 `open_1k` prompts that kept
their single early-run response. Run 034 gave each a second Qwen3.5-397B-A17B sample (the
first is in run 000, 007, 008, 011, or 012), so every prompt of batches 000–055 now has two
Qwen3.5-397B-A17B responses; run 033 gave each a second R1 sample (the first is in run
003, 006, 009, 010, or 013), so every prompt of batches 000–055 also has two R1 responses.
A prompt trimmed during curation after its first sample (five in
batch 041 on 2026-09-28) got the second sample on the trimmed text.
Set `batch_056` lists the 5,000 prompts of batch 056; run 036 answered them twice with
Qwen3.5-397B-A17B, so every prompt of batches 000–056 has two Qwen3.5-397B-A17B responses,
and run 035 answered them twice with R1, so every prompt of batches 000–056 also has two R1
responses.
Set `batches_057-060_062-064` lists the 30,872 prompts of batches 057–060 and 062–064; run 039
answered them twice with Qwen3.5-397B-A17B and run 038 twice with R1. Set `batch_066` lists the
19,999 prompts of batch 066, answered twice by each model (runs 042 and 043), and set `batch_065`
the 19,999 prompts of batch 065, answered twice by each model as well (runs 045 and 044). So every
prompt of batches 000–060 and 062–066 has two responses from each model.

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

## Link prompts

A *link prompt* comes with one to three web pages that the asker shares: the prompt text
gives their URLs, as a user pasting links would, and the model that answers sees each
page's text in its user message, ahead of the prompt. The answering model gets no tools
and fetches nothing, so a response is still a single completion; it can read the shared
pages and nothing else on the web. Link prompts let the dataset build on real web pages
(blog and forum posts, encyclopedia entries, Stack Exchange threads, papers) without
publishing them: the dataset holds the pages' URLs, metadata, and hashes, not their text.

Link prompts are written in link batches of their own (`generate_prompt_oai.py
--link-prompts`). The generating model picks a domain as usual and chooses the pages
itself, among stable links only: links to a version of a page that cannot change, such
as a Wayback Machine capture with its full timestamp
(`https://web.archive.org/web/20260621024306/https://www.lesswrong.com/posts/...`), a
Wikipedia revision (the page's "Permanent link", `index.php?title=...&oldid=...`), an entry
in a quarterly archive edition of the Stanford Encyclopedia of Philosophy
(`plato.stanford.edu/archives/fall2026/entries/...`), or one version of an arXiv paper,
by its abstract link (`https://arxiv.org/abs/2307.04879v2`). `generators/link_cache.py` lists the patterns (`STABLE_LINKS`);
more kinds can be added. A stable link is a page of its own: `tools/build_link_cache.py`
fetches its text from the link itself (for a Wayback capture, the page as archived, and
only if the archive has a capture at exactly that timestamp; for a Wikipedia revision,
that revision as Wikipedia renders it, through its API, since Wikipedia's robots.txt bars
scripts from the permanent-link pages; for an arXiv version, that version's source, which
arXiv keeps as it was submitted, rendered by LaTeXML in a sandbox; a version whose source is
only a PDF, or that LaTeXML cannot render, is skipped rather than taken from a PDF), never
from the live page it is a version of, and
the prompt gives the link as it is. (arXiv's own HTML versions are not stable: arXiv
re-renders them.) A domain lists its stable links under `stable_urls`,
apart from the links under `urls`, which remain the inspiration links of ordinary prompts;
`tools/add_stable_links.py` adds them (on 2026-10-22, for every linked Wikipedia article, the
revision current that day: 9,891 links on 3,523 domains; and for every linked arXiv paper the
version the link names, else the latest: 989 links to 816 papers on 455 domains). The five domains offered are drawn
among those with stable links of 1,500 to 100,000 characters of text, and under each the
meta-prompt lists up to three of them, with URL, title, author, site, date, length, license,
and opening words.
The model reads the pages it considers with its web_fetch tool, which serves them from
frozen copies: every listed page's text is frozen when the prompt is sampled, into an
append-only store keyed by the SHA-256 hash of each text (`link_cache/snapshots.sqlite`, not
published). So the generating model reads exactly the text the answering model will get,
and a later re-crawl of the cache cannot change it. The prompt attaches a page by giving its
URL: one page, or two or three if the prompt compares or combines them, usually from the
chosen domain, with at most 16,000 words together. The meta-prompt asks for a prompt that
depends on what the attached pages actually say and does not paste them; it may ask for a
whole page to be reworked (translated, rewritten, summarized throughout) only if the page is
under CC BY or CC0 or in the public domain. A generated prompt is generated again if it
gives an unlisted URL, attaches no page, more than three pages, or more than 16,000 words,
or attaches a page the model did not read. Link samples drop the inspiration links and the
quote-inclusion instruction. The sidecar lists the pages offered (`pages_offered`), read
(`pages_read`), and attached (`attached_pages`); a page's entry has the URL as the prompt
gives it and as the domain list has it, title, author, site, publication date, the license
where the source states one, when and how the text was fetched, its length, and its hash.

`generate_responses.py` sends a link prompt as one user message: each page as a `<page
url="...">` element (a header with the title, author, site, date, and license where known,
a blank line, and the text), the pages separated by blank lines, then a blank line and the
prompt (format `page-v1`, `generators/attached_pages.py`). The response file keeps the
prompt text alone under `prompt` and lists the pages' URLs and hashes under
`attached_pages`; `run.yaml` names the page format and the store.

On the Hub, link batches and the runs that answer them have configs of their own,
`link_prompts` and `link_responses`, whose rows add the `attached_pages` list. Since every
attached page is a stable link, its URL pins the page: anyone can fetch it and extract the
text as `tools/build_link_cache.py` does, and the hash tells whether the result is the text
the models saw. A link batch with an attached page that is not a stable link is not
exported.
`tools/check_link_batch.py` reports on a link batch: the pages per prompt, their sources and
licenses, whether the store holds every text, URL problems, how much of a page the prompts
copy, and prompts that seem to ask for a whole page that is not openly licensed to be
reworked.

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
- The four batches generated with Tencent's HY4 preview (043, 045, 054, 059) have
  flaws the other generators rarely show, and HY4 is not used for new batches. In
  808 prompts of batch 054 (1.6%), 88 of batch 045 (0.4%), and 4 of batch 043, a
  stray Chinese word, now and then a Korean or Japanese one, stands in for an
  English word ("the repricing of尾部 risk", "selection and多重 comparisons");
  sometimes the asker corrects it in the next words ("sorry, ..."). 72 prompts of
  batch 054 contain a leaked `<｜hy_place▁holder▁no▁813｜>` token, and 27 of those
  break off mid-sentence right after it. These prompts were left in place: the
  answering models mostly read past the stray word (in a sample of 150 such
  prompts, 2-3% of the R1 and Qwen answers mention or repeat it). Batch 059's 30
  stray words were translated back and its five word-salad prompts deleted, as was
  one gibberish prompt in batch 054. GLM-5.3, Qwen3.8 2.4T, DeepSeek V4 Pro, and
  MiMo batches have 49 stray words between them. `tools/check_batch.py` flags all
  of these (counts and examples in `QUALITY_NOTES.md`).

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

**Provenance notice.** The prompts of batches 000–021, 030, 063, 064, and 067 are outputs of Anthropic
Claude models. If you use them, you are responsible for complying with
[Anthropic's terms and usage policies](https://www.anthropic.com/legal) as they
apply to Claude outputs — in particular, restrictions on using outputs to train
models that compete with Anthropic. Batch 037 is the output of Muse Spark 1.3, a
proprietary Meta model accessed through the standard tier of the
[Meta Model API](https://developer.meta.com/ai/products/meta-model-api/) via
OpenRouter; its use is subject to Meta's terms for that API. Batches 022–029, 031, and 040 were generated with Qwen
3.8 27B, an open-weights model released under Apache 2.0; via OpenRouter, batches
032–033 with DeepSeek V4 Pro, batches 049, 051, 052, and 066 with DeepSeek V4 Pro 0813, and batches
039 and 041 with DeepSeek V4.1 Flash, and batches 053, 055–058, and 060 with Xiaomi's MiMo-V2.6-Pro, open-weights
models released under the MIT license, batches 042, 044, and 046 with Thinking
Machines' Inkling and batches 043, 045, 054, and 059 with Tencent's HY4 preview, both open-weights
models released under Apache 2.0, and batches 034–035, 062, and 065 with GLM-5.3, an open-weights model released under Z.ai's GLM-5.3
License (MIT terms plus a security-review condition for model-as-a-service operators
above $10 billion in annual revenue; it places no restrictions on the use of
outputs). Batches 036, 038, and 048 were generated with Qwen3.8 2.4T-A95B, an open-weights model
released under the Qwen3.8-Max License (MIT terms plus an attribution requirement
for products above 100 million monthly users or $20 million in monthly revenue, and
a separate-license requirement for model-as-a-service businesses above $50 million
in annual revenue; no restrictions on the use of outputs). Batches 047 and 050 were generated
with Kimi K3, an open-weights model released under Moonshot's Kimi K3 License (MIT terms
plus an attribution requirement for products above 100 million monthly active users or
$20 million in monthly revenue; no restrictions on the use of outputs). Responses under `responses/` come only from open-weights models whose
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
tools/install_latexml.sh              # LaTeXML and TeX Live 2025 for arXiv sources (half an hour, 5 GB)
python tools/arxiv_latexml.py --self-test   # the sandbox LaTeXML runs in holds
python tools/build_link_cache.py      # local copies of the domain links for web_fetch (a few hours)

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
