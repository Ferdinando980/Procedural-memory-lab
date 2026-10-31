import json

from cognitive_rpg.adapters.base import CompletionResult, ModelAdapter
from cognitive_rpg.models import Book
from cognitive_rpg.verification.probe_generator import (
    EvaluationProbe,
    EvaluationSuite,
    compile_evaluation_suite,
    evaluate_suite_stability,
    shared_ngrams,
    validate_suite,
)


def _book():
    return Book("b", 1, "Any procedure", "any", [], [], [], "Before answering, identify the central request and list every binding constraint.", "any", "", "VERIFIED", 1, 1, [])


class FixedAdapter(ModelAdapter):
    PROVIDER = "test"
    def __init__(self, payload): self.payload = payload
    def complete(self, *args, **kwargs): return CompletionResult(json.dumps(self.payload), 0, 0, 0, 0, "test", "test")
    def count_input_tokens(self, *args, **kwargs): return 0


def test_antcopy_rejects_six_word_sequence_but_accepts_transfer():
    assert shared_ngrams(_book().procedure_text, "Please identify the central request and list every binding constraint now")
    assert not shared_ngrams(_book().procedure_text, "Organize the obligations in this unfamiliar situation")


def test_probe_generator_compiles_all_five_generic_probe_roles():
    probes = []
    for kind in ("applicable", "transfer", "boundary", "adversarial", "negative_control"):
        probes.append({
            "id": kind, "kind": kind,
            "request": f"Independent scenario for {kind} with unfamiliar details",
            "should_apply": kind != "negative_control",
            "expected_behavior": "observable change", "rubric": ["one concrete check"],
        })
    suite = compile_evaluation_suite(_book(), FixedAdapter({"criterion": "observable", "probes": probes}))
    assert len(suite.probes) == 5
    assert validate_suite(_book(), suite.probes) == []


def test_validator_rejects_missing_negative_control():
    probe = EvaluationProbe("a", "applicable", "A novel independent request", True, "change", ["check"])
    assert "missing negative_control" in validate_suite(_book(), [probe])


class SequenceAdapter(ModelAdapter):
    """Returns each payload in order, cycling -- lets a test script exactly
    which verdict the judge produces on each of the judge_reps repeated
    calls, unlike FixedAdapter which always answers the same way."""
    PROVIDER = "test"
    def __init__(self, payloads, cost_per_call=0.0):
        self.payloads = list(payloads)
        self.cost_per_call = cost_per_call
        self.calls = 0
    def complete(self, *args, **kwargs):
        payload = self.payloads[self.calls % len(self.payloads)]
        self.calls += 1
        return CompletionResult(json.dumps(payload), 0, 0, self.cost_per_call, 0, "test", "test")
    def count_input_tokens(self, *args, **kwargs): return 0


def _one_probe_suite():
    probe = EvaluationProbe("p", "applicable", "A fresh independent request", True, "observable change", ["check output"])
    return EvaluationSuite("b", 1, "criterion", [probe], "preregistered")


def test_evaluate_suite_stability_reports_agreement_and_real_judge_cost():
    judge = SequenceAdapter([{"score_a": 1, "score_b": 2, "winner": "B", "reason": "skilled covered the constraint"}], cost_per_call=0.01)
    stability = evaluate_suite_stability(_book(), _one_probe_suite(), FixedAdapter({}), judge, judge_reps=3)
    assert len(stability) == 1
    result = stability[0]
    assert result.agreement == 1.0
    assert result.verdict.winner == "SKILLED"  # probe index 0 -> A=direct, B=skilled
    assert result.samples == ("SKILLED", "SKILLED", "SKILLED")
    assert round(result.judge_cost_usd, 6) == 0.03


def test_evaluate_suite_stability_flags_genuine_three_way_tie_as_unstable():
    judge = SequenceAdapter([
        {"score_a": 1, "score_b": 0, "winner": "A", "reason": "direct was enough"},
        {"score_a": 0, "score_b": 1, "winner": "B", "reason": "skilled was better"},
        {"score_a": 1, "score_b": 1, "winner": "TIE", "reason": "equivalent"},
    ])
    stability = evaluate_suite_stability(_book(), _one_probe_suite(), FixedAdapter({}), judge, judge_reps=3)
    assert stability[0].verdict.winner == "UNSTABLE"
    assert stability[0].samples == ("DIRECT", "SKILLED", "TIE")
    assert round(stability[0].agreement, 6) == round(1 / 3, 6)


def test_evaluate_suite_stability_adaptive_stops_early_on_a_decisive_first_verdict():
    # score margin |8 - 1| = 7 >= the default decisive_margin=3.0 -- an
    # "atom", should not spend the other 2 reps of judge_reps=3.
    judge = SequenceAdapter([{"score_a": 1, "score_b": 8, "winner": "B", "reason": "clearly better"}], cost_per_call=0.01)
    stability = evaluate_suite_stability(_book(), _one_probe_suite(), FixedAdapter({}), judge, judge_reps=3, adaptive=True)
    assert judge.calls == 1
    assert stability[0].samples == ("SKILLED",)
    assert round(stability[0].judge_cost_usd, 6) == 0.01


def test_evaluate_suite_stability_adaptive_escalates_on_an_ambiguous_first_verdict():
    # score margin |4 - 5| = 1 < decisive_margin=3.0 -- a "particle", must
    # use the full judge_reps budget, same as the non-adaptive path.
    judge = SequenceAdapter([
        {"score_a": 4, "score_b": 5, "winner": "B", "reason": "slightly better"},
        {"score_a": 4, "score_b": 5, "winner": "B", "reason": "slightly better"},
        {"score_a": 4, "score_b": 5, "winner": "B", "reason": "slightly better"},
    ], cost_per_call=0.01)
    stability = evaluate_suite_stability(_book(), _one_probe_suite(), FixedAdapter({}), judge, judge_reps=3, adaptive=True)
    assert judge.calls == 3
    assert stability[0].samples == ("SKILLED", "SKILLED", "SKILLED")
