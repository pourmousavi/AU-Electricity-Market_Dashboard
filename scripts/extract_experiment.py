"""AST helpers for the one-off split of the bundled dashboards.

Given a block of statements to become an experiment's render() body, work out
which top-level functions, classes and constants it transitively needs, and
emit a standalone module. `ast` only decides which statements to emit and
where each one starts and ends -- it never writes the output text. Every
statement is copied out of the original source's exact lines instead. These
are teaching scripts; comments and original formatting carry real
information, and `ast.unparse` would silently discard them.
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


def _bind(target: ast.expr, node: ast.stmt, out: dict[str, ast.stmt]) -> None:
    """Record every name a single assignment target binds, pointing at `node`.

    Handles plain `Name` targets and tuple/list-unpacking targets
    (`A, B = 1, 2`). Anything else -- `obj.attr = ...`, subscript targets,
    starred targets -- can't be indexed by name, and rather than silently
    dropping it (leaving a later lookup to fail mysteriously) this raises,
    so an unhandled shape is a loud crash here instead of a missing constant
    three files downstream.
    """
    if isinstance(target, ast.Name):
        out[target.id] = node
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            _bind(elt, node, out)
    else:
        raise ValueError(
            f"Cannot index assignment target {ast.dump(target)} at line "
            f"{node.lineno}; extend _bind() in scripts/extract_experiment.py "
            "to handle it."
        )


def _definitions(tree: ast.Module) -> dict[str, ast.stmt]:
    """Top-level defs, classes and constant assignments, by name.

    Covers plain `Name` targets, `AnnAssign` with a `Name` target (`B: dict =
    ...`), and tuple/list-unpacking `Assign` targets (`A, B = 1, 2`).
    """
    out: dict[str, ast.stmt] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                _bind(target, node, out)
        elif isinstance(node, ast.AnnAssign):
            _bind(node.target, node, out)
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

    Limitation: this only matches bare module-level `if` guards. It returns
    `[]` for sources/week7_ed_viu.py and sources/week8_pf_auction.py, which
    centralise their session-state setup inside a function
    (`initialize_session_state()`) instead of writing the guards directly at
    module level. That's fine for how this plan uses the function -- weeks 7
    and 8 build their render() preamble by hand in their own extraction
    tasks -- but do not assume an empty result from this function means a
    source has no session-state initialisation to carry.
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


def _segment(lines: list[str], start_line: int, end_line: int) -> str:
    """Exact source text for the 1-indexed, inclusive line range."""
    return "\n".join(lines[start_line - 1:end_line])


def _source_text(lines: list[str], node: ast.stmt) -> str:
    """A node's exact source text, plus any contiguous `#` comment block
    immediately above it.

    Walks back from the line above `node`'s first line while each line,
    stripped, starts with `#`; the block (if any) is included verbatim.
    Interior comments and blank lines inside the node's own span are already
    part of the slice, since this copies raw source lines rather than
    regenerating code from the tree.
    """
    start = node.lineno
    while start > 1 and lines[start - 2].strip().startswith("#"):
        start -= 1
    return _segment(lines, start, node.end_lineno)


def build_module(source: str, body: list[ast.stmt], roots: list[ast.stmt],
                 docstring: str, extra_head: str = "") -> str:
    """Render the text of a standalone experiment module.

    `ast` decides which statements to emit and where each one starts and
    ends; every statement is then copied verbatim out of `source`'s text
    (never regenerated with `ast.unparse`), so comments and formatting
    survive untouched.
    """
    tree = ast.parse(source)
    lines = source.splitlines()
    parts = [f'"""{docstring}"""', ""]
    parts += [_segment(lines, node.lineno, node.end_lineno) for node in imports(tree)]
    if extra_head:
        parts += ["", extra_head]
    parts.append("")
    for node in closure(tree, roots):
        parts += [_source_text(lines, node), ""]

    blocks = [_source_text(lines, node) for node in session_state_guards(tree)]
    if body:
        body_text = _segment(lines, body[0].lineno, body[-1].end_lineno)
        blocks.append(textwrap.dedent(body_text))
    render_body = "\n\n".join(blocks) if blocks else "pass"
    parts += ["def render() -> None:",
              textwrap.indent(render_body, "    "), ""]
    return "\n".join(parts)
