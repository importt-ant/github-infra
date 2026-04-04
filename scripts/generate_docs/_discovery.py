from __future__ import annotations

import sys
from pathlib import Path


def _discover_package(src: Path) -> str:
    """Return the top-level package name found under *src*."""
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
        dotted = ".".join(rel.with_suffix("").parts)
        if dotted.endswith(".__init__"):
            dotted = dotted[: -len(".__init__")]
        modules.append(dotted)

    seen: set[str] = set()
    result: list[str] = []
    for module in modules:
        if module not in seen:
            seen.add(module)
            result.append(module)
    return result
