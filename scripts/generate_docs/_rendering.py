from __future__ import annotations

import griffe
from griffe import DocstringSectionKind

from _cleanup import _clean
from _docstrings import _render_docstring
from _signatures import _sig


def _is_private(name: str) -> bool:
    return name.startswith("_")


def _render_function(fn: griffe.Function, level: int = 3) -> str:
    hashes = "#" * level
    header = f"{hashes} `{fn.name}{_sig(fn)}`"
    body = _render_docstring(fn)
    return f"{header}\n\n{body}" if body else header


def _render_class(cls: griffe.Class) -> str:
    out: list[str] = [f"## `{cls.name}`"]

    body = _render_docstring(cls)
    if body:
        out.append(body)

    for name, member in cls.members.items():
        if _is_private(name):
            continue
        if isinstance(member, griffe.Attribute) and "property" in member.labels:
            if member.docstring:
                member.docstring.parser = "numpy"
                desc_parts = []
                for section in member.docstring.parse():
                    if section.kind == DocstringSectionKind.text:
                        desc_parts.append(_clean(section.value))
                desc = " ".join(desc_parts).replace("\n", " ")
                out.append(f"### `{name}`\n\n{desc}")

    for name, member in cls.members.items():
        if _is_private(name):
            continue
        if isinstance(member, griffe.Function):
            out.append("---")
            out.append(_render_function(member, level=3))

    return "\n\n".join(out)


def _render_module(mod: griffe.Module) -> str:
    out: list[str] = []

    if mod.docstring:
        mod.docstring.parser = "numpy"
        for section in mod.docstring.parse():
            if section.kind == DocstringSectionKind.text:
                first_line = section.value.strip().splitlines()[0]
                out.append(f"> {_clean(first_line)}")
                break

    for name, member in mod.members.items():
        if _is_private(name):
            continue
        if isinstance(member, griffe.Class):
            out.append("---")
            out.append(_render_class(member))
        elif isinstance(member, griffe.Function):
            out.append("---")
            out.append(_render_function(member, level=2))

    return "\n\n".join(out)
