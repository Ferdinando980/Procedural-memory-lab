"""Executable test of real Librarian retrieval for two-Book packages."""

import json
import sys

from .. import config
from ..adapters.gemma_adapter import GemmaAdapter
from ..agents.worker import solve
from ..domain.verifier import run_tests
from ..librarian.librarian import route
from ..models import Task


TASKS = [
    Task(
        "multi_case_float", "multi_case_float", "normalize_and_compare",
        "normalize_and_compare",
        "def normalize_and_compare(name, expected, reading, target):\n    return name == expected and reading == target\n",
        "def test_both():\n    assert normalize_and_compare('Admin', 'admin', 0.1 + 0.2, 0.3) is True\n",
        "MULTI_BOOK", [], ["case-sensitivity", "string-comparison", "floating-point", "equality-check"],
    ),
    Task(
        "multi_division_boundary", "multi_division_boundary", "middle_and_all",
        "middle_and_all",
        "def middle_and_all(xs):\n    mid = len(xs) / 2\n    return xs[mid], [xs[i] for i in range(len(xs) - 1)]\n",
        "def test_both():\n    assert middle_and_all([1, 2, 3]) == (2, [1, 2, 3])\n",
        "MULTI_BOOK", [], ["integer-division", "type-error", "index-boundary", "slicing"],
    ),
]


def main() -> int:
    repetitions = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    adapter = GemmaAdapter(config.GEMMA_MODEL)
    rows = []
    for task in TASKS:
        package = route(task, max_books=2, respect_value_policy=False)
        patterns = [book.pattern_id for book in package.books]
        retrieval_ok = len(set(patterns)) == 2
        for repetition in range(1, repetitions + 1):
            candidate, completion = solve(task, adapter, package)
            verdict = run_tests(candidate, task.test_source)
            rows.append({
                "task_id": task.task_id, "repetition": repetition,
                "retrieved_patterns": patterns, "retrieval_ok": retrieval_ok,
                "passed": verdict.passed, "input_tokens": completion.input_tokens,
                "output_tokens": completion.output_tokens, "latency_ms": completion.latency_ms,
                "feedback": verdict.stdout if not verdict.passed else "",
            })
            print(f"{task.task_id} {repetition}/{repetitions}: {patterns} -> {'PASS' if verdict.passed else 'FAIL'}", flush=True)
    out = config.LOG_DIR / "multibook_packages_2026_09_20"
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "tasks": len(TASKS), "trajectories": len(rows),
        "retrievals_with_two_books": sum(row["retrieval_ok"] for row in rows),
        "passes": sum(row["passed"] for row in rows),
    }
    (out / "results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["retrievals_with_two_books"] == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
