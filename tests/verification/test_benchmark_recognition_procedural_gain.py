from cognitive_rpg.adapters.base import CompletionResult, ModelAdapter
from cognitive_rpg.models import Book, Task
from cognitive_rpg.verification.benchmarks.benchmark_recognition_procedural_gain import (
    RecognitionProceduralSpec,
    run_recognition_procedural_probe,
)

_WRONG = "def add_one(x):\n    return x\n"
_RIGHT = "def add_one(x):\n    return x + 1\n"


def _task():
    return Task(
        "add_one_task", "off_by_one", "add_one_missing", "add_one",
        "def add_one(x):\n    return x\n",
        "def test_add_one():\n    assert add_one(2) == 3\n",
        "KNOWN", [], [],
    )


def _book():
    return Book(
        "book_off_by_one", 1, "Off-by-one fix", "python", [], [], [],
        "PROCEDURE_MARKER: add one to the input before returning it.",
        "off_by_one", "", "VERIFIED", 1, 1, [],
    )


def _spec():
    return RecognitionProceduralSpec(
        "off_by_one",
        diagnosis="DIAGNOSIS_MARKER: this function is off by one.",
        anonymous_procedure="ANON_MARKER: add one to the input before returning it, without naming the bug type.",
        sham_procedure="SHAM_MARKER: double the input value instead of adjusting it by one.",
    )


def _other_spec():
    return RecognitionProceduralSpec(
        "wrong_comparison_operator",
        diagnosis="OTHER_DIAGNOSIS_MARKER: this function uses the wrong comparison operator.",
        anonymous_procedure="irrelevant for this test",
        sham_procedure="irrelevant for this test",
    )


class MarkerAwareAdapter(ModelAdapter):
    """Simulates a causal effect: returns the RIGHT fix only when the
    prompt contains a marker that would genuinely tell a real model how to
    fix the bug (the real procedure, D; the anonymous procedure, C; or the
    sham -- which does NOT actually fix it, so sham stays wrong). This lets
    the test verify the gain arithmetic against a fully controlled,
    synthetic accuracy pattern instead of trusting hand-computed numbers."""
    PROVIDER = "test"

    def __init__(self):
        self.prompts_seen: list[str] = []

    def complete(self, prompt, system=None, max_tokens=1024, thinking_budget=None):
        self.prompts_seen.append(prompt)
        if "PROCEDURE_MARKER" in prompt or "ANON_MARKER" in prompt:
            code = _RIGHT
        else:
            code = _WRONG
        return CompletionResult(f"```python\n{code}\n```", 0, 0, 0, 0, "test", "test")

    def count_input_tokens(self, *args, **kwargs):
        return 0


def test_all_six_conditions_produce_distinct_prompts():
    adapter = MarkerAwareAdapter()
    run_recognition_procedural_probe(_task(), _book(), _spec(), _other_spec(), adapter, reps=1)
    # 6 conditions x 1 rep = 6 calls; the prompt text must differ across
    # conditions (each condition's skill content is genuinely different),
    # otherwise the whole experiment would be measuring nothing.
    assert len(adapter.prompts_seen) == 6
    assert len(set(adapter.prompts_seen)) == 6


def test_gain_arithmetic_matches_a_controlled_accuracy_pattern():
    # With MarkerAwareAdapter: A (no marker) -> wrong; B (diagnosis only,
    # no procedure marker) -> wrong; C (anonymous procedure) -> right;
    # D (full skill) -> right; E (diagnosis + sham, no real marker) ->
    # wrong; F (wrong diagnosis + real procedure) -> right.
    adapter = MarkerAwareAdapter()
    result = run_recognition_procedural_probe(_task(), _book(), _spec(), _other_spec(), adapter, reps=2)
    acc = {c: r.accuracy for c, r in result.conditions.items()}
    assert acc == {"A": 0.0, "B": 0.0, "C": 1.0, "D": 1.0, "E": 0.0, "F": 1.0}
    assert result.recognition_gain == 0.0       # Acc(B) - Acc(A) = 0 - 0
    assert result.procedural_gain == 1.0        # Acc(D) - Acc(B) = 1 - 0
    assert result.anonymous_procedural_gain == 1.0  # Acc(C) - Acc(A) = 1 - 0
    assert result.diagnosis_dependence == 0.0   # Acc(D) - Acc(C) = 1 - 1
    assert result.teaching_fraction == 1.0      # (1-0) / (1-0)


def test_teaching_fraction_is_none_when_full_skill_equals_baseline():
    class AlwaysWrongAdapter(ModelAdapter):
        PROVIDER = "test"
        def complete(self, *args, **kwargs):
            return CompletionResult(f"```python\n{_WRONG}\n```", 0, 0, 0, 0, "test", "test")
        def count_input_tokens(self, *args, **kwargs):
            return 0

    result = run_recognition_procedural_probe(_task(), _book(), _spec(), _other_spec(), AlwaysWrongAdapter(), reps=1)
    assert result.teaching_fraction is None
