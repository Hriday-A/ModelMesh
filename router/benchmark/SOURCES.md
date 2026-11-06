# Where the benchmark prompts come from

All 200 prompts in `prompts.csv` are items from public benchmarks. None were written for
this project. Each row's `source` column names the dataset, config/split and row index,
so every prompt can be traced to the original. The rows were sampled with a fixed seed
(490), using the filters below. The selection script is deterministic; rerunning it on the same
downloads gives the same 200 rows. Dolly and the large sets were sampled from random
100-row pages, not the whole dataset.

## Why these benchmarks

Published LLM routers are trained and evaluated on public "golden" sets like these:

- **RouteLLM** (Ong et al., 2024, arXiv 2406.18665) evaluates on MT-Bench, MMLU and GSM8K.
- **RouterBench** (Hu et al., 2024, arXiv 2403.12031) builds its routing benchmark from
  MBPP, GSM8K, MT-Bench, MMLU, Hellaswag, Winogrande and ARC.

We keep their core sets (MBPP, GSM8K, MT-Bench). We leave out MMLU, Hellaswag, Winogrande
and ARC, which are multiple-choice: a 1–10 judge has little to grade there, and ModelMesh
users ask open-ended questions. In their place we add open-ended sets for the six ModelMesh
categories.

## Mix (200 prompts)

| Category | Easy | Medium | Hard |
|---|---|---|---|
| Coding (34) | MBPP sanitized, 12 | HumanEval, 11 | BigCodeBench-Hard (instruct), 11 |
| Math (33) | GSM8K, 11 | MATH-500 levels 2–3, 11 | MATH-500 level 5, 11 |
| Summarization (33) | XSum, 150–350-word articles, 11 | CNN/DailyMail, 350–600 words, 11 | CNN/DailyMail, 750–1,000 words, 11 |
| Extraction (33) | SQuAD v2 answerable, passages ≤ 250 words, 11 | Dolly information_extraction, 11 | DROP numeric questions, 11 |
| Writing (33) | Dolly creative_writing whose instruction asks to write, compose, create, etc. (Dolly mislabels some plain questions), 11 | MT-Bench writing/roleplay (turn 1), 11 | IFEval, prompts with ≥ 3 constraints, 11 |
| Chat (34) | Dolly open_qa/general_qa/brainstorming, 12 | MT-Bench humanities/stem (turn 1), 11 | Arena-Hard-Auto v0.1, excluding its coding, technical and math topic clusters, 11 |

**How difficulty is set:** by each benchmark's own level where it has one (MATH level,
BigCodeBench-Hard, Arena-Hard), and otherwise by which benchmark the item comes from or by
input length (summarization). These labels are our grouping; the router never sees them.

## Prompt wrappers

Where a benchmark item is not already a full instruction, it is wrapped in a fixed
template:

- **MBPP:** the template from the MBPP paper: "You are an expert Python programmer, and
  here is your task: … Your code should pass these tests: …"
- **HumanEval:** "Complete the following Python function. Return the complete function."
  followed by the function signature and docstring.
- **XSum:** "Summarize the following article in one sentence."
- **CNN/DailyMail:** "Summarize the following news article in 3 sentences." (HELM's
  standard instruction)
- **SQuAD v2:** "Answer the question using only the passage below. Reply with the shortest
  exact answer from the passage."
- **DROP:** "Read the passage and answer the question. Give only the final answer."
- **All other sets** (BigCodeBench instruct prompt, GSM8K, MATH, Dolly instruction plus
  context, MT-Bench turn 1, IFEval, Arena-Hard) are used verbatim.

## References for the judge

The `reference` column carries the benchmark's gold material: the canonical solution, the
final answer and worked solution, the reference summary, the accepted answer spans, a
human-written response, or IFEval's constraint list. `export_for_judging` shows it to the
judge, never to the models. Reference-guided grading makes LLM judges noticeably more
reliable on math and reasoning (Zheng et al., 2023, "Judging LLM-as-a-Judge with MT-Bench
and Chatbot Arena", arXiv 2306.05685).

Two kinds of prompt have no reference:
- **Arena-Hard:** it compares answers against a baseline model rather than a gold answer.
- **MT-Bench writing, roleplay, humanities and stem:** MT-Bench only has references for
  math, reasoning and coding.

## Licenses

From each dataset's Hugging Face card:

| Dataset | License |
|---|---|
| google-research-datasets/mbpp | CC BY 4.0 |
| openai/openai_humaneval | MIT |
| bigcode/bigcodebench-hard | not stated on the card (BigCodeBench is Apache-2.0 on GitHub; check before redistributing) |
| openai/gsm8k | MIT |
| HuggingFaceH4/MATH-500 | not stated on the card (from MATH, Hendrycks et al., MIT) |
| EdinburghNLP/xsum | listed as "unknown" |
| abisee/cnn_dailymail | Apache 2.0 |
| rajpurkar/squad_v2 | CC BY-SA 4.0 |
| ucinlp/drop | CC BY-SA 4.0 |
| databricks/databricks-dolly-15k | CC BY-SA 3.0 |
| HuggingFaceH4/mt_bench_prompts | Apache 2.0 |
| google/IFEval | Apache 2.0 |
| lmarena-ai/arena-hard-auto-v0.1 | Apache 2.0 |

We use these items for course evaluation only.

## Known limitations

- **Contamination:** these benchmarks are public, so the three models may have seen them
  in training. Scores may be higher than on fresh user prompts. This affects all three
  models, so comparing them is still meaningful, but absolute quality is likely
  overstated.
- **Data quality:** Dolly and XSum responses and summaries are crowd-written, and some are
  imperfect. The judge is told that a reference is one good answer, not the only one.
- **Long inputs:** summarization and extraction prompts are long, so batches containing
  them are longer to paste.

## Rebuilding the set

```bash
mkdir -p /tmp/bench_raw
python router/benchmark/scripts/fetch_benchmarks.py /tmp/bench_raw          # Hugging Face datasets-server API
python router/benchmark/scripts/build_prompts.py /tmp/bench_raw router/benchmark/prompts.csv
```

The fetch samples random pages with seed 490. The API sometimes rate-limits; the script retries.
