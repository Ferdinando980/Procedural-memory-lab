"""Replay only recorded F failures through the failure-triggered recovery path.

This measures the quantity the runtime policy cares about: recovered failures,
not whether a pre-emptive hint changes already-successful attempts.
"""

import json
from pathlib import Path

from .. import config
from ..adapters.factory import build_adapter
from ..agents.worker import MAX_OUTPUT_TOKENS, SYSTEM_PROMPT, build_recovery_prompt, extract_code
from ..domain.task_generator import generate_tasks
from ..domain.verifier import run_tests
from ..librarian.librarian import route
from . import detective


def main() -> None:
    source = config.LOG_DIR / "fpe_v7_statistical_2026_09_20" / "results.jsonl"
    output_dir = config.LOG_DIR / "detective_recovery_2026_09_20"
    output_dir.mkdir(parents=True, exist_ok=True)
    task = next(t for t in generate_tasks() if t.task_id == "floating_point_equality__temperature_reached__variant")
    package = route(task)
    adapter = build_adapter("small")
    failures = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()
                if line.strip() and not json.loads(line)["passed"]]

    results = []
    hypothesis = None
    for index, row in enumerate(failures):
        failed_source = extract_code(row["code"])
        before = run_tests(failed_source, task.test_source)
        if before.passed:
            results.append({
                "source_rep": row["rep"], "recovered": True,
                "recovered_by": "deterministic_code_normalization",
                "tests_passed": before.tests_passed, "tests_total": before.tests_total,
                "detective_resolved": False, "failure_diagnosed": False,
                "supported_case": None, "input_tokens": 0, "output_tokens": 0,
                "latency_ms": 0.0, "recovered_code": failed_source,
            })
            continue
        if index == 0:
            for book in package.books:
                candidate = detective.investigate_cached(book, task, adapter, force=True)
                if candidate and candidate.status == "RESOLVED" and not candidate.by_elimination:
                    hypothesis = (book, candidate)
                    break

        case_hint = None
        if hypothesis:
            book, hyp = hypothesis
            action = detective.action_for_hypothesis(book, hyp)
            case_hint = (
                f"Applicable skill case: {hyp.supported_case}. Evidence: {hyp.evidence_quote}."
                + (f" Prescribed action: {action}." if action else "")
            )
        current_source, current_verification = failed_source, before
        attempts = 0
        totals = {"input_tokens": 0, "output_tokens": 0, "latency_ms": 0.0}
        diagnosis = None
        while attempts < 2 and not current_verification.passed:
            attempts += 1
            hint = case_hint
            feedback = (current_verification.stdout or current_verification.error or "Verifier failed without diagnostic output")[-6000:]
            diagnosis = None
            for book in package.books:
                diagnosis = detective.diagnose_failure(book, current_source, feedback, adapter)
                if diagnosis:
                    detail = (
                        f"Verified failure: {diagnosis.failure_quote}. "
                        + (f"Relevant skill instruction: {diagnosis.skill_quote}. " if diagnosis.skill_quote else "")
                        + f"Required repair: {diagnosis.repair_instruction}"
                    )
                    hint = f"{hint} {detail}" if hint else detail
                    break
            prompt = build_recovery_prompt(task, current_source, feedback, package, hint)
            completion = adapter.complete(prompt=prompt, system=SYSTEM_PROMPT, max_tokens=MAX_OUTPUT_TOKENS)
            totals["input_tokens"] += completion.input_tokens
            totals["output_tokens"] += completion.output_tokens
            totals["latency_ms"] += completion.latency_ms
            current_source = extract_code(completion.text)
            current_verification = run_tests(current_source, task.test_source)
        result = {
            "source_rep": row["rep"], "recovered": current_verification.passed,
            "recovered_by": "detective_retry" if current_verification.passed else None,
            "recovery_attempts": attempts,
            "tests_passed": current_verification.tests_passed, "tests_total": current_verification.tests_total,
            "detective_resolved": hypothesis is not None,
            "failure_diagnosed": diagnosis is not None,
            "supported_case": hypothesis[1].supported_case if hypothesis else None,
            **totals, "recovered_code": current_source,
        }
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)

    recovered = sum(r["recovered"] for r in results)
    summary = {
        "historical_sample": 30, "historical_first_pass_successes": 22,
        "failures_replayed": len(results), "failures_recovered": recovered,
        "recovery_rate": recovered / len(results) if results else 0.0,
        "final_successes": 22 + recovered,
        "final_accuracy": (22 + recovered) / 30,
        "deterministic_normalizations": sum(r["recovered_by"] == "deterministic_code_normalization" for r in results),
        "detective_investigations": 1 if any(r["recovered_by"] != "deterministic_code_normalization" for r in results) else 0,
        "first_retry_recoveries": sum(r.get("recovery_attempts") == 1 and r["recovered"] for r in results),
        "second_retry_incremental_recoveries": sum(r.get("recovery_attempts") == 2 and r["recovered"] for r in results),
        "worker_retries_exploratory": sum(r.get("recovery_attempts", 0) for r in results),
        "runtime_retry_cap_selected": 1,
    }
    (output_dir / "results.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in results), encoding="utf-8"
    )
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
