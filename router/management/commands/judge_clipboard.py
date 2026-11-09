"""Judge the batches in ChatGPT with the clipboard doing the file work (macOS).

    python manage.py judge_clipboard

For each batch that has no valid reply yet:
  1. the batch is copied to your clipboard;
  2. paste it into a NEW ChatGPT chat and send;
  3. copy ChatGPT's whole reply, come back here and press Enter.
The reply is checked (every answer scored, scores 1-10) and saved as
judgments/batch_NN.csv. If something is wrong you are told what, and you can
copy a corrected reply and press Enter again. Safe to stop and rerun: batches
with a valid saved reply are skipped.
"""

import json
import re
import subprocess

from django.core.management.base import BaseCommand, CommandError

from router.management.commands.import_judgments import read_reply
from router.training import bench_path


def copy_to_clipboard(text):
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)


def read_clipboard():
    return subprocess.run(["pbpaste"], capture_output=True, check=True).stdout.decode("utf-8", "replace")


def expected_pairs(batch_text, key):
    """{(prompt_id, label)} the judge must score in this batch."""
    pairs = set()
    for pid in re.findall(r"^## Prompt (\S+)\s*$", batch_text, re.M):
        for label in key.get(pid, {}):
            pairs.add((pid, label))
    return pairs


def check_reply(text, expected):
    """List of problems with a pasted reply (empty list = valid)."""
    lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("```")]
    if not lines or not lines[0].replace(" ", "").lower().startswith("prompt_id,label,score"):
        return ["The reply must start with the header prompt_id,label,score,reason. Copy only the CSV block."]
    import csv
    import io

    problems, seen = [], set()
    for i, row in enumerate(csv.DictReader(io.StringIO("\n".join(lines))), start=2):
        pid, label = (row.get("prompt_id") or "").strip(), (row.get("label") or "").strip().upper()
        if (pid, label) not in expected:
            problems.append(f"line {i}: {pid}/{label} is not an answer in this batch")
            continue
        try:
            score = int(str(row.get("score", "")).strip())
        except ValueError:
            score = None
        if score is None or not 1 <= score <= 10:
            problems.append(f"line {i}: score must be a whole number 1-10, got {row.get('score')!r}")
        if (pid, label) in seen:
            problems.append(f"line {i}: {pid}/{label} appears twice")
        seen.add((pid, label))
    missing = sorted(expected - seen)
    if missing:
        problems.append("missing scores for: " + ", ".join(f"{p}/{l}" for p, l in missing[:12])
                        + (" …" if len(missing) > 12 else ""))
    return problems


class Command(BaseCommand):
    help = "Judge batches in ChatGPT: copies each batch to the clipboard and saves the checked reply."

    def handle(self, *args, **opts):
        key_path = bench_path("judge_key.json")
        if not key_path.exists():
            raise CommandError("judge_key.json not found. Run export_for_judging first.")
        key = json.loads(key_path.read_text(encoding="utf-8"))["key"]
        batches = sorted(bench_path("judge_batches").glob("batch_*.md"))
        if not batches:
            raise CommandError("No judge_batches/batch_*.md files. Run export_for_judging first.")
        out_dir = bench_path("judgments")
        out_dir.mkdir(exist_ok=True)

        todo = []
        for batch in batches:
            expected = expected_pairs(batch.read_text(encoding="utf-8"), key)
            saved = out_dir / f"{batch.stem}.csv"
            if saved.exists() and not check_reply(saved.read_text(encoding="utf-8"), expected):
                continue
            todo.append((batch, expected, saved))
        done = len(batches) - len(todo)
        self.stdout.write(f"{len(batches)} batches: {done} already judged, {len(todo)} to go.")
        if not todo:
            self.stdout.write(self.style.SUCCESS("All batches judged. Next: python manage.py import_judgments"))
            return

        for n, (batch, expected, saved) in enumerate(todo, start=1):
            copy_to_clipboard(batch.read_text(encoding="utf-8"))
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\n[{done + n}/{len(batches)}] {batch.name} ({len(expected)} answers) is on your clipboard."))
            self.stdout.write("  1. Open a NEW chat with ChatGPT's strongest model, paste (Cmd+V), send.")
            self.stdout.write("  2. Copy ChatGPT's whole reply (the copy button under it).")
            self.stdout.write("  3. Come back and press Enter.  (s = skip this batch, q = quit)")
            while True:
                try:
                    choice = input("> ").strip().lower()
                except (KeyboardInterrupt, EOFError):
                    choice = "q"
                    self.stdout.write("")
                if choice == "q":
                    self.stdout.write("Stopped. Run judge_clipboard again to continue.")
                    return
                if choice == "s":
                    break
                if choice == "c":  # copy the batch again, e.g. after copying something else
                    copy_to_clipboard(batch.read_text(encoding="utf-8"))
                    self.stdout.write("  Batch copied to the clipboard again.")
                    continue
                reply = read_clipboard()
                problems = check_reply(reply, expected)
                if not problems:
                    lines = [l for l in reply.splitlines() if l.strip() and not l.strip().startswith("```")]
                    saved.write_text("\n".join(lines) + "\n", encoding="utf-8")
                    self.stdout.write(self.style.SUCCESS(f"  Saved {saved.name}: all {len(expected)} answers scored."))
                    break
                self.stdout.write(self.style.WARNING("  That reply has problems:"))
                for p in problems[:8]:
                    self.stdout.write(f"    - {p}")
                self.stdout.write("  Ask ChatGPT to fix it (e.g. 'You missed some rows. Reply with the full CSV "
                                  "for every answer.'), copy the new reply, press Enter.  (c = copy batch again)")

        self.stdout.write(self.style.SUCCESS("\nDone for now. Next: python manage.py import_judgments"))
