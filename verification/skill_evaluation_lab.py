"""Research-only evaluation laboratory for arbitrary Books.

Cartographer and Notary have distinct authority. Scenario simulation and the
remaining RPG metaphors are tools owned by Probe Generator/orchestrator.
"""

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
import re
from typing import Iterable

from ..adapters.base import ModelAdapter
from ..models import Book
from .probe_generator import (
    EvaluationProbe,
    EvaluationSuite,
    ProbeStability,
    ProbeVerdict,
    evaluate_suite,
    evaluate_suite_stability,
    shared_ngrams,
    validate_suite,
)


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
REQUIRED_SCENARIOS = (
    "applicable", "transfer", "boundary", "adversarial", "negative_control"
)
SCENARIO_INSTRUCTIONS = {
    "applicable": "Use a natural, direct case where the mapped trigger is clearly present.",
    "transfer": "Move the principle to a distant domain, vocabulary and setting not used by the applicable case; preserve the underlying behavioral claim.",
    "boundary": "Place one decisive fact exactly near the apply/do-not-apply boundary so rigid pattern matching is likely to fail.",
    "adversarial": "Use distracting or conflicting details that tempt omission or over-application, while retaining a defensible expected behavior.",
    "negative_control": "Create a request where applying the procedure adds needless structure or harm; the correct behavior is to answer normally without displaying the procedure.",
}


@dataclass(frozen=True)
class BehaviorMap:
    book_id: str
    claim: str
    triggers: list[str]
    exclusions: list[str]
    observable_effects: list[str]
    failure_modes: list[str]
    evidence_sources: list[str]
    assumptions: list[str]


@dataclass(frozen=True)
class ExperimentManifest:
    book_fingerprint: str
    map_fingerprint: str
    suite_fingerprint: str
    preregistered_criterion: str
    seen_probe_fingerprints: tuple[str, ...] = ()
    labels_hidden: bool = True


@dataclass(frozen=True)
class NotaryVerdict:
    status: str  # VALID | INVALID | CONTAMINATED | INSUFFICIENT_EVIDENCE
    reasons: list[str]


@dataclass(frozen=True)
class EvidenceDecision:
    action: str  # CONTINUE | STOP_NO_REGRESSION | STOP_HARM | STOP_UPLIFT | UNKNOWN
    skilled_wins: int
    direct_wins: int
    ties: int
    unknown: int


@dataclass
class EvaluationRun:
    behavior_map: BehaviorMap
    suite: EvaluationSuite
    manifest: ExperimentManifest
    notary: NotaryVerdict
    verdicts: list[ProbeVerdict] = field(default_factory=list)
    decision: EvidenceDecision | None = None
    stability: list[ProbeStability] = field(default_factory=list)  # only populated when judge_reps > 1


def fingerprint(value: object) -> str:
    """Sigillo: stable provenance fingerprint for preregistration/contamination."""
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _json(text: str) -> dict | None:
    match = _JSON_RE.search(text)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


_CARTOGRAPHER_SYSTEM = """You are the Cartographer. Convert one arbitrary procedure
into a falsifiable behavior map. Do not create test questions and do not judge
answers. Separate triggers from exclusions. Describe only observable effects;
do not use vague claims such as 'better'. List plausible failure modes,
available evidence sources, and assumptions. Return ONLY JSON with keys claim,
triggers, exclusions, observable_effects, failure_modes, evidence_sources,
assumptions; every field except claim is an array of at most three concise
non-empty strings. Keep the whole JSON under 500 words."""


def map_behavior(book: Book, adapter: ModelAdapter, max_attempts: int = 3) -> BehaviorMap:
    feedback = ""
    for _ in range(max_attempts):
        prompt = f"TITLE: {book.title}\nPROCEDURE:\n```\n{book.procedure_text}\n```"
        if feedback:
            prompt += f"\nREJECTED BECAUSE: {feedback}"
        result = adapter.complete(prompt, system=_CARTOGRAPHER_SYSTEM, max_tokens=768, thinking_budget=0)
        data = _json(result.text)
        if data is None:
            feedback = "missing JSON"
            continue
        keys = ("triggers", "exclusions", "observable_effects", "failure_modes", "evidence_sources", "assumptions")
        lists = {key: [str(v).strip() for v in data.get(key, []) if str(v).strip()] for key in keys}
        claim = str(data.get("claim", "")).strip()
        required = ("triggers", "exclusions", "observable_effects", "failure_modes")
        if not claim or any(not lists[key] for key in required):
            feedback = "claim, triggers, exclusions, observable_effects and failure_modes are required"
            continue
        return BehaviorMap(book.id, claim, **lists)
    raise ValueError(f"could not produce a valid behavior map: {feedback}")


