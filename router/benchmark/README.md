# Router benchmark: build the training data, train, evaluate

The router learns from real answers. You run your prompts through all three Lumen
models (Ornith 1.0 35B, DeepSeek V4 Flash, GLM 5.3) once, have a judge score every answer, and train on those scores. After that
the app calls only one model per prompt.

Needs `LUMEN_API_KEY` in `.env` for step 2 (costs are in Lumen coins; a few coins for 200 prompts × 3 models).
Run every command from the project root with the virtualenv active.

## 1. Write the prompts

Copy `prompts.template.csv` to `prompts.csv` and add about 200 prompts:

| Column | What to put |
|---|---|
| `id` | Unique id, e.g. `P001` |
| `prompt` | The full prompt. Wrap it in double quotes if it has commas or line breaks; write a literal `"` as `""` |
| `category` | `coding`, `math`, `summarization`, `writing`, `extraction` or `chat` |
| `difficulty` | `easy`, `medium` or `hard` (your guess, used in the report) |
| `source` | Where it came from: written by you, or a public dataset, split and row |
| `reference` | Optional. The benchmark's gold answer; shown to the judge, never to the models |

Aim for about 33 per category, with a mix of easy, medium and hard. Include prompts
where you expect the small model to fail; that is what the router needs to learn.

## 2. Run the benchmark

```bash
python manage.py run_benchmark --limit 3     # try 3 prompts first
python manage.py run_benchmark               # then everything (skips finished rows)
```

Writes `results.jsonl` (answer, tokens, latency, cost for every prompt × model) and
saves each model's median latency and median cost per answer for the router's speed and cost scores. Stops at `--max-spend`
(default 10 coins; stops cleanly if the Lumen budget runs out). If something fails, rerun with `--retry-errors`.

## 3. Judge the answers (offline, in ChatGPT)

```bash
python manage.py export_for_judging --batch-size 10
```

Easiest (macOS): `python manage.py judge_clipboard`. It copies each batch to your
clipboard; you paste it into a new ChatGPT chat, copy the reply and press Enter. It checks the
reply and saves it for you. Or do it by hand:

1. Open `judge_batches/batch_01.md`, start a **new chat** with ChatGPT's strongest model,
   and paste the whole file. Answers are labeled A/B/C in random order; the judge never
   sees model names.
2. Save its CSV reply as `judgments/batch_01.csv`. Repeat for each batch.
3. Write the judge model's name and the date in `judgments/JUDGE.md`.
4. Hand-grade about 30 answers yourself in `spot_checks.csv`
   (`prompt_id,model_id,human_score`). Look up which model is which in `judge_key.json`
   *after* you have graded.

```bash
python manage.py import_judgments
```

Checks every row, writes `labels.csv`, and prints how often you and the judge agree.

## 4. Train

```bash
python manage.py train_router
```

Holds out 20% of prompts as the test set (saved in `split.json`, reused on retraining),
trains on the rest and writes `router/artifacts/router.joblib`. The app picks it up on
the next request; no restart needed.

## 5. Evaluate

```bash
python manage.py evaluate_router
```

Writes `docs/eval/router_eval.md`: the router against always-small/medium/large, random,
keyword rules and the oracle, plus calibration, a cost-vs-quality curve and per-prompt
decisions. Uses only the recorded results; it makes no API calls.

## Files

| File | Made by | Commit? |
|---|---|---|
| `prompts.csv`, `rubric.md` | you | yes |
| `results.jsonl` | `run_benchmark` | yes (evidence for the report) |
| `judge_batches/*.md`, `judge_key.json` | `export_for_judging` | yes |
| `judgments/*.csv`, `judgments/JUDGE.md`, `spot_checks.csv` | you | yes |
| `labels.csv`, `split.json` | `import_judgments`, `train_router` | yes |
