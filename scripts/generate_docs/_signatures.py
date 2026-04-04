from __future__ import annotations

import griffe


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
