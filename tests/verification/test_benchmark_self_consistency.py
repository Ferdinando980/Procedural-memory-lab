from cognitive_rpg.adapters.base import CompletionResult, ModelAdapter
from cognitive_rpg.models import Task
from cognitive_rpg.verification.benchmarks.benchmark_self_consistency import (
    run_self_consistency_benchmark,
    run_self_consistency_probe,
    run_self_consistency_probe_adaptive,
    run_self_consistency_replicated,
)


def _task():
    return Task(
        "add_one_task", "off_by_one", "add_one_missing", "add_one",
        "def add_one(x):\n    return x\n",
        "def test_add_one():\n    assert add_one(2) == 3\n",
        "KNOWN", [], [],
    )


class SequenceCodeAdapter(ModelAdapter):
    """Returns each code snippet in order, cycling -- lets a test control
    exactly what the k self-consistency samples are, unlike a fixed
    single-answer fake."""
    PROVIDER = "test"
    def __init__(self, codes: list[str]):
        self.codes = codes
        self.calls = 0
    def complete(self, *args, **kwargs):
        code = self.codes[self.calls % len(self.codes)]
        self.calls += 1
        return CompletionResult(f"```python\n{code}\n```", 0, 0, 0, 0, "test", "test")
    def count_input_tokens(self, *args, **kwargs): return 0


_WRONG = "def add_one(x):\n    return x"
_RIGHT = "def add_one(x):\n    return x + 1"


def test_majority_vote_recovers_from_a_wrong_first_sample():
    # First sample is wrong; 2 of the remaining 3 agree on the correct fix --
    # single-sample baseline fails, majority vote succeeds (2 vs 1, a clean
    # majority, not a tie). This is the exact phenomenon self-consistency
    # is supposed to demonstrate.
    adapter = SequenceCodeAdapter([_WRONG, _RIGHT, _RIGHT])
    result = run_self_consistency_probe(_task(), adapter, k=3)
    assert result.single_sample_passed is False
    assert result.majority_vote_passed is True
    assert result.samples_passed == [False, True, True]


def test_behaviorally_identical_but_textually_different_candidates_are_merged():
    # Empirically confirmed gap this fixes (TODO.md point 17): a live k=3
    # smoke test found 3 candidates that all passed pytest but shared no
    # normalized-string match at all. Reproduced here deterministically:
    # two candidates with different variable names/structure but IDENTICAL
    # behavior on the extracted probe input (add_one(2) -> 3), one genuine
    # outlier. A string-based vote would see 3 distinct keys (a tie, like
    # the test above); a behavior-based vote must see 2-1.
    reworded_right = "def add_one(n):\n    result = n + 1\n    return result\n"
    adapter = SequenceCodeAdapter([_WRONG, _RIGHT, reworded_right])
    result = run_self_consistency_probe(_task(), adapter, k=3)
    assert result.single_sample_passed is False
    assert result.majority_vote_passed is True
    assert result.samples_passed == [False, True, True]


def test_genuine_three_way_tie_reports_no_majority_not_an_arbitrary_pick():
    third = "def add_one(x):\n    return x - 1"
    adapter = SequenceCodeAdapter([_WRONG, _RIGHT, third])
    result = run_self_consistency_probe(_task(), adapter, k=3)
    assert result.majority_vote_passed is None
    assert result.single_sample_passed is False


def test_benchmark_aggregates_single_vs_majority_accuracy_across_tasks():
    always_right = SequenceCodeAdapter([_RIGHT])
    benchmark = run_self_consistency_benchmark([_task(), _task()], always_right, k=3)
    assert benchmark.n_tasks == 2
    assert benchmark.single_sample_accuracy == 1.0
    assert benchmark.majority_vote_accuracy == 1.0
    assert benchmark.unresolved_votes == 0
    # 2/2 leaves real uncertainty at this n -- the interval must NOT collapse
    # to (1.0, 1.0), the same false-precision failure that motivated adding
    # a real confidence interval to every accuracy number in this project.
    low, high = benchmark.single_sample_ci95
    assert low > 0.0 and low < 1.0
    assert high == 1.0
    assert benchmark.majority_vote_ci95 == benchmark.single_sample_ci95


def test_adaptive_probe_stops_at_k_min_when_the_first_samples_already_agree():
    # Both k_min=2 samples behaviorally agree ("atom") -- must NOT spend the
    # k_max=7 budget. Matches this project's own k-sweep finding that extra
    # sampling gave zero benefit on deterministic tasks.
    always_right = SequenceCodeAdapter([_RIGHT])
    result = run_self_consistency_probe_adaptive(_task(), always_right, k_min=2, k_max=7)
    assert result.k == 2
    assert always_right.calls == 2
    assert result.majority_vote_passed is True


def test_adaptive_probe_escalates_up_to_k_max_when_samples_disagree():
    # k_min=2 disagree (_WRONG then _RIGHT) -- must escalate. With only
    # 2 distinct codes to cycle through, it keeps disagreeing until k_max.
    flip = SequenceCodeAdapter([_WRONG, _RIGHT])
    result = run_self_consistency_probe_adaptive(_task(), flip, k_min=2, k_max=4)
    assert result.k == 4
    assert flip.calls == 4


def test_replicated_benchmark_computes_mean_and_stddev_across_runs():
    # 1 task, k=3, repeats=2: exactly 6 total calls -- codes engineered so
    # run 1 is 100% correct and run 2 is 0% correct, to confirm the
    # aggregation is across RUNS (0.5 mean, real nonzero stddev), not
    # silently averaged away inside a single run.
    varies_by_run = SequenceCodeAdapter([_RIGHT, _RIGHT, _RIGHT, _WRONG, _WRONG, _WRONG])
    replicated = run_self_consistency_replicated([_task()], varies_by_run, k=3, repeats=2)
    assert replicated.repeats == 2
    assert len(replicated.runs) == 2
    assert replicated.runs[0].single_sample_accuracy == 1.0
    assert replicated.runs[1].single_sample_accuracy == 0.0
    assert replicated.single_sample_mean == 0.5
    assert replicated.single_sample_stddev > 0.0
