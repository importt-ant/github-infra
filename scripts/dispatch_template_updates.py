"""Dispatch template-update events to repositories initialized from github-infra.

This script is intended to run in the github-infra repository after pushes to
``main``. It finds repositories owned by the configured account that contain a
``.copier-answers.yml`` file referencing ``github-infra``, then sends a
``repository_dispatch`` event to each one so they can run ``copier update`` in
repo-local CI against the latest infra commit.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

API_ROOT = "https://api.github.com"
DISPATCH_EVENT = "github-infra-template-update"


def github_request(
    method: str,
    path: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    """Call the GitHub API and return ``(status_code, decoded_json_or_text)``."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{API_ROOT}{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "github-infra-template-sync",
        },
    )

    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            body: Any = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            body = raw
        return exc.code, body


def list_owned_repositories(owner: str, token: str) -> list[dict[str, Any]]:
    """Return all non-archived repos owned by *owner* visible to the token."""
    repos: list[dict[str, Any]] = []
    page = 1

    while True:
        status, body = github_request(
            "GET",
            f"/user/repos?affiliation=owner&per_page=100&page={page}",
            token,
        )
        if status != 200:
            sys.exit(f"Failed to list repositories: {body}")
        if not body:
            break

        for repo in body:
            if repo.get("owner", {}).get("login") != owner:
                continue
            if repo.get("archived") or repo.get("disabled"):
                continue
            repos.append(repo)

        page += 1

    return repos


def load_copier_answers(owner: str, repo: str, token: str) -> str | None:
    """Return decoded ``.copier-answers.yml`` content, or ``None`` if absent."""
    status, body = github_request(
        "GET",
        f"/repos/{owner}/{repo}/contents/.copier-answers.yml",
        token,
    )
    if status == 404:
        return None
    if status != 200:
        print(f"skip {repo}: could not read .copier-answers.yml ({body})")
        return None

    content = body.get("content", "")
    if not content:
        return None

    decoded = base64.b64decode(content).decode("utf-8")
    return decoded


def dispatch_update(
    owner: str,
    repo: str,
    token: str,
    *,
    template_repo: str,
    template_ref: str,
) -> bool:
    """Send the repository_dispatch event to *repo*."""
    status, body = github_request(
        "POST",
        f"/repos/{owner}/{repo}/dispatches",
        token,
        payload={
            "event_type": DISPATCH_EVENT,
            "client_payload": {
                "template_repo": template_repo,
                "template_ref": template_ref,
            },
        },
    )
    if status == 204:
        return True

    print(f"failed to dispatch to {repo}: {body}")
    return False


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN")
    owner = os.environ.get("TEMPLATE_OWNER")
    template_repo = os.environ.get("TEMPLATE_REPO")
    template_ref = os.environ.get("TEMPLATE_REF")

    if not token:
        sys.exit("GITHUB_TOKEN environment variable is not set")
    if not owner:
        sys.exit("TEMPLATE_OWNER environment variable is not set")
    if not template_repo:
        sys.exit("TEMPLATE_REPO environment variable is not set")
    if not template_ref:
        sys.exit("TEMPLATE_REF environment variable is not set")

    repositories = list_owned_repositories(owner, token)
    template_repo_name = template_repo.split("/", maxsplit=1)[-1]

    targeted: list[str] = []
    dispatched: list[str] = []

    for repo in repositories:
        repo_name = repo["name"]
        if repo_name == template_repo_name:
            continue

        answers = load_copier_answers(owner, repo_name, token)
        if answers is None or "github-infra" not in answers:
            continue

        targeted.append(repo_name)
        if dispatch_update(
            owner,
            repo_name,
            token,
            template_repo=template_repo,
            template_ref=template_ref,
        ):
            dispatched.append(repo_name)

    print(f"owner      : {owner}")
    print(f"template   : {template_repo}")
    print(f"template ref: {template_ref}")
    print(f"targeted   : {len(targeted)}")
    print(f"dispatched : {len(dispatched)}")

    if targeted:
        print("\nRepositories notified:")
        for repo_name in dispatched:
            print(f"  - {repo_name}")


if __name__ == "__main__":
    main()
