# ModelMesh smart router: AI plan and initial implementation

Owner: Srinath · App: `router` · Screens 11 (Routing rules) and 12 (Explanation & feedback)
P2-A3 First-Draft Requirement 3.

## 1. What the AI does

ModelMesh sends each prompt to one of three open-weight models served by UIUC's Lumen
API (OpenAI-compatible). They are tiered by total parameters, checked on each model's
Hugging Face page:

| Tier | Model (Lumen id) | Total params | Input / output coins per 1M tokens |
|---|---|---|---|
| Small | Ornith 1.0 35B (`ornith-1.0-35b`, FP8 weights, MoE) | 35B (active not stated) | 0.05 / 0.10 |
| Medium | DeepSeek V4 Flash 0731 (`deepseek-v4-flash`) | 304B | 0.16 / 0.37 |
| Large | GLM 5.3 (`glm-5.3`) | 753B | 1.32 / 4.25 |

The small tier was first Qwen3.6 35B-A3B (0.19 / 1.14), but that cost more per output token
than the medium model, so it was replaced with Ornith 1.0 35B and list price now rises with
size. List price is still not the whole story: all three are thinking models and write very
different numbers of tokens (on one test question: Ornith 509 output tokens, DeepSeek 54,
GLM 48). So the router ranks cost by each model's **median measured cost per answer** from
the benchmark (falling back to list price until every model has been measured), and speed
by median measured latency. Tier is a label for explanations and keyword fallback. All three are thinking models; every call
sets `reasoning_effort=high` so latency and cost are comparable (the GLM and DeepSeek cards list only low/high/max; GLM treats any other value as max) (`ROUTER_REASONING_EFFORT`).

The large model costs about 11× the medium model per output token and may be better on
hard prompts. Sending everything to it wastes coins, and sending everything to a cheaper
model may hurt quality. The router **predicts, for each prompt, each model's chance of
giving a good answer**, then picks the model with the best trade-off between that chance,
price and speed for the user's priority (Balanced, Cheapest, Fastest, Best quality).

## 2. Technique and why

**Approach: a learned router trained on our own judged benchmark.** It follows RouteLLM
(Ong et al., 2024, arXiv 2406.18665), extended from two models to three.

- **The LLMs are never trained or fine-tuned.** Only the router is.
- **Prompt embedding:** `sentence-transformers/all-MiniLM-L6-v2`, a small (22M-parameter)
  Hugging Face model running on CPU. It turns a prompt into 384 numbers that capture its
  meaning. Measured: about 7 ms per prompt after loading.
- **Quality predictors:** one scikit-learn logistic regression per LLM, trained on
  "did the judge rate this model's answer 9/10 or better?" (near-perfect; see section 6 for
  why 9 and not 7). Output: P(good answer).
- **Category classifier:** a logistic regression over the same embedding, predicting one of
  coding, math, summarization, writing, extraction, chat. Used for explanations, admin
  rules and feedback, not for the decision itself.
- **Decision formula:**
  `score = P(good) × w_quality − price × w_cost − slowness × w_speed`, where price (median
  measured coins per answer) and slowness (median measured latency) are relative to the
  most expensive and slowest model (0–1) and the weights come
  from the user's priority times the admin sliders on Screen 11.
- **Confidence bar:** if the best-scoring model's P(good) is below the threshold (default
  0.6), the router moves to a model that clears it.
- **Learning from users:** star ratings on Screen 12 pull each model's P(good) for that
  category toward the average rating: `(5·P + n·stars/5) / (5 + n)`.

**Why this over the alternatives**