_MIME_SYSTEM = """You simulate one diverse user to create ONE fresh evaluation
scenario for the exact requested kind. Never change the supplied kind or
should_apply value. Never copy examples, names, scenarios or any six-word
sequence from the source procedure. Do not answer the request. Return ONLY JSON
{"request":"...","expected_behavior":"...","rubric":["..."]}. Rubric
items must be observable from the answer and must not reveal a reference answer."""


def generate_scenarios(book: Book, behavior: BehaviorMap, adapter: ModelAdapter, max_attempts: int = 3) -> EvaluationSuite:
    probes: list[EvaluationProbe] = []
    used_requests: list[str] = []
    for kind in REQUIRED_SCENARIOS:
        feedback = ""
        should_apply = kind != "negative_control"
        for attempt in range(max_attempts):
            prompt = (
                f"KIND: {kind}\nKIND REQUIREMENT: {SCENARIO_INSTRUCTIONS[kind]}\n"
                f"SHOULD_APPLY: {str(should_apply).lower()}\n"
                f"BEHAVIOR MAP:\n{json.dumps(asdict(behavior), ensure_ascii=False)}\n"
                f"ALREADY USED REQUESTS:\n{json.dumps(used_requests, ensure_ascii=False)}\n"
                f"SOURCE PROCEDURE FOR ANTI-COPY ONLY:\n```\n{book.procedure_text}\n```"
            )
            if feedback:
                prompt += f"\nREJECTED BECAUSE:\n{feedback}"
            concise_system = _MIME_SYSTEM + " Keep the request under 80 words and use at most three rubric items of at most 12 words each."
            result = adapter.complete(prompt, system=concise_system, max_tokens=384, thinking_budget=0)
            data = _json(result.text)
            if data is None:
                feedback = "missing JSON"
                continue
            probe = EvaluationProbe(
                f"{book.id}:{kind}", kind, str(data.get("request", "")).strip(),
                should_apply, str(data.get("expected_behavior", "")).strip(),
                [str(v).strip() for v in data.get("rubric", []) if str(v).strip()],
            )
            errors = []
            if not probe.request or not probe.expected_behavior or not probe.rubric:
                errors.append("missing request, expected_behavior or rubric")
            if shared_ngrams(book.procedure_text, probe.request):
                errors.append("request copies a six-word sequence from source")
            normalized = " ".join(re.findall(r"[^\W_]+", probe.request.casefold(), flags=re.UNICODE))
            prior = {" ".join(re.findall(r"[^\W_]+", value.casefold(), flags=re.UNICODE)) for value in used_requests}
            if normalized in prior:
                errors.append("request duplicates an earlier scenario")
            if errors:
                feedback = "; ".join(errors)
                continue
            probes.append(probe)
            used_requests.append(probe.request)
            break
        else:
            raise ValueError(f"could not generate {kind} scenario: {feedback}")
    errors = validate_suite(book, probes)
    if errors:
        raise ValueError("invalid completed suite: " + "; ".join(errors))
    criterion = "; ".join(behavior.observable_effects)
    return EvaluationSuite(book.id, book.version, criterion, probes, "preregistered")


_ILLUSIONIST_SYSTEM = """Paraphrase one evaluation request into semantically
equivalent forms with different wording, order, tone and surface context.
Preserve every binding condition and do not make the tested procedure more
obvious. Return ONLY JSON {"variants":["..."]}."""


def generate_paraphrases(probe: EvaluationProbe, source_procedure: str, adapter: ModelAdapter, count: int = 3) -> list[str]:
    """Illusionist: surface variation; ownership stays with Probe Generator."""
    result = adapter.complete(
        f"COUNT: {count}\nREQUEST:\n{probe.request}",
        system=_ILLUSIONIST_SYSTEM, max_tokens=1024, thinking_budget=0,
    )
    data = _json(result.text) or {}
    variants = []
    for value in data.get("variants", []):
        text = str(value).strip()
        if text and text != probe.request and not shared_ngrams(source_procedure, text):
            variants.append(text)
    return list(dict.fromkeys(variants))[:count]


def preregister(book: Book, behavior: BehaviorMap, suite: EvaluationSuite, seen: Iterable[str] = ()) -> ExperimentManifest:
    return ExperimentManifest(
        fingerprint(asdict(book)), fingerprint(asdict(behavior)), fingerprint(asdict(suite)),
        suite.criterion, tuple(sorted(set(seen))), True,
    )


