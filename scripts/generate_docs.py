"""Generate clean GitHub-flavoured markdown docs from NumPy docstrings.

Usage
-----
    python generate_docs.py --src src/ --out docs/

The package name is auto-discovered from the first top-level directory found
under --src that contains an ``__init__.py``.  All sub-modules are discovered
recursively; no hardcoded module list is required.

Writes one .md file per module into --out, mirroring the package structure,
plus an ``index.md`` table.
"""

from __future__ import annotations

import argparse
import re
import sys
import textwrap
from pathlib import Path

try:
    import griffe
    from griffe import DocstringSectionKind, Object
except ImportError:
    sys.exit("griffe not found.  Run: pip install griffe")

# ── RST → Markdown cleanup ───────────────────────────────────────────────────

_RST_ROLES = re.compile(r":(?:meth|func|class|attr|mod|exc):`([^`]+)`")
_DOUBLE_TICKS = re.compile(r"``([^`]+)``")
_EXAMPLE_BLOCK = re.compile(
    r"Example(?:s)?::\n\n((?:[ \t][^\n]*(?:\n|$)|[ \t]*\n)+)",
    re.MULTILINE,
)


def _clean(text: str) -> str:
    """Convert RST markup in docstring prose to GitHub-flavoured Markdown."""
    text = _RST_ROLES.sub(lambda m: f"`{m.group(1)}`", text)
    text = _DOUBLE_TICKS.sub(lambda m: f"`{m.group(1)}`", text)

    def _example_sub(m: re.Match) -> str:
        code = textwrap.dedent(m.group(1)).rstrip()
        return f"**Example**\n\n```python\n{code}\n```"

    text = _EXAMPLE_BLOCK.sub(_example_sub, text)
    return text.strip()


# ── Signature builder ─────────────────────────────────────────────────────────


def _sig(obj: griffe.Function) -> str:
    """Return a compact signature string, skipping ``self``."""
    parts = []
    for p in obj.parameters:
        if p.name == "self":
            continue
        piece = p.name
        if p.annotation is not None:
            piece += f": {p.annotation}"
        if p.default is not None:
            piece += f" = {p.default}"
        parts.append(piece)
    ret = f" → {obj.returns}" if obj.returns else ""
    return f"({', '.join(parts)}){ret}"


# ── Section renderers ─────────────────────────────────────────────────────────


def _params_table(items: list) -> str:
    rows = []
    for p in items:
        desc = _clean(p.description or "").replace("\n", " ")
        rows.append(f"| `{p.name}` | {desc} |")
    return "| Name | Description |\n|---|---|\n" + "\n".join(rows)


def _returns_block(items: list) -> str:
    lines = []
    for r in items:
        annotation = str(r.annotation) if r.annotation else ""
        desc = _clean(r.description or "").replace("\n", " ")
        if annotation:
            lines.append(f"`{annotation}` — {desc}" if desc else f"`{annotation}`")
        else:
            lines.append(desc)
    return "\n".join(lines)


def _raises_table(items: list) -> str:
    rows = []
    for exc in items:
        desc = _clean(exc.description or "").replace("\n", " ")
        exc_type = str(exc.annotation) if exc.annotation else "Exception"
        rows.append(f"| `{exc_type}` | {desc} |")
    return "| Exception | When |\n|---|---|\n" + "\n".join(rows)


# ── Docstring → Markdown ──────────────────────────────────────────────────────


def _render_docstring(obj: Object) -> str:
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


# ── Object renderers ──────────────────────────────────────────────────────────


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
                for s in member.docstring.parse():
                    if s.kind == DocstringSectionKind.text:
                        desc_parts.append(_clean(s.value))
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


# ── Module discovery ─────────────────────────────────────────────────────────


def _discover_package(src: Path) -> str:
    """Return the top-level package name found under *src*.

    Raises
    ------
    SystemExit
        If no package (directory with ``__init__.py``) is found.
    """
    for candidate in sorted(src.iterdir()):
        if candidate.is_dir() and (candidate / "__init__.py").exists():
            return candidate.name
    sys.exit(f"No Python package found under {src}. Expected a directory with __init__.py.")


def _discover_modules(pkg_name: str, src: Path) -> list[str]:
    """Return sorted dotted module paths for every ``*.py`` file in the package."""
    pkg_root = src / pkg_name
    modules: list[str] = []
    for py_file in sorted(pkg_root.rglob("*.py")):
        rel = py_file.relative_to(src)
        # e.g. keygen/fields/enum.py → keygen.fields.enum
        dotted = ".".join(rel.with_suffix("").parts)
        # collapse __init__ → parent package
        if dotted.endswith(".__init__"):
            dotted = dotted[: -len(".__init__")]
        modules.append(dotted)
    # deduplicate while preserving order (package before sub-modules)
    seen: set[str] = set()
    result: list[str] = []
    for m in modules:
        if m not in seen:
            seen.add(m)
            result.append(m)
    return result


# ── Index ─────────────────────────────────────────────────────────────────────


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
        names = ", ".join(f"`{n}`" for n in _public_names(mod))
        slug = mod_name.replace(".", "/")
        rows.append(f"| [{mod_name}]({slug}.md) | {names} | {summary} |")

    table = "| Module | Public API | Description |\n|---|---|---|\n" + "\n".join(rows)
    return f"# API Reference\n\n{table}\n"


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--src",
        default="src/",
        help="Source root that contains the package directory (default: src/).",
    )
    parser.add_argument(
        "--out",
        default="docs/",
        help="Output directory for generated Markdown files (default: docs/).",
    )
    parser.add_argument(
        "--package",
        default=None,
        metavar="NAME",
        help="Package name to document.  Auto-discovered from --src when omitted.",
    )
    args = parser.parse_args()

    src = Path(args.src)
    out = Path(args.out)

    pkg_name = args.package or _discover_package(src)
    modules = _discover_modules(pkg_name, src)

    print(f"Package : {pkg_name}")
    print(f"Modules : {len(modules)}")
    print(f"Output  : {out}")
    print()

    pkg = griffe.load(pkg_name, search_paths=[str(src)])
    out.mkdir(exist_ok=True)

    for mod_name in modules:
        if "." in mod_name:
            sub = mod_name[len(pkg_name) + 1:]
            mod = pkg[sub]
        else:
            mod = pkg

        slug = mod_name.replace(".", "/")
        out_path = out / f"{slug}.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(_render_module(mod) + "\n", encoding="utf-8")
        print(f"  wrote {out_path}")

    index_path = out / "index.md"
    index_path.write_text(_render_index(pkg, pkg_name, modules), encoding="utf-8")
    print(f"  wrote {index_path}")
    print("\nDone.")


if __name__ == "__main__":
    main()
