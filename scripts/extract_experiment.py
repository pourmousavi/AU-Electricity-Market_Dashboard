"""AST helpers for the one-off split of the bundled dashboards.

Given a block of statements to become an experiment's render() body, work out
which top-level functions, classes and constants it transitively needs, and
emit a standalone module. Code is copied verbatim via ast.unparse of the
original nodes -- no reformatting, no rewriting.
"""
from __future__ import annotations

import ast
import textwrap


def _names_used(nodes: list[ast.stmt]) -> set[str]:
    used = set()
    for node in nodes:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name):
                used.add(sub.id)
            elif isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name):
                used.add(sub.value.id)
    return used


def _definitions(tree: ast.Module) -> dict[str, ast.stmt]:
    """Top-level defs, classes and simple constant assignments, by name."""
    out: dict[str, ast.stmt] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node
    return out


def closure(tree: ast.Module, roots: list[ast.stmt]) -> list[ast.stmt]:
    """Every top-level definition reachable from `roots`, in source order."""
    defined = _definitions(tree)
    needed: set[str] = set()
    frontier = _names_used(roots)

    while frontier:
        name = frontier.pop()
        if name in needed or name not in defined:
            continue
        needed.add(name)
        frontier |= _names_used([defined[name]])

    root_ids = {id(node) for node in roots}
    picked, seen = [], set()
    for node in tree.body:
        if id(node) in root_ids or id(node) in seen:
            continue
        for name in needed:
            if defined.get(name) is node:
                picked.append(node)
                seen.add(id(node))
                break
    return picked


def imports(tree: ast.Module) -> list[ast.stmt]:
    """All module-level imports, kept wholesale.

    Deliberately not pruned to what is used: a missing import is a crash, an
    extra one is a lint note. Prune by hand later if it matters.
    """
    return [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]


def session_state_guards(tree: ast.Module) -> list[ast.stmt]:
    """Module-level `if 'key' not in st.session_state:` initialisation blocks.

    These run before anything else in the original module, so they go at the
    top of render(). They are idempotent, so all of them are carried.
    """
    out = []
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if (isinstance(test, ast.Compare)
                and isinstance(test.ops[0], ast.NotIn)
                and "session_state" in ast.unparse(test.comparators[0])):
            out.append(node)
    return out


def build_module(source: str, body: list[ast.stmt], roots: list[ast.stmt],
                 docstring: str, extra_head: str = "") -> str:
    """Render the text of a standalone experiment module."""
    tree = ast.parse(source)
    parts = [f'"""{docstring}"""', ""]
    parts += [ast.unparse(node) for node in imports(tree)]
    if extra_head:
        parts += ["", extra_head]
    parts.append("")
    for node in closure(tree, roots):
        parts += [ast.unparse(node), ""]

    guards = session_state_guards(tree)
    lines = [ast.unparse(node) for node in guards + body] or ["pass"]
    parts += ["def render() -> None:",
              textwrap.indent("\n".join(lines), "    "), ""]
    return "\n".join(parts)
