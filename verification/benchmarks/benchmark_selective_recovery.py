"""Fresh all-catalog benchmark of F followed by failure-triggered recovery.

Each task gets one FD trajectory.  Its first VERIFICATION is exactly F because
quest_runner does not invoke Detective before failure; RECOVERY_VERIFICATION is
the selective-tool outcome.  This avoids comparing unrelated stochastic first
attempts.
"""

import json
import os
from collections import defaultdict

from ... import config
from ...adapters.factory import build_adapter
from ...domain.task_generator import generate_tasks
from ...experiment.events import read_events
from ...experiment.experiment_log import archive, read_all
from ...experiment.quest_runner import run_quest
from ...librarian import librarian
from ...library.loader import load_books
from ...models import SkillPackage


FORCE_BOOKS = os.getenv("FORCE_BOOKS", "").strip() == "1"
EXPERIMENT_ID = (
    "selective_recovery_forced_books_2026_09_20" if FORCE_BOOKS
    else "selective_recovery_multi_2026_09_20"
)


def _summarize() -> dict:
    events = read_events(EXPERIMENT_ID)
    records = read_all(EXPERIMENT_ID)
    by_quest = defaultdict(list)
    for event in events:
        by_quest[event["quest_id"]].append(event)
    rows = []
    for record in records:
        qid = f'{record["task_id"]}::{record["config_name"]}'
        quest_events = by_quest[qid]
        initial = next(e for e in quest_events if e["event_type"] == "VERIFICATION")
        recoveries = [e for e in quest_events if e["event_type"] == "RECOVERY_VERIFICATION"]
        recovery = recoveries[-1] if recoveries else None
        detective = next((e for e in quest_events if e["event_type"] == "DETECTIVE_RESULT"), None)
        rows.append({
            "task_id": record["task_id"], "pattern_id": record["task_id"].split("__", 1)[0],
            "split": record["split"], "coverage": record["coverage"],
            "initial_passed": initial["data"]["passed"],
            "recovery_attempted": recovery is not None,
            "recovery_attempts": len(recoveries),
            "final_passed": record["passed"],
            "recovered": bool(recovery and not initial["data"]["passed"] and recovery["data"]["passed"]),
            "detective_resolved": bool(detective and detective["data"].get("case_resolved", False)),
            "detective_model_calls": int(detective["data"].get("model_calls", 0)) if detective else 0,
            "input_tokens": record["input_tokens"], "output_tokens": record["output_tokens"],
            "latency_ms": record["latency_ms"],
        })
    patterns = {}
    for pattern in sorted({r["pattern_id"] for r in rows}):
        group = [r for r in rows if r["pattern_id"] == pattern]
        failures = [r for r in group if not r["initial_passed"]]
        recovered = [r for r in failures if r["recovered"]]
        patterns[pattern] = {
            "n": len(group), "initial_passes": sum(r["initial_passed"] for r in group),
            "initial_failures": len(failures), "recovery_attempts": sum(r["recovery_attempted"] for r in group),
            "recovered": len(recovered), "final_passes": sum(r["final_passed"] for r in group),
            "worker_retries": sum(r["recovery_attempts"] for r in group),
            "policy_evidence": "NO_FAILURE_EXPOSURE" if not failures else ("RECOVERY_OBSERVED" if recovered else "NO_RECOVERY_OBSERVED"),
        }
    failures = [r for r in rows if not r["initial_passed"]]
    summary = {
        "tasks": len(rows), "initial_passes": sum(r["initial_passed"] for r in rows),
        "initial_accuracy": sum(r["initial_passed"] for r in rows) / len(rows),
        "initial_failures": len(failures), "recovery_attempts": sum(r["recovery_attempted"] for r in rows),
        "worker_retries": sum(r["recovery_attempts"] for r in rows),
        "recovered": sum(r["recovered"] for r in rows),
        "final_passes": sum(r["final_passed"] for r in rows),
        "final_accuracy": sum(r["final_passed"] for r in rows) / len(rows),
        "detective_model_calls": sum(r["detective_model_calls"] for r in rows),
        "patterns": patterns,
    }
    out = config.experiment_dir(EXPERIMENT_ID)
    (out / "policy_rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    (out / "policy_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    archive(EXPERIMENT_ID)
    adapter = build_adapter("small")
    if FORCE_BOOKS:
        latest = {}
        for book in load_books():
            current = latest.get(book.pattern_id)
            if current is None or book.version > current.version:
                latest[book.pattern_id] = book
        librarian.route = lambda task: SkillPackage(
            books=[latest[task.pattern_id]] if task.pattern_id in latest else [],
            coverage="FULL" if task.pattern_id in latest else "NONE",
        )
    tasks = generate_tasks(seed=42)
    if FORCE_BOOKS:
        live_rows_path = config.experiment_dir("selective_recovery_multi_2026_09_20") / "policy_rows.jsonl"
        live_rows = [json.loads(line) for line in live_rows_path.read_text(encoding="utf-8").splitlines() if line]
        failed_ids = {row["task_id"] for row in live_rows if not row["initial_passed"]}
        tasks = [task for task in tasks if task.task_id in failed_ids]
    for index, task in enumerate(tasks, 1):
        run_quest(task, EXPERIMENT_ID, "FD", adapter, use_librarian=True, use_detective=True)
        print(f"{index}/{len(tasks)} {task.task_id}", flush=True)
    print(json.dumps(_summarize(), indent=2), flush=True)


if __name__ == "__main__":
    main()
