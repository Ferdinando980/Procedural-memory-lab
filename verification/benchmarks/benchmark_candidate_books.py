"""Paired baseline/candidate evaluation without exposing candidates to routing."""

import json
import sys

from ... import config
from ...adapters.gemma_adapter import GemmaAdapter
from ...agents.worker import solve
from ...domain.task_generator import generate_tasks
from ...domain.verifier import run_tests
from ...library.loader import load_candidate_books
from ...models import SkillPackage


PATTERNS = {"variable_shadowing", "incorrect_sort_key_or_order"}


def main() -> int:
    repetitions = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    adapter = GemmaAdapter(config.GEMMA_MODEL)
    books = {book.pattern_id: book for book in load_candidate_books()}
    tasks = [task for task in generate_tasks(seed=42) if task.pattern_id in PATTERNS]
    rows = []
    for task in tasks:
        for repetition in range(1, repetitions + 1):
            for condition, package in (
                ("baseline", SkillPackage()),
                ("candidate", SkillPackage([books[task.pattern_id]], "FULL")),
            ):
                source, completion = solve(task, adapter, package)
                verdict = run_tests(source, task.test_source)
                rows.append({
                    "task_id": task.task_id, "pattern_id": task.pattern_id,
                    "repetition": repetition, "condition": condition,
                    "passed": verdict.passed, "input_tokens": completion.input_tokens,
                    "output_tokens": completion.output_tokens, "latency_ms": completion.latency_ms,
                    "feedback": verdict.stdout if not verdict.passed else "",
                })
                print(f"{task.task_id} {repetition}/{repetitions} {condition}: {'PASS' if verdict.passed else 'FAIL'}", flush=True)
    per_pattern = {}
    for pattern in sorted(PATTERNS):
        cells = {}
        for condition in ("baseline", "candidate"):
            selected = [r for r in rows if r["pattern_id"] == pattern and r["condition"] == condition]
            cells[condition] = {"passes": sum(r["passed"] for r in selected), "n": len(selected)}
        cells["delta_passes"] = cells["candidate"]["passes"] - cells["baseline"]["passes"]
        cells["promotion_eligible"] = cells["delta_passes"] > 0 and cells["candidate"]["passes"] >= 5
        per_pattern[pattern] = cells
    summary = {"unique_tasks": len(tasks), "repetitions": repetitions,
               "trajectories": len(rows), "patterns": per_pattern}
    out = config.LOG_DIR / "candidate_books_2026_09_20"
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
