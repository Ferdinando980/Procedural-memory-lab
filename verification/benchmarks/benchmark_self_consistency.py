"""Measures whether majority-vote self-consistency (Wang et al. 2022,
arXiv:2203.11171, "Self-Consistency Improves Chain of Thought Reasoning")
actually improves task-solving accuracy in this project's verifiable code
domain -- not just judge-verdict agreement, which is what probe_generator.
evaluate_suite_stability measures for the non-Python skill-evaluation lab
(a different metric; see TODO.md point 17 for why the two are not
interchangeable). Ground truth here is real pytest (domain/verifier.
run_tests), not an LLM judge, so this is the one place in the project where
"was the majority-voted answer actually correct" can be checked
mechanically, the same way Wang et al. check majority-voted answers against
GSM8K/SVAMP/AQuA/StrategyQA/ARC-challenge ground truth.

Reuses existing roles, adds none (ARCHITETTURA-SISTEMA.md): Worker (agents/worker.py)
produces k independent candidates for the same task/route; the domain
Verifier (domain/verifier.run_tests) is the ground truth; Stabilizer
(verification/stabilizer.majority_vote) does the vote -- exactly its
existing generic contract, used here with a BEHAVIOR signature as the key
(2026-09-21, fixing a real, empirically confirmed gap: an earlier version
voted on normalized source text, and a live k=3 smoke test on
wrong_comparison_operator__merge_intervals found 3 candidates that all
passed pytest yet shared no normalized-string match at all -- literal-
string voting could not see they agreed). _behavior_signature() extracts
the literal-argument calls to fn_name that test_source already exercises
(via ast.walk, never guessing an input), runs each candidate against them
in a fresh subprocess -- the SAME isolation domain/verifier.run_tests
already uses for untrusted LLM code, nothing exec'd in-process -- and
signs the candidate by its OWN outputs, never the expected value, so no
ground truth leaks into the vote. Falls back to normalized source (the
original, simpler key) only when test_source has no literal-argument call
to extract at all -- a disclosed degrade, not a silent one.

Deliberately NOT built on verification/recovery_party.py despite the
surface similarity ("sample k candidates, verify with pytest"):
run_recovery_party tries prioritized, semantically DIFFERENT routes and
selects the first candidate whose real verdict already passed -- it looks
at ground truth to choose the winner. Self-consistency selects by VOTE
alone, blind to ground truth, and only checks correctness of the
already-chosen candidate afterward; reusing recovery_party's
early-stop-on-verified-pass selection here would let the verifier pick the
winner instead of the vote, defeating the exact thing this benchmark exists
to measure."""

import ast
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ...adapters.base import ModelAdapter
from ...agents.worker import SYSTEM_PROMPT, build_prompt, extract_code
from ...domain.verifier import run_tests
from ...experiment.statistics import wilson_interval
from ...models import SkillPackage, Task
from ..stabilizer import majority_vote


def _normalize(code: str) -> str:
    return "\n".join(line.rstrip() for line in code.strip().splitlines())


def _extract_probe_inputs(test_source: str, fn_name: str, max_probes: int = 5) -> list[str]:
    """Literal call-argument source snippets for fn_name, found by walking
    test_source's real AST (2026-09-21) -- never the expected/correct
    output, only the INPUT arguments the test already exercises. A call
    with a non-literal argument (a variable, a fixture) is skipped, not
    guessed at. Built to fix a real, empirically confirmed gap: the k=3
    live smoke test on wrong_comparison_operator__merge_intervals found 3
    candidates that all passed pytest but shared no normalized-string match
    at all -- literal-string voting could not see they agreed."""
    try:
        tree = ast.parse(test_source)
    except SyntaxError:
        return []
    probes: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == fn_name):
            continue
        try:
            args = [ast.literal_eval(arg) for arg in node.args]
            kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in node.keywords if kw.arg}
        except (ValueError, TypeError):
            continue
        call_src = ", ".join([repr(a) for a in args] + [f"{k}={v!r}" for k, v in kwargs.items()])
        if call_src not in probes:
            probes.append(call_src)
        if len(probes) >= max_probes:
            break
    return probes


