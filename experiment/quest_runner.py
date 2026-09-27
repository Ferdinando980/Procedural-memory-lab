from ..adapters.base import CompletionResult, ModelAdapter
from ..agents.worker import MAX_OUTPUT_TOKENS, SYSTEM_PROMPT, build_prompt, extract_code
from ..cheater import solution_bank
from ..domain.verifier import run_tests
from ..librarian import librarian
from ..librarian.competence import probe_capability, should_retrieve
from ..librarian.context_budget import enforce_budget
from ..models import SkillPackage, Task
from ..verification.failure_recovery import recover_failed_attempt
from .events import emit
from .experiment_log import LogRecord, append, new_record


def run_quest(
    task: Task,
    experiment_id: str,
    config_name: str,
    adapter: ModelAdapter,
    use_librarian: bool = False,
    use_cheater: bool = False,
    use_detective: bool = False,
    use_retrieval_gate: bool = False,
) -> LogRecord:
    """Run one quest; optionally recover a verified failure with Detective.

    ``use_detective`` never changes the first F attempt.  Only a failed
    executable verification triggers investigation and one feedback-grounded
    retry.  Thus a 5/5 F run makes zero Detective calls, while a 4/5 run gives
    the single failed case one recovery opportunity.

    ``use_retrieval_gate`` (2026-09-21, TODO.md point 20/21 application #1,
    default False -- no behavior change for any existing caller): only takes
    effect together with ``use_librarian``. Before routing, runs librarian.
    competence.probe_capability (2 real, unaided Worker samples on THIS
    task, verified with real pytest) and skips retrieval entirely when
    should_retrieve() says the result was a deterministic PASS ("atom" --
    the Worker already solves this reliably without help, the exact case
    experiment/metrics.py::retrieval_waste_analysis measured as 81.3%
    historical waste). The 2 probe calls have a real token cost of their
    own, tracked as their own event -- this is a genuine trade (probe cost
    now vs skill-injection cost later), not a free optimization, and must
    be measured, not assumed.
    """
    npc = f"{config_name}:npc"
    ev = emit(
        experiment_id, task.task_id, config_name, npc, "QUEST_CREATED",
        reason="assign_quest", split=task.split, pattern_id=task.pattern_id,
    )

    ev = emit(
        experiment_id, task.task_id, config_name, npc, "NPC_ASSIGNED",
        parent_event_id=ev.event_id, reason="fixed_experiment_design",
        provider=adapter.PROVIDER, model=getattr(adapter, "model", None) or getattr(adapter, "model_name", "?"),
        use_librarian=use_librarian, use_cheater=use_cheater,
    )

    # Real token cost of retrieval, broken down: the base prompt (task alone) vs
    # what the retrieved skill context adds on top of it -- answers "who's using
    # all those extra tokens" instead of only seeing one combined number.
    base_prompt = build_prompt(task, None)
    base_tokens = adapter.count_input_tokens(base_prompt, system=SYSTEM_PROMPT)

    skill_package = None
    gated_skip = False
    if use_librarian or use_cheater:
        source = "librarian" if use_librarian else "cheater"
        ev = emit(
            experiment_id, task.task_id, config_name, f"{config_name}:{source}", "RETRIEVAL_STARTED",
            parent_event_id=ev.event_id, reason="route_skill",
        )

        if use_retrieval_gate and use_librarian:
            probe_prompt = build_prompt(task, None)
            probe_tokens_estimate = adapter.count_input_tokens(probe_prompt, system=SYSTEM_PROMPT)
            is_deterministic, probe_results = probe_capability(task, adapter, reps=2)
            gated_skip = not should_retrieve(is_deterministic, probe_results)
            ev = emit(
                experiment_id, task.task_id, config_name, f"{config_name}:{source}", "RETRIEVAL_GATE_DECISION",
                parent_event_id=ev.event_id, reason="atom_particle_probe",
                is_deterministic=is_deterministic, probe_results=probe_results, skipped_retrieval=gated_skip,
                # Real cost of the 2-sample probe itself -- an honest trade
                # against the skill-injection tokens it might save, not a
                # free optimization. Exact per-call token/cost accounting
                # isn't exposed by probe_capability's return value (it only
                # returns pass/fail), so this is an estimate of the input
                # side only (2x the base prompt, since the probe reuses the
                # same unaided prompt) -- output tokens/cost for the 2 real
                # calls are real but not separately itemized here.
                input_tokens=probe_tokens_estimate * 2, output_tokens=0,
            )

        if gated_skip:
            skill_package = SkillPackage(books=[], coverage="NONE")
        else:
            skill_package = librarian.route(task) if use_librarian else solution_bank.route(task)

        model_id = getattr(adapter, "model", None) or getattr(adapter, "model_name", "?")
        skill_package, base_over_budget, dropped_book_ids = enforce_budget(
            base_tokens=base_tokens,
            skill_package=skill_package,
            adapter=adapter,
            system=SYSTEM_PROMPT,
            build_prompt_with_books=lambda books: build_prompt(task, SkillPackage(books=books)),
            model=model_id,
        )
        if base_over_budget:
            ev = emit(
                experiment_id, task.task_id, config_name, f"{config_name}:{source}",
                "CONTEXT_BUDGET_BASE_EXCEEDED",
                parent_event_id=ev.event_id, reason="base_prompt_too_large",
                base_prompt_tokens=base_tokens, model=model_id,
                dropped_book_ids=dropped_book_ids,
            )
        elif dropped_book_ids:
            ev = emit(
                experiment_id, task.task_id, config_name, f"{config_name}:{source}",
                "CONTEXT_BUDGET_BOOKS_DROPPED",
                parent_event_id=ev.event_id, reason="over_context_budget",
                dropped_book_ids=dropped_book_ids, model=model_id,
            )

        prompt = build_prompt(task, skill_package)
        prompt_tokens = adapter.count_input_tokens(prompt, system=SYSTEM_PROMPT)
        ev = emit(
            experiment_id, task.task_id, config_name, f"{config_name}:{source}", "RETRIEVAL_RESULT",
            parent_event_id=ev.event_id, reason="route_skill",
            coverage=skill_package.coverage,
            skill_ids=[book.id for book in skill_package.books],
            detective_hint_used=False,
            base_prompt_tokens=base_tokens,
            skill_context_tokens=max(0, prompt_tokens - base_tokens),
            # Deterministic tag-overlap / solution-lookup retrieval makes no
            # model call of its own -- the skill_context_tokens above are
            # what it adds to the NEXT call (the worker's), not a cost the
            # retrieval step itself incurs.
            input_tokens=0, output_tokens=0,
        )
    else:
        prompt = base_prompt
        prompt_tokens = base_tokens

    ev = emit(
        experiment_id, task.task_id, config_name, f"{config_name}:worker", "PROMPT_BUILT",
        parent_event_id=ev.event_id, reason="build_prompt",
        prompt_chars=len(prompt), input_tokens_estimate=prompt_tokens,
        base_prompt_tokens=base_tokens,
        skill_context_tokens=max(0, prompt_tokens - base_tokens),
    )

    ev = emit(
        experiment_id, task.task_id, config_name, f"{config_name}:worker", "MODEL_CALL_STARTED",
        parent_event_id=ev.event_id, reason="solve_task",
        provider=adapter.PROVIDER, model=getattr(adapter, "model", None) or getattr(adapter, "model_name", "?"),
    )
    completion = adapter.complete(prompt=prompt, system=SYSTEM_PROMPT, max_tokens=MAX_OUTPUT_TOKENS)
    candidate_source = extract_code(completion.text)

    ev = emit(
        experiment_id, task.task_id, config_name, f"{config_name}:worker", "MODEL_CALL_FINISHED",
        parent_event_id=ev.event_id, reason="solve_task",
        model=completion.model, provider=completion.provider,
        input_tokens=completion.input_tokens, output_tokens=completion.output_tokens,
        cached_input_tokens=completion.cached_input_tokens,
        reasoning_output_tokens=completion.reasoning_output_tokens,
        cost_usd=completion.cost_usd, latency_ms=completion.latency_ms,
        retries=completion.retries, paused_seconds=completion.paused_seconds,
    )

    verification = run_tests(candidate_source, task.test_source)
    ev = emit(
        experiment_id, task.task_id, config_name, f"{config_name}:checker", "VERIFICATION",
        parent_event_id=ev.event_id, reason="verify_fix",
        passed=verification.passed, tests_total=verification.tests_total,
        tests_passed=verification.tests_passed,
        failed_candidate_source=candidate_source if not verification.passed else None,
        verifier_feedback=(verification.stdout or verification.error) if not verification.passed else None,
        # pytest subprocess makes no model call -- real cost here is 0.
        input_tokens=0, output_tokens=0,
    )

    # Recovery is deliberately failure-triggered.  The first attempt above is
    # byte-for-byte the normal F path, so successful work is never perturbed.
    recovery_calls: list[CompletionResult] = []
    if use_detective and not verification.passed:
        ev = emit(
            experiment_id, task.task_id, config_name, f"{config_name}:detective", "RECOVERY_STARTED",
            parent_event_id=ev.event_id, reason="verified_failure",
            initial_tests_passed=verification.tests_passed, initial_tests_total=verification.tests_total,
        )
        outcome = recover_failed_attempt(
            task, candidate_source, verification, adapter,
            initial_package=skill_package, use_librarian=use_librarian,
        )
        skill_package = outcome.post_failure_package
        recovery_calls.extend(outcome.detective_calls)
        ev = emit(
            experiment_id, task.task_id, config_name, f"{config_name}:librarian", "POST_FAILURE_RETRIEVAL",
            parent_event_id=ev.event_id, reason="route_verified_failure",
            failure_status=outcome.failure.status,
            skill_ids=[book.id for book in skill_package.books], coverage=skill_package.coverage,
            input_tokens=0, output_tokens=0,
        )
        ev = emit(
            experiment_id, task.task_id, config_name, f"{config_name}:detective", "DETECTIVE_RESULT",
            parent_event_id=ev.event_id, reason="diagnose_verified_failure",
            resolved=outcome.detective_hint is not None, hint=outcome.detective_hint,
            case_resolved=outcome.case_resolved,
            failure_diagnosed=outcome.failure_diagnosed,
            model_calls=len(outcome.detective_calls),
            input_tokens=sum(c.input_tokens for c in outcome.detective_calls),
            output_tokens=sum(c.output_tokens for c in outcome.detective_calls),
            cost_usd=sum(c.cost_usd for c in outcome.detective_calls),
            latency_ms=sum(c.latency_ms for c in outcome.detective_calls),
        )
        recovery = outcome.worker_call
        recovery_calls.append(recovery)
        recovered_source = outcome.recovered_source
        ev = emit(
            experiment_id, task.task_id, config_name, f"{config_name}:worker", "RECOVERY_MODEL_CALL_FINISHED",
            parent_event_id=ev.event_id, reason="repair_verified_failure",
            model=recovery.model, provider=recovery.provider,
            input_tokens=recovery.input_tokens, output_tokens=recovery.output_tokens,
            cached_input_tokens=recovery.cached_input_tokens,
            reasoning_output_tokens=recovery.reasoning_output_tokens,
            cost_usd=recovery.cost_usd, latency_ms=recovery.latency_ms,
            retries=recovery.retries, paused_seconds=recovery.paused_seconds,
            detective_hint_used=outcome.detective_hint is not None,
        )
        verification = outcome.verification
        ev = emit(
            experiment_id, task.task_id, config_name, f"{config_name}:checker", "RECOVERY_VERIFICATION",
            parent_event_id=ev.event_id, reason="verify_recovery",
            passed=verification.passed, tests_total=verification.tests_total,
            tests_passed=verification.tests_passed, input_tokens=0, output_tokens=0,
            failed_candidate_source=recovered_source if not verification.passed else None,
            verifier_feedback=(verification.stdout or verification.error) if not verification.passed else None,
        )
        ev = emit(
            experiment_id, task.task_id, config_name, f"{config_name}:inspector", "INSPECTOR_VERDICT",
            parent_event_id=ev.event_id, reason="audit_recovery_trajectory",
            status=outcome.inspector_verdict.status,
            responsible=outcome.inspector_verdict.responsible,
            verdict_reason=outcome.inspector_verdict.reason,
            input_tokens=0, output_tokens=0,
        )

    if recovery_calls:
        calls = [completion, *recovery_calls]
        completion = CompletionResult(
            text=recovery.text,
            input_tokens=sum(c.input_tokens for c in calls),
            output_tokens=sum(c.output_tokens for c in calls),
            cached_input_tokens=sum(c.cached_input_tokens for c in calls),
            reasoning_output_tokens=(
                sum(c.reasoning_output_tokens or 0 for c in calls)
                if any(c.reasoning_output_tokens is not None for c in calls) else None
            ),
            cost_usd=sum(c.cost_usd for c in calls), latency_ms=sum(c.latency_ms for c in calls),
            model=completion.model, provider=completion.provider,
            retries=sum(c.retries for c in calls), paused_seconds=sum(c.paused_seconds for c in calls),
        )

    record = new_record(
        experiment_id=experiment_id,
        task_id=task.task_id,
        split=task.split,
        config_name=config_name,
        completion=completion,
        passed=verification.passed,
        coverage=skill_package.coverage if skill_package else "N/A",
    )
    append(record)
    emit(
        experiment_id, task.task_id, config_name, npc, "QUEST_COMPLETED",
        parent_event_id=ev.event_id, reason="log_result", passed=verification.passed,
    )
    return record
