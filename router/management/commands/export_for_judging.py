"""Write judging batches to paste into ChatGPT.

    python manage.py export_for_judging --batch-size 5

Each batch has the judge prompt from rubric.md, then for each prompt the three
answers in random order, labeled A/B/C. The judge never sees model names. The
label → model key is saved in judge_key.json (do not paste that file).
"""

import json
import random
import re

from django.core.management.base import BaseCommand, CommandError

from router.models import RouterModel
from router.training import NO_ANSWER_TEXT, BenchmarkError, bench_path, counts_as_attempt, read_prompts, read_results

LABELS = "ABCDEFGH"


def judge_prompt():
    text = bench_path("rubric.md").read_text(encoding="utf-8")
    match = re.search(r"<!-- JUDGE PROMPT START -->\s*(.*?)\s*<!-- JUDGE PROMPT END -->", text, re.S)
    if not match:
        raise CommandError("rubric.md is missing the JUDGE PROMPT START/END markers.")
    return match.group(1)


class Command(BaseCommand):
    help = "Export anonymized answers in batches for the offline ChatGPT judge."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=5, help="Prompts per batch (default 5).")
        parser.add_argument("--seed", type=int, default=7, help="Seed for shuffling answer labels.")

    def handle(self, *args, **opts):
        try:
            prompts = read_prompts()
        except BenchmarkError as e:
            raise CommandError(str(e))
        results = read_results()
        model_ids = list(RouterModel.objects.filter(enabled=True).values_list("model_id", flat=True))
        if len(model_ids) > len(LABELS):
            raise CommandError("Too many models for A–H labels.")

        ready, skipped = [], []
        for p in prompts:
            answers = [results.get((p["id"], m)) for m in model_ids]
            if all(a and counts_as_attempt(a) for a in answers):
                ready.append((p, answers))
            else:
                skipped.append(p["id"])
        if not ready:
            raise CommandError("No prompt has a successful answer from every model yet. Run run_benchmark first.")

        rng = random.Random(opts["seed"])
        key, header = {}, judge_prompt()
        batch_dir = bench_path("judge_batches")
        batch_dir.mkdir(exist_ok=True)
        for old in batch_dir.glob("batch_*.md"):
            old.unlink()

        size = opts["batch_size"]
        batches = [ready[i:i + size] for i in range(0, len(ready), size)]
        for n, batch in enumerate(batches, start=1):
            parts = [f"# ModelMesh judging batch {n:02d} of {len(batches):02d}\n", header, "\n---\n"]
            for prompt, answers in batch:
                shuffled = answers[:]
                rng.shuffle(shuffled)
                key[prompt["id"]] = {LABELS[i]: a["model_id"] for i, a in enumerate(shuffled)}
                parts.append(f"\n## Prompt {prompt['id']}\n\n{prompt['prompt']}\n")
                if prompt.get("reference"):
                    parts.append(f"\n### Reference from the benchmark (for checking; wording need not match)\n\n{prompt['reference']}\n")
                for i, a in enumerate(shuffled):
                    parts.append(f"\n### Answer {LABELS[i]}\n\n{a['answer'] if a['status'] == 'ok' else NO_ANSWER_TEXT}\n")
                parts.append("\n---\n")
            parts.append("\nReply with only the CSV block: prompt_id,label,score,reason\n")
            (batch_dir / f"batch_{n:02d}.md").write_text("".join(parts), encoding="utf-8")

        bench_path("judge_key.json").write_text(json.dumps({"seed": opts["seed"], "key": key}, indent=2), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Wrote {len(batches)} batches for {len(ready)} prompts to {batch_dir}."))
        if skipped:
            self.stdout.write(self.style.WARNING(f"Skipped {len(skipped)} prompts without all answers: {', '.join(skipped[:15])}"))
        self.stdout.write(
            "Next: paste each batch into ChatGPT (new chat per batch), save each reply as "
            "router/benchmark/judgments/batch_NN.csv, then run import_judgments."
        )
