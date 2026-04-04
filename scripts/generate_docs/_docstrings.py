from __future__ import annotations

from typing import Any

from griffe import DocstringSectionKind, Object

from _cleanup import _clean


def _params_table(items: list[Any]) -> str:
    rows = []
    for p in items:
        desc = _clean(p.description or "").replace("\n", " ")
        rows.append(f"| `{p.name}` | {desc} |")
    return "| Name | Description |\n|---|---|\n" + "\n".join(rows)


def _returns_block(items: list[Any]) -> str:
    lines = []
    for r in items:
        annotation = str(r.annotation) if r.annotation else ""
        desc = _clean(r.description or "").replace("\n", " ")
        if annotation:
            lines.append(f"`{annotation}` — {desc}" if desc else f"`{annotation}`")
        else:
            lines.append(desc)
    return "\n".join(lines)


def _raises_table(items: list[Any]) -> str:
    rows = []
    for exc in items:
        desc = _clean(exc.description or "").replace("\n", " ")
        exc_type = str(exc.annotation) if exc.annotation else "Exception"
        rows.append(f"| `{exc_type}` | {desc} |")
    return "| Exception | When |\n|---|---|\n" + "\n".join(rows)


def _render_docstring(obj: Object) -> str:
    """Render a docstring object as GitHub-flavoured Markdown."""
    if obj.docstring is None:
        return ""

    obj.docstring.parser = "numpy"
    sections = obj.docstring.parse()
    out: list[str] = []

    for section in sections:
        kind = section.kind
        value = section.value

        if kind == DocstringSectionKind.text:
            out.append(_clean(value))
        elif kind == DocstringSectionKind.parameters:
            out.append(f"**Parameters**\n\n{_params_table(value)}")
        elif kind == DocstringSectionKind.returns:
            rendered = _returns_block(value)
            if rendered:
                out.append(f"**Returns**\n\n{rendered}")
        elif kind == DocstringSectionKind.raises:
            out.append(f"**Raises**\n\n{_raises_table(value)}")
        elif kind == DocstringSectionKind.examples:
            out.append(f"**Example**\n\n```python\n{value.rstrip()}\n```")

    return "\n\n".join(out)
