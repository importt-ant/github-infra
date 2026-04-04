from __future__ import annotations

import griffe
from griffe import DocstringSectionKind

from _cleanup import _clean
from _rendering import _is_private


def _module_summary(mod: griffe.Module) -> str:
    if mod.docstring is None:
        return ""
    mod.docstring.parser = "numpy"
    for section in mod.docstring.parse():
        if section.kind == DocstringSectionKind.text:
            return _clean(section.value.strip().splitlines()[0])
    return ""


def _public_names(mod: griffe.Module) -> list[str]:
    return [
        name
        for name, member in mod.members.items()
        if not _is_private(name) and isinstance(member, (griffe.Class, griffe.Function))
    ]


def _render_index(pkg: griffe.Package, pkg_name: str, modules: list[str]) -> str:
    top_level = [m for m in modules if m.count(".") <= 1]
    rows = []
    for mod_name in top_level:
        if "." in mod_name:
            sub = mod_name[len(pkg_name) + 1:]
            mod = pkg[sub]
        else:
            mod = pkg
        summary = _module_summary(mod)
        names = ", ".join(f"`{name}`" for name in _public_names(mod))
        slug = mod_name.replace(".", "/")
        rows.append(f"| [{mod_name}]({slug}.md) | {names} | {summary} |")

    table = "| Module | Public API | Description |\n|---|---|---|\n" + "\n".join(rows)
    return f"# API Reference\n\n{table}\n"
