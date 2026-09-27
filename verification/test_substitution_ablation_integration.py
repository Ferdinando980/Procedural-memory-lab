import json

from ..adapters.base import CompletionResult, ModelAdapter
from ..models import Book
from .substitution_ablation import run_ablation_on_generated_probes


def _book():
    return Book(
        "code_skill", 1, "Off-by-one fix", "python", [], [], [],
        "When a function returns its input unchanged instead of applying the required transform, add the missing operation.",
        "off_by_one", "", "VERIFIED", 1, 1, [],
    )


_VALID_PROBE_PAYLOAD = {
    "problem_id": "add_one_missing",
    "fn_name": "add_one",
    "buggy_source": "def add_one(x):\n    return x\n",
    "test_source": "def test_add_one():\n    assert add_one(2) == 3\n",
}


class GeneratorAdapter(ModelAdapter):
    """Always returns the same genuinely-buggy probe -- self-check (a real
    pytest subprocess via domain/verifier.run_tests) passes because
    add_one(2) really does return 2, not 3."""
    PROVIDER = "test"
    def complete(self, *args, **kwargs):
        return CompletionResult(json.dumps(_VALID_PROBE_PAYLOAD), 0, 0, 0, 0, "test", "test")
    def count_input_tokens(self, *args, **kwargs): return 0


class NoProbeGeneratorAdapter(ModelAdapter):
    PROVIDER = "test"
    def complete(self, *args, **kwargs):
        return CompletionResult("not JSON at all", 0, 0, 0, 0, "test", "test")
    def count_input_tokens(self, *args, **kwargs): return 0


class TestSubjectAdapter(ModelAdapter):
    """Model under test for the ablation itself -- extract_value below never
    looks at the returned code, only at which variant was injected, so any
    well-formed code block is fine here."""
    PROVIDER = "test"
    def complete(self, *args, **kwargs):
        return CompletionResult("```python\ndef add_one(x):\n    return x + 1\n```", 0, 0, 0, 0, "test", "test")
    def count_input_tokens(self, *args, **kwargs): return 0


def test_run_ablation_on_generated_probes_wires_generator_output_into_ablation_engine():
    result = run_ablation_on_generated_probes(
        experiment_id="test_ablation_generated_probes",
        book=_book(),
        slot_name="fixed_marker",
        slot_variants={"X": "variant text mentioning X"},
        generator_adapter=GeneratorAdapter(),
        test_adapter=TestSubjectAdapter(),
        extract_value=lambda code: "X",
        reps=2,
    )
    assert result is not None
    assert result.book_id == "code_skill"
    assert result.slot_name == "fixed_marker"
    assert result.total_checks == 2  # 1 tracked task (category C) x 2 reps
    assert result.tracked_lockstep == 2
    assert result.tracking_ratio == 1.0


def test_run_ablation_on_generated_probes_returns_none_when_generator_produces_no_usable_probe():
    result = run_ablation_on_generated_probes(
        experiment_id="test_ablation_generated_probes_empty",
        book=_book(),
        slot_name="fixed_marker",
        slot_variants={"X": "variant"},
        generator_adapter=NoProbeGeneratorAdapter(),
        test_adapter=TestSubjectAdapter(),
        extract_value=lambda code: "X",
    )
    assert result is None
