from ..domain.verifier import run_tests
from ..models import Task
from .code_recovery_party import CodeFailureEvidence, run_code_recovery_party
from .python_runesmith import enumerate_local_transformations


def _find_passing(source, tests):
    return [candidate for candidate in enumerate_local_transformations(source) if run_tests(candidate.source, tests).passed]


def test_runesmith_can_find_boundary_change_without_a_bug_label():
    source = "def allowed(x):\n    return x > 8\n"
    tests = "def test_boundary():\n    assert allowed(8) is True\n"
    assert _find_passing(source, tests)


def test_runesmith_can_remove_cross_call_mutable_state():
    source = "def collect(xs, out=[]):\n    out.extend(xs)\n    return out\n"
    tests = "def test_calls():\n    assert collect([1]) == [1]\n    assert collect([2]) == [2]\n"
    assert _find_passing(source, tests)


def test_party_composes_three_local_transformations_without_model_calls():
    source = '''def reverse_words(s):
    result = []
    for word in s.split():
        result.append(word[::-1].upper())
    return " ".join(result)
'''
    tests = '''def test_words():
    assert reverse_words("the quick fox") == "fox quick the"
    assert reverse_words("hello") == "hello"
'''
    task = Task("holdout", "unknown", "unknown", "reverse_words", source, tests, "NOVEL", [], [])

    class NoModel:
        PROVIDER = "forbidden"
        def complete(self, *args, **kwargs):
            raise AssertionError("the AST tool should solve this before a model call")

    outcome = run_code_recovery_party(CodeFailureEvidence(task, source, "verified failure"), NoModel())
    assert outcome.selected is not None
    assert outcome.selected.route.id.startswith("runesmith:")


def test_runesmith_ignores_presentation_fences():
    source = "def allowed(x):\n    return x > 8\n\n```python\n"
    assert enumerate_local_transformations(source)
