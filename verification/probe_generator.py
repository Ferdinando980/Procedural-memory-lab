"""Automates writing A/B/C probe tasks (task-sonda) for an arbitrary skill
(Book) -- the step canary.py did entirely by hand for floating_point_equality
(see its module docstring, 2026-08-18/19: reading the skill, inventing a
plausible no-hint / domain-hint / explicit-hint problem, writing buggy_source
plus a pytest suite that actually distinguishes buggy from fixed, all by a
human).

Generated via the Expert adapter (generation infrastructure, not the model
under test -- same role split as skill_repair.py's rewriter). Every generated
probe is self-checked the same way a human author would have to satisfy by
construction: buggy_source must actually FAIL its own test_source (a "bug"
that already passes its own tests measures nothing) -- verified by actually
running it (domain/verifier.run_tests), retried up to a fixed number of
attempts, never accepted on the model's own claim alone.

MANDATORY before trusting this on any untested skill (see the plan,
Workstream A point 2): rerun it on floating_point_equality, whose true
qualitative shape is already known from canary.py, and check the freshly
generated probes reproduce the same kind of tier-c tracking / tier-b
selectivity when fed through substitution_ablation.py -- see
validate_probe_generator_milestone.py. Skipping this and trusting generated
probes on a brand-new skill first would repeat exactly the mistake
substitution_ablation.py's own validation milestone was built to avoid.
"""

import json
import re

from ..adapters.base import ModelAdapter
from ..domain.verifier import run_tests
from ..models import Book, Task
from .stabilizer import extract_json_object

# Mirrors canary.py's own category definitions (module docstring) exactly --
# this is the automation of that existing, hand-validated taxonomy, not a new
# one.
CATEGORY_DESCRIPTIONS = {
    "A": (
        "CATEGORY_A (explicit hint): a problem where the missing parameter/rule "
        "the skill supplies (a tolerance, a default, an operator choice, ...) IS "
        "stated explicitly in the problem's own wording (a percentage, a named "
        "margin, a concrete rule). Measures whether the model APPLIES the "
        "procedure when given what it needs, not whether it invents anything."
    ),
    "B": (
        "CATEGORY_B (domain-recognizable, no number): a problem where the "
        "parameter is NOT stated as a number or explicit rule, but the domain is "
        "recognizable from naming (a physical unit in a variable name, a "
        "domain-specific term). Some signal, just not a number."
    ),
    "C": (
        "CATEGORY_C (no signal at all): no number, no percentage, no unit, no "
        "domain-revealing naming anywhere in the problem. Only a genuine probe "
        "if there really IS a derivable correct answer from general reasoning "
        "alone (a real convention, e.g. currency -> cent precision) -- if you "
        "cannot think of a real, defensible reason the correct value follows "
        "from general knowledge without ANY hint, still write the most "
        "hint-free version you can; do not invent a fake convention to make it "
        "look valid. Whether it is actually usable is decided later, by "
        "checking whether an unaided model converges on it independently -- "
        "not assumed here."
    ),
}

_PROBE_SYSTEM_PROMPT = (
    "You write probe tasks used to test whether a language model applies a "
    "debugging procedure ('skill') by genuine reasoning or by copying a "
    "literal example from the procedure's own text verbatim. Given a skill's "
    "procedure text and a target category, invent ONE new, small, "
    "self-contained Python function with a realistic bug matching the "
    "skill's pattern, plus a pytest test suite (plain `def test_...(): "
    "assert ...` functions only -- no imports, no fixtures, no pytest.mark) "
    "that actually FAILS against the buggy version and would PASS a correct "
    "fix. Return ONLY a single JSON object, no prose, no markdown code "
    'fences, with exactly these keys: {"problem_id": "...", "fn_name": '
    '"...", "buggy_source": "...", "test_source": "..."}. buggy_source and '
    "test_source are raw Python source code as JSON strings (use \\n for "
    "newlines). Do not reuse any example, function name, or scenario that "
    "already appears in the procedure text verbatim -- a probe that recites "
    "the skill's own example measures nothing."
)

_SPLIT_BY_CATEGORY = {"A": "CATEGORY_A", "B": "CATEGORY_B", "C": "CATEGORY_C"}


