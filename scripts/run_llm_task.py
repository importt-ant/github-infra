"""Run one or more LLM tasks over a project's source files via the GitHub Models API.

Each task is defined by a *fingerprint* — a Markdown file with a YAML front-matter
header that specifies the task name and which files to process, followed by the
system prompt that the LLM receives.

The script is designed to be called from GitHub Actions after checking out the
github-infra repo alongside the target project:

    python .infra/scripts/run_llm_task.py \\
        --fingerprint .infra/fingerprints/docstrings-numpy.md \\
        --fingerprint .infra/fingerprints/comments.md \\
        --src src/ \\
        --changed-only \\
        --base origin/main

Multiple ``--fingerprint`` flags run each task sequentially; files are
re-read before every pass so the output of task N feeds task N+1.

─── Fingerprint file format ──────────────────────────────────────────────────

    ---
    task_name: "Update NumPy docstrings"
    file_patterns:
      - "*.py"
    ---
    You are a Python documentation expert ...
    [rest of system prompt]

``file_patterns`` uses ``fnmatch`` globs applied to filenames (not full paths).
List multiple patterns to match several file types.

─── Environment ──────────────────────────────────────────────────────────────

GITHUB_TOKEN
    Required.  A GitHub PAT or the Actions-injected ``secrets.GITHUB_TOKEN``.
    Must have the ``models:read`` permission for GitHub Models free tier access.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

try:
    import openai
except ImportError:
    sys.exit("openai package not found.  Run: pip install openai")

# ── Configuration ─────────────────────────────────────────────────────────────

GITHUB_MODELS_URL = "https://models.inference.ai.azure.com"
DEFAULT_MODEL = "gpt-4o-mini"

# Low-tier models (gpt-4o-mini, Phi-4, Llama, etc.) allow 15 req/min on the
# free plan → one request every 4 seconds minimum.
REQUEST_DELAY = 4.0

# If the LLM returns a file substantially shorter than the original it likely
# truncated the output (free tier caps at 4 000 output tokens).  Abort the
# write rather than silently corrupt the file.
TRUNCATION_RATIO = 0.75

# Number of additional attempts after the first failure (delay doubles each time).
MAX_RETRIES = 2

# Comment written at the top of any file that could not be processed after all
# retries, so it can be found easily with grep.
FAILURE_COMMENT = "# LLM-REVIEW-FAILED"

# ── Fingerprint loading ───────────────────────────────────────────────────────

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
    """Split YAML front-matter from body; return (meta dict, body string)."""
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
    """Parse *path* and return a :class:`Fingerprint`.

    Parameters
    ----------
    path:
        Absolute or relative path to a ``*.md`` fingerprint file.

    Returns
    -------
    Fingerprint
        Parsed task definition ready for use by the runner.

    Raises
    ------
    SystemExit
        If the file is missing or malformed.
    """
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


# ── File collection ───────────────────────────────────────────────────────────


def _matches(path: Path, patterns: list[str]) -> bool:
    """Return True if *path*'s filename matches any of *patterns*."""
    return any(fnmatch.fnmatch(path.name, p) for p in patterns)


def collect_all_files(src: Path, patterns: list[str]) -> list[Path]:
    """Return all files under *src* matching *patterns*."""
    return sorted(p for p in src.rglob("*") if p.is_file() and _matches(p, patterns))


def collect_changed_files(src: Path, patterns: list[str], base: str) -> list[Path]:
    """Return files under *src* that differ from *base* and match *patterns*.

    Uses ``git diff --name-only --diff-filter=ACMR <base>...HEAD`` so the
    result mirrors exactly what a pull-request diff shows.

    Parameters
    ----------
    src:
        Root directory to restrict results to.
    patterns:
        Filename glob patterns to filter by.
    base:
        Git ref to diff against, e.g. ``"origin/main"``.

    Returns
    -------
    list[Path]
        Sorted list of matching changed files that exist on disk.
    """
    repo_root = Path.cwd()
    try:
        result = subprocess.run(
            [
                "git", "diff",
                "--name-only",
                "--diff-filter=ACMR",
                f"{base}...HEAD",
                "--",
                str(src.relative_to(repo_root)) if src.is_relative_to(repo_root) else str(src),
            ],
            capture_output=True, text=True, check=True, cwd=repo_root,
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


# ── LLM helpers ───────────────────────────────────────────────────────────────


def _build_client(token: str) -> openai.OpenAI:
    return openai.OpenAI(base_url=GITHUB_MODELS_URL, api_key=token)


def _call_llm(
    client: openai.OpenAI,
    model: str,
    system_prompt: str,
    source: str,
    task_name: str,
) -> str:
    """Send *source* to the model with *system_prompt* and return the result.

    Parameters
    ----------
    client:
        Configured OpenAI client pointed at the GitHub Models endpoint.
    model:
        Model identifier, e.g. ``"gpt-4o-mini"``.
    system_prompt:
        Full system prompt from the fingerprint file.
    source:
        Complete source file contents to process.
    task_name:
        Human-readable task name used in the user message.

    Returns
    -------
    str
        The (possibly unchanged) file contents returned by the model.
    """
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Apply the task '{task_name}' to the following source file. "
                    "Return the complete file and nothing else — no code fences, "
                    "no commentary before or after.\n\n"
                    f"{source}"
                ),
            },
        ],
        temperature=0,
    )
    return response.choices[0].message.content or source


