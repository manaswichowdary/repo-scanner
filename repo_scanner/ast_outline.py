"""Turn a Python file into an outline of its classes and functions."""

from __future__ import annotations

import ast


def _args(node: ast.AST) -> str:
    a = node.args
    names = [x.arg for x in a.posonlyargs + a.args]
    if a.vararg:
        names.append("*" + a.vararg.arg)
    names += [x.arg for x in a.kwonlyargs]
    if a.kwarg:
        names.append("**" + a.kwarg.arg)
    return ", ".join(n for n in names if n not in ("self", "cls"))


def _doc(node: ast.AST) -> str:
    text = ast.get_docstring(node) or ""
    return text.strip().splitlines()[0][:100] if text.strip() else ""


def outline_python(source: str) -> str | None:
    """Return an outline, or None when the file does not parse."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    lines: list[str] = []
    doc = _doc(tree)
    if doc:
        lines.append(f"module: {doc}")
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases = ", ".join(ast.unparse(b) for b in node.bases)
            head = f"class {node.name}" + (f"({bases})" if bases else "")
            d = _doc(node)
            lines.append(head + (f"  # {d}" if d else ""))
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    lines.append(f"  def {item.name}({_args(item)})")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            d = _doc(node)
            prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            lines.append(f"{prefix} {node.name}({_args(node)})" + (f"  # {d}" if d else ""))
    return "\n".join(lines)
