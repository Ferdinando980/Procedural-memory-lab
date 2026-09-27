"""Complete failure-triggered recovery shared by runtime and benchmarks."""

from dataclasses import dataclass

from ..adapters.base import CompletionResult, ModelAdapter
from ..agents.worker import MAX_OUTPUT_TOKENS, SYSTEM_PROMPT, build_recovery_prompt, extract_code
from ..domain.verifier import VerificationResult, run_tests
from ..librarian import librarian
from ..models import FailureRecord, SkillPackage, Task
from . import detective, inspector
from .inspector import InspectorVerdict


class RecordingAdapter(ModelAdapter):
    def __init__(self, delegate: ModelAdapter):
        self.delegate = delegate
        self.PROVIDER = delegate.PROVIDER
        self.calls: list[CompletionResult] = []

    def complete(self, prompt, system=None, max_tokens=1024, thinking_budget=None):
        result = self.delegate.complete(prompt, system, max_tokens, thinking_budget)
        self.calls.append(result)
        return result

    def count_input_tokens(self, prompt, system=None):
        return self.delegate.count_input_tokens(prompt, system)


@dataclass
class RecoveryOutcome:
    failure: FailureRecord
    post_failure_package: SkillPackage
    recovered_source: str
    verification: VerificationResult
    detective_hint: str | None
    case_resolved: bool
    failure_diagnosed: bool
    detective_calls: list[CompletionResult]
    worker_call: CompletionResult
    inspector_verdict: InspectorVerdict


def recover_failed_attempt(
    task: Task,
    failed_source: str,
    failed_verification: VerificationResult,
    adapter: ModelAdapter,
    initial_package: SkillPackage | None = None,
    *,
    use_librarian: bool = True,
) -> RecoveryOutcome:
    """Run exactly one full recovery; callers must supply a real failed test."""
    if failed_verification.passed:
        raise ValueError("recovery can only start from a verified failure")
    feedback = (failed_verification.stdout or failed_verification.error or "Verifier failed without diagnostic output")[-6000:]
    failure = FailureRecord(
        task_id=task.task_id, phase="initial_attempt", status="VERIFIED_FAILURE",
        failed_source=failed_source, verifier_feedback=feedback,
        tests_passed=failed_verification.tests_passed,
        tests_total=failed_verification.tests_total,
    )
    package = (
        librarian.route_after_failure(task, failure, initial_package)
        if use_librarian else (initial_package or SkillPackage())
    )
    detective_adapter = RecordingAdapter(adapter)
    hint = None
    for book in package.books:
        if not book.decision_table:
            continue
        hypothesis = detective.investigate_cached(book, task, detective_adapter)
        if hypothesis and hypothesis.status == "RESOLVED" and not hypothesis.by_elimination:
            action = detective.action_for_hypothesis(book, hypothesis)
            hint = (
                f"Applicable skill case: {hypothesis.supported_case}. "
                f"Evidence: {hypothesis.evidence_quote}."
                + (f" Prescribed action: {action}." if action else "")
            )
            break
    case_resolved = hint is not None
    diagnosis = None
    for book in package.books:
        diagnosis = detective.diagnose_failure(book, failed_source, feedback, detective_adapter)
        if diagnosis:
            break
    if diagnosis is None:
        diagnosis = detective.diagnose_failure_generic(failed_source, feedback, detective_adapter)
    if diagnosis:
        detail = (
            f"Verified failure: {diagnosis.failure_quote}. "
            + (f"Relevant skill instruction: {diagnosis.skill_quote}. " if diagnosis.skill_quote else "")
            + f"Required repair: {diagnosis.repair_instruction}"
        )
        hint = f"{hint} {detail}" if hint else detail
    prompt = build_recovery_prompt(task, failed_source, feedback, package, hint)
    worker_call = adapter.complete(prompt=prompt, system=SYSTEM_PROMPT, max_tokens=MAX_OUTPUT_TOKENS)
    recovered_source = extract_code(worker_call.text)
    verification = run_tests(recovered_source, task.test_source)
    verdict = inspector.judge_online_recovery(
        failure_recorded=True, recovery_passed=verification.passed,
        detective_diagnosed=diagnosis is not None,
    )
    return RecoveryOutcome(
        failure, package, recovered_source, verification, hint, case_resolved,
        diagnosis is not None, detective_adapter.calls, worker_call, verdict,
    )