def notarize(book: Book, behavior: BehaviorMap, suite: EvaluationSuite, manifest: ExperimentManifest) -> NotaryVerdict:
    """Judge experiment validity, never answer quality."""
    reasons = validate_suite(book, suite.probes)
    if manifest.book_fingerprint != fingerprint(asdict(book)):
        reasons.append("book changed after preregistration")
    if manifest.map_fingerprint != fingerprint(asdict(behavior)):
        reasons.append("behavior map changed after preregistration")
    if manifest.suite_fingerprint != fingerprint(asdict(suite)):
        reasons.append("suite changed after preregistration")
    if manifest.preregistered_criterion != suite.criterion or not suite.criterion.strip():
        reasons.append("criterion missing or changed after preregistration")
    if not manifest.labels_hidden:
        reasons.append("direct/skilled labels are not hidden from the judge")
    current = {fingerprint(probe.request) for probe in suite.probes}
    contaminated = sorted(current.intersection(manifest.seen_probe_fingerprints))
    if contaminated:
        return NotaryVerdict("CONTAMINATED", [f"{len(contaminated)} probe(s) previously seen"] + reasons)
    if reasons:
        return NotaryVerdict("INVALID", reasons)
    if not behavior.evidence_sources:
        return NotaryVerdict("INSUFFICIENT_EVIDENCE", ["behavior map declares no evidence source"])
    return NotaryVerdict("VALID", [])


def evidence_decision(verdicts: list[ProbeVerdict], minimum_decided: int = 5) -> EvidenceDecision:
    """Clessidra + Veggente: bounded, conservative stopping decision."""
    skilled = sum(v.winner == "SKILLED" for v in verdicts)
    direct = sum(v.winner == "DIRECT" for v in verdicts)
    ties = sum(v.winner == "TIE" for v in verdicts)
    unknown = len(verdicts) - skilled - direct - ties
    decided = skilled + direct + ties
    action = "CONTINUE"
    if decided >= minimum_decided:
        if direct > skilled:
            action = "STOP_HARM"
        elif skilled > direct:
            action = "STOP_UPLIFT"
        else:
            action = "STOP_NO_REGRESSION"
    if not verdicts or unknown == len(verdicts):
        action = "UNKNOWN"
    return EvidenceDecision(action, skilled, direct, ties, unknown)


def build_bestiary(verdicts: list[ProbeVerdict], suite: EvaluationSuite) -> dict[str, dict[str, int]]:
    """Bestiario: aggregate outcomes by scenario kind without inventing causes."""
    kinds = {probe.id: probe.kind for probe in suite.probes}
    result: dict[str, dict[str, int]] = {}
    for verdict in verdicts:
        bucket = result.setdefault(kinds.get(verdict.probe_id, "unknown"), {})
        bucket[verdict.winner] = bucket.get(verdict.winner, 0) + 1
    return result


def run_lab(
    book: Book,
    architect: ModelAdapter,
    worker: ModelAdapter,
    judge: ModelAdapter,
    seen: Iterable[str] = (),
    judge_reps: int = 1,
) -> EvaluationRun:
    """Full research flow. The Notary can abstain before expensive answers.

    judge_reps=1 (default) keeps the original single-shot behavior, no cost
    or result change for existing calibration/holdout runs. judge_reps>1
    (Clessidra-bounded, never unbounded) repeats only the judge's verdict
    against a fixed answer pair per probe via probe_generator.
    evaluate_suite_stability, measuring whether a STOP_UPLIFT/STOP_HARM
    decision survives judge noise -- see that function's docstring for why
    a genuine judge tie is reported as UNSTABLE rather than silently
    resolved. run.stability carries the per-probe agreement ratio and the
    real judge cost paid to measure it; run.verdicts/run.decision use the
    majority verdict either way, so evidence_decision/build_bestiary need no
    changes (UNSTABLE falls into the existing 'unknown' bucket, same as
    UNKNOWN)."""
    behavior = map_behavior(book, architect)
    suite = generate_scenarios(book, behavior, architect)
    manifest = preregister(book, behavior, suite, seen)
    notary = notarize(book, behavior, suite, manifest)
    run = EvaluationRun(behavior, suite, manifest, notary)
    if notary.status != "VALID":
        return run
    if judge_reps > 1:
        run.stability = evaluate_suite_stability(book, suite, worker, judge, judge_reps)
        run.verdicts = [stability.verdict for stability in run.stability]
    else:
        run.verdicts = evaluate_suite(book, suite, worker, judge)  # Specchio: blind A/B with alternating labels.
    run.decision = evidence_decision(run.verdicts)
    return run