def _build_probe_prompt(book: Book, category: str, avoid_problem_ids: list[str], feedback: str | None = None) -> str:
    avoid = f" Avoid these problem_ids, already used for this skill: {avoid_problem_ids}." if avoid_problem_ids else ""
    prompt = (
        f"Skill procedure text (pattern: {book.pattern_id!r}):\n\n{book.procedure_text}\n\n"
        f"Target category:\n{CATEGORY_DESCRIPTIONS[category]}\n\n"
        f"Write ONE new probe task for this category, matching pattern {book.pattern_id!r}.{avoid}"
    )
    if feedback:
        prompt += f"\n\nPrevious attempt failed: {feedback}"
    return prompt


def _parse_generated_task(text: str, book: Book, category: str) -> Task | None:
    # extract_json_object (verification/stabilizer.py), not the old greedy
    # _JSON_RE regex -- balanced-brace scanning instead of first-'{'-to-
    # last-'}', the confirmed cause of 'invalid Qwen verdict' elsewhere
    # (benchmark_skill_evaluation_holdout.py, 2026-09-21) whenever the
    # generated text has any extra brace before/after the real JSON object.
    data = extract_json_object(text)
    if data is None:
        return None
    required = {"problem_id", "fn_name", "buggy_source", "test_source"}
    if not required.issubset(data) or not isinstance(data["problem_id"], str):
        return None
    if not data["buggy_source"].strip() or not data["test_source"].strip():
        return None
    return Task(
        task_id=f"{book.pattern_id}__{data['problem_id']}__generated_{category.lower()}",
        pattern_id=book.pattern_id,
        problem_id=data["problem_id"],
        fn_name=data["fn_name"],
        buggy_source=data["buggy_source"],
        test_source=data["test_source"],
        split=_SPLIT_BY_CATEGORY[category],
        problem_tags=list(book.problem_tags),
        capability_tags=list(book.capability_tags),
    )


def generate_probe(
    book: Book,
    category: str,
    adapter: ModelAdapter,
    avoid_problem_ids: list[str] | None = None,
    max_attempts: int = 3,
) -> Task | None:
    """One self-checked probe in the given category, or None if max_attempts
    is exhausted without producing a usable one. 'Usable' means: parses into a
    Task, AND buggy_source genuinely fails test_source (verified by actually
    running it, not assumed from the model's own claim) -- the same bar a
    human author meets by construction when hand-writing a canary task."""
    avoid = list(avoid_problem_ids or [])
    feedback: str | None = None
    for _ in range(max_attempts):
        prompt = _build_probe_prompt(book, category, avoid, feedback)
        # 4096, not 1024: a smaller cap silently truncated reasoning-model
        # output mid-JSON (the same failure agents/worker.py already
        # documents for this provider class -- gemini-3.7-flash spends
        # hundreds of tokens on internal reasoning before writing anything).
        # Every category A/B attempt failed to parse under 1024, not because
        # the model couldn't write a valid probe.
        completion = adapter.complete(prompt=prompt, system=_PROBE_SYSTEM_PROMPT, max_tokens=4096)
        task = _parse_generated_task(completion.text, book, category)
        if task is None:
            # 2026-09-18: name the concrete parse failure instead of a silent
            # retry -- same fix as method_trap.py's generate_trap_scenario,
            # same reasoning (a blind retry with no diagnostic repeats itself).
            feedback = "your response did not parse into a valid task -- return ONLY JSON with problem_id, fn_name, non-empty buggy_source, and non-empty test_source, no prose, no markdown fences."
            continue
        result = run_tests(task.buggy_source, task.test_source)
        if result.passed:
            # The "buggy" source passes its own tests -- the tests don't
            # actually exercise the claimed bug, so this probe would measure
            # nothing. Not usable; retry with this problem_id excluded so the
            # model doesn't just regenerate the same non-bug.
            avoid.append(task.problem_id)
            feedback = f"'{task.problem_id}'s buggy_source PASSED its own test_source -- the bug wasn't real. Make the bug more clearly present, or the tests more sensitive to it."
            continue
        return task
    return None


