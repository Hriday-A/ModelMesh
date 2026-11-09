"""Train the router's classifiers from the judged benchmark.

    python manage.py train_router

Keeps the same test prompts across retraining (split.json), so evaluation
numbers stay comparable. New prompts are split 80/20 when they first appear.
"""

import json

import joblib
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from router import classifier
from router.models import RouterModel
from router.training import (
    GOOD_SCORE, BenchmarkError, bench_path, build_dataset, fit_artifact, read_labels, read_prompts, split_ids,
)


class Command(BaseCommand):
    help = "Train one logistic regression per model (P good answer) plus a category classifier."

    def add_arguments(self, parser):
        parser.add_argument("--test-size", type=float, default=0.2)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--resplit", action="store_true", help="Throw away split.json and split again.")

    def handle(self, *args, **opts):
        model_ids = list(RouterModel.objects.filter(enabled=True).values_list("model_id", flat=True))
        try:
            rows = build_dataset(read_prompts(), read_labels(), model_ids)
        except BenchmarkError as e:
            raise CommandError(str(e))
        if len(rows) < 10:
            raise CommandError(f"Only {len(rows)} prompts are judged for every model; need at least 10.")

        train_ids, test_ids = self.load_split(rows, opts)
        train = [r for r in rows if r["id"] in train_ids]
        self.stdout.write(f"Training on {len(train)} prompts, holding out {len(test_ids)} for evaluate_router.")

        labels = {m: [int(r["scores"][m] >= GOOD_SCORE) for r in train] for m in model_ids}
        artifact = fit_artifact(
            [r["prompt"] for r in train], [r["category"] for r in train], labels, classifier.embed, settings.ROUTER_EMBEDDER
        )
        artifact["cv"] = self.cross_validate(train, labels)
        joblib.dump(artifact, settings.ROUTER_ARTIFACT_PATH)

        for m in model_ids:
            entry, good = artifact["models"][m], sum(labels[m])
            kind = "logistic regression" if entry["kind"] == "logistic" else f"constant p={entry['p']:.2f} (only one class)"
            cv = artifact["cv"].get(m)
            cv_text = f", cross-validated accuracy {cv:.0%}" if cv is not None else ""
            self.stdout.write(f"  {m}: good on {good}/{len(train)} training prompts → {kind}{cv_text}")
        self.stdout.write(self.style.SUCCESS(f"Saved {settings.ROUTER_ARTIFACT_PATH}. Next: python manage.py evaluate_router"))

    def load_split(self, rows, opts):
        path = bench_path("split.json")
        ids = {r["id"] for r in rows}
        if path.exists() and not opts["resplit"]:
            saved = json.loads(path.read_text(encoding="utf-8"))
            train, test = set(saved["train"]) & ids, set(saved["test"]) & ids
            new_rows = [r for r in rows if r["id"] not in train | test]
            if new_rows:
                new_train, new_test = split_ids(new_rows, opts["test_size"], opts["seed"])
                train |= set(new_train)
                test |= set(new_test)
        else:
            train_list, test_list = split_ids(rows, opts["test_size"], opts["seed"])
            train, test = set(train_list), set(test_list)
        path.write_text(json.dumps({"seed": opts["seed"], "train": sorted(train), "test": sorted(test)}, indent=2), encoding="utf-8")
        return train, test

    def cross_validate(self, train, labels):
        """5-fold accuracy for each model that has both classes (fewer folds if data is thin)."""
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import StratifiedKFold, cross_val_score

        vectors = classifier.embed([r["prompt"] for r in train])
        scores = {}
        for model_id, y in labels.items():
            minority = min(sum(y), len(y) - sum(y))
            if minority < 2:
                scores[model_id] = None
                continue
            folds = StratifiedKFold(n_splits=min(5, minority), shuffle=True, random_state=0)
            scores[model_id] = float(cross_val_score(LogisticRegression(max_iter=2000), vectors, y, cv=folds).mean())
        return scores
