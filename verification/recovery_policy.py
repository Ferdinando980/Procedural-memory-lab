"""Evidence-based policy optimizer for failure-triggered architectural tools."""

import json
from collections import defaultdict
from pathlib import Path

from .. import config


def recommend(rows: list[dict], min_failures: int = 3) -> dict:
    by_pattern = defaultdict(list)
    for row in rows:
        by_pattern[row["pattern_id"]].append(row)
    recommendations = {}
    for pattern, group in sorted(by_pattern.items()):
        failures = [row for row in group if not row.get("initial_passed", False)]
        attempted = [row for row in failures if row.get("recovery_attempted", False)]
        recovered = [row for row in attempted if row.get("recovered", False)]
        resolved = [row for row in attempted if row.get("detective_resolved", False)]
        if not failures:
            decision = "NO_FAILURE_EVIDENCE"
        elif not attempted:
            decision = "KEEP_CURRENT_ROUTING"
        elif len(attempted) < min_failures:
            decision = "COLLECT_MORE_FAILURES"
        elif recovered:
            decision = "ENABLE_ON_VERIFIED_FAILURE"
        else:
            decision = "DO_NOT_ENABLE"
        mode = (
            "CASE_PLUS_FAILURE_FEEDBACK"
            if attempted and len(resolved) * 2 >= len(attempted)
            else "FAILURE_FEEDBACK_ONLY"
        )
        recommendations[pattern] = {
            "observations": len(group), "initial_failures": len(failures),
            "recovery_attempts": len(attempted), "recoveries": len(recovered),
            "recovery_rate": len(recovered) / len(attempted) if attempted else None,
            "decision": decision, "recovery_mode": mode,
        }
    return recommendations


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> None:
    live = _read_jsonl(config.LOG_DIR / "selective_recovery_multi_2026_09_20" / "policy_rows.jsonl")
    forced = _read_jsonl(config.LOG_DIR / "selective_recovery_forced_books_2026_09_20" / "policy_rows.jsonl")
    historical = _read_jsonl(config.LOG_DIR / "detective_recovery_2026_09_20" / "results.jsonl")
    historical_rows = [{
        "pattern_id": "floating_point_equality", "initial_passed": False,
        "recovery_attempted": row.get("recovered_by") != "deterministic_code_normalization",
        "recovered": row.get("recovered_by") == "detective_retry",
        "detective_resolved": bool(row.get("detective_resolved")),
    } for row in historical]
    result = {
        "rules": {
            "always_on": False, "trigger": "verified_failure",
            "worker_retry_cap": 1, "minimum_failures_for_promotion": 3,
            "legacy_books": "failure_feedback_only",
            "decision_table_books": "case_plus_failure_feedback",
        },
        "live_catalog": recommend(live),
        "forced_diagnostic": recommend(forced),
        "historical_fpe": recommend(historical_rows),
    }
    out = config.LOG_DIR / "recovery_policy_2026_09_20"
    out.mkdir(parents=True, exist_ok=True)
    (out / "policy.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
