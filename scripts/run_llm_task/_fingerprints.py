from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_KV = re.compile(r"^(\w+)\s*:\s*(.+)$")
_LIST_ITEM = re.compile(r"^\s*-\s*(.+)$")


@dataclass
class Fingerprint:
    """Parsed representation of a fingerprint Markdown file."""

    path: Path
    task_name: str
    file_patterns: list[str]
    system_prompt: str


def _parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Split YAML front-matter from body; return metadata and prompt body."""
    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text

    body = text[match.end():]
    meta: dict[str, object] = {}
    current_list_key: str | None = None

    for line in match.group(1).splitlines():
        list_match = _LIST_ITEM.match(line)
        if list_match and current_list_key:
            cast = meta.setdefault(current_list_key, [])
            cast.append(list_match.group(1).strip('"').strip("'"))  # type: ignore[union-attr]
            continue

        kv = _KV.match(line)
        if kv:
            key, val = kv.group(1), kv.group(2).strip().strip('"').strip("'")
            if val == "":
                meta[key] = []
                current_list_key = key
            else:
                meta[key] = val
                current_list_key = None
        else:
            current_list_key = None

    return meta, body


def load_fingerprint(path: Path) -> Fingerprint:
    """Parse *path* and return a fingerprint definition."""
    if not path.is_file():
        sys.exit(f"Fingerprint not found: {path}")

    text = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)

    task_name = str(meta.get("task_name", path.stem))
    patterns = meta.get("file_patterns", ["*.py"])
    if isinstance(patterns, str):
        patterns = [patterns]

    return Fingerprint(
        path=path,
        task_name=task_name,
        file_patterns=list(patterns),
        system_prompt=body.strip(),
    )
