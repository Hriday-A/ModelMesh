"""Build router/benchmark/prompts.csv from downloaded public-benchmark rows.

Deterministic: seed 490. Every row records dataset, split and row index.
"""
import csv, json, random, re, sys

RAW, OUT = sys.argv[1], sys.argv[2]
rng = random.Random(490)
words = lambda t: len(re.findall(r"\S+", t or ""))

def load(name):
    d = json.load(open(f"{RAW}/{name}.json"))
    return d, d["rows"]

CODE_HINT = re.compile(r"```|\bcode\b|python|javascript|typescript|\bsql\b|function|script|\bapi\b|regex|c\+\+|\bjava\b|rust|golang|html|css|bash|shell|class |def |import |program|compile|docker|kubernetes|react|excel formula|vba|latex|matlab", re.I)

# Arena-Hard topic clusters that are coding/technical or math, so they belong to other categories.
TECH_OR_MATH_CLUSTER = re.compile(r"python|code|coding|develop|script|sql|linux|docker|kubernetes|react|php|rust|swift|kotlin|javascript|typescript|css|django|flask|laravel|node|excel|vba|network|aws|cuda|gpu|hdl|hlsl|api|web|regex|pandas|matplotlib|tkinter|wpf|streamlit|gradio|shiny|tidyverse|pytorch|jax|assembly|algorithm|array|linked list|data struct|fibonacci|\bpi\b|prime|random number|string|character|word position|concurren|cron|nix|ffmpeg|video|bot|testing|mocking|monad|lambda|deobfusc|reverse eng|shader|ray tracing|kalman|fourier|sharding|autoencoder|yolo|transformer|matrix|roblox|game dev|browser|odoo|sap |symfony|tailwind|subtitle|archive|crypto|multisig|security|hacking|xss|ssh|system32|awk|terminal|kernel|package|json|query|tag valid|gis|pdf|audio|binance|databricks|data process|smart home|e-commerce|android|calculat|computing|leave request|sentiment|retrieval|llm|huggingface|prompt|machine learning|batch size|gradient|math|algebra|probab|dice|geometry|analysis|proving|statistic|sample size|number|train time|investment|circular motion|time calc|electromag|cube|sequence|vector|sat solving|ticket pricing|money and trans|commission|draws|walking|plate stacks|pattern|abc|conflicting|readiness|word count|longest words|lojban|translation|chess|tic-tac|ddr4|keyboard|upscal|jpeg|radar|sensor|solar|weather|elo", re.I)
CREATIVE = re.compile(r"\b(write|compose|create|draft|story|poem|haiku|song|lyrics|letter|essay|imagine|pretend|invent|limerick|script|speech|tweet|slogan|tagline|ad)\b", re.I)

def pick(name, n, keep=lambda r: True):
    d, rows = load(name)
    pool = [r for r in rows if keep(r)]
    if len(pool) < n:
        raise SystemExit(f"{name}: only {len(pool)} rows pass the filter, need {n}")
    return d, rng.sample(pool, n)

def src(d, r, label):
    return f"{label} ({d['dataset']}, {d['config']}/{d['split']}, row {r['row_idx']})"

items = []
def add(category, difficulty, d, chosen, label, prompt_fn, ref_fn):
    for r in chosen:
        items.append({"category": category, "difficulty": difficulty, "prompt": prompt_fn(r).strip(),
                      "source": src(d, r, label), "reference": (ref_fn(r) or "").strip()})

# ---- coding (34)
d, ch = pick("mbpp", 12)
add("coding", "easy", d, ch, "MBPP sanitized",
    lambda r: f"You are an expert Python programmer, and here is your task: {r['prompt']} Your code should pass these tests:\n\n" + "\n".join(r["test_list"]),
    lambda r: r["code"])
d, ch = pick("humaneval", 11)
add("coding", "medium", d, ch, "HumanEval",
    lambda r: "Complete the following Python function. Return the complete function.\n\n```python\n" + r["prompt"].rstrip() + "\n```",
    lambda r: "Canonical solution (function body):\n" + r["canonical_solution"])
d, ch = pick("bigcodebench_hard", 11, lambda r: len(r["instruct_prompt"]) < 2200 and len(r["canonical_solution"]) < 2500)
add("coding", "hard", d, ch, "BigCodeBench-Hard (instruct)", lambda r: r["instruct_prompt"],
    lambda r: "Canonical solution (function body):\n" + r["canonical_solution"])

# ---- math (33)
d, ch = pick("gsm8k", 11)
add("math", "easy", d, ch, "GSM8K", lambda r: r["question"],
    lambda r: "Worked solution; the final answer follows ####:\n" + r["answer"])
d, ch = pick("math_mid", 11)
add("math", "medium", d, ch, "MATH-500 (level 2-3)", lambda r: r["problem"],
    lambda r: f"Final answer: {r['answer']}\n\nWorked solution:\n{r['solution']}")
d, ch = pick("math_hard", 11)
add("math", "hard", d, ch, "MATH-500 (level 5)", lambda r: r["problem"],
    lambda r: f"Final answer: {r['answer']}\n\nWorked solution:\n{r['solution']}")

