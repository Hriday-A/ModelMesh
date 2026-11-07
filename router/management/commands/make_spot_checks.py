"""Pick answers for you to grade by hand, to measure how far the judge can be trusted.

    python manage.py make_spot_checks            # 30 answers
    python manage.py make_spot_checks --n 24

Writes:
  spot_check_sheet.md  the prompts, references and answers to grade. It is blind:
                       no model names, no judge scores.
  spot_checks.csv      one row per item: fill in human_score (1-10, same rubric).
  spot_check_key.json  which prompt and model each item is (don't open it until you're done).

The sample is spread over categories and models, and about a third are answers the
judge rated below 7, so agreement is tested on failures as well as successes.
Then run import_judgments: it prints how often you and the judge agree.
"""

import csv
import json
import random

from django.core.management.base import BaseCommand, CommandError

from router.training import GOOD_SCORE, bench_path, read_prompts, read_results


class Command(BaseCommand):
    help = "Create a blind sheet of answers for hand grading (judge-agreement check)."

    def add_arguments(self, parser):
        parser.add_argument("--n", type=int, default=30, help="How many answers (default 30).")
        parser.add_argument("--seed", type=int, default=490)

    def handle(self, *args, **opts):
        csv_path = bench_path("spot_checks.csv")
        if csv_path.exists() and any(r.get("human_score", "").strip() for r in csv.DictReader(csv_path.open())):
            raise CommandError("spot_checks.csv already has your scores. Delete it first to make a new sheet.")
        labels_path = bench_path("labels.csv")
        if not labels_path.exists():
            raise CommandError("labels.csv not found. Run import_judgments first.")
        prompts = {p["id"]: p for p in read_prompts()}
        results = read_results()
        judged = [
            r for r in csv.DictReader(labels_path.open(encoding="utf-8"))
            if not r["reason"].startswith("auto") and results.get((r["prompt_id"], r["model_id"]), {}).get("status") == "ok"
        ]
        rng = random.Random(opts["seed"])
        rng.shuffle(judged)

        n = opts["n"]
        low_target = n // 3
        categories = sorted({prompts[r["prompt_id"]]["category"] for r in judged})
        models = sorted({r["model_id"] for r in judged})
        picked, used_prompts = [], set()

        def take(pool, k):
            for r in pool:
                if len(picked) >= k:
                    return
                if r["prompt_id"] in used_prompts:
                    continue
                cat = prompts[r["prompt_id"]]["category"]
                if sum(prompts[p["prompt_id"]]["category"] == cat for p in picked) >= -(-n // len(categories)):
                    continue
                if sum(p["model_id"] == r["model_id"] for p in picked) >= -(-n // len(models)):
                    continue
                picked.append(r)
                used_prompts.add(r["prompt_id"])

        take([r for r in judged if int(r["score"]) < GOOD_SCORE], low_target)
        take(judged, n)
        rng.shuffle(picked)

        key, parts = {}, ["# Spot-check sheet\n",
                          "Grade each answer from 1 to 10 with the same rubric as the judge "
                          "(see rubric.md; 7 or more = good). Use the reference to check correctness. "
                          "Write your scores in spot_checks.csv. Don't open spot_check_key.json until you're done.\n"]
        for i, r in enumerate(picked, start=1):
            p = prompts[r["prompt_id"]]
            key[str(i)] = {"prompt_id": r["prompt_id"], "model_id": r["model_id"]}
            parts.append(f"\n---\n\n## Item {i} · {p['category']} · {p['difficulty']}\n\n### Prompt\n\n{p['prompt']}\n")
            if p.get("reference"):
                parts.append(f"\n### Reference from the benchmark\n\n{p['reference']}\n")
            parts.append(f"\n### Answer\n\n{results[(r['prompt_id'], r['model_id'])]['answer']}\n")

        bench_path("spot_check_sheet.md").write_text("".join(parts), encoding="utf-8")
        bench_path("spot_check_key.json").write_text(json.dumps(key, indent=2), encoding="utf-8")
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["item", "human_score", "note"])
            for i in range(1, len(picked) + 1):
                w.writerow([i, "", ""])
        low = sum(int(r["score"]) < GOOD_SCORE for r in picked)
        self.stdout.write(self.style.SUCCESS(
            f"Wrote {len(picked)} items to spot_check_sheet.md ({low} the judge rated below {GOOD_SCORE})."))
        self.stdout.write("Grade them in spot_checks.csv (human_score 1-10), then run import_judgments.")
