"""Run one or more LLM tasks over a project's source files via the GitHub Models API.

Each task is defined by a *fingerprint* — a Markdown file with a YAML front-matter
header that specifies the task name and which files to process, followed by the
system prompt that the LLM receives.

The script is designed to be called from GitHub Actions after checking out the
github-infra repo alongside the target project:

    python .infra/scripts/run_llm_task/run_llm_task.py \
        --fingerprint .infra/fingerprints/standardize-docstrings.md \
        --fingerprint .infra/fingerprints/standardize-comments.md \
        --src src/ \
        --changed-only \
        --base origin/main

Multiple ``--fingerprint`` flags run each task sequentially; files are
re-read before every pass so the output of task N feeds task N+1.

─── Fingerprint file format ──────────────────────────────────────────────────

    ---
    task_name: "Update NumPy docstrings"
    file_patterns:
      - "*.py"
        exclude_patterns:
            - "__init__.py"
    ---
    You are a Python documentation expert ...
    [rest of system prompt]

``file_patterns`` uses ``fnmatch`` globs applied to filenames (not full paths).
Use ``exclude_patterns`` to skip risky filenames such as ``__init__.py``.
List multiple patterns to match several file types.

─── Environment ──────────────────────────────────────────────────────────────

GITHUB_TOKEN
    Required. A GitHub PAT or the Actions-injected ``secrets.GITHUB_TOKEN``.
    Must have the ``models:read`` permission for GitHub Models free tier access.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from _config import DEFAULT_MODEL, FAILURE_COMMENT
from _files import collect_all_files, collect_changed_files
from _fingerprints import load_fingerprint
from _llm import build_client
from _runner import run_task


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

    client = build_client(token)
    src = Path(args.src)
    if not src.is_dir():
        sys.exit(f"--src directory not found: {src}")

    fingerprints = [load_fingerprint(Path(path)) for path in args.fingerprints]

    print(f"Model   : {args.model}")
    print(f"Src     : {src}")
    print(f"Tasks   : {len(fingerprints)}")
    print(f"Scope   : {'changed vs ' + args.base if args.changed_only else 'all files'}")
    print(f"Dry run : {args.dry_run}")
    print()

    total_changed: list[Path] = []
    total_errors: list[tuple[Path, str]] = []

    for fingerprint in fingerprints:
        print(f"─── Task: {fingerprint.task_name} ({'|'.join(fingerprint.file_patterns)}) ───")

        if args.changed_only:
            files = collect_changed_files(
                src,
                fingerprint.file_patterns,
                args.base,
                exclude_patterns=fingerprint.exclude_patterns,
            )
        else:
            files = collect_all_files(
                src,
                fingerprint.file_patterns,
                exclude_patterns=fingerprint.exclude_patterns,
            )

        if not files:
            print("  No matching files — skipping.\n")
            continue

        changed, errors = run_task(
            fingerprint,
            files,
            client=client,
            model=args.model,
            dry_run=args.dry_run,
        )
        total_changed.extend(changed)
        total_errors.extend(errors)
        print()

    print(f"Done — {len(total_changed)} file(s) updated, {len(total_errors)} error(s).")
    if total_errors:
        print("\nErrors (files annotated with LLM-REVIEW-FAILED comment):")
        for path, message in total_errors:
            print(f"  {path}: {message}")
        print(
            "\nTo find annotated files locally run:\n"
            f"  grep -rl '{FAILURE_COMMENT.removeprefix('# ')}' src/\n"
        )


if __name__ == "__main__":
    main()
