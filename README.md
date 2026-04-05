# github-infra

Shared GitHub Actions workflows, LLM task runner, fingerprint prompts, and
Copier project template for all `importt-ant` Python packages.

---

## Repository layout

```
scripts/
  run_llm_task/
    run_llm_task.py        ← llm task entrypoint
    ...                    ← modular llm-task helpers
  generate_docs/
    generate_docs.py       ← docs entrypoint
    ...                    ← modular doc-generation helpers
fingerprints/
  standardize-docstrings.md      ← rewrite docstrings to NumPy style
  standardize-comments.md        ← standardise inline comments
.github/
  workflows/
    dispatch-template-updates.yml ← owner-side fan-out on pushes to main
    prepare-for-release.yml← reusable: orchestrate release cleanup passes
    run-pytest.yml         ← reusable: run pytest on a chosen ref
    llm-task.yml           ← reusable: run one fingerprint pass
    ruff.yml               ← reusable: fix + format
    generate-docs.yml      ← reusable: regenerate docs/
    open-pr.yml            ← reusable: open/update the PR
    publish-to-pypi.yml    ← reusable: publish to PyPI
template/                  ← Copier project template
```

---

## Reusable workflows

### `publish-to-pypi.yml` — publish a released build to PyPI

Called from the manual release workflow after the GitHub release is created.
Builds the package and publishes it to PyPI via Trusted Publisher.

```yaml
# inside .github/workflows/tag.yml
jobs:
  publish:
    uses: importt-ant/github-infra/.github/workflows/publish-to-pypi.yml@main
    with:
      python-version: "3.12"
    secrets: inherit
```

---

### `run-pytest.yml` — reusable release-line test job

Runs `pytest` for a chosen ref. Use it whenever you want an explicit test gate,
such as before publishing a release tag.

```yaml
jobs:
  pytest:
    uses: importt-ant/github-infra/.github/workflows/run-pytest.yml@main
    with:
      python-version: "3.12"
      checkout-ref: release/2.6.34
    secrets: inherit
```

  ---

  ### `tag.yml` in templated repos — manual release-and-publish entrypoint

  This is a project-level workflow meant to be triggered manually from the
  Actions UI while the selected ref is `release/x.y.z`. It:

  1. runs `pytest`
  2. creates and pushes tag `vX.Y.Z`
  3. creates the GitHub release
  4. publishes to PyPI
  5. opens PRs from `release/x.y.z` into `main` and `dev/x.y`

---

### `prepare-for-release.yml` — release cleanup orchestrator

Calls smaller reusable workflows in sequence: one LLM pass per fingerprint,
then `ruff`, then docs generation, then PR creation.

The `fingerprints` input is a newline-separated list of paths relative to
this repo's root. Mix and match any combination:

```yaml
# .github/workflows/release.yml
name: Prepare Release Branch
on:
  workflow_dispatch:
    inputs:
      dev-branch:
        required: true
      version:
        required: true
jobs:
  review:
    uses: importt-ant/github-infra/.github/workflows/prepare-for-release.yml@main
    with:
      python-version: "3.12"
      source-branch: release/${{ inputs.version }}
      working-branch: groom/release-${{ inputs.version }}
      pr-base-branch: release/${{ inputs.version }}
      fingerprints: |
        fingerprints/standardize-docstrings.md
        fingerprints/standardize-comments.md
    secrets: inherit
```

The project-level release workflow is now manual-only. It creates
`release/x.y.z` from the chosen `dev/x.y` branch when needed, reuses the
existing release branch when it is already present, and then runs the full
grooming stack for every release.

**Optional inputs:**

| Input | Default | Description |
|---|---|---|
| `python-version` | `3.12` | Python version for the runner |
| `model` | `gpt-4o-mini` | GitHub Models model ID (free tier) |
| `src-dir` | `src/` | Source directory to scan |
| `base-branch` | `origin/main` | Git ref for `--changed-only` diff |
| `pr-base-branch` | `main` | Base branch for the pull request |
| `run-doc-generator` | `true` | Run `scripts/generate_docs/generate_docs.py` |

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

Current built-in fingerprints:

- `fingerprints/standardize-docstrings.md`
- `fingerprints/standardize-comments.md`

---

## Copier template

Scaffolds a new `importt-ant` Python library with `pyproject.toml`,
`.gitignore`, and branch-oriented workflow callers pre-configured.

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

### Automatic template sync on infra pushes to main

Each templated repo can include a `sync-template.yml` workflow that listens for
the `github-infra-template-update` repository-dispatch event and runs:

```bash
copier update --trust --defaults --vcs-ref <commit-sha-or-ref>
```

The owner-side workflow in `github-infra` now fans this event out on every push
to `main`, using the newest `main` commit SHA as the Copier ref. To enable that
fan-out, add a secret named
`TEMPLATE_SYNC_TOKEN` to `github-infra` with permission to dispatch workflow
events to your downstream repositories.

If a downstream template sync may update files under `.github/workflows/`, add a
repository secret with the same name, `TEMPLATE_SYNC_TOKEN`, to that downstream
repo as well. Use a token that can push workflow-file changes and open pull
requests for that repository.

The reusable workflows in `github-infra` now prefer that same
`TEMPLATE_SYNC_TOKEN` for repository checkouts, branch pushes, and pull-request
creation, including the manual release-branch preparation flow. When the secret
is absent, they fall back to the default workflow token.

