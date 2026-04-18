# github-infra

Shared reusable GitHub Actions workflows and helper scripts for all
`importt-ant` Python repositories.

---

## Repository layout

```
.github/
  workflows/
    run-pytest.yml         ← reusable: run pytest on a chosen ref
    ruff.yml               ← reusable: fix + format with ruff
    generate-docs.yml      ← reusable: regenerate docs/
    open-pr.yml            ← reusable: open/update a PR
    publish-to-pypi.yml    ← reusable: publish to PyPI
scripts/
  generate_docs/           ← doc-generation helpers used by generate-docs.yml
```

---

## Reusable workflows

### `run-pytest.yml` — test gate

Runs `pytest` for a chosen ref. Use it as an explicit test gate, e.g. before
publishing a release tag.

```yaml
jobs:
  pytest:
    uses: importt-ant/github-infra/.github/workflows/run-pytest.yml@main
    with:
      python-version: "3.12"
      checkout-ref: release/2.6.34
    secrets: inherit
```

| Input | Default | Description |
|---|---|---|
| `python-version` | `3.12` | Python version to test with |
| `install-extras` | `dev` | pip extras to install |
| `checkout-ref` | triggering ref | Git ref to test |
| `pytest-command` | `pytest` | Command used to run the test suite |

---

### `ruff.yml` — lint and format

Runs `ruff check --fix` and `ruff format`, then commits and pushes any changes.

```yaml
jobs:
  ruff:
    uses: importt-ant/github-infra/.github/workflows/ruff.yml@main
    with:
      python-version: "3.12"
      src-dir: src/
    secrets: inherit
```

| Input | Default | Description |
|---|---|---|
| `python-version` | `3.12` | Python version |
| `src-dir` | `src/` | Source directory to scan |
| `source-branch` | triggering ref | Branch to treat as the source |
| `working-branch` | source branch | Branch where commits are written |

---

### `generate-docs.yml` — API reference Markdown

Generates API reference Markdown from source code using `griffe` and commits
the result to `docs/`.

```yaml
jobs:
  docs:
    uses: importt-ant/github-infra/.github/workflows/generate-docs.yml@main
    with:
      python-version: "3.12"
      src-dir: src/
    secrets: inherit
```

| Input | Default | Description |
|---|---|---|
| `python-version` | `3.12` | Python version |
| `src-dir` | `src/` | Source directory to scan |
| `source-branch` | triggering ref | Branch to treat as the source |
| `working-branch` | source branch | Branch where commits are written |

---

### `open-pr.yml` — open or update a pull request

Opens a pull request from the head branch into the base branch. Skips if a PR
already exists for the same head/base combination.

```yaml
jobs:
  pr:
    uses: importt-ant/github-infra/.github/workflows/open-pr.yml@main
    with:
      head-branch: my-feature
      base-branch: main
      title: "chore: automated updates"
    secrets: inherit
```

| Input | Default | Description |
|---|---|---|
| `head-branch` | triggering ref | Head branch for the PR |
| `base-branch` | `main` | Base branch for the PR |
| `title` | auto-generated | PR title override |

---

### `publish-to-pypi.yml` — publish to PyPI

Builds and publishes a package to PyPI using Trusted Publishing (OIDC).

> **Note:** PyPI Trusted Publishing does not reliably support reusable
> workflows. You may need to define the publish job directly in your repo-local
> workflow instead.

```yaml
jobs:
  pypi:
    uses: importt-ant/github-infra/.github/workflows/publish-to-pypi.yml@main
    secrets: inherit
```

| Input | Default | Description |
|---|---|---|
| `python-version` | `3.12` | Python version to build with |