def generate_probe_set(
    book: Book,
    adapter: ModelAdapter,
    categories: tuple[str, ...] = ("A", "B", "C"),
    max_attempts: int = 3,
) -> dict[str, Task | None]:
    """Generates one probe per requested category. A None entry for 'C' is
    expected and legitimate (see CATEGORY_C's own description above) -- a
    caller must NOT treat a None C as a bug in this generator, matching
    canary.py's own INVALID_EXAMPLES precedent (most hand-attempted C probes
    there were invalid; only currency and significant-figures ever
    validated). A None for A or B is more concerning and worth logging."""
    used_ids: list[str] = []
    probes: dict[str, Task | None] = {}
    for category in categories:
        task = generate_probe(book, category, adapter, avoid_problem_ids=used_ids, max_attempts=max_attempts)
        probes[category] = task
        if task is not None:
            used_ids.append(task.problem_id)
    return probes


# Generic, domain-independent evaluation suites
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from ..adapters.base import ModelAdapter
from ..models import Book
from .stabilizer import majority_vote


PROBE_KINDS = ("applicable", "transfer", "boundary", "adversarial", "negative_control")


@dataclass(frozen=True)
class EvaluationProbe:
    id: str
    kind: str
    request: str
    should_apply: bool
    expected_behavior: str
    rubric: list[str]


@dataclass(frozen=True)
class EvaluationSuite:
    book_id: str
    book_version: int
    criterion: str
    probes: list[EvaluationProbe]
    generated_at: str


@dataclass(frozen=True)
class ProbeVerdict:
    probe_id: str
    direct_score: float
    skilled_score: float
    winner: str
    reason: str


def _words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE)


def shared_ngrams(left: str, right: str, size: int = 6) -> set[str]:
    a, b = _words(left), _words(right)
    if len(a) < size or len(b) < size:
        return set()
    source = {" ".join(a[i:i + size]) for i in range(len(a) - size + 1)}
    return {" ".join(b[i:i + size]) for i in range(len(b) - size + 1)} & source


def validate_suite(book: Book, probes: list[EvaluationProbe]) -> list[str]:
    errors: list[str] = []
    ids, requests = set(), set()
    for probe in probes:
        if probe.kind not in PROBE_KINDS:
            errors.append(f"{probe.id}: invalid kind")
        if not probe.id or probe.id in ids:
            errors.append(f"{probe.id or '(empty)'}: duplicate or empty id")
        ids.add(probe.id)
        normalized = " ".join(_words(probe.request))
        if not normalized or normalized in requests:
            errors.append(f"{probe.id}: duplicate or empty request")
        requests.add(normalized)
        overlap = shared_ngrams(book.procedure_text, probe.request)
        if overlap:
            errors.append(f"{probe.id}: copied phrase: {sorted(overlap)[0]}")
        if not probe.expected_behavior or not probe.rubric:
            errors.append(f"{probe.id}: missing expected behavior or rubric")
        if (probe.kind == "negative_control") == probe.should_apply:
            errors.append(f"{probe.id}: wrong should_apply value")
    for kind in PROBE_KINDS:
        if not any(probe.kind == kind for probe in probes):
            errors.append(f"missing {kind}")
    return errors


_COMPILE_SYSTEM = """You are the Probe Generator. Compile a fresh evaluation for one arbitrary
procedure. Generate exactly five independent user requests: applicable;
transfer (same principle in a distant context); boundary; adversarial; and
negative_control where the procedure must not be applied. Do not answer the
requests. Do not reuse examples, names, scenarios, or any six-word sequence
from the procedure. Derive observable expected behavior and a concrete rubric
for each request. The negative control must test selectivity, not obedience.
Return ONLY JSON: {"criterion":"...","probes":[{"id":"...","kind":"applicable|transfer|boundary|adversarial|negative_control","request":"...","should_apply":true,"expected_behavior":"...","rubric":["..."]}]}.
The procedure may concern any domain. Never assume programming, tests, study,
writing, or any fixed subject."""


