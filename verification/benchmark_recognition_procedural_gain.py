"""Decomposes the accuracy gain a skill produces (D vs A here -- the same
comparison other experiments in this project call F vs B) into two
causally-separated components: how much comes from the skill telling the
Worker WHAT KIND of problem it is (Recognition Gain) vs how much comes from
telling it HOW TO FIX IT once the problem is already recognized (Procedural
Gain).

Idea proposed by the user (2026-09-21), inspired by -- and explicitly NOT
more novel than -- the established Task Recognition vs Task Learning
distinction in in-context learning (Pan, Gao, Chen, Chen, "What In-Context
Learning 'Learns' In-Context: Disentangling Task Recognition and Task
Learning", ACL 2023 Findings, arXiv:2305.09731; extended by "Localizing
Task Recognition and Task Learning in In-Context Learning via Attention
Head Analysis", arXiv:2509.24164, Sept 2025). Verified via web search
(2026-09-21) that this exact 6-condition factorial design (diagnosis-only /
anonymous-procedure / full-skill / sham / mismatched-diagnosis), applied
specifically to textual procedural skill libraries for agents rather than
few-shot ICL demonstrations, does not appear directly covered -- SkillRouter
(arXiv:2603.22455) and SkillLens (arXiv:2605.08386) are adjacent
(retrieval/routing, not this execution-time decomposition). Defensible
framing if ever written up: "applies the known TR/TL distinction to agent
skill libraries via a causal 6-condition design", not "discovers" the
distinction itself.

Six conditions, same task, same Worker, ground truth via real pytest
(domain/verifier.run_tests), same discipline as every other causal ablation
in this package (substitution_ablation.py, benchmark_self_consistency.py).
Skill content is delivered the SAME way every other code-domain experiment
in this project delivers it -- via a SkillPackage embedded into the prompt
by agents/worker.py::build_prompt, with `system` held fixed at SYSTEM_PROMPT
throughout -- not via the `system` parameter the way the non-Python
skill_evaluation_lab.py does it; the two domains have different established
conventions and this stays consistent with the code domain's own:

  A: baseline -- no skill at all.
  B: diagnosis only -- names the problem class, gives no fix.
  C: anonymous procedure -- the real fix mechanism, but with the
     pattern-identifying label/framing stripped (same substantive content
     as D, minus the classification).
  D: full skill -- the REAL Book procedure_text, unmodified.
  E: correct diagnosis + sham procedure -- a plausible-sounding but
     genuinely wrong/unhelpful procedure, paired with the correct
     diagnosis.
  F: wrong diagnosis + correct procedure -- a DIFFERENT skill's diagnosis
     text, paired with THIS skill's real, correct procedure_text.

RecognitionProceduralSpec.diagnosis/anonymous_procedure/sham_procedure are
hand-authored per pattern, not auto-generated -- same reasoning
substitution_ablation.py already documents for slot_variants/extract_value:
auto-inferring "what counts as the diagnosis-only version of this skill" or
"a plausible sham" for an arbitrary skill is real, harder future work, not
faked here. Condition F requires at least 2 authored patterns to draw a
mismatched diagnosis from -- run_recognition_procedural_probe takes the
second pattern's spec explicitly rather than guessing one."""

from dataclasses import dataclass

from ..adapters.base import ModelAdapter
from ..agents.worker import SYSTEM_PROMPT, build_prompt, extract_code
from ..domain.verifier import run_tests
from ..models import Book, SkillPackage, Task

CONDITIONS = ("A", "B", "C", "D", "E", "F")


@dataclass(frozen=True)
class RecognitionProceduralSpec:
    pattern_id: str
    diagnosis: str
    anonymous_procedure: str
    sham_procedure: str


@dataclass(frozen=True)
class ConditionResult:
    condition: str
    n: int
    passed: int
    accuracy: float


@dataclass(frozen=True)
class RecognitionProceduralResult:
    pattern_id: str
    task_id: str
    conditions: dict[str, ConditionResult]
    recognition_gain: float        # Acc(B) - Acc(A)
    procedural_gain: float         # Acc(D) - Acc(B)
    anonymous_procedural_gain: float  # Acc(C) - Acc(A)
    diagnosis_dependence: float    # Acc(D) - Acc(C)
    teaching_fraction: float | None  # (Acc(D)-Acc(B)) / (Acc(D)-Acc(A)), None if D==A


def _condition_package(
    condition: str, book: Book, spec: RecognitionProceduralSpec, other_spec: RecognitionProceduralSpec,
) -> SkillPackage | None:
    if condition == "A":
        return None
    if condition == "B":
        text = spec.diagnosis
    elif condition == "C":
        text = spec.anonymous_procedure
    elif condition == "D":
        text = book.procedure_text
    elif condition == "E":
        text = f"{spec.diagnosis}\n\n{spec.sham_procedure}"
    elif condition == "F":
        text = f"{other_spec.diagnosis}\n\n{book.procedure_text}"
    else:
        raise ValueError(f"unknown condition {condition!r}")
    fake_book = Book(
        id=f"{book.id}__condition_{condition}", version=book.version, title=f"{book.title} ({condition})",
        domain=book.domain, problem_tags=[], capability_tags=[], resource_tags=[], procedure_text=text,
        pattern_id=book.pattern_id, canonical_problem_id="", status="EXPERIMENTAL", confidence=0,
        verification_count=0, verification_types=[],
    )
    return SkillPackage(books=[fake_book], coverage="FULL")


def run_recognition_procedural_probe(
    task: Task,
    book: Book,
    spec: RecognitionProceduralSpec,
    other_spec: RecognitionProceduralSpec,
    adapter: ModelAdapter,
    reps: int = 3,
) -> RecognitionProceduralResult:
    """One task, all 6 conditions, `reps` independent samples each -- ground
    truth checked with real pytest, never assumed. `other_spec` is a
    DIFFERENT pattern's spec, used only for condition F's mismatched
    diagnosis; its own procedure/sham text is not used here."""
    conditions: dict[str, ConditionResult] = {}
    for condition in CONDITIONS:
        package = _condition_package(condition, book, spec, other_spec)
        prompt = build_prompt(task, package)
        passed = 0
        for _ in range(reps):
            completion = adapter.complete(prompt=prompt, system=SYSTEM_PROMPT, max_tokens=4096)
            code = extract_code(completion.text)
            if run_tests(code, task.test_source).passed:
                passed += 1
        conditions[condition] = ConditionResult(condition, reps, passed, passed / reps if reps else 0.0)

    acc = {c: r.accuracy for c, r in conditions.items()}
    recognition_gain = acc["B"] - acc["A"]
    procedural_gain = acc["D"] - acc["B"]
    anonymous_procedural_gain = acc["C"] - acc["A"]
    diagnosis_dependence = acc["D"] - acc["C"]
    denom = acc["D"] - acc["A"]
    teaching_fraction = (procedural_gain / denom) if abs(denom) > 1e-9 else None
    return RecognitionProceduralResult(
        task.pattern_id, task.task_id, conditions,
        recognition_gain, procedural_gain, anonymous_procedural_gain, diagnosis_dependence, teaching_fraction,
    )
