"""Current debugging adapter for the domain-neutral recovery party."""

from dataclasses import dataclass

from ..adapters.base import CompletionResult, ModelAdapter
from ..agents.worker import MAX_OUTPUT_TOKENS, SYSTEM_PROMPT, build_recovery_prompt, extract_code
from ..domain.verifier import VerificationResult, run_tests
from ..models import SkillPackage, Task
from .python_runesmith import enumerate_local_transformations
from .recovery_party import CandidateTrial, PartyOutcome, SearchBudget, RecoveryRoute, run_recovery_party


ROUTES = [
    RecoveryRoute(
        "field_medic",
        "Make the smallest change that directly satisfies the failed observation. Preserve every unrelated behavior.",
        priority=30,
        context_policy="full",
    ),
    RecoveryRoute(
        "rune_smith",
        "Reconstruct the simplest implementation from the stated task and observable examples. Do not preserve a failed implementation choice merely because it already exists.",
        priority=20,
        context_policy="evidence_only",
    ),
    RecoveryRoute(
        "devils_advocate",
        "Find the smallest counterexample explaining why the previous correction failed, then produce a correction that handles both that counterexample and the already passing behavior.",
        priority=10,
        context_policy="evidence_only",
    ),
]


@dataclass(frozen=True)
class CodeFailureEvidence:
    task: Task
    failed_source: str
    verifier_feedback: str
    package: SkillPackage | None = None
    detective_hint: str | None = None


@dataclass
class CodeCandidate:
    source: str
    completion: CompletionResult | None


def run_code_recovery_party(
    evidence: CodeFailureEvidence,
    adapter: ModelAdapter,
    policy: SearchBudget = SearchBudget(),
) -> PartyOutcome[CodeCandidate, VerificationResult]:
    # Zero-token, reversible local search goes first. This is one domain tool
    # plugged into a generic role; the party core has no Python knowledge.
    tool_trials = []
    frontier = [(evidence.failed_source, [], -1)]
    seen = {evidence.failed_source}
    # Depth three permits small compositions (for example, independent local
    # defects) while the hard cap keeps the zero-token search predictable.
    for _depth in range(3):
        next_frontier = []
        for source, history, _score in frontier:
            for rune in enumerate_local_transformations(source):
                if rune.source in seen:
                    continue
                seen.add(rune.source)
                transformations = history + [rune.transformation]
                verdict = run_tests(rune.source, evidence.task.test_source)
                route = RecoveryRoute(
                    "runesmith:" + "+".join(transformations),
                    "; ".join(transformations), priority=100,
                )
                trial = CandidateTrial(route, CodeCandidate(rune.source, None), verdict, verdict.passed, 0)
                tool_trials.append(trial)
                if verdict.passed:
                    return PartyOutcome(trial, tool_trials, False)
                next_frontier.append((rune.source, transformations, verdict.tests_passed or 0))
                if len(tool_trials) >= 320:
                    break
            if len(tool_trials) >= 320:
                break
        frontier = sorted(next_frontier, key=lambda item: item[2], reverse=True)[:32]
        if not frontier or len(tool_trials) >= 320:
            break

    def produce(item: CodeFailureEvidence, route: RecoveryRoute):
        hint_parts = [part for part in [item.detective_hint, f"Recovery route: {route.instruction}"] if part]
        prompt = build_recovery_prompt(
            item.task, item.failed_source, item.verifier_feedback,
            item.package if route.context_policy == "full" else None,
            "\n".join(hint_parts),
        )
        completion = adapter.complete(prompt=prompt, system=SYSTEM_PROMPT, max_tokens=MAX_OUTPUT_TOKENS)
        candidate = CodeCandidate(extract_code(completion.text), completion)
        return candidate, completion.input_tokens + completion.output_tokens

    def verify(candidate: CodeCandidate):
        verdict = run_tests(candidate.source, evidence.task.test_source)
        return verdict, verdict.passed

    model_outcome = run_recovery_party(evidence, ROUTES, produce, verify, policy)
    model_outcome.trials = tool_trials + model_outcome.trials
    return model_outcome