def compile_evaluation_suite(book: Book, adapter: ModelAdapter, max_attempts: int = 3) -> EvaluationSuite:
    feedback = ""
    for _ in range(max_attempts):
        prompt = f"TITLE: {book.title}\n\nPROCEDURE:\n```\n{book.procedure_text}\n```"
        if feedback:
            prompt += f"\n\nPrevious suite was rejected:\n{feedback}"
        completion = adapter.complete(prompt, system=_COMPILE_SYSTEM, max_tokens=4096, thinking_budget=0)
        data = extract_json_object(completion.text)
        if data is None:
            feedback = "no JSON object"
            continue
        try:
            probes = [
                EvaluationProbe(
                    id=str(item.get("id", "")).strip(),
                    kind=str(item.get("kind", "")).strip(),
                    request=str(item.get("request", "")).strip(),
                    should_apply=item.get("should_apply") is True,
                    expected_behavior=str(item.get("expected_behavior", "")).strip(),
                    rubric=[str(value).strip() for value in item.get("rubric", []) if str(value).strip()],
                )
                for item in data.get("probes", []) if isinstance(item, dict)
            ]
        except (json.JSONDecodeError, TypeError, AttributeError) as error:
            feedback = f"invalid JSON shape: {error}"
            continue
        errors = validate_suite(book, probes)
        if errors:
            feedback = "\n".join(errors)
            continue
        return EvaluationSuite(
            book.id, book.version, str(data.get("criterion", "")).strip(), probes,
            datetime.now(timezone.utc).isoformat(),
        )
    raise ValueError(f"could not compile a valid evaluation suite: {feedback}")


_ANSWER_SYSTEM = "Respond to the user request directly."
_JUDGE_SYSTEM = """Blindly score response A and response B against only the request,
expected behavior, and rubric. Do not reward phrase overlap. For a negative
control, penalize unnecessary application of the tested behavior. Return ONLY
JSON: {"score_a":0,"score_b":0,"winner":"A|B|TIE|UNKNOWN","reason":"..."}."""


def _judge_pair(probe: EvaluationProbe, a_text: str, b_text: str, index: int, judge: ModelAdapter):
    """One blind judge call over a FIXED response pair -- factored out of
    evaluate_suite (2026-09-21) so evaluate_suite_stability can repeat just
    this call against the same answers without regenerating them, isolating
    judge-verdict noise from answer-generation noise. Returns (ProbeVerdict,
    CompletionResult) -- the raw completion is kept so a caller can account
    real judge cost/tokens per repeated call, same as any other adapter call
    in this package."""
    prompt = (
        f"REQUEST:\n{probe.request}\n\nEXPECTED:\n{probe.expected_behavior}\n\n"
        f"RUBRIC:\n- " + "\n- ".join(probe.rubric) + f"\n\nRESPONSE A:\n{a_text}\n\nRESPONSE B:\n{b_text}"
    )
    result = judge.complete(prompt, system=_JUDGE_SYSTEM, max_tokens=512, thinking_budget=0)
    data = extract_json_object(result.text)
    if data is None:
        return ProbeVerdict(probe.id, 0, 0, "UNKNOWN", f"judge returned no JSON; raw={result.text[:300]!r}"), result
    try:
        score_a, score_b = float(data.get("score_a", 0)), float(data.get("score_b", 0))
        winner = str(data.get("winner", "UNKNOWN")).upper()
        direct_score, skilled_score = (score_a, score_b) if index % 2 == 0 else (score_b, score_a)
        mapped = {"A": "DIRECT", "B": "SKILLED"} if index % 2 == 0 else {"A": "SKILLED", "B": "DIRECT"}
        return ProbeVerdict(probe.id, direct_score, skilled_score, mapped.get(winner, winner), str(data.get("reason", ""))), result
    except (json.JSONDecodeError, TypeError, ValueError):
        return ProbeVerdict(probe.id, 0, 0, "UNKNOWN", "judge returned invalid JSON"), result