| Option | Why not (for now) |
|---|---|
| Ask an LLM to pick the model | Adds a paid call and hundreds of ms to every request; harder to evaluate. |
| Fine-tune a small LLM or BERT as the router | Needs thousands of examples and a GPU; we have about 200. RouteLLM found light embedding-based routers competitive with BERT/LLM classifiers. Planned as a Dec 8 comparison once the benchmark has about 300 prompts. |
| Hosted classifier (TypeSafe Jev, via LiteLLM's Auto Router) | Paid external dependency, and the router would be someone else's model. Planned as an optional second opinion and baseline. |
| Keyword rules only | Kept as the fallback and as a baseline; misses paraphrases. |

Related work considered: Arch-Router (arXiv 2506.16655) for human-readable routing
categories (our Screen 11 rules); LiteLLM's routing strategies and fallbacks; multi-turn
routing (DialRouter arXiv 2604.12385, SWRouter arXiv 2609.11414, SeqRoute arXiv 2605.25424)
for the Dec 8 extension.

## 3. Input and output

- **In:** the prompt text and the priority (from the Playground form, the `/api/chat`
  body, or the user's profile default).
- **Out:** the chosen model and an ordered list of fallbacks, the predicted category,
  P(good) for every model, the score table, and a one-line reason. Example format:
  `Coding · chance of a good answer: Ornith 41% / DeepSeek 88% / GLM 93% · Balanced → DeepSeek V4 Flash`
  (illustrative numbers, not a measured result).

## 4. How it connects to Django

```
Playground form / POST /api/chat
  → accounts.services.run_prompt()            (Hriday's code, unchanged)
    → router.services.route(prompt, priority)  (settings.MODELMESH_ROUTER)
        decide(): embed → 3 × P(good) → feedback blend → score → confidence bar → admin rules
        llm.complete(top model); on error, the next model (failover)
    → RequestLog saved
      → router.signals: saves RoutingDecision (OneToOne RequestLog) and sets the real
        per-model cost_usd, so the Usage dashboard is correct
  → Playground shows the answer and the reason
  → /routing/requests/ → /routing/explain/<id>/ shows the score table and takes star feedback
```

Models: `RouterModel` (the 3 Lumen models and coin prices), `RoutingRule` (FKs to
RouterModel), `RoutingSettings`, `RoutingDecision` (OneToOne `RequestLog`), `Feedback`
(OneToOne `RequestLog`, FK User). The router depends on nothing unmerged from teammates.

## 5. Reliability

| Situation | What happens |
|---|---|
| Empty prompt | Rejected by the form; `decide()` also refuses it. |
| No trained classifier yet, or the file is corrupt | Keyword rules choose a model tier; the decision records `keyword_fallback`. |
| Embedder fails | Same keyword fallback; the error is logged. |
| A model errors, rate limits or refuses | The next model in order is tried; Screen 12 lists each attempt. |
| Every model fails | The request is saved as an error with the last error message. |
| No API key on the server | Clear error: "No Lumen API key found." A spent coin budget stops the benchmark cleanly. |
| Unexpected output (empty answer) | Treated as a failure and the next model is tried. |
| Privacy | Prompts go only to Lumen (UIUC/NCSA). The offline judge sees benchmark prompts we wrote, never user prompts. The CSV export (analytics) leaves prompts out. |

## 6. Evaluation plan and results

### Setup

- **Prompts:** 200 items from public benchmarks used by routing papers (RouteLLM, RouterBench):
  MBPP, HumanEval, BigCodeBench-Hard, GSM8K, MATH-500, XSum, CNN/DailyMail, SQuAD v2, Dolly,
  DROP, MT-Bench, IFEval and Arena-Hard. 6 categories × easy/medium/hard; sources, filters and
  licenses in `router/benchmark/SOURCES.md`.
- **Answers:** every prompt was sent to all three models on Lumen (`run_benchmark`,
  `reasoning_effort=high`): 600 calls, 0.56 coins in total. The main run allowed 4–5 minutes
  and 12,000 tokens per answer; unfinished answers were retried with 10 minutes and 32,000
  tokens, and a 30-minute retry was started but stopped for time. Answers that never finished
  (DeepSeek: 31 timeouts; Ornith: 10 thinking-budget overruns) are scored 1 automatically. 4 prompts were
  dropped because Lumen returned server errors (500), leaving **196 prompts**.
- **Judge:** GPT-6 Astra (High) in ChatGPT, used offline, one new chat per batch of
  10 prompts, answers anonymized and shuffled, with the benchmark's reference answer when
  there is one (see `router/benchmark/judgments/JUDGE.md`). It scores quality only, 1–10.
  Cost and latency are measured, not judged.
- **Split:** 156 prompts to train, 40 held out for testing, stratified by category, fixed seed.

### What the benchmark showed about the models (196 prompts)

| | Ornith 1.0 35B (small) | DeepSeek V4 Flash (medium) | GLM 5.3 (large) |
|---|---|---|---|
| Near-perfect answers (score 9–10) | 53% | 67% | 72% |
| Acceptable answers (score 7–10) | 78% | 81% | 90% |
| No answer (timeout / thinking budget) | 10 | 31 | 0 |
| Median latency on Lumen | 11.9 s | 16.3 s | 2.5 s |
| Median coins per answer | 0.00018 | 0.00016 | 0.00150 |
| Median output tokens (of which thinking) | 1,667 (1,362) | 192 (82) | 279 (18) |
| Median tokens per second on Lumen | 145 | 11 | 110 |

- **Size did not predict speed.** The largest model, GLM, was the fastest and the best, but
  costs about 8–10× more per answer. Ornith generates fastest but thinks the longest; DeepSeek
  writes short answers but Lumen serves it at about 11 tokens per second, so its latency and
  timeouts reflect the hosting more than the model.
- **Where the small model is enough** (share of near-perfect answers, small / medium / large):
  extraction 79% / 79% / 73% and coding 67% / 61% / 70% are close; summarization
  45% / 91% / 94% and writing 36% / 55% / 64% are not; chat (mostly Arena-Hard and MT-Bench)
  is hard for all three (19% / 38% / 41%).
- **The routing opportunity:** on 145 of 196 prompts (74%) a cheaper model than GLM gave a
  near-perfect answer (Ornith on 104, DeepSeek on another 41). GLM alone succeeded on 16; no
  model did on 35.

### Choosing the "good answer" bar: 7 vs. 9

The router learns from "was this answer good?". With the rubric's bar of 7, 78–90% of answers
were "good", and on the **training prompts** the classifiers learned nothing beyond that base
rate (cross-validated accuracy equal to always guessing "good": 75%, 79%, 89%). With a bar of
9 ("near-perfect"), the labels are more balanced and the small model's classifier beat its
base rate by 11 points (63% vs. 52%); 77 prompts instead of 53 separate the models. The bar
was therefore set to **9**, using training data only. Results at 7 are kept for comparison
(`docs/eval/router_eval_bar7.md`).

### Router results on the 40 held-out prompts (bar 9; `docs/eval/router_eval.md`)

| Strategy | Near-perfect answers | Avg judge score | Cost vs. always-GLM | Avg latency |
|---|---|---|---|---|
| Always Ornith (small) | 57% | 8.30 | 12% | 13.3 s |
| Always DeepSeek (medium) | 75% | 8.25 | 11% | 58.4 s |
| Always GLM (large) | 80% | 9.28 | 100% | 3.2 s |
| Random | 71% | 8.61 | 41% | 25.0 s |
| Keyword rules (no ML) | 70% | 8.38 | 33% | 35.6 s |
| **Router · Balanced** | **78%** | **8.75** | **46%** | 31.2 s |
| Router · Best quality | 80% | 9.15 | 77% | 13.9 s |
| Oracle (perfect router) | 90% | 9.35 | 56% | 16.1 s |

- **Balanced** keeps 78% near-perfect answers, 2 points below always using GLM, at 46% of its
  cost, and beats random (71%) and keyword rules (70%) at a similar cost.
- **Always DeepSeek** is a strong simple baseline (75% at 11% of the cost) if users can wait
  about a minute on Lumen.
- **Predictions:** test accuracy 70% (Ornith, base rate 57%), 72% (DeepSeek, 75%) and
  80% (GLM, 80%): only the small model's classifier adds information. The category classifier
  is 90% accurate. Router overhead: **9 ms** per request (embedding + scoring, CPU).
- **The confidence bar dominates.** With probabilities mostly between 40% and 75%, the 0.6
  confidence bar decides most picks, so cost weights from 0.2 to 2.0 give the same choices and
  Balanced equals Cheapest. Tuning the bar is the first improvement (section 8).
- **At bar 7** (for comparison) Balanced reached 90% acceptable answers at 45% of the cost,
  the same as random (89% at 41%): the router added nothing at that bar.

With 40 test prompts, one prompt is 2.5 points: the router's 7-point lead over random is about
3 prompts. The direction is consistent with the training-set results, but it is not conclusive.

## 7. Known limitations

- Coverage gap: every training prompt is a benchmark task, so the router has never seen small
  talk. It predicts "hi, how are you?" as a writing/chat task and sends it to DeepSeek. Admin
  rules on Screen 11 (whole-word keywords, e.g. "hi, hello, how are you" → Ornith) cover this
  now; adding everyday prompts to the benchmark is planned for Dec 8.
- A 40-prompt test set is small; one prompt moves a rate by 2.5 points.
- Labels are skewed toward high scores (about half of judged answers got 10), partly because
  public benchmark items may be memorized; the router has relatively few failures to learn from.
- Contamination: the benchmark items are public and older than the three models, so the models
  may have seen them in training (most likely for GSM8K, MATH, HumanEval and MBPP). The judge
  still grades fairly against the reference, but the router may learn that a small model is
  "good enough" on memorized items and over-route new hard prompts to it. A fresh, hand-written
  test slice is planned for Dec 8 to measure this.
- The benchmark ran several calls to Lumen at once (`--workers`) to finish in time. If Lumen
  queues requests per key, measured latencies are somewhat higher than for a single request.
- Timeouts were not given equal time: most of DeepSeek's 31 timeouts had 4–10 minutes, not
  the 30 minutes planned, because the last retry was stopped for time. Some would probably
  have finished, so DeepSeek's quality is somewhat understated.
- No-answers count as failures: when a model timed out (no reply within 4–10 minutes on
  Lumen) or spent its whole token budget thinking, that answer is scored 1 automatically.
  This mostly hit DeepSeek V4 Flash on hard prompts (36 timeouts) and Ornith (11 budget
  overruns). It reflects what a user would experience, but part of DeepSeek's "failure" is
  Lumen's serving speed, not the model's ability.
- The judge is a single LLM (GPT-6 Astra, High); its scores are the only quality signal.
- Single-turn only: each prompt is routed on its own, with no conversation history.
- "Saved vs. the priciest model" assumes it would have used the same number of tokens. Thinking models can use very different token counts, so treat the saving as an estimate.
- The small and medium-cost models run FP8-quantized weights on Lumen, which may differ slightly from the original releases.
- Measured cost per answer is a median over benchmark prompts; a single request can cost much more if the model thinks at length.
- In the evaluation, median cost and latency come from the training prompts only, so the test prompts do not leak into the router's inputs.
- Lumen may be reachable only from the campus network, which affects deployment.
- The embedder adds about 7 ms per request, and a few seconds on the first request after
  a server start while it loads.

## 8. Next steps (Dec 8)

- Grow the benchmark to about 300–400 prompts and retrain.
- Compare a fine-tuned small classifier and Jev with the logistic-regression baseline.
- Multi-turn routing once the Playground has conversations.
- Tune the confidence bar (now 0.6, which overrides the cost weight) with cross-validation
  on the training prompts, then re-test (Part 4.4 improvement).
- Try features beyond the small embedder (prompt length, category, a stronger embedding model)
  and more hard prompts, so the medium and large classifiers learn more than their base rate.
- README_AI.md, deployment and cost/scalability write-up (Parts 5–6).
