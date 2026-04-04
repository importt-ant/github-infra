"""Generate clean GitHub-flavoured markdown docs from NumPy docstrings.

Usage
-----
    python scripts/generate_docs/generate_docs.py --src src/ --out docs/

The package name is auto-discovered from the first top-level directory found
under --src that contains an ``__init__.py``. All sub-modules are discovered
recursively; no hardcoded module list is required.

Writes one .md file per module into --out, mirroring the package structure,
plus an ``index.md`` table.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import griffe
except ImportError:
    sys.exit("griffe not found. Run: pip install griffe")

from _discovery import _discover_modules, _discover_package
from _indexing import _render_index
from _rendering import _render_module


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
        help="Package name to document. Auto-discovered from --src when omitted.",
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
