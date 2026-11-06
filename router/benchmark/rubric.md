# Judging rubric

The judge scores **answer quality only**, from 1 to 10. Cost and latency are measured
by `run_benchmark`; they are never part of the score. A score of **7 or more counts
as a good answer**: that is the label the router learns from.

Use the same judge model and the same prompt below for every batch. Record the judge
model's name and the date in `judgments/JUDGE.md`.

| Score | Meaning |
|---|---|
| 9–10 | Correct, complete, follows every instruction. Nothing important to fix. |
| 7–8 | Correct and useful. Small omissions or style issues only. |
| 4–6 | Partly correct or incomplete. A user would need to fix or redo part of it. |
| 1–3 | Wrong, off-topic, refuses without reason, or ignores the instructions. |

Rules for the judge:
- Judge each answer on its own against the prompt. Do not rank answers against each other.
- Length is not quality. A short correct answer can score 10.
- For code, check that it would run and does what was asked.
- For math, check the final answer and the key steps.
- If the prompt asks for a format (JSON, bullet list, word limit), not following it costs points.
- Some prompts come with a reference from their benchmark (gold answer, reference summary,
  canonical solution, or the constraints to check). Use it to check correctness; an answer
  does not have to match its wording, and a reference summary is one good answer, not the only one.

The text between the markers below is pasted at the top of every judging batch by
`python manage.py export_for_judging`. Edit it here, not in the batch files.

<!-- JUDGE PROMPT START -->
You are an expert evaluator. For each prompt below there are three anonymous answers labeled A, B and C, in random order. Score EACH answer on its own from 1 to 10 for quality: correctness, completeness and following the prompt's instructions.

Scale: 9–10 correct, complete, follows every instruction · 7–8 correct and useful with small issues · 4–6 partly correct or incomplete · 1–3 wrong, off-topic or ignores the instructions.

If a "Reference from the benchmark" is given, use it to check correctness (final answers must agree; wording need not match; a reference summary is one good answer among many). If there is none, judge on your own knowledge.

Rules: judge each answer independently; do not reward length; for code, check it would run and does what was asked; for math, check the final answer and key steps; not following a requested format costs points.

Reply with ONLY a CSV block, no other text, with this exact header and one row per answer:
prompt_id,label,score,reason
Use the prompt_id exactly as written. label is A, B or C. score is a whole number from 1 to 10. reason is at most 15 words, in double quotes.
<!-- JUDGE PROMPT END -->
