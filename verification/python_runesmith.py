"""Bounded Python AST candidate tool used by the existing Worker.

It enumerates local transformations without predicting which bug exists.
The existing executable Verifier is the only selector.
"""

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class RuneCandidate:
    source: str
    transformation: str


def _render(tree: ast.AST) -> str:
    ast.fix_missing_locations(tree)
    return ast.unparse(tree).strip() + "\n"


def enumerate_local_transformations(source: str) -> list[RuneCandidate]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Presentation fences are not program semantics. Strip fence-only
        # lines once; any genuinely malformed program still routes safely to
        # the generative Worker instead of crashing the recovery search.
        source = "\n".join(line for line in source.splitlines() if not line.strip().startswith("```"))
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
    candidates: list[RuneCandidate] = []

    comparison_ops = [ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq]
    comparisons = [node for node in ast.walk(tree) if isinstance(node, ast.Compare)]
    for index, node in enumerate(comparisons):
        if len(node.ops) != 1:
            continue
        original = type(node.ops[0])
        for replacement in comparison_ops:
            if replacement is original:
                continue
            clone = ast.parse(source)
            target = [n for n in ast.walk(clone) if isinstance(n, ast.Compare)][index]
            target.ops[0] = replacement()
            candidates.append(RuneCandidate(_render(clone), f"comparison:{original.__name__}->{replacement.__name__}"))

    returns = [node for node in ast.walk(tree) if isinstance(node, ast.Return) and node.value is not None]
    for index, _ in enumerate(returns):
        clone = ast.parse(source)
        target = [n for n in ast.walk(clone) if isinstance(n, ast.Return) and n.value is not None][index]
        target.value = ast.UnaryOp(op=ast.Not(), operand=target.value)
        candidates.append(RuneCandidate(_render(clone), "return:negate"))

    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and not node.args and not node.keywords
    ]
    for index, call in enumerate(calls):
        clone = ast.parse(source)
        target = [
            n for n in ast.walk(clone)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and not n.args and not n.keywords
        ][index]
        replacement = target.func.value
        for parent in ast.walk(clone):
            for field, value in ast.iter_fields(parent):
                if value is target:
                    setattr(parent, field, replacement)
                elif isinstance(value, list):
                    for offset, child in enumerate(value):
                        if child is target:
                            value[offset] = replacement
        candidates.append(RuneCandidate(_render(clone), f"call:elide:{call.func.attr}"))

    subscripts = [node for node in ast.walk(tree) if isinstance(node, ast.Subscript)]
    for index, _ in enumerate(subscripts):
        clone = ast.parse(source)
        target = [n for n in ast.walk(clone) if isinstance(n, ast.Subscript)][index]
        replacement = target.value
        for parent in ast.walk(clone):
            for field, value in ast.iter_fields(parent):
                if value is target:
                    setattr(parent, field, replacement)
                elif isinstance(value, list):
                    for offset, child in enumerate(value):
                        if child is target:
                            value[offset] = replacement
        candidates.append(RuneCandidate(_render(clone), "subscript:elide"))

    loops = [node for node in ast.walk(tree) if isinstance(node, (ast.For, ast.comprehension))]
    for index, _ in enumerate(loops):
        clone = ast.parse(source)
        target = [n for n in ast.walk(clone) if isinstance(n, (ast.For, ast.comprehension))][index]
        target.iter = ast.Call(func=ast.Name(id="reversed", ctx=ast.Load()), args=[target.iter], keywords=[])
        candidates.append(RuneCandidate(_render(clone), "iteration:reverse"))

    numeric_assignments = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and isinstance(node.value, (ast.BinOp, ast.UnaryOp, ast.IfExp))
    ]
    for index, _ in enumerate(numeric_assignments):
        for value in (1e-9, 1e-6, 1e-3, 1e-2, 1e-1, 1.0):
            clone = ast.parse(source)
            target = [
                n for n in ast.walk(clone)
                if isinstance(n, (ast.Assign, ast.AnnAssign))
                and isinstance(n.value, (ast.BinOp, ast.UnaryOp, ast.IfExp))
            ][index]
            target.value = ast.Constant(value)
            candidates.append(RuneCandidate(_render(clone), f"numeric_assignment:{value:g}"))

    functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for function_index, function in enumerate(functions):
        positional = function.args.args[-len(function.args.defaults):] if function.args.defaults else []
        for default_index, (argument, default) in enumerate(zip(positional, function.args.defaults)):
            constructors = {ast.List: "[]", ast.Set: "set()", ast.Dict: "{}"}
            constructor = next((text for kind, text in constructors.items() if isinstance(default, kind)), None)
            if (
                constructor is None and isinstance(default, ast.Call)
                and isinstance(default.func, ast.Name) and default.func.id in {"list", "set", "dict"}
                and not default.args and not default.keywords
            ):
                constructor = {"list": "[]", "set": "set()", "dict": "{}"}[default.func.id]
            if constructor is None:
                continue
            clone = ast.parse(source)
            target_function = [n for n in ast.walk(clone) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))][function_index]
            target_function.args.defaults[default_index] = ast.Constant(None)
            guard = ast.parse(f"if {argument.arg} is None:\n    {argument.arg} = {constructor}").body[0]
            target_function.body.insert(0, guard)
            candidates.append(RuneCandidate(_render(clone), f"default:fresh:{argument.arg}"))

    unique = {}
    for candidate in candidates:
        if candidate.source != source:
            unique.setdefault(candidate.source, candidate)
    return list(unique.values())