def _behavior_signature(code: str, fn_name: str, test_source: str, timeout: float = 10.0) -> str | None:
    """Runs the candidate against every input literally called on fn_name in
    test_source, in a FRESH SUBPROCESS -- the same isolation domain/
    verifier.run_tests already uses for untrusted LLM-generated code, never
    exec'd in-process -- and returns a signature built from the candidate's
    OWN outputs. The expected/correct value is never read, so no ground
    truth leaks into the vote (a wrong-but-consistent candidate still gets
    a real, comparable signature). Two candidates behaviorally identical on
    every extracted input get the same signature even if their source
    differs; one that raises on an input gets a recorded '<error>' entry
    for that input, not a silent drop. Returns None only when no probe
    inputs could be extracted at all (nothing to compare on -- caller
    should fall back to a literal-source key in that case, not treat this
    as 'all candidates agree')."""
    probes = _extract_probe_inputs(test_source, fn_name)
    if not probes:
        return None
    calls = "\n".join(
        f"try:\n    print(repr({fn_name}({p})))\nexcept Exception as e:\n    print('<error>', type(e).__name__)"
        for p in probes
    )
    script = f"{code}\n\n{calls}\n"
    with tempfile.TemporaryDirectory() as tmpdir:
        script_file = Path(tmpdir) / "candidate_probe.py"
        script_file.write_text(script, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, str(script_file)], capture_output=True, text=True, timeout=timeout, cwd=tmpdir,
            )
        except subprocess.TimeoutExpired:
            return "<timeout>"
    return proc.stdout.strip() if proc.returncode == 0 else f"<crash:{proc.returncode}>"


def _vote_key(code: str, task: Task) -> str:
    """Behavior signature when the task's test exercises fn_name with at
    least one literal-argument call; falls back to normalized source
    otherwise (a genuine, disclosed degrade -- not a silent one, see
    _behavior_signature's own None case)."""
    signature = _behavior_signature(code, task.fn_name, task.test_source)
    return signature if signature is not None else _normalize(code)


@dataclass
class SelfConsistencyResult:
    task_id: str
    k: int
    single_sample_passed: bool          # baseline: the first of the k samples alone, matching Wang et al.'s single-greedy-sample baseline
    majority_vote_passed: bool | None   # None when the vote itself found no clear majority (fail-closed, same rule as evaluate_suite_stability's UNSTABLE)
    samples_passed: list[bool] = field(default_factory=list)  # ground truth per sample, for inspection only -- NEVER used to pick the winner


def run_self_consistency_probe(
    task: Task,
    adapter: ModelAdapter,
    skill_package: SkillPackage | None = None,
    k: int = 5,
) -> SelfConsistencyResult:
    """One task, k independent samples, one vote. The vote never sees which
    samples pass their tests -- ground truth is checked only AFTER the vote
    has already picked a winner, so this measures the same thing Wang et
    al. measure: does voting on the answer alone, with no oracle, find the
    correct one more often than a single sample does."""
    prompt = build_prompt(task, skill_package)
    codes: list[str] = []
    for _ in range(k):
        completion = adapter.complete(prompt=prompt, system=SYSTEM_PROMPT, max_tokens=4096)
        codes.append(extract_code(completion.text))
    keys = [_vote_key(code, task) for code in codes]
    winner = majority_vote(keys)
    samples_passed = [run_tests(code, task.test_source).passed for code in codes]
    single_passed = samples_passed[0] if samples_passed else False
    majority_passed = None
    if winner is not None:
        winning_code = codes[keys.index(winner)]
        majority_passed = run_tests(winning_code, task.test_source).passed
    return SelfConsistencyResult(task.task_id, k, single_passed, majority_passed, samples_passed)


def run_self_consistency_probe_adaptive(
    task: Task,
    adapter: ModelAdapter,
    skill_package: SkillPackage | None = None,
    k_min: int = 2,
    k_max: int = 7,
) -> SelfConsistencyResult:
    """Application #3 of TODO.md point 20's atom/particle gate: samples
    k_min first; if the vote keys already agree (an 'atom' -- deterministic,
    every rep behaves the same), stops there instead of spending the full
    k_max budget. This project's own k-sweep (this module, k=3/5/7 on 8
    NOVEL tasks) found ZERO benefit from extra sampling on the 7/8 tasks
    that were deterministic either way -- this is the adaptive policy that
    finding implies: escalate sampling only on genuine disagreement
    ('particle'), where a vote has real work to do. Returned
    SelfConsistencyResult.k reflects how many samples were ACTUALLY used
    (k_min on an atom, up to k_max on a particle), not a fixed budget spent
    unconditionally -- an honest signal of the real savings, not a nominal
    parameter."""
    prompt = build_prompt(task, skill_package)
    codes: list[str] = []
    for _ in range(k_min):
        completion = adapter.complete(prompt=prompt, system=SYSTEM_PROMPT, max_tokens=4096)
        codes.append(extract_code(completion.text))
    keys = [_vote_key(code, task) for code in codes]
    while len(set(keys)) > 1 and len(codes) < k_max:
        completion = adapter.complete(prompt=prompt, system=SYSTEM_PROMPT, max_tokens=4096)
        code = extract_code(completion.text)
        codes.append(code)
        keys.append(_vote_key(code, task))
    winner = majority_vote(keys)
    samples_passed = [run_tests(code, task.test_source).passed for code in codes]
    single_passed = samples_passed[0] if samples_passed else False
    majority_passed = None
    if winner is not None:
        winning_code = codes[keys.index(winner)]
        majority_passed = run_tests(winning_code, task.test_source).passed
    return SelfConsistencyResult(task.task_id, len(codes), single_passed, majority_passed, samples_passed)