# ---- summarization (33); difficulty by article length
d, ch = pick("xsum", 11, lambda r: 150 <= words(r["document"]) <= 350)
add("summarization", "easy", d, ch, "XSum",
    lambda r: "Summarize the following article in one sentence.\n\n" + r["document"],
    lambda r: "Reference summary: " + r["summary"])
d, ch = pick("cnn", 11, lambda r: 350 <= words(r["article"]) <= 600)
add("summarization", "medium", d, ch, "CNN/DailyMail 3.0.0",
    lambda r: "Summarize the following news article in 3 sentences.\n\n" + r["article"],
    lambda r: "Reference highlights:\n" + r["highlights"])
d, ch = pick("cnn", 11, lambda r: 750 <= words(r["article"]) <= 1000)
add("summarization", "hard", d, ch, "CNN/DailyMail 3.0.0",
    lambda r: "Summarize the following news article in 3 sentences.\n\n" + r["article"],
    lambda r: "Reference highlights:\n" + r["highlights"])

# ---- extraction (33)
d, ch = pick("squad", 11, lambda r: r["answers"]["text"] and words(r["context"]) <= 250)
add("extraction", "easy", d, ch, "SQuAD v2",
    lambda r: f"Answer the question using only the passage below. Reply with the shortest exact answer from the passage.\n\nPassage: {r['context']}\n\nQuestion: {r['question']}",
    lambda r: "Accepted answers: " + " | ".join(dict.fromkeys(r["answers"]["text"])))
d, ch = pick("dolly_ie", 11, lambda r: r["context"].strip() and words(r["context"]) <= 400)
add("extraction", "medium", d, ch, "Dolly 15k (information_extraction)",
    lambda r: f"{r['instruction']}\n\n{r['context']}",
    lambda r: "Human-written reference response: " + r["response"])
d, ch = pick("drop", 11, lambda r: words(r["passage"]) <= 450 and "number" in r["answers_spans"]["types"])
add("extraction", "hard", d, ch, "DROP",
    lambda r: f"Read the passage and answer the question. Give only the final answer.\n\nPassage: {r['passage'].strip()}\n\nQuestion: {r['question']}",
    lambda r: "Accepted answers: " + " | ".join(dict.fromkeys(r["answers_spans"]["spans"])))

# ---- writing (33)
d, ch = pick("dolly", 11, lambda r: r["category"] == "creative_writing" and not r["context"].strip() and CREATIVE.search(r["instruction"]))
add("writing", "easy", d, ch, "Dolly 15k (creative_writing)", lambda r: r["instruction"],
    lambda r: "Human-written reference response (one acceptable answer): " + r["response"])
d, ch = pick("mtbench", 11, lambda r: r["category"] in ("writing", "roleplay"))
add("writing", "medium", d, ch, "MT-Bench (writing/roleplay, turn 1)", lambda r: r["prompt"][0],
    lambda r: "\n".join(r["reference"]) if r.get("reference") else "")
d, ch = pick("ifeval", 11, lambda r: len(r["instruction_id_list"]) >= 3 and "http" not in r["prompt"])
add("writing", "hard", d, ch, "IFEval",
    lambda r: r["prompt"],
    lambda r: "Constraints the answer must follow (IFEval instruction ids): " + ", ".join(r["instruction_id_list"])
              + "\nParameters: " + json.dumps([{k: v for k, v in kw.items() if v is not None} for kw in r["kwargs"]]))

# ---- chat (34)
d, ch = pick("dolly", 12, lambda r: r["category"] in ("open_qa", "general_qa", "brainstorming") and not r["context"].strip() and words(r["instruction"]) >= 4)
add("chat", "easy", d, ch, "Dolly 15k (open_qa/general_qa/brainstorming)", lambda r: r["instruction"],
    lambda r: "Human-written reference response (one acceptable answer): " + r["response"])
d, ch = pick("mtbench", 11, lambda r: r["category"] in ("humanities", "stem"))
add("chat", "medium", d, ch, "MT-Bench (humanities/stem, turn 1)", lambda r: r["prompt"][0],
    lambda r: "\n".join(r["reference"]) if r.get("reference") else "")
def arena_text(r):
    t = r["turns"]
    t = json.loads(t) if isinstance(t, str) else t
    return t[0]["content"]
d, ch = pick("arena_hard", 11, lambda r: not TECH_OR_MATH_CLUSTER.search(r["cluster"]) and not CODE_HINT.search(arena_text(r)) and len(arena_text(r)) < 1500)
add("chat", "hard", d, ch, "Arena-Hard-Auto v0.1", arena_text, lambda r: "")

assert len(items) == 200, len(items)
seen = set()
for it in items:
    assert it["prompt"] not in seen, it["source"]; seen.add(it["prompt"])
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["id", "prompt", "category", "difficulty", "source", "reference"])
    w.writeheader()
    for i, it in enumerate(items, start=1):
        w.writerow({"id": f"P{i:03d}", **it})
from collections import Counter
print(Counter((i["category"], i["difficulty"]) for i in items))
print("with reference:", sum(bool(i["reference"]) for i in items))
