"""Phased non-code calibration: Gemma freezes pairs, Qwen judges them."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
from pathlib import Path

from .. import config
from ..adapters.gemma_adapter import GemmaAdapter
from ..adapters.qwen_adapter import QwenAdapter
from ..models import Book
from .skill_evaluation_lab import (
    BehaviorMap, build_bestiary, evidence_decision, generate_scenarios, map_behavior,
    notarize, preregister,
)
from .stabilizer import extract_json_object


CALIBRATION_EXPERIMENT = "skill_evaluation_calibration_2026_09_20"
TRUE_HOLDOUT_EXPERIMENT = "skill_evaluation_true_holdout_2026_09_20"
NEW_HOLDOUT_EXPERIMENT = "skill_evaluation_new_holdout_2026_09_21"
ANSWER_SYSTEM = "Respond to the user request directly."
JUDGE_SYSTEM = """Blindly score A and B against only the request, expected
behavior and rubric. Do not infer which response used a skill. For a negative
control, penalize unnecessary application. Return ONLY JSON:
{"score_a":0,"score_b":0,"winner":"A|B|TIE|UNKNOWN","reason":"..."}."""


def calibration_books() -> list[Book]:
    specs = [
        ("uncertainty", "Uncertainty disclosure", "When evidence is incomplete, separate known facts, assumptions, and unknowns. Calibrate confidence and request the smallest missing fact that could change the answer. Do not add uncertainty language when evidence is complete."),
        ("decision", "Reversible decision", "For a costly uncertain choice, identify a reversible low-cost trial, its success signal, stop condition, and deadline before recommending full commitment. Do not turn trivial or already irreversible choices into experiments."),
        ("explanation", "Audience-fit explanation", "Before explaining a concept, infer the audience's stated goal and current familiarity. Use one suitable analogy, define unavoidable jargon, and include a concrete check of understanding. Do not add teaching scaffolding to a request for a bare factual value."),
    ]
    return [Book(f"holdout_{key}", 1, title, "general", [key], ["reasoning"], [], text, key, "", "HOLDOUT", 0, 0, []) for key, title, text in specs]


def true_holdout_books() -> list[Book]:
    # New skill, never seen by any Cartografo/Mimo/Notaio debugging pass. Do
    # not edit this text after a run to fix a rejection or a bad verdict --
    # by the project's own rule, a failed gate gets recorded, not patched.
    specs = [
        ("root_cause", "Root-cause diagnosis", "When asked to fix a problem whose cause is not yet confirmed, list at least two plausible causes, name the smallest piece of evidence that would discriminate between them, and only recommend the cheapest fix that addresses the discriminated cause. Do not diagnose when the user has already stated the confirmed cause or explicitly asked for a stopgap."),
    ]
    return [Book(f"trueholdout_{key}", 1, title, "general", [key], ["reasoning"], [], text, key, "", "HOLDOUT", 0, 0, []) for key, title, text in specs]


def new_holdout_books() -> list[Book]:
    # Two more genuinely new skills (2026-09-21), never seen by any
    # Cartografo/Mimo/Notaio pass, added to close TODO.md point 13's
    # 'estendere a Book non Python diversi da quelli già usati' gap --
    # calibration and true_holdout only ever exercised 4 total (uncertainty,
    # decision, explanation, root_cause). Deliberately different failure
    # shapes from all four: tradeoff makes an explicit comparison claim
    # (closer to 'decision' but about STATING a comparison, not running a
    # trial); scope makes an explicit assumption-disclosure claim about
    # effort magnitude (closer to 'uncertainty' but about scope, not
    # evidence completeness). Do not edit this text after a run to fix a
    # rejection or a bad verdict -- same rule as true_holdout_books().
    specs = [
        ("tradeoff", "Tradeoff disclosure", "When recommending one option among several viable alternatives, name the single most relevant tradeoff axis and state briefly what is sacrificed by choosing it over the alternative. Do not add tradeoff framing when there is only one reasonable option or the user has already chosen and is asking for execution, not comparison."),
        ("scope", "Scope clarification before large effort", "When a request could plausibly mean a small task or a much larger one and the difference in effort is significant, state the assumed scope explicitly before proceeding instead of silently picking one. Do not state an assumed scope when the request is already unambiguous from context."),
    ]
    return [Book(f"newholdout_{key}", 1, title, "general", [key], ["reasoning"], [], text, key, "", "HOLDOUT", 0, 0, []) for key, title, text in specs]


def _path(experiment: str) -> Path:
    return config.experiment_dir(experiment) / "frozen_pairs.json"


def author_phase(experiment: str, book_list: list[Book]) -> None:
    def build_row(book):
        architect = QwenAdapter()
        root = config.experiment_dir(experiment)
        map_checkpoint = root / f"map_{book.id}.json"
        suite_checkpoint = root / f"suite_{book.id}.json"
        if map_checkpoint.exists():
            behavior = BehaviorMap(**json.loads(map_checkpoint.read_text(encoding="utf-8")))
        else:
            behavior = map_behavior(book, architect)
            map_checkpoint.write_text(json.dumps(asdict(behavior), ensure_ascii=False, indent=2), encoding="utf-8")
        if suite_checkpoint.exists():
            from .probe_generator import EvaluationProbe, EvaluationSuite
            raw = json.loads(suite_checkpoint.read_text(encoding="utf-8"))
            suite = EvaluationSuite(raw["book_id"], raw["book_version"], raw["criterion"], [EvaluationProbe(**probe) for probe in raw["probes"]], raw["generated_at"])
        else:
            suite = generate_scenarios(book, behavior, architect, max_attempts=5)
            suite_checkpoint.write_text(json.dumps(asdict(suite), ensure_ascii=False, indent=2), encoding="utf-8")
        manifest = preregister(book, behavior, suite)
        notary = notarize(book, behavior, suite, manifest)
        return {"book": asdict(book), "behavior": asdict(behavior), "suite": asdict(suite), "manifest": asdict(manifest), "notary": asdict(notary)}
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(build_row, book_list))
    authored = config.experiment_dir(experiment) / "authored_suites.json"
    authored.write_text(json.dumps({"status": "PREREGISTERED_BEFORE_ANSWERS", "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"books": len(rows), "valid": sum(row["notary"]["status"] == "VALID" for row in rows)}, indent=2))


def answer_phase(experiment: str) -> None:
    authored = config.experiment_dir(experiment) / "authored_suites.json"
    payload = json.loads(authored.read_text(encoding="utf-8"))
    if payload.get("status") != "PREREGISTERED_BEFORE_ANSWERS":
        raise RuntimeError("suites are not preregistered")
    def answer_row(row):
        checkpoint = config.experiment_dir(experiment) / f"checkpoint_{row['book']['id']}.json"
        if checkpoint.exists():
            return json.loads(checkpoint.read_text(encoding="utf-8"))
        if row["notary"]["status"] != "VALID":
            row["pairs"] = []
            checkpoint.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
            return row
        worker = GemmaAdapter(config.GEMMA_MODEL)
        pairs = []
        for index, probe in enumerate(row["suite"]["probes"]):
            request = probe["request"]
            direct = worker.complete(request, system=ANSWER_SYSTEM, max_tokens=768)
            skilled = worker.complete(request, system=row["book"]["procedure_text"], max_tokens=768)
            a, b = (direct.text, skilled.text) if index % 2 == 0 else (skilled.text, direct.text)
            pairs.append({
                "probe": probe, "a": a, "b": b,
                "a_is": "DIRECT" if index % 2 == 0 else "SKILLED",
                "b_is": "SKILLED" if index % 2 == 0 else "DIRECT",
                "worker_tokens": direct.input_tokens + direct.output_tokens + skilled.input_tokens + skilled.output_tokens,
            })
        row["pairs"] = pairs
        checkpoint.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
        return row
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(answer_row, payload["rows"]))
    _path(experiment).write_text(json.dumps({"status": "FROZEN_BEFORE_JUDGING", "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"books": len(rows), "pairs": sum(len(row["pairs"]) for row in rows)}, indent=2))


def qwen_phase(experiment: str) -> None:
    payload = json.loads(_path(experiment).read_text(encoding="utf-8"))
    if payload.get("status") != "FROZEN_BEFORE_JUDGING":
        raise RuntimeError("calibration set is not in frozen pre-judging state")
    judge = QwenAdapter()
    all_verdicts = []
    per_book = []
    from .probe_generator import EvaluationProbe, EvaluationSuite, ProbeVerdict
    for row in payload["rows"]:
        verdicts = []
        probes = []
        for pair in row["pairs"]:
            probe = EvaluationProbe(**pair["probe"])
            probes.append(probe)
            prompt = f"REQUEST:\n{probe.request}\nEXPECTED:\n{probe.expected_behavior}\nRUBRIC:\n- " + "\n- ".join(probe.rubric) + f"\nRESPONSE A:\n{pair['a']}\nRESPONSE B:\n{pair['b']}"
            result = judge.complete(prompt, system=JUDGE_SYSTEM, max_tokens=512, thinking_budget=0)
            data = extract_json_object(result.text)
            try:
                if data is None:
                    raise ValueError("no balanced JSON object found")
                raw = str(data.get("winner", "UNKNOWN")).upper()
                winner = pair["a_is"] if raw == "A" else pair["b_is"] if raw == "B" else raw
                verdict = ProbeVerdict(probe.id, float(data.get("score_a", 0)), float(data.get("score_b", 0)), winner, str(data.get("reason", "")))
            except (ValueError, TypeError):
                # Raw text preserved (truncated) instead of thrown away --
                # 'invalid Qwen verdict' alone gave no way to diagnose the
                # two prior occurrences of this failure retroactively.
                verdict = ProbeVerdict(probe.id, 0, 0, "UNKNOWN", f"invalid Qwen verdict; raw={result.text[:300]!r}")
            verdicts.append(verdict)
            all_verdicts.append(verdict)
        suite = EvaluationSuite(row["book"]["id"], 1, row.get("suite", {}).get("criterion", ""), probes, "frozen")
        per_book.append({"book_id": row["book"]["id"], "verdicts": [asdict(v) for v in verdicts], "decision": asdict(evidence_decision(verdicts)), "bestiary": build_bestiary(verdicts, suite)})
    summary = {"status": "JUDGED_BY_QWEN", "decision": asdict(evidence_decision(all_verdicts)), "books": per_book}
    (config.experiment_dir(experiment) / "result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("author", "answer", "judge"))
    parser.add_argument("--set", dest="book_set", choices=("calibration", "true_holdout", "new_holdout"), default="calibration")
    args = parser.parse_args()
    if args.book_set == "calibration":
        experiment, book_list = CALIBRATION_EXPERIMENT, calibration_books()
    elif args.book_set == "true_holdout":
        experiment, book_list = TRUE_HOLDOUT_EXPERIMENT, true_holdout_books()
    else:
        experiment, book_list = NEW_HOLDOUT_EXPERIMENT, new_holdout_books()
    if args.phase == "author":
        author_phase(experiment, book_list)
    elif args.phase == "answer":
        answer_phase(experiment)
    else:
        qwen_phase(experiment)
