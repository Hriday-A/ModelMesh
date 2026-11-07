"""Read the judge's CSV replies and turn them into training labels.

    python manage.py import_judgments

Reads router/benchmark/judgments/*.csv (pasted from ChatGPT), maps labels A/B/C
back to models with judge_key.json and writes labels.csv. If spot_checks.csv
exists (prompt_id, model_id, human_score), prints how often you and the judge agree.
"""

import csv
import io
import json
import statistics

from django.core.management.base import BaseCommand, CommandError

from router.training import GOOD_SCORE, NO_ANSWER_SCORE, bench_path


def read_reply(path):
    """Rows from one saved reply. Ignores ``` fences and blank lines that chat UIs add."""
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip() and not l.strip().startswith("```")]
    return list(csv.DictReader(io.StringIO("\n".join(lines))))


class Command(BaseCommand):
    help = "Import judge scores from judgments/*.csv and write labels.csv."

    def handle(self, *args, **opts):
        key_path = bench_path("judge_key.json")
        if not key_path.exists():
            raise CommandError("judge_key.json not found. Run export_for_judging first.")
        saved = json.loads(key_path.read_text(encoding="utf-8"))
        key, auto = saved["key"], saved.get("auto", {})
        files = sorted(bench_path("judgments").glob("*.csv"))
        if not files:
            raise CommandError("No judgments/*.csv files yet. Save each ChatGPT reply there.")

        scores, reasons, errors = {}, {}, []
        for path in files:
            rows = read_reply(path)
            if rows and not {"prompt_id", "label", "score"} <= set(rows[0]):
                errors.append(f"{path.name}: header must be prompt_id,label,score,reason")
                continue
            for i, row in enumerate(rows, start=2):
                pid, label = (row.get("prompt_id") or "").strip(), (row.get("label") or "").strip().upper()
                where = f"{path.name} line {i}"
                if pid not in key or label not in key[pid]:
                    errors.append(f"{where}: unknown prompt/label {pid!r}/{label!r}")
                    continue
                try:
                    score = int(str(row.get("score", "")).strip())
                except ValueError:
                    score = None
                if score is None or not 1 <= score <= 10:
                    errors.append(f"{where}: score must be a whole number 1–10, got {row.get('score')!r}")
                    continue
                model_id = key[pid][label]
                if (pid, model_id) in scores:
                    errors.append(f"{where}: {pid}/{label} was scored twice")
                    continue
                scores[(pid, model_id)] = score
                reasons[(pid, model_id)] = (row.get("reason") or "").strip()

        if errors:
            raise CommandError("Fix these rows and run again:\n  " + "\n  ".join(errors[:30]))

        # No-answers are failed answers: scored automatically, never judged.
        for pid, models in auto.items():
            for model_id, kind in models.items():
                scores[(pid, model_id)] = NO_ANSWER_SCORE
                reasons[(pid, model_id)] = f"auto: no answer ({kind.replace('_', ' ')})"
        all_ids = sorted(set(key) | set(auto))
        models_for = {pid: set(key.get(pid, {}).values()) | set(auto.get(pid, {})) for pid in all_ids}
        complete = [pid for pid in all_ids if all((pid, m) in scores for m in models_for[pid])]
        missing = [pid for pid in all_ids if pid not in complete]
        with bench_path("labels.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["prompt_id", "model_id", "score", "good", "reason"])
            for pid in complete:
                for model_id in sorted(models_for[pid]):
                    s = scores[(pid, model_id)]
                    writer.writerow([pid, model_id, s, int(s >= GOOD_SCORE), reasons[(pid, model_id)]])

        self.stdout.write(self.style.SUCCESS(f"Wrote labels for {len(complete)} prompts to labels.csv."))
        n_auto = sum(len(v) for v in auto.values())
        if n_auto:
            self.stdout.write(f"{n_auto} no-answers were scored {NO_ANSWER_SCORE} automatically.")
        if missing:
            self.stdout.write(self.style.WARNING(f"{len(missing)} prompts are not fully judged yet: {', '.join(missing[:15])}"))
        self.report_by_model(scores)
        self.report_spot_checks(scores)

    def report_by_model(self, scores):
        by_model = {}
        for (pid, model_id), s in scores.items():
            by_model.setdefault(model_id, []).append(s)
        for model_id, values in sorted(by_model.items()):
            good = sum(v >= GOOD_SCORE for v in values)
            self.stdout.write(f"  {model_id}: mean score {statistics.mean(values):.2f}, good {good}/{len(values)}")

    def report_spot_checks(self, scores):
        path = bench_path("spot_checks.csv")
        if not path.exists():
            self.stdout.write("No spot_checks.csv yet: hand-grade about 30 answers to measure judge agreement.")
            return
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        key_path = bench_path("spot_check_key.json")
        if rows and "item" in rows[0] and key_path.exists():  # blind sheet from make_spot_checks
            key = json.loads(key_path.read_text(encoding="utf-8"))
            for r in rows:
                r.update(key.get(str(r["item"]).strip(), {}))
        pairs = [
            (int(r["human_score"]), scores[(r["prompt_id"], r["model_id"])])
            for r in rows
            if r.get("prompt_id") and (r["prompt_id"], r["model_id"]) in scores and (r.get("human_score") or "").strip()
        ]
        if not pairs:
            self.stdout.write("spot_checks.csv has no rows that match judged answers.")
            return
        same_label = sum((h >= GOOD_SCORE) == (j >= GOOD_SCORE) for h, j in pairs)
        mae = statistics.mean(abs(h - j) for h, j in pairs)
        self.stdout.write(
            f"Judge vs. you on {len(pairs)} answers: same good/not-good label {same_label / len(pairs):.0%}, "
            f"average score difference {mae:.2f} points."
        )
