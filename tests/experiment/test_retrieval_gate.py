from cognitive_rpg import config
from cognitive_rpg.adapters.base import CompletionResult, ModelAdapter
from cognitive_rpg.models import Book, SkillPackage, Task
from cognitive_rpg.experiment import quest_runner


class SequenceAdapter(ModelAdapter):
    PROVIDER = "test"

    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.complete_calls = 0

    def complete(self, prompt, system=None, max_tokens=1024, thinking_budget=None):
        self.complete_calls += 1
        return CompletionResult(
            text=next(self.outputs), input_tokens=10, output_tokens=5,
            cost_usd=0.0, latency_ms=1.0, model="test", provider="test",
        )

    def count_input_tokens(self, prompt, system=None):
        return len(prompt.split())


def _task():
    return Task(
        task_id="gate-routing", pattern_id="p", problem_id="p",
        fn_name="f", buggy_source="def f(x):\n    return x - 1\n",
        test_source="def test_f():\n    assert f(2) == 3\n", split="VARIANT",
        problem_tags=["p"], capability_tags=["p"],
    )


def _package():
    return SkillPackage(books=[Book(
        id="b", version=1, title="b", domain="test", problem_tags=["p"],
        capability_tags=["p"], resource_tags=[], procedure_text="Add one.",
        pattern_id="p", canonical_problem_id="p", status="VERIFIED",
        confidence=1.0, verification_count=1, verification_types=["test"],
    )], coverage="FULL")


_RIGHT = "```python\ndef f(x):\n    return x + 1\n```"
_WRONG = "```python\ndef f(x):\n    return x - 1\n```"


def test_gate_skips_retrieval_on_a_deterministic_probe_pass(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)

    def _route_must_not_be_called(task):
        raise AssertionError("librarian.route called despite the probe finding a deterministic pass")
    monkeypatch.setattr(quest_runner.librarian, "route", _route_must_not_be_called)

    # 2 probe calls (both correct, an "atom") + 1 real solve call.
    adapter = SequenceAdapter([_RIGHT, _RIGHT, _RIGHT])
    record = quest_runner.run_quest(
        _task(), "gate-atom-pass", "F", adapter,
        use_librarian=True, use_retrieval_gate=True,
    )
    assert record.passed is True
    assert record.coverage == "NONE"  # no skill was retrieved
    assert adapter.complete_calls == 3


def test_gate_proceeds_to_retrieval_on_probe_disagreement(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)
    route_calls = []
    monkeypatch.setattr(quest_runner.librarian, "route", lambda task: (route_calls.append(task), _package())[1])

    # 2 probe calls that DISAGREE (a "particle") + 1 real solve call.
    adapter = SequenceAdapter([_RIGHT, _WRONG, _RIGHT])
    record = quest_runner.run_quest(
        _task(), "gate-particle", "F", adapter,
        use_librarian=True, use_retrieval_gate=True,
    )
    assert len(route_calls) == 1
    assert record.coverage == "FULL"
    assert adapter.complete_calls == 3


def test_gate_off_by_default_reproduces_original_behavior(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)
    route_calls = []
    monkeypatch.setattr(quest_runner.librarian, "route", lambda task: (route_calls.append(task), _package())[1])

    # use_retrieval_gate omitted (default False): no probe calls at all,
    # route() called unconditionally -- identical to today's behavior.
    adapter = SequenceAdapter([_RIGHT])
    record = quest_runner.run_quest(_task(), "gate-off", "F", adapter, use_librarian=True)
    assert len(route_calls) == 1
    assert adapter.complete_calls == 1
