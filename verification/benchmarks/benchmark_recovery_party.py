"""Escalate only the failures not recovered by either historical FR or FULL."""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from ... import config
from ...adapters.gemma_adapter import GemmaAdapter
from ...domain.task_generator import generate_tasks
from ...experiment.events import read_events
from ...librarian.librarian import route_after_failure
from ...models import FailureRecord
from ..code_recovery_party import CodeFailureEvidence, run_code_recovery_party
from ..recovery_party import SearchBudget


SOURCE_EXPERIMENT = "selective_recovery_195_2026_09_20"
PREVIOUS_EXPERIMENT = "full_failure_flow_2026_09_20"
OUTPUT_EXPERIMENT = "recovery_party_2026_09_20"


def _base(task_id: str) -> str:
    return task_id.split("__trial", 1)[0]


def main() -> None:
    tasks = {task.task_id: task for task in generate_tasks(seed=42)}
    previous_path = config.experiment_dir(PREVIOUS_EXPERIMENT) / "results.jsonl"
    previous = [json.loads(line) for line in previous_path.read_text(encoding="utf-8").splitlines()]
    residual_ids = {
        row["trial_task_id"] for row in previous
        if not row["fr_passed"] and not row["full_passed"]
    }
    failures = {}
    for event in read_events(SOURCE_EXPERIMENT):
        if event["event_type"] != "VERIFICATION" or event["data"].get("passed"):
            continue
        if event["task_id"] in residual_ids:
            failures[event["task_id"]] = event["data"]

    adapter = GemmaAdapter(config.GEMMA_MODEL)

    def replay(trial_id: str):
        data = failures[trial_id]
        task = tasks[_base(trial_id)]
        feedback = data["verifier_feedback"]
        failure = FailureRecord(
            trial_id, "post_recovery", "VERIFIED_FAILURE",
            data["failed_candidate_source"], feedback,
        )
        package = route_after_failure(task, failure)
        outcome = run_code_recovery_party(
            CodeFailureEvidence(task, data["failed_candidate_source"], feedback, package),
            adapter,
            SearchBudget(max_candidates=3, stop_on_first_pass=True),
        )
        return {
            "trial_task_id": trial_id,
            "pattern_id": task.pattern_id,
            "recovered": outcome.selected is not None,
            "winning_route": outcome.selected.route.id if outcome.selected else None,
            "routes_tried": [trial.route.id for trial in outcome.trials],
            "passes": [trial.passed for trial in outcome.trials],
            "tokens": sum(trial.cost_units for trial in outcome.trials),
        }

    rows = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(replay, trial_id) for trial_id in sorted(residual_ids)]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            print(
                f"{len(rows)}/{len(residual_ids)} {row['trial_task_id']}: "
                f"{'PASS' if row['recovered'] else 'FAIL'} {row['routes_tried']}",
                flush=True,
            )
    rows.sort(key=lambda row: row["trial_task_id"])
    prior_union = sum(row["fr_passed"] or row["full_passed"] for row in previous)
    recovered = sum(row["recovered"] for row in rows)
    summary = {
        "residual_failures": len(rows),
        "party_recoveries": recovered,
        "historical_fr_full_union": prior_union,
        "combined_recoveries": prior_union + recovered,
        "combined_final_accuracy": (172 + prior_union + recovered) / 195,
        "party_tokens": sum(row["tokens"] for row in rows),
    }
    out = config.experiment_dir(OUTPUT_EXPERIMENT)
    (out / "results.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8",
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
