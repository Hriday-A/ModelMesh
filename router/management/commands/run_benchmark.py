"""Send every benchmark prompt to every model and save the answers.

    python manage.py run_benchmark                 # all prompts × all enabled models
    python manage.py run_benchmark --limit 5       # try 5 prompts first
    python manage.py run_benchmark --max-spend 3   # stop once 3 coins are spent
    python manage.py run_benchmark --workers 4     # 4 calls to Lumen at a time

Calls the real Lumen API (needs LUMEN_API_KEY in .env). Costs are in Lumen coins.
Safe to stop and rerun: answers already saved are skipped.
"""

import json
import os
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.services import ProviderError
from router import llm
from router.llm import QuotaExceeded, ThinkingBudgetExceeded
from router.models import RouterModel
from router.training import BenchmarkError, bench_path, counts_as_attempt, read_prompts, read_results

RETRY_DELAYS = [10, 30, 60]  # seconds, for rate limits and server errors


class Command(BaseCommand):
    help = "Run the benchmark prompts through every enabled model and save results.jsonl."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, help="Only the first N prompts.")
        parser.add_argument("--models", nargs="+", help="Model ids to run (default: all enabled).")
        parser.add_argument("--max-spend", type=float, default=10.0, help="Stop after this many coins (default 10).")
        parser.add_argument("--retry-errors", action="store_true", help="Run again where a previous attempt failed.")
        parser.add_argument("--skip", nargs="+", default=[], help="Prompt ids to leave for later (e.g. --skip P015).")
        parser.add_argument("--workers", type=int, default=1, help="Calls to run at the same time (default 1).")

    def handle(self, *args, **opts):
        try:
            prompts = read_prompts()
        except BenchmarkError as e:
            raise CommandError(str(e))
        if opts["limit"]:
            prompts = prompts[: opts["limit"]]
        if opts["skip"]:
            prompts = [p for p in prompts if p["id"] not in set(opts["skip"])]
            self.stdout.write(f"Skipping for now: {', '.join(opts['skip'])}. Run again without --skip to finish them.")
        models = RouterModel.objects.filter(enabled=True)
        if opts["models"]:
            models = models.filter(model_id__in=opts["models"])
        models = list(models)
        if not models:
            raise CommandError("No matching enabled models.")

        out_path = bench_path("results.jsonl")
        done = read_results(out_path)
        todo = [
            (p, m) for p in prompts for m in models
            if (p["id"], m.model_id) not in done
            or (opts["retry_errors"] and done[(p["id"], m.model_id)]["status"] != "ok")
        ]
        spent = sum(Decimal(str(r.get("cost_usd", 0))) for r in done.values())
        self.stdout.write(f"{len(todo)} calls to make ({len(done)} already saved, {spent:.4f} spent so far, in coins).")

        lock = threading.Lock()
        state = {"spent": spent, "n": 0}
        max_spend = Decimal(str(opts["max_spend"]))

        def work(prompt, model):
            with lock:
                if state["spent"] >= max_spend:
                    return None
            return self.run_one(prompt, model)

        with out_path.open("a", encoding="utf-8") as out:
            pool = ThreadPoolExecutor(max_workers=max(1, opts["workers"]))
            futures = {pool.submit(work, p, m): (p, m) for p, m in todo}
            try:
                for future in as_completed(futures):
                    prompt, model = futures[future]
                    record = future.result()
                    if record is None:
                        continue
                    with lock:  # one writer at a time, so lines never interleave
                        state["spent"] += Decimal(str(record["cost_usd"]))
                        state["n"] += 1
                        out.write(json.dumps(record) + "\n")
                        out.flush()
                    status = "ok" if record["status"] == "ok" else f"ERROR {record['error']}"
                    self.stdout.write(
                        f"[{state['n']}/{len(todo)}] {prompt['id']} {model.model_id}: {status} · "
                        f"{record['latency_ms']} ms · {record['cost_usd']:.5f} coins · total {state['spent']:.4f}"
                    )
            except KeyboardInterrupt:
                out.flush()
                self.stdout.write(self.style.WARNING(
                    f"Stopped. {state['n']} new answers saved; calls in progress are dropped. Rerun to continue."))
                os._exit(130)  # don't wait for calls still in flight
            except CommandError:
                pool.shutdown(wait=False, cancel_futures=True)
                raise
            pool.shutdown()
            if state["spent"] >= max_spend:
                self.stdout.write(self.style.WARNING(f"Stopped early: reached --max-spend {opts['max_spend']} coins."))

        self.update_latencies(models)

    def run_one(self, prompt, model):
        record = {"prompt_id": prompt["id"], "model_id": model.model_id, "status": "error", "answer": "",
                  "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": None, "latency_ms": 0, "cost_usd": 0.0,
                  "stop_reason": None, "error": None, "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        for attempt, delay in enumerate([0] + RETRY_DELAYS):
            if delay:
                self.stdout.write(f"  {prompt['id']} {model.model_id}: retrying in {delay}s…")
                time.sleep(delay)
            try:
                answer = llm.complete(model.model_id, prompt["prompt"])
            except QuotaExceeded:
                raise CommandError("The Lumen coin budget is spent. Wait for it to refill, then rerun; finished answers are kept.")
            except ThinkingBudgetExceeded as e:
                # A real outcome, not a glitch: the model gave no answer, and the tokens cost coins.
                u = e.usage
                record.update({
                    "error": str(e), "error_kind": "thinking_budget", "max_tokens": settings.ROUTER_MAX_TOKENS,
                    "input_tokens": u["input_tokens"], "output_tokens": u["output_tokens"],
                    "reasoning_tokens": u["reasoning_tokens"], "latency_ms": u["latency_ms"],
                    "cost_usd": float(model.cost(u["input_tokens"], u["output_tokens"])),
                })
                return record
            except ProviderError as e:
                record["error"] = str(e)
                retryable = "rate limiting" in str(e) or "Provider error (5" in str(e) or "Could not reach" in str(e)
                if retryable and attempt < len(RETRY_DELAYS):
                    continue
                return record
            record.update({
                "status": "ok", "answer": answer["text"], "input_tokens": answer["input_tokens"],
                "output_tokens": answer["output_tokens"], "reasoning_tokens": answer.get("reasoning_tokens"),
                "latency_ms": answer["latency_ms"],
                "cost_usd": float(model.cost(answer["input_tokens"], answer["output_tokens"])),
                "stop_reason": answer["stop_reason"], "error": None,
            })
            return record
        return record

    def update_latencies(self, models):
        """Store each model's median latency and cost per answer; the router uses them for speed and cost."""
        results = read_results()
        for model in models:
            ok = [r for (pid, mid), r in results.items() if mid == model.model_id and counts_as_attempt(r)]
            if ok:
                model.avg_latency_ms = int(statistics.median(r["latency_ms"] for r in ok))
                model.avg_cost = Decimal(str(statistics.median(r["cost_usd"] for r in ok))).quantize(Decimal("0.00000001"))
                model.save(update_fields=["avg_latency_ms", "avg_cost"])
                self.stdout.write(f"{model.name}: median {model.avg_latency_ms} ms and {model.avg_cost} coins "
                                  f"per answer over {len(ok)} answers.")
