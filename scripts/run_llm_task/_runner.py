from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from _config import (
    FAILURE_COMMENT,
    MAX_RETRIES,
    REQUEST_DELAY,
    TRUNCATION_MIN_SOURCE_CHARS,
    TRUNCATION_RATIO,
)
from _llm import call_llm

if TYPE_CHECKING:
    import openai

    from _fingerprints import Fingerprint


def run_task(
    fingerprint: Fingerprint,
    files: list[Path],
    *,
    client: openai.OpenAI,
    model: str,
    dry_run: bool,
) -> tuple[list[Path], list[tuple[Path, str]]]:
    """Run a single fingerprint task over *files*."""
    changed: list[Path] = []
    errors: list[tuple[Path, str]] = []

    for index, path in enumerate(files, 1):
        rel = path.relative_to(Path.cwd())
        print(f"  [{index}/{len(files)}] {rel}", end=" … ", flush=True)

        source = path.read_text(encoding="utf-8")
        last_exc = ""
        result: str | None = None

        for attempt in range(MAX_RETRIES + 1):
            if attempt > 0:
                delay = REQUEST_DELAY * (2**attempt)
                print(f"    (retry {attempt}/{MAX_RETRIES}, waiting {delay:.0f} s)", flush=True)
                time.sleep(delay)

            try:
                candidate = call_llm(
                    client,
                    model,
                    fingerprint.system_prompt,
                    source,
                    fingerprint.task_name,
                )

                if (
                    len(source) >= TRUNCATION_MIN_SOURCE_CHARS
                    and len(candidate) < len(source) * TRUNCATION_RATIO
                ):
                    raise RuntimeError(
                        f"Response is {len(candidate)} chars but source is {len(source)} chars "
                        "— likely output truncation. Try a larger output limit or split the file."
                    )

                result = candidate
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = str(exc)

        if result is None:
            print(f"FAILED (annotated): {last_exc}")
            errors.append((path, last_exc))
            if not dry_run:
                comment = f"{FAILURE_COMMENT}: {last_exc}\n"
                existing = path.read_text(encoding="utf-8")
                if not existing.startswith(FAILURE_COMMENT):
                    path.write_text(comment + existing, encoding="utf-8")
            time.sleep(REQUEST_DELAY)
            continue

        if result == source:
            print("unchanged")
        elif dry_run:
            print("would update (dry-run)")
            changed.append(path)
        else:
            path.write_text(result, encoding="utf-8")
            print("updated")
            changed.append(path)

        if index < len(files):
            time.sleep(REQUEST_DELAY)

    return changed, errors
