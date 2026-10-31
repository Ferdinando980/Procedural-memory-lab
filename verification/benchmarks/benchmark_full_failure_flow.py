"""Replay saved Gemma failures: verifier-feedback retry vs complete tool flow."""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from ... import config
from ...adapters.gemma_adapter import GemmaAdapter
from ...agents.worker import MAX_OUTPUT_TOKENS, SYSTEM_PROMPT, build_recovery_prompt, extract_code
from ...domain.task_generator import generate_tasks
from ...domain.verifier import run_tests
from ...experiment.events import read_events
from ...librarian.librarian import route
from ..failure_recovery import recover_failed_attempt


SOURCE_EXPERIMENT = "selective_recovery_195_2026_09_20"
OUTPUT_EXPERIMENT = "full_failure_flow_2026_09_20"


def _base_task_id(trial_task_id: str) -> str:
    return trial_task_id.split("__trial", 1)[0]


def _feedback_retry(task, failed_source, feedback, adapter):
    prompt = build_recovery_prompt(task, failed_source, feedback, None, None)
    completion = adapter.complete(prompt=prompt, system=SYSTEM_PROMPT, max_tokens=MAX_OUTPUT_TOKENS)
    source = extract_code(completion.text)
    verdict = run_tests(source, task.test_source)
    return verdict, completion


def main() -> None:
    tasks = {task.task_id: task for task in generate_tasks(seed=42)}
    failures = []
    for event in read_events(SOURCE_EXPERIMENT):
        if event["event_type"] != "VERIFICATION" or event["data"].get("passed"):
            continue
        data = event["data"]
        failures.append((event["task_id"], data["failed_candidate_source"], data["verifier_feedback"]))
    adapter = GemmaAdapter(config.GEMMA_MODEL)

    def replay(item):
        trial_id, failed_source, feedback = item
        task = tasks[_base_task_id(trial_id)]
        initial = run_tests(failed_source, task.test_source)
        fr_verdict, fr_call = _feedback_retry(task, failed_source, feedback, adapter)
        full = recover_failed_attempt(
            task, failed_source, initial, adapter,
            initial_package=route(task), use_librarian=True,
        )
        return {
            "trial_task_id": trial_id, "pattern_id": task.pattern_id,
            "post_failure_books": [b.pattern_id for b in full.post_failure_package.books],
            "fr_passed": fr_verdict.passed,
            "full_passed": full.verification.passed,
            "detective_diagnosed": full.failure_diagnosed,
            "case_resolved": full.case_resolved,
            "inspector_status": full.inspector_verdict.status,
            "fr_calls": 1,
            "full_detective_calls": len(full.detective_calls),
            "full_worker_calls": 1,
            "fr_tokens": fr_call.input_tokens + fr_call.output_tokens,
            "full_tokens": sum(c.input_tokens + c.output_tokens for c in [*full.detective_calls, full.worker_call]),
        }

    rows = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(replay, item) for item in failures]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            print(
                f"{len(rows)}/{len(failures)} {row['trial_task_id']}: "
                f"FR={'PASS' if row['fr_passed'] else 'FAIL'} "
                f"FULL={'PASS' if row['full_passed'] else 'FAIL'} "
                f"books={row['post_failure_books']}", flush=True,
            )
    rows.sort(key=lambda row: row["trial_task_id"])
    summary = {
        "source_failures": len(rows),
        "fr_recoveries": sum(r["fr_passed"] for r in rows),
        "full_recoveries": sum(r["full_passed"] for r in rows),
        "full_diagnoses": sum(r["detective_diagnosed"] for r in rows),
        "post_failure_retrievals_with_books": sum(bool(r["post_failure_books"]) for r in rows),
        "inspector_solid": sum(r["inspector_status"] == "SOLID" for r in rows),
        "fr_total_tokens": sum(r["fr_tokens"] for r in rows),
        "full_total_tokens": sum(r["full_tokens"] for r in rows),
    }
    out = config.experiment_dir(OUTPUT_EXPERIMENT)
    (out / "results.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8",
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
