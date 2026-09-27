"""Domain-neutral bounded search over independently produced recovery candidates.

The party knows nothing about Python, tests, or Books. A domain adapter
supplies evidence, candidate producers, and an external verifier.
"""

from dataclasses import dataclass, field
from typing import Callable, Generic, TypeVar


EvidenceT = TypeVar("EvidenceT")
CandidateT = TypeVar("CandidateT")
VerdictT = TypeVar("VerdictT")


@dataclass(frozen=True)
class RecoveryRoute:
    id: str
    instruction: str
    priority: int = 0
    context_policy: str = "full"  # full | evidence_only; interpreted by adapters


@dataclass
class CandidateTrial(Generic[CandidateT, VerdictT]):
    route: RecoveryRoute
    candidate: CandidateT
    verdict: VerdictT
    passed: bool
    cost_units: int = 0


@dataclass(frozen=True)
class SearchBudget:
    max_candidates: int = 3
    max_cost_units: int | None = None
    stop_on_first_pass: bool = True


@dataclass
class PartyOutcome(Generic[CandidateT, VerdictT]):
    selected: CandidateTrial[CandidateT, VerdictT] | None
    trials: list[CandidateTrial[CandidateT, VerdictT]] = field(default_factory=list)
    exhausted_budget: bool = False


def run_recovery_party(
    evidence: EvidenceT,
    routes: list[RecoveryRoute],
    produce: Callable[[EvidenceT, RecoveryRoute], tuple[CandidateT, int]],
    verify: Callable[[CandidateT], tuple[VerdictT, bool]],
    policy: SearchBudget = SearchBudget(),
) -> PartyOutcome[CandidateT, VerdictT]:
    """Let the existing Worker try bounded routes and the Verifier judge them.

    Route order is deterministic. The search budget caps exploration and can
    stop at the first externally verified success. No candidate judges itself.
    """
    trials: list[CandidateTrial[CandidateT, VerdictT]] = []
    spent = 0
    for route in sorted(routes, key=lambda item: (-item.priority, item.id))[:policy.max_candidates]:
        candidate, cost = produce(evidence, route)
        spent += max(0, cost)
        verdict, passed = verify(candidate)
        trial = CandidateTrial(route, candidate, verdict, passed, cost)
        trials.append(trial)
        if passed and policy.stop_on_first_pass:
            return PartyOutcome(trial, trials, False)
        if policy.max_cost_units is not None and spent >= policy.max_cost_units:
            return PartyOutcome(next((t for t in trials if t.passed), None), trials, True)
    return PartyOutcome(next((t for t in trials if t.passed), None), trials, False)
