# github-infra

Shared GitHub Actions workflows, LLM task runner, fingerprint prompts, and
Copier project template for all `importt-ant` Python packages.

---

## Repository layout

```
scripts/
  run_llm_task.py          ← generic LLM task runner (used by the reusable workflow)
fingerprints/
  docstrings-numpy.md      ← rewrite docstrings to NumPy style
  comments.md              ← standardise inline comments
  coding-practices.md      ← enforce naming, typing, guard-clause conventions
.github/
  workflows/
    python-publish.yml     ← reusable: test + publish to PyPI
    python-review.yml      ← reusable: run LLM tasks + open PR
template/                  ← Copier project template
```

---

## Reusable workflows

### `python-publish.yml` — Test & publish to PyPI

Triggered on `v*` tag pushes. Runs tests, builds, publishes via Trusted
Publisher, and creates a GitHub release.

```yaml
# .github/workflows/publish.yml
name: Publish to PyPI
on:
  push:
    tags: ["v*"]
jobs:
  publish:
    uses: importt-ant/github-infra/.github/workflows/python-publish.yml@main
    with:
      python-version: "3.12"   # optional
      install-extras: "dev"    # optional
    secrets: inherit
```

---

### `python-review.yml` — LLM task runner

Checks out this repo as `.infra/` alongside the calling project, runs
`scripts/run_llm_task.py` with the fingerprints you specify, commits any
changes, and opens a PR for review.

The `fingerprints` input is a newline-separated list of paths relative to
this repo's root. Mix and match any combination:

```yaml
# .github/workflows/docs.yml
name: Generate Documentation
on:
  push:
    branches: ["docs/**"]
  workflow_dispatch:
    inputs:
      model:
        default: "gpt-4o-mini"
jobs:
  review:
    uses: importt-ant/github-infra/.github/workflows/python-review.yml@main
    with:
      python-version: "3.12"
      model: ${{ github.event.inputs.model || 'gpt-4o-mini' }}

      # Choose which tasks to run — order matters (output of each feeds the next).
      fingerprints: |
        fingerprints/docstrings-numpy.md
        fingerprints/comments.md
        fingerprints/coding-practices.md
    secrets: inherit
```

**Release-type examples:**

| Branch / scenario | Fingerprints to use |
|---|---|
| Full release (`docs/2.0`) | all three |
| Minor release (`docs/2.1`) | `coding-practices.md` only |
| Quick doc fix | `docstrings-numpy.md` only |

**Optional inputs:**

| Input | Default | Description |
|---|---|---|
| `python-version` | `3.12` | Python version for the runner |
| `model` | `gpt-4o-mini` | GitHub Models model ID (free tier) |
| `src-dir` | `src/` | Source directory to scan |
| `base-branch` | `origin/main` | Git ref for `--changed-only` diff |
| `run-doc-generator` | `true` | Run `generate_docs.py` when present |

---

## Fingerprints

Fingerprint files define what the LLM is asked to do. Each is a Markdown file
with YAML front-matter followed by the system prompt:

```markdown
---
task_name: "Update NumPy docstrings"
file_patterns:
  - "*.py"
---
You are a Python documentation expert ...
```

Add new fingerprints under `fingerprints/` and reference them by path in any
project's workflow. The runner processes files changed in the PR diff only
(`--changed-only`), so large repos stay within the GitHub Models free-tier
rate limits (150 requests/day for `gpt-4o-mini`).

---

## Copier template

Scaffolds a new `importt-ant` Python library with `pyproject.toml`,
`.gitignore`, and both workflow callers pre-configured.

```bash
pip install copier
copier copy /path/to/github-infra <new-project-dir>
```

**Template variables (prompted):**

| Variable | Default | Description |
|---|---|---|
| `project_name` | — | PyPI / GitHub name (e.g. `keygen`) |
| `package_name` | `project_name` (hyphens → underscores) | Importable name |
| `description` | — | One-line description |
| `development_status` | `3 - Alpha` | PyPI status classifier |
| `min_python` | `3.12` | Minimum Python version |
| `optional_extras` | `{}` | Dict of extra name → package list |

**Repo-level constants (edit once in `copier.yml`, never prompted):**

| Variable | Current value |
|---|---|
| `author_name` | Maximilian Todea |
| `author_email` | demon.and.max@gmail.com |
| `github_username` | importt-ant |

Update an existing project after template changes:
```bash
# inside the project repo
copier update
```