@dataclass
class SelfConsistencyBenchmark:
    k: int
    n_tasks: int
    single_sample_accuracy: float
    majority_vote_accuracy: float
    unresolved_votes: int  # tasks where the k samples had no clear majority (fail-closed, counted as a failure in majority_vote_accuracy -- same philosophy as evaluate_suite_stability's UNSTABLE landing in evidence_decision's 'unknown' bucket)
    single_sample_ci95: tuple[float, float] = (0.0, 1.0)
    majority_vote_ci95: tuple[float, float] = (0.0, 1.0)


def run_self_consistency_benchmark(
    tasks: list[Task],
    adapter: ModelAdapter,
    skill_package: SkillPackage | None = None,
    k: int = 5,
) -> SelfConsistencyBenchmark:
    """Aggregate over a task set: single-sample accuracy (the baseline Wang
    et al. compare against) vs majority-vote accuracy, same k, same tasks --
    the actual number this project was missing when compared against the
    published self-consistency baseline.

    Both accuracies now carry a real 95% Wilson interval (2026-09-21, found
    missing when comparing against published baselines -- every accuracy
    number in this project used to be a bare point estimate with no
    uncertainty at all). This does not fix the small-n problem itself, only
    makes it visible instead of implying false precision."""
    results = [run_self_consistency_probe(task, adapter, skill_package, k) for task in tasks]
    n = len(results)
    single_wins = sum(r.single_sample_passed for r in results)
    majority_wins = sum(bool(r.majority_vote_passed) for r in results)
    single_accuracy = single_wins / n if n else 0.0
    majority_accuracy = majority_wins / n if n else 0.0
    unresolved = sum(r.majority_vote_passed is None for r in results)
    return SelfConsistencyBenchmark(
        k, n, single_accuracy, majority_accuracy, unresolved,
        wilson_interval(single_wins, n), wilson_interval(majority_wins, n),
    )


@dataclass
class ReplicatedBenchmark:
    repeats: int
    k: int
    n_tasks: int
    single_sample_mean: float
    single_sample_stddev: float
    majority_vote_mean: float
    majority_vote_stddev: float
    runs: list[SelfConsistencyBenchmark] = field(default_factory=list)


def run_self_consistency_replicated(
    tasks: list[Task],
    adapter: ModelAdapter,
    skill_package: SkillPackage | None = None,
    k: int = 5,
    repeats: int = 3,
) -> ReplicatedBenchmark:
    """TODO.md point 18's 'run ripetuti con seed diversi': repeats the WHOLE
    benchmark (fresh independent samples every time -- the adapter's own
    non-zero temperature already makes each repeat a real, different draw,
    no explicit seed parameter needed or available on the local adapters
    used in this project) and reports mean/stddev ACROSS runs -- a
    different, complementary uncertainty to wilson_interval's, which only
    describes the spread WITHIN one run's n tasks. A single run answers
    'how much does k help on these tasks, once'; this answers 'does that
    answer itself change if you just run the exact same benchmark again'.
    stddev is population stddev (no Bessel correction) -- deliberately: the
    goal here is describing the observed spread of these specific repeats,
    not estimating a population parameter from a sample, and repeats is
    typically small (single digits) where the correction barely matters
    anyway."""
    import statistics

    runs = [run_self_consistency_benchmark(tasks, adapter, skill_package, k) for _ in range(repeats)]
    single_values = [run.single_sample_accuracy for run in runs]
    majority_values = [run.majority_vote_accuracy for run in runs]
    return ReplicatedBenchmark(
        repeats, k, len(tasks),
        statistics.fmean(single_values), statistics.pstdev(single_values),
        statistics.fmean(majority_values), statistics.pstdev(majority_values),
        runs,
    )