def evaluate_suite(
    book: Book,
    suite: EvaluationSuite,
    worker: ModelAdapter,
    judge: ModelAdapter,
) -> list[ProbeVerdict]:
    verdicts = []
    for index, probe in enumerate(suite.probes):
        direct = worker.complete(probe.request, system=_ANSWER_SYSTEM, max_tokens=2048)
        skilled = worker.complete(probe.request, system=book.procedure_text, max_tokens=2048)
        # Alternate labels to reduce fixed first-position preference.
        a, b = (direct.text, skilled.text) if index % 2 == 0 else (skilled.text, direct.text)
        verdict, _ = _judge_pair(probe, a, b, index, judge)
        verdicts.append(verdict)
    return verdicts


@dataclass(frozen=True)
class ProbeStability:
    probe_id: str
    verdict: ProbeVerdict            # majority verdict across reps, or UNSTABLE (see below)
    agreement: float                 # majority_count / judge_reps
    samples: tuple[str, ...]         # winner label per repeated judge call, in order
    judge_cost_usd: float            # total judge $ spent measuring this one probe's stability


def evaluate_suite_stability(
    book: Book,
    suite: EvaluationSuite,
    worker: ModelAdapter,
    judge: ModelAdapter,
    judge_reps: int = 3,
    adaptive: bool = False,
    decisive_margin: float = 3.0,
) -> list[ProbeStability]:
    """Repeats ONLY the judge call (Clessidra-bounded at judge_reps, never
    unbounded sampling) against a FIXED direct/skilled answer pair per probe
    -- the same isolate-the-noisy-step methodology stabilizer.py documents
    for every other holistic yes/no LLM judgment in this package ('does this
    skill have a risky slot?', etc.), applied here to evaluate_suite's own
    judge.complete() call, which nothing covered before this. A STOP_UPLIFT/
    STOP_HARM decision built on a single unrepeated judge call per probe
    cannot distinguish a real effect from judge noise on that one call.

    Deliberately NOT built on stabilizer.vote_for_result: that function's
    fail-closed behavior only covers found-vs-not-found ties (a verdict is
    always produced here, never None), not a genuine three-way split among
    DIRECT/SKILLED/TIE/UNKNOWN -- letting Counter's insertion-order tie-break
    silently pick a winner in that case would hide exactly the instability
    this function exists to surface. Uses stabilizer.majority_vote instead
    (2026-09-21), which does surface that kind of tie as None -- shared with
    verification.benchmark_self_consistency's own vote over Worker
    candidates instead of two copies of the same tie rule.

    adaptive (2026-09-21, TODO.md point 20, application #2 of the atom/
    particle gate): when True, stops after the FIRST judge call if its own
    score margin already looks decisive (|direct_score - skilled_score| >=
    decisive_margin) -- an 'atom' verdict, ReASC's single-sample decision
    stage applied to this judge instead of to self-consistency sampling.
    Spends the full judge_reps budget only on genuinely close calls
    ('particle'). False (default) reproduces today's fixed-reps behavior
    exactly, no change for any existing caller."""
    results: list[ProbeStability] = []
    for index, probe in enumerate(suite.probes):
        direct = worker.complete(probe.request, system=_ANSWER_SYSTEM, max_tokens=2048)
        skilled = worker.complete(probe.request, system=book.procedure_text, max_tokens=2048)
        a, b = (direct.text, skilled.text) if index % 2 == 0 else (skilled.text, direct.text)
        samples: list[ProbeVerdict] = []
        judge_cost = 0.0
        for rep in range(judge_reps):
            verdict, completion = _judge_pair(probe, a, b, index, judge)
            samples.append(verdict)
            judge_cost += completion.cost_usd
            if adaptive and rep == 0 and abs(verdict.direct_score - verdict.skilled_score) >= decisive_margin:
                break
        counts = Counter(sample.winner for sample in samples)
        winner_label = majority_vote([sample.winner for sample in samples])
        top_count = counts.most_common(1)[0][1]
        agreement = top_count / len(samples) if samples else 0.0
        if winner_label is None:
            majority = ProbeVerdict(probe.id, 0, 0, "UNSTABLE", f"judge tied across {len(samples)} reps: {dict(counts)}")
        else:
            majority = next(sample for sample in samples if sample.winner == winner_label)
        results.append(ProbeStability(probe.id, majority, agreement, tuple(sample.winner for sample in samples), judge_cost))
    return results

