"""One non-code Gemma smoke test for the arbitrary-skill evaluation lab."""

from dataclasses import asdict
import json

from .. import config
from ..adapters.gemma_adapter import GemmaAdapter
from ..models import Book
from .skill_evaluation_lab import build_bestiary, run_lab


EXPERIMENT = "skill_evaluation_lab_2026_09_20"


def main() -> None:
    book = Book(
        "meeting_commitment_check", 1, "Commitment check", "communication",
        ["meeting", "commitment"], ["constraint_tracking"], [],
        "Before confirming a plan, identify the owner, concrete deliverable, "
        "deadline, and unresolved dependency. Ask only for fields that are "
        "missing. Do not force this checklist onto requests that are not a "
        "commitment or plan.",
        "meeting_commitment_check", "", "CANDIDATE", 0.0, 0, [],
    )
    adapter = GemmaAdapter(config.GEMMA_MODEL)
    run = run_lab(book, adapter, adapter, adapter)
    payload = {
        "scope": "mechanical smoke test; same local model creates and judges",
        "book": asdict(book),
        "behavior_map": asdict(run.behavior_map),
        "suite": asdict(run.suite),
        "manifest": asdict(run.manifest),
        "notary": asdict(run.notary),
        "verdicts": [asdict(value) for value in run.verdicts],
        "decision": asdict(run.decision) if run.decision else None,
        "bestiary": build_bestiary(run.verdicts, run.suite),
    }
    out = config.experiment_dir(EXPERIMENT)
    (out / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "notary": run.notary.status,
        "probes": len(run.suite.probes),
        "verdicts": len(run.verdicts),
        "decision": run.decision.action if run.decision else None,
        "bestiary": payload["bestiary"],
    }, indent=2))


if __name__ == "__main__":
    main()