# ── Task runner ───────────────────────────────────────────────────────────────


def run_task(
    fp: Fingerprint,
    files: list[Path],
    *,
    client: openai.OpenAI,
    model: str,
    dry_run: bool,
) -> tuple[list[Path], list[tuple[Path, str]]]:
    """Run a single fingerprint task over *files*.

    Parameters
    ----------
    fp:
        Loaded fingerprint definition.
    files:
        Files to process for this task.
    client:
        Configured OpenAI client.
    model:
        Model identifier.
    dry_run:
        When True, report what would change without writing anything.

    Returns
    -------
    tuple[list[Path], list[tuple[Path, str]]]
        ``(changed_paths, error_list)`` where each error is ``(path, message)``.
    """
    changed: list[Path] = []
    errors: list[tuple[Path, str]] = []

    for i, path in enumerate(files, 1):
        rel = path.relative_to(Path.cwd())
        print(f"  [{i}/{len(files)}] {rel}", end=" … ", flush=True)

        source = path.read_text(encoding="utf-8")
        last_exc: str = ""
        result: str | None = None

        for attempt in range(MAX_RETRIES + 1):
            if attempt > 0:
                delay = REQUEST_DELAY * (2 ** attempt)  # 8 s, 16 s …
                print(f"    (retry {attempt}/{MAX_RETRIES}, waiting {delay:.0f} s)", flush=True)
                time.sleep(delay)

            try:
                candidate = _call_llm(client, model, fp.system_prompt, source, fp.task_name)

                if len(candidate) < len(source) * TRUNCATION_RATIO:
                    raise RuntimeError(
                        f"Response is {len(candidate)} chars but source is {len(source)} chars "
                        "— likely output truncation. Try a larger output limit or split the file."
                    )

                result = candidate
                break

            except Exception as exc:  # noqa: BLE001
                last_exc = str(exc)

        if result is None:
            # All retries exhausted — annotate the file and record the error.
            print(f"FAILED (annotated): {last_exc}")
            errors.append((path, last_exc))
            if not dry_run:
                comment = f"{FAILURE_COMMENT}: {last_exc}\n"
                # Prepend the comment only if it is not already there.
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

        if i < len(files):
            time.sleep(REQUEST_DELAY)

    return changed, errors


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--fingerprint",
        action="append",
        metavar="PATH",
        dest="fingerprints",
        required=True,
        help=(
            "Path to a fingerprint Markdown file defining the LLM task. "
            "Repeat the flag to run multiple tasks in sequence."
        ),
    )
    parser.add_argument(
        "--src",
        default="src/",
        metavar="DIR",
        help="Source directory to scan for files (default: src/).",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"GitHub Models model ID (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help=(
            "Only process files that differ from --base. "
            "Recommended in CI to stay within free-tier rate limits."
        ),
    )
    parser.add_argument(
        "--base",
        default="origin/main",
        metavar="REF",
        help="Git ref to diff against when --changed-only is set (default: origin/main).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing any files.",
    )
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN environment variable is not set.")

    client = _build_client(token)
    src = Path(args.src)
    if not src.is_dir():
        sys.exit(f"--src directory not found: {src}")

    fingerprints = [load_fingerprint(Path(p)) for p in args.fingerprints]

    print(f"Model   : {args.model}")
    print(f"Src     : {src}")
    print(f"Tasks   : {len(fingerprints)}")
    print(f"Scope   : {'changed vs ' + args.base if args.changed_only else 'all files'}")
    print(f"Dry run : {args.dry_run}")
    print()

    total_changed: list[Path] = []
    total_errors: list[tuple[Path, str]] = []

    for fp in fingerprints:
        print(f"─── Task: {fp.task_name} ({'|'.join(fp.file_patterns)}) ───")

        if args.changed_only:
            files = collect_changed_files(src, fp.file_patterns, args.base)
        else:
            files = collect_all_files(src, fp.file_patterns)

        if not files:
            print("  No matching files — skipping.\n")
            continue

        changed, errors = run_task(fp, files, client=client, model=args.model, dry_run=args.dry_run)
        total_changed.extend(changed)
        total_errors.extend(errors)
        print()

    print(f"Done — {len(total_changed)} file(s) updated, {len(total_errors)} error(s).")
    if total_errors:
        print("\nErrors (files annotated with LLM-REVIEW-FAILED comment):")
        for p, msg in total_errors:
            print(f"  {p}: {msg}")
        print(
            "\nTo find annotated files locally run:\n"
            "  grep -rl 'LLM-REVIEW-FAILED' src/\n"
        )


if __name__ == "__main__":
    main()
