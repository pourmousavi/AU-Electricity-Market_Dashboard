"""In-memory AST surgery that isolates one tab of a vendored dashboard.

The vendored source on disk is never modified. We parse it, replace the body of
every `with tabN:` block that is not the selected one with `pass`, and hand the
transformed tree back to the runner. Unselected tabs therefore never execute —
no wasted solver time, and disabled content is never computed.

This is deliberately strict: if a source file stops matching the expected
`tab1, tab2 = st.tabs([...])` / `with tabN:` shape, we raise instead of quietly
rendering the wrong thing.
"""
from __future__ import annotations

import ast


class TabSurgeryError(Exception):
    """The source does not match the tab pattern we can transform."""


def _find_tabs_assignment(tree: ast.Module) -> ast.Assign:
    assigns = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "tabs"
    ]
    if len(assigns) != 1:
        raise TabSurgeryError(
            f"expected exactly one `... = st.tabs([...])` assignment, found {len(assigns)}"
        )
    return assigns[0]


def _find_enclosing_body(tree: ast.Module, target: ast.stmt) -> list[ast.stmt]:
    """Return the statement list that directly contains `target`.

    This confines later matching to the same scope as the `st.tabs(...)`
    assignment (module level for Week 6, inside `main()` for Weeks 7/8)
    rather than walking the whole tree, so an unrelated `with`-block in a
    nested scope that happens to reuse a tab variable's name is never
    touched.
    """
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            body = getattr(node, field, None)
            if isinstance(body, list) and any(stmt is target for stmt in body):
                return body
    raise TabSurgeryError("could not locate the scope containing the st.tabs(...) assignment")


def select_tab(source: str, selector: str) -> tuple[ast.Module, int]:
    """Blank every tab body except the one labelled `selector`.

    Returns the transformed tree and the selected tab's zero-based index.
    """
    tree = ast.parse(source)
    assign = _find_tabs_assignment(tree)

    target = assign.targets[0]
    if not isinstance(target, ast.Tuple):
        raise TabSurgeryError("st.tabs result is not unpacked into a tuple of names")
    if not all(isinstance(el, ast.Name) for el in target.elts):
        raise TabSurgeryError("st.tabs targets are not all plain names")
    names = [el.id for el in target.elts]

    if not assign.value.args:
        raise TabSurgeryError("st.tabs called without a label list")
    label_node = assign.value.args[0]
    if not isinstance(label_node, ast.List):
        raise TabSurgeryError("st.tabs labels are not a literal list")
    if not all(isinstance(el, ast.Constant) and isinstance(el.value, str)
               for el in label_node.elts):
        raise TabSurgeryError("st.tabs labels are not all literal strings")
    labels = [el.value for el in label_node.elts]

    if len(names) != len(labels):
        raise TabSurgeryError(
            f"{len(names)} tab variables but {len(labels)} labels"
        )
    if selector not in labels:
        raise TabSurgeryError(f"no tab labelled {selector!r}; available: {labels}")

    index = labels.index(selector)
    keep = names[index]

    scope_body = _find_enclosing_body(tree, assign)

    for node in scope_body:
        if not isinstance(node, ast.With):
            continue
        tab_items = [
            item for item in node.items
            if isinstance(item.context_expr, ast.Name) and item.context_expr.id in names
        ]
        if not tab_items:
            continue
        if len(node.items) != 1:
            bad_name = tab_items[0].context_expr.id
            raise TabSurgeryError(
                f"tab variable {bad_name!r} is combined with another context "
                "manager in a single `with` statement, which is not supported"
            )
        name = tab_items[0].context_expr.id
        if name != keep:
            node.body = [ast.Pass()]

    ast.fix_missing_locations(tree)
    return tree, index
