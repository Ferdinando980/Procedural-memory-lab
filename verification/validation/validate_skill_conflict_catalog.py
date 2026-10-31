"""Gemma-only validation corpus for skill_conflict.py.

The production catalog currently never retrieves two Books together, so this
builds six small, executable tasks with explicit relationship ground truth:
two INDEPENDENT, two COMPOUND, and two REAL_CONFLICT. The Books reuse live
procedures where possible; opposing procedures are minimal synthetic fixtures.
"""

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from ... import config
from ...adapters.gemma_adapter import GemmaAdapter
from ...library.loader import load_books
from ...librarian.librarian import _latest_per_pattern
from ...models import Book, Task
from ..skill_conflict import check_conflict


def _book(book_id: str, text: str) -> Book:
    return Book(book_id, 1, book_id, "programming", [], [], ["python"], text,
                book_id, book_id, "TEST_FIXTURE", 1.0, 1, ["executable_fixture"])


def _task(task_id: str, source: str, tests: str) -> Task:
    return Task(task_id, "multi_skill_fixture", task_id, task_id, source, tests,
                "VALIDATION", [], [])


def cases():
    live = {b.pattern_id: b for b in _latest_per_pattern(load_books())}
    exact = _book("preserve_exact_case", "For identifiers whose case is meaningful, compare the original strings exactly with `==`; do not call casefold().")
    folded = _book("force_casefold", "For every string comparison, normalize both operands with `.casefold()` before comparing them.")
    inclusive = _book("inclusive_boundary", "For the maximum allowed value, accept equality by using `value <= limit`.")
    exclusive = _book("exclusive_boundary", "For a strict upper bound, reject equality by using `value < limit`.")

    compound1 = _task("normalize_and_compare", "def normalize_and_compare(name, expected, reading, target):\n    return name == expected and reading == target\n", "def test_both():\n    assert normalize_and_compare('Admin','admin',100.005,100.0) is True\n")
    compound2 = _task("middle_and_last", "def middle_and_last(xs):\n    mid = len(xs) / 2\n    return xs[mid], [xs[i] for i in range(len(xs)-1)]\n", "def test_both():\n    assert middle_and_last([1,2,3]) == (2,[1,2,3])\n")
    independent1 = _task("float_only", "def close(a,b):\n    return a == b\n", "def test_close():\n    assert close(0.1+0.2,0.3) is True\n")
    independent2 = _task("case_only", "def same(a,b):\n    return a == b\n", "def test_case():\n    assert same('Admin','admin') is True\n")
    conflict1 = _task("case_sensitive_id", "def same_id(a,b):\n    return a.casefold() == b.casefold()\n", "def test_case_matters():\n    assert same_id('abc','ABC') is False\n")
    conflict2 = _task("strict_capacity", "def fits(value,limit):\n    return value <= limit\n", "def test_equal_rejected():\n    assert fits(10,10) is False\n")
    return [
        ("COMPOUND", live["wrong_string_case_comparison"], live["floating_point_equality"], compound1),
        ("COMPOUND", live["integer_division_truncation"], live["index_out_of_range_boundary"], compound2),
        ("INDEPENDENT", live["floating_point_equality"], live["wrong_string_case_comparison"], independent1),
        ("INDEPENDENT", live["wrong_string_case_comparison"], live["integer_division_truncation"], independent2),
        ("REAL_CONFLICT", folded, exact, conflict1),
        ("REAL_CONFLICT", inclusive, exclusive, conflict2),
    ]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    adapter = GemmaAdapter(config.GEMMA_MODEL)
    rows = []
    for expected, a, b, task in cases():
        report = check_conflict(a, b, task, adapter, n_samples=3)
        observed = report.relationship if report else "INCONCLUSIVE"
        row = {"task_id": task.task_id, "expected": expected, "observed": observed,
               "passed": observed == expected, "report": asdict(report) if report else None}
        rows.append(row)
        print(f"{task.task_id}: {observed} (atteso {expected}) -- {'OK' if row['passed'] else 'FAIL'}", flush=True)
    run_id = os.getenv("SKILL_CONFLICT_RUN_ID", "main").strip() or "main"
    out = config.LOG_DIR / "skill_conflict_validation_2026_09_20" / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    passed = sum(r["passed"] for r in rows)
    print(f"Totale: {passed}/{len(rows)}")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
