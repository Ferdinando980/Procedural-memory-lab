import re

from ..adapters.base import CompletionResult, ModelAdapter
from ..models import SkillPackage, Task

SYSTEM_PROMPT = (
    "You are a Python debugging specialist. You will be given a single buggy "
    "Python function. Return ONLY the corrected function definition, as a single "
    "Python code block. Do not include the test suite, explanations, or any text "
    "outside the code block. Keep the function name and signature identical to "
    "the input unless the signature itself is the bug."
)

# 1024 silently truncated reasoning-model output: extended-thinking models (e.g.
# gemini-3.6-flash) spend hundreds of tokens on internal reasoning before writing
# the actual function, so a low cap cut the code off mid-answer and failed
# verification on a formatting artifact, not a real capability gap. 4096 leaves
# comfortable headroom after even ~1000 reasoning tokens.
MAX_OUTPUT_TOKENS = 4096

_CODE_FENCE_RE = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL)


def extract_code(text: str) -> str:
    match = _CODE_FENCE_RE.search(text)
    code = (match.group(1) if match else text).strip()
    # Local models occasionally emit an additional fence-only line after an
    # otherwise valid fenced answer (observed in 5/8 historical FPE failures).
    # A presentation marker is not Python and is safe to remove mechanically;
    # never spend a Detective/Worker recovery call on this formatting residue.
    code = "\n".join(line for line in code.splitlines() if line.strip() != "```").strip()
    return code + "\n"


def build_prompt(task: Task, skill_package: SkillPackage | None = None) -> str:
    context = ""
    if skill_package and skill_package.books:
        context = (
            "You have access to the following relevant debugging notes. Use them "
            "if they apply; ignore them if they don't.\n\n"
            f"{skill_package.as_prompt_context()}\n\n"
        )

    return (
        f"{context}"
        f"Buggy function (problem: {task.problem_id}):\n\n"
        f"```python\n{task.buggy_source}\n```\n\n"
        "Return the corrected function."
    )


def build_recovery_prompt(
    task: Task,
    failed_source: str,
    verifier_feedback: str,
    skill_package: SkillPackage | None = None,
    detective_hint: str | None = None,
) -> str:
    """Build a second-attempt prompt grounded in an objective failed test.

    The original task and retrieved notes stay unchanged.  The failed attempt
    and verifier output are data, not instructions; explicit delimiters keep
    their roles clear for small local models.
    """
    base = build_prompt(task, skill_package).removesuffix("Return the corrected function.")
    hint = f"\nDetective findings:\n{detective_hint}\n" if detective_hint else ""
    return (
        f"{base}"
        "A previous correction failed the executable verifier. Repair that attempt using "
        "the concrete feedback below. The verifier failure is the primary constraint: the new "
        "function must directly eliminate every shown exception or failed assertion. Never return "
        "the previous correction unchanged. Preserve behavior that is not implicated by the "
        "failure and do not broaden the change speculatively.\n\n"
        f"Previous correction:\n```python\n{failed_source.strip()}\n```\n\n"
        f"Verifier feedback:\n```text\n{verifier_feedback.strip()}\n```\n"
        f"{hint}\n"
        "Return the corrected function."
    )


def solve(task: Task, adapter: ModelAdapter, skill_package: SkillPackage | None = None) -> tuple[str, CompletionResult]:
    prompt = build_prompt(task, skill_package)
    result = adapter.complete(prompt=prompt, system=SYSTEM_PROMPT, max_tokens=MAX_OUTPUT_TOKENS)
    return extract_code(result.text), result
