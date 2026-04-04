from __future__ import annotations

import re
import textwrap

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
