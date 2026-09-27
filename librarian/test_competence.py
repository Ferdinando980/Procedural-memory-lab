import json

from ..adapters.base import CompletionResult, ModelAdapter
from ..models import Task
from .competence import build_competence_profile, probe_capability, should_retrieve


def _task(capability_tags):
    return Task("t1", "pattern_x", "problem_x", "fn_x", "def fn_x(): pass\n", "def test_fn_x(): assert fn_x() is None\n", "KNOWN", [], capability_tags)


def test_build_competence_profile_aggregates_only_config_b_by_capability():
    tasks_by_id = {
        "task_low": _task(["timezone-arithmetic"]),
        "task_high": _task(["regex-generation"]),
        "task_shared": _task(["timezone-arithmetic", "regex-generation"]),
    }
    records = [
        {"task_id": "task_low", "config_name": "B", "passed": False},
        {"task_id": "task_low", "config_name": "B", "passed": False},
        {"task_id": "task_low", "config_name": "B", "passed": True},
        {"task_id": "task_high", "config_name": "B", "passed": True},
        {"task_id": "task_high", "config_name": "B", "passed": True},
        # config F record must be ignored -- competence is about the Worker unaided
        {"task_id": "task_low", "config_name": "F", "passed": True},
        # a shared-capability task contributes to both tags
        {"task_id": "task_shared", "config_name": "B", "passed": True},
    ]
    profile = build_competence_profile(records, tasks_by_id)
    assert profile["timezone-arithmetic"].n == 4  # 3 from task_low (config B only) + 1 from task_shared
    assert profile["timezone-arithmetic"].successes == 2
    assert profile["regex-generation"].n == 3
    assert profile["regex-generation"].successes == 3
    assert profile["regex-generation"].mean == 1.0


def test_build_competence_profile_empty_records_yields_no_entries():
    assert build_competence_profile([], {}) == {}


class SequenceCodeAdapter(ModelAdapter):
    PROVIDER = "test"
    def __init__(self, codes):
        self.codes = codes
        self.calls = 0
    def complete(self, *args, **kwargs):
        code = self.codes[self.calls % len(self.codes)]
        self.calls += 1
        return CompletionResult(f"```python\n{code}\n```", 0, 0, 0, 0, "test", "test")
    def count_input_tokens(self, *args, **kwargs): return 0


def _pass_fail_task():
    return Task(
        "add_one_task", "off_by_one", "add_one_missing", "add_one",
        "def add_one(x):\n    return x\n",
        "def test_add_one():\n    assert add_one(2) == 3\n",
        "KNOWN", [], ["off-by-one"],
    )


def test_probe_capability_detects_atom_when_reps_agree():
    always_right = SequenceCodeAdapter(["def add_one(x):\n    return x + 1\n"])
    deterministic, results = probe_capability(_pass_fail_task(), always_right, reps=2)
    assert deterministic is True
    assert results == [True, True]


def test_probe_capability_detects_particle_when_reps_disagree():
    flip = SequenceCodeAdapter(["def add_one(x):\n    return x + 1\n", "def add_one(x):\n    return x\n"])
    deterministic, results = probe_capability(_pass_fail_task(), flip, reps=2)
    assert deterministic is False
    assert results == [True, False]


def test_should_retrieve_is_false_only_for_a_deterministic_pass():
    assert should_retrieve(True, [True, True]) is False   # atom-pass -- retrieval would be wasted
    assert should_retrieve(True, [False, False]) is True  # atom-fail -- a real, repeated gap
    assert should_retrieve(False, [True, False]) is True  # particle -- genuine disagreement
