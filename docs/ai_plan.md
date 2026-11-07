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
  "did the judge rate this model's answer 7/10 or better?". Output: P(good answer).
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

Benchmark: 200 prompts from public benchmarks used by routing papers (RouteLLM, RouterBench), e.g. MBPP, HumanEval, GSM8K, MATH-500, CNN/DailyMail, SQuAD v2, DROP, MT-Bench, IFEval and Arena-Hard; see `router/benchmark/SOURCES.md`. 6 categories (160 train / 40 held-out test),
each answered by all three models (`run_benchmark`). Every answer is scored 1–10 for
quality by ChatGPT's strongest model, used offline with a fixed rubric
(`router/benchmark/rubric.md`), anonymized A/B/C answers, and about 30 hand-graded spot
checks to measure judge agreement. Cost and latency are measured, not judged.

Metrics (`evaluate_router` → `docs/eval/router_eval.md`):
- average judge score and share of good answers;
- total cost (coins) and share of always-large cost;
- quality kept vs. always-large;
- how often the router matches the oracle (cheapest model the judge rated good);
- calibration of P(good); router overhead in ms;
- a cost-vs-quality curve across cost weights;
- baselines: always-small, always-medium, always-large, random, keyword rules.

**Results:** to be filled in from `docs/eval/router_eval.md` once the benchmark has been
run and judged. No results are claimed before then.

## 7. Known limitations

- A 40-prompt test set is small; one prompt moves a rate by 2.5 points.
- Contamination: the benchmark items are public and older than the three models, so the models
  may have seen them in training (most likely for GSM8K, MATH, HumanEval and MBPP). The judge
  still grades fairly against the reference, but the router may learn that a small model is
  "good enough" on memorized items and over-route new hard prompts to it. A fresh, hand-written
  test slice is planned for Dec 8 to measure this.
- The benchmark ran several calls to Lumen at once (`--workers`) to finish in time. If Lumen
  queues requests per key, measured latencies are somewhat higher than for a single request.
- No-answers count as failures: when a model timed out (no reply within 4–10 minutes on
  Lumen) or spent its whole token budget thinking, that answer is scored 1 automatically.
  This mostly hit DeepSeek V4 Flash on hard prompts (36 timeouts) and Ornith (11 budget
  overruns). It reflects what a user would experience, but part of DeepSeek's "failure" is
  Lumen's serving speed, not the model's ability.
- The judge is one LLM; its scores are checked against about 30 human grades, not all.
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
- Calibration fixes and threshold tuning based on the evaluation (Part 4.4 improvement).
- README_AI.md, deployment and cost/scalability write-up (Parts 5–6).
