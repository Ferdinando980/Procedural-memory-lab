"""Model-specific competence estimates per capability, built by pure
aggregation over already-logged records -- same pattern as experiment/
metrics.py and experiment/economics.py (they take records/events as
parameters, they don't read files themselves). Extends the Librarian's
existing "select relevant skills" authority (ARCHITETTURA-SISTEMA.md righe
46-51, ROLE-AUDIT-2026-09-20.md riga 19/34) with a richer selection signal;
no new role registered.

Two distinct sources of competence evidence:
1. Passive (build_competence_profile): historical B-config (Worker alone,
   no skill) log records, joined to their Task via task_id for
   capability_tags -- the SAME join pattern already used by
   experiment/economics.py::economic_classification, since LogRecord
   (experiment/experiment_log.py) carries no capability_tags itself.
2. Active (probe_capability): a cheap atom/particle probe (2 independent
   resamples of the SAME task, verified with real pytest) for when passive
   evidence is thin or absent. This is TODO.md point 20's diagnostic-probe
   piece, built from resampling variance (Kuhn et al. 2023 "Semantic
   Uncertainty", arXiv:2302.09664; ReASC, arXiv:2601.02970) rather than a
   generated micro-test -- not a novel mechanism, a known one applied here.

Deliberately NOT called from inside librarian.route(): route()'s own
docstring states routing "never shows up as a hidden cost" (no model call,
no embedding API) -- an invariant this module does not break. A caller
builds/refreshes a competence profile as an explicit, separate step (from
logs, or via probe_capability when logs are thin) and passes the result
into route(competence_profile=...)."""

from collections import defaultdict
from dataclasses import dataclass

from ..adapters.base import ModelAdapter
from ..agents.worker import SYSTEM_PROMPT, build_prompt, extract_code
from ..domain.verifier import run_tests
from ..experiment.statistics import wilson_interval
from ..models import Task


@dataclass(frozen=True)
class CapabilityEstimate:
    capability: str
    n: int
    successes: int
    mean: float                    # successes / n, or 0.5 (uninformative prior) when n == 0
    ci95: tuple[float, float]      # wilson_interval(successes, n) -- (0.0, 1.0) when n == 0


def build_competence_profile(
    records: list[dict],
    tasks_by_id: dict[str, Task],
    config_name: str = "B",
) -> dict[str, CapabilityEstimate]:
    """Passive competence estimate: aggregates real config_name (default
    'B' -- Worker alone, no skill; the question is how competent the model
    is WITHOUT help) outcomes per capability_tag. A task carrying multiple
    capability_tags contributes to EVERY one of them -- a known
    simplification (can't isolate which specific tag caused a pass/fail on
    a multi-tag task), stated not hidden. Capabilities never observed in
    `records` simply do not appear in the returned dict -- callers treat a
    missing key as maximal uncertainty (see librarian.route's
    _competence_value), not as zero."""
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # capability -> [successes, n]
    for record in records:
        if record.get("config_name") != config_name:
            continue
        task = tasks_by_id.get(record.get("task_id"))
        if task is None:
            continue
        for capability in task.capability_tags:
            bucket = counts[capability]
            bucket[1] += 1
            if record.get("passed"):
                bucket[0] += 1
    return {
        capability: CapabilityEstimate(
            capability, n, successes, successes / n if n else 0.5, wilson_interval(successes, n),
        )
        for capability, (successes, n) in counts.items()
    }


def probe_capability(task: Task, adapter: ModelAdapter, reps: int = 2) -> tuple[bool, list[bool]]:
    """Active diagnostic probe: reps independent resamples of the Worker
    ALONE on this exact task, verified with real pytest
    (domain/verifier.run_tests) -- no skill injected. Returns
    (is_deterministic, [passed, ...]).

    is_deterministic True ("atom", every rep agreed, all pass or all fail)
    mirrors ReASC's single-sample decision stage -- resampling further
    would not change the outcome, matching this project's own k-sweep
    finding (TODO.md point 17) that self-consistency's vote gave zero
    benefit on tasks that were deterministically right or wrong every time.
    False ("particle", the reps disagreed) is where genuine outcome
    variance exists -- where both self-consistency voting AND skill
    retrieval have real leverage, since the outcome is not yet settled by
    a single sample.

    Ground truth only, never looks at a skill -- this measures the
    WORKER's own unaided competence on one task, the same signal
    build_competence_profile aggregates passively over many tasks."""
    prompt = build_prompt(task, None)
    results = []
    for _ in range(reps):
        completion = adapter.complete(prompt=prompt, system=SYSTEM_PROMPT, max_tokens=4096)
        code = extract_code(completion.text)
        results.append(run_tests(code, task.test_source).passed)
    deterministic = len(set(results)) == 1
    return deterministic, results


def should_retrieve(is_deterministic: bool, results: list[bool]) -> bool:
    """Application #1 of TODO.md point 20's atom/particle gate: given
    probe_capability's own output, decides whether retrieving a skill is
    worth the token cost. An 'atom-pass' (deterministic, every unaided rep
    already succeeded) means retrieval is very likely wasted -- this is the
    exact case experiment/metrics.py::retrieval_waste_analysis measured as
    81.3% historical waste, turned here from a retrospective diagnosis into
    a per-task decision. Anything else -- a deterministic FAILURE (real,
    repeated capability gap) or genuine disagreement between reps
    ('particle') -- means retrieval is worth attempting. Pure decision
    function, no I/O: the caller is responsible for actually calling
    probe_capability first and for actually skipping/attempting retrieval
    based on the result."""
    if is_deterministic and all(results):
        return False
    return True
