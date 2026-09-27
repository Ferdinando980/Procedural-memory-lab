from .. import config
from ..adapters.base import CompletionResult, ModelAdapter
from ..experiment import quest_runner
from . import failure_recovery
from ..agents.worker import extract_code
from ..models import Book, SkillPackage, Task


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
        task_id="recovery-routing", pattern_id="p", problem_id="p",
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
        decision_table=[
            {"trigger": "the task needs addition", "question": "Does the task require addition?", "action": "add one", "fallback": False},
            {"trigger": "otherwise", "action": "leave unchanged", "fallback": True},
        ],
    )], coverage="FULL")


def _prepare(monkeypatch, tmp_path):
    monkeypatch.setattr(quest_runner.librarian, "route", lambda task: _package())
    monkeypatch.setattr(failure_recovery.detective, "diagnose_failure", lambda *args, **kwargs: None)
    monkeypatch.setattr(failure_recovery.detective, "diagnose_failure_generic", lambda *args, **kwargs: None)
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)


def test_detective_is_not_called_when_first_attempt_passes(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    monkeypatch.setattr(
        failure_recovery.detective, "investigate_cached",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Detective called on success")),
    )
    adapter = SequenceAdapter(["```python\ndef f(x):\n    return x + 1\n```"])
    record = quest_runner.run_quest(_task(), "routing-pass", "FD", adapter, use_librarian=True, use_detective=True)
    assert record.passed is True
    assert adapter.complete_calls == 1


def test_one_failed_attempt_triggers_one_recovery(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    detective_calls = []
    monkeypatch.setattr(
        failure_recovery.detective, "investigate_cached",
        lambda *args, **kwargs: detective_calls.append(1) or None,
    )
    adapter = SequenceAdapter([
        "```python\ndef f(x):\n    return x - 1\n```",
        "```python\ndef f(x):\n    return x + 1\n```",
    ])
    record = quest_runner.run_quest(_task(), "routing-recover", "FD", adapter, use_librarian=True, use_detective=True)
    assert record.passed is True
    assert detective_calls == [1]
    assert adapter.complete_calls == 2
    assert record.input_tokens == 20


def test_failure_without_initial_book_still_gets_one_recovery(monkeypatch, tmp_path):
    monkeypatch.setattr(quest_runner.librarian, "route", lambda task: SkillPackage())
    monkeypatch.setattr(failure_recovery.librarian, "route_after_failure", lambda *args, **kwargs: SkillPackage())
    monkeypatch.setattr(failure_recovery.detective, "diagnose_failure_generic", lambda *args, **kwargs: None)
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)
    adapter = SequenceAdapter([
        "```python\ndef f(x):\n    return x - 1\n```",
        "```python\ndef f(x):\n    return x + 1\n```",
    ])
    record = quest_runner.run_quest(
        _task(), "routing-no-book", "FDL-I", adapter,
        use_librarian=True, use_detective=True,
    )
    assert record.passed is True
    assert adapter.complete_calls == 2


def test_extract_code_removes_stray_fence_lines():
    raw = "def f(x):\n    return x + 1\n\n```\n"
    assert extract_code(raw) == "def f(x):\n    return x + 1\n"
