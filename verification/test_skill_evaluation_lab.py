from dataclasses import replace
import json

from ..adapters.base import CompletionResult, ModelAdapter
from ..models import Book
from .probe_generator import EvaluationProbe, EvaluationSuite, ProbeVerdict
from .skill_evaluation_lab import (
    BehaviorMap, build_bestiary, evidence_decision, fingerprint, generate_paraphrases, notarize,
    preregister,
)


def book():
    return Book("b", 1, "Constraints", "any", [], [], [], "Identify every binding constraint before answering.", "any", "", "VERIFIED", 1, 1, [])


def behavior(evidence=True):
    return BehaviorMap("b", "constraints are preserved", ["multiple constraints"], ["simple request"], ["all constraints addressed"], ["omits one constraint"], ["answer inspection"] if evidence else [], [])


def suite():
    probes = [
        EvaluationProbe(kind, kind, f"Fresh independent scenario concerning {kind}", kind != "negative_control", "observable outcome", ["check output"])
        for kind in ("applicable", "transfer", "boundary", "adversarial", "negative_control")
    ]
    return EvaluationSuite("b", 1, "all observable checks", probes, "preregistered")


def test_notary_accepts_preregistered_fresh_suite_and_abstains_without_evidence():
    manifest = preregister(book(), behavior(), suite())
    assert notarize(book(), behavior(), suite(), manifest).status == "VALID"
    no_evidence = behavior(False)
    assert notarize(book(), no_evidence, suite(), preregister(book(), no_evidence, suite())).status == "INSUFFICIENT_EVIDENCE"


def test_notary_detects_contamination_and_post_registration_change():
    original = suite()
    seen = [fingerprint(original.probes[0].request)]
    assert notarize(book(), behavior(), original, preregister(book(), behavior(), original, seen)).status == "CONTAMINATED"
    manifest = preregister(book(), behavior(), original)
    changed = replace(original, criterion="changed after answers")
    assert notarize(book(), behavior(), changed, manifest).status == "INVALID"


def test_seer_stops_for_uplift_harm_tie_and_unknown():
    make = lambda winner: ProbeVerdict(str(winner), 0, 0, winner, "")
    assert evidence_decision([make("SKILLED")] * 3 + [make("TIE")] * 2).action == "STOP_UPLIFT"
    assert evidence_decision([make("DIRECT")] * 3 + [make("TIE")] * 2).action == "STOP_HARM"
    assert evidence_decision([make("DIRECT"), make("SKILLED")] + [make("TIE")] * 3).action == "STOP_NO_REGRESSION"
    assert evidence_decision([make("UNKNOWN")] * 5).action == "UNKNOWN"


def test_bestiary_groups_observed_outcomes_without_diagnosing():
    verdicts = [ProbeVerdict("applicable", 1, 2, "SKILLED", ""), ProbeVerdict("negative_control", 2, 1, "DIRECT", "")]
    assert build_bestiary(verdicts, suite()) == {"applicable": {"SKILLED": 1}, "negative_control": {"DIRECT": 1}}


class FixedAdapter(ModelAdapter):
    PROVIDER = "test"
    def complete(self, *args, **kwargs):
        return CompletionResult(json.dumps({"variants": ["A distant reformulation with novel vocabulary", "A distant reformulation with novel vocabulary", ""]}), 0, 0, 0, 0, "test", "test")
    def count_input_tokens(self, *args, **kwargs): return 0


def test_illusionist_deduplicates_surface_variants():
    assert generate_paraphrases(suite().probes[0], book().procedure_text, FixedAdapter()) == ["A distant reformulation with novel vocabulary"]
