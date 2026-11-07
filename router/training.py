"""Benchmark files, the train/test split and fitting the router's classifiers.

Files in router/benchmark/ (see the README there):
  prompts.csv     id, prompt, category, difficulty, source       (you write this)
  results.jsonl   one line per prompt × model answer             (run_benchmark)
  labels.csv      prompt_id, model_id, score, good               (import_judgments)
  split.json      which prompt ids are train and test            (train_router)
"""

import csv
import json
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

from .models import CATEGORY_CHOICES

GOOD_SCORE = 7  # a judge score of 7–10 out of 10 counts as a good answer
CATEGORIES = [c for c, _ in CATEGORY_CHOICES]
DIFFICULTIES = ["easy", "medium", "hard"]


class BenchmarkError(Exception):
    """A benchmark file is missing or malformed. The message says what to fix."""


def bench_path(name):
    return Path(settings.ROUTER_BENCHMARK_DIR) / name


def read_prompts(path=None):
    path = Path(path or bench_path("prompts.csv"))
    if not path.exists():
        raise BenchmarkError(f"{path} not found. Copy prompts.template.csv and add your prompts.")
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = {"id", "prompt", "category", "difficulty"} - set(reader.fieldnames or [])
        if missing:
            raise BenchmarkError(f"{path.name} is missing columns: {', '.join(sorted(missing))}")
        rows = list(reader)
    problems, seen = [], set()
    for i, row in enumerate(rows, start=2):
        pid = row["id"].strip()
        if not pid or pid in seen:
            problems.append(f"line {i}: id is empty or repeated ({pid!r})")
        seen.add(pid)
        if not row["prompt"].strip():
            problems.append(f"line {i}: prompt is empty")
        if row["category"].strip() not in CATEGORIES:
            problems.append(f"line {i}: category must be one of {', '.join(CATEGORIES)}")
        if row["difficulty"].strip() not in DIFFICULTIES:
            problems.append(f"line {i}: difficulty must be easy, medium or hard")
    if problems:
        raise BenchmarkError(f"{path.name} has problems:\n  " + "\n  ".join(problems[:20]))
    return [{k: (v or "").strip() for k, v in row.items()} for row in rows]


def counts_as_attempt(record):
    """An answer the model really produced, or a real 'no answer' (thinking budget used up).

    Both cost time and coins, so both count in median latency and cost, and both are judged.
    """
    return record.get("status") == "ok" or record.get("error_kind") == "thinking_budget"


NO_ANSWER_TEXT = "[No answer. The model used its entire token budget thinking and never wrote a reply.]"


def read_results(path=None):
    """{(prompt_id, model_id): record}. Later lines win, so reruns replace old answers."""
    path = Path(path or bench_path("results.jsonl"))
    results = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                results[(record["prompt_id"], record["model_id"])] = record
    return results


def read_labels(path=None):
    """{(prompt_id, model_id): score}."""
    path = Path(path or bench_path("labels.csv"))
    if not path.exists():
        raise BenchmarkError(f"{path} not found. Run import_judgments first.")
    with path.open(newline="", encoding="utf-8") as f:
        return {(r["prompt_id"], r["model_id"]): int(r["score"]) for r in csv.DictReader(f)}


def build_dataset(prompts, labels, model_ids):
    """Prompts that have a judge score for every model."""
    rows = []
    for p in prompts:
        scores = {m: labels.get((p["id"], m)) for m in model_ids}
        if all(s is not None for s in scores.values()):
            rows.append({**p, "scores": scores})
    return rows


def split_ids(rows, test_size=0.2, seed=42):
    """Stratified by category when every category has at least 2 prompts."""
    rng = random.Random(seed)
    counts = Counter(r["category"] for r in rows)
    groups = {}
    if min(counts.values()) >= 2:
        for r in rows:
            groups.setdefault(r["category"], []).append(r["id"])
    else:
        groups["all"] = [r["id"] for r in rows]
    train, test = [], []
    for ids in groups.values():
        ids = sorted(ids)
        rng.shuffle(ids)
        n_test = max(1, round(len(ids) * test_size))
        test += ids[:n_test]
        train += ids[n_test:]
    return sorted(train), sorted(test)


def fit_artifact(texts, categories, labels_by_model, embed_fn, embedder_name):
    """Train one logistic regression per model plus a category classifier.

    labels_by_model: {model_id: [1 if good else 0, ...]} aligned with texts.
    If a model's labels are all the same (e.g. Opus good on every prompt),
    a smoothed constant probability is stored instead, because logistic
    regression needs both classes.
    """
    from sklearn.linear_model import LogisticRegression

    vectors = embed_fn(texts)
    models = {}
    for model_id, labels in labels_by_model.items():
        positives = sum(labels)
        if positives in (0, len(labels)):
            models[model_id] = {"kind": "constant", "p": (positives + 1) / (len(labels) + 2)}
        else:
            clf = LogisticRegression(max_iter=2000, C=1.0)
            clf.fit(vectors, labels)
            models[model_id] = {"kind": "logistic", "clf": clf}

    if len(set(categories)) > 1:
        category_clf = LogisticRegression(max_iter=2000, C=1.0).fit(vectors, categories)
    else:
        category_clf = _ConstantCategory(categories[0])

    return {
        "version": 1,
        "embedder": embedder_name,
        "good_score": GOOD_SCORE,
        "models": models,
        "category_clf": category_clf,
        "n_train": len(texts),
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


class _ConstantCategory:
    """Stand-in category classifier when the training set has one category."""

    def __init__(self, category):
        self.category = category

    def predict(self, vectors):
        return [self.category] * len(vectors)
