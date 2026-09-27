"""One command for a 5x39 selective-recovery research cycle and policy report."""

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace

from .. import config
from ..adapters.gemma_adapter import GemmaAdapter
from ..domain.task_generator import generate_tasks
from ..experiment.events import read_events
from ..experiment.experiment_log import archive, read_all
from ..experiment.quest_runner import run_quest
from .recovery_policy import recommend


def main() -> None:
    repetitions = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    experiment_id = sys.argv[2] if len(sys.argv) > 2 else "selective_recovery_195_2026_09_20"
    archive(experiment_id)
    # This benchmark characterizes the local Worker specifically. Do not use
    # build_adapter("small"): that role is user-configurable and may point at
    # a cloud provider, making runs incomparable without any code change.
    adapter = GemmaAdapter(config.GEMMA_MODEL)
    base_tasks = generate_tasks(seed=42)
    trials = [
        replace(task, task_id=f"{task.task_id}__trial{rep + 1}")
        for rep in range(repetitions) for task in base_tasks
    ]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(run_quest, task, experiment_id, "FD", adapter, use_librarian=True, use_detective=True)
            for task in trials
        ]
        for done, future in enumerate(as_completed(futures), 1):
            future.result()
            if done % 10 == 0 or done == len(futures):
                print(f"{done}/{len(futures)}", flush=True)

    events = read_events(experiment_id)
    by_quest = {}
    for event in events:
        by_quest.setdefault(event["quest_id"], []).append(event)
    rows = []
    for record in read_all(experiment_id):
        quest = by_quest[f'{record["task_id"]}::FD']
        initial = next(e for e in quest if e["event_type"] == "VERIFICATION")
        recoveries = [e for e in quest if e["event_type"] == "RECOVERY_VERIFICATION"]
        detective = next((e for e in quest if e["event_type"] == "DETECTIVE_RESULT"), None)
        pattern = record["task_id"].split("__", 1)[0]
        rows.append({
            "task_id": record["task_id"], "pattern_id": pattern,
            "initial_passed": bool(initial["data"]["passed"]),
            "recovery_attempted": bool(recoveries), "recovered": bool(recoveries and record["passed"]),
            "final_passed": record["passed"],
            "detective_resolved": bool(detective and detective["data"].get("case_resolved", False)),
            "input_tokens": record["input_tokens"], "output_tokens": record["output_tokens"],
            "latency_ms": record["latency_ms"],
        })
    summary = {
        "design": {"unique_tasks": len(base_tasks), "repetitions": repetitions, "trajectories": len(rows)},
        "initial_passes": sum(r["initial_passed"] for r in rows),
        "final_passes": sum(r["final_passed"] for r in rows),
        "recoveries": sum(r["recovered"] for r in rows),
        "policy": recommend(rows),
    }
    out = config.experiment_dir(experiment_id)
    (out / "policy_rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    (out / "research_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    rates = summary["policy"]
    lines = [
        "# Selective recovery research cycle", "",
        f"- Semantic tasks: {len(base_tasks)}",
        f"- Repetitions per task: {repetitions}",
        f"- Stochastic trajectories: {len(rows)}",
        f"- Initial passes: {summary['initial_passes']}/{len(rows)}",
        f"- Final passes: {summary['final_passes']}/{len(rows)}",
        f"- Recovered failures: {summary['recoveries']}", "",
        "The trajectory count measures repeatability over the same task catalog; it is not the number of independent semantic problems.",
        "", "## Pattern policy", "",
    ]
    for pattern, policy in sorted(rates.items()):
        lines.append(
            f"- **{pattern}**: `{policy['decision']}`; "
            f"mode `{policy['recovery_mode']}`; "
            f"failures {policy['initial_failures']}/{policy['observations']}; "
            f"recoveries {policy['recoveries']}/{policy['recovery_attempts']}."
        )
    (out / "research_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
