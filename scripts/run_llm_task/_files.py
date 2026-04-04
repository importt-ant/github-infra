from __future__ import annotations

import fnmatch
import subprocess
import sys
from pathlib import Path


def _matches(path: Path, patterns: list[str]) -> bool:
    """Return True if *path*'s filename matches any of *patterns*."""
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in patterns)


def collect_all_files(src: Path, patterns: list[str]) -> list[Path]:
    """Return all files under *src* matching *patterns*."""
    return sorted(path for path in src.rglob("*") if path.is_file() and _matches(path, patterns))


def collect_changed_files(src: Path, patterns: list[str], base: str) -> list[Path]:
    """Return files under *src* that differ from *base* and match *patterns*."""
    repo_root = Path.cwd()
    try:
        result = subprocess.run(
            [
                "git",
                "diff",
                "--name-only",
                "--diff-filter=ACMR",
                f"{base}...HEAD",
                "--",
                str(src.relative_to(repo_root)) if src.is_relative_to(repo_root) else str(src),
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_root,
        )
    except subprocess.CalledProcessError as exc:
        sys.exit(f"git diff failed (is '{base}' a valid ref?):\n{exc.stderr.strip()}")

    paths: list[Path] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        path = repo_root / line
        if path.is_file() and _matches(path, patterns):
            paths.append(path)

    return sorted(paths)
