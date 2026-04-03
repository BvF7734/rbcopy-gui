# GitHub Actions

This project uses GitHub Actions for automation. Workflow files live in `.github/workflows/`.

## Active Workflows

### `release.yaml` – Lint, Test, and Build Windows Executable

**Trigger**: Push of a version tag matching `v[0-9]+.[0-9]+.[0-9]+` (e.g. `v1.0.0`)

**Purpose**: Runs the full quality gate (linting, type checking, tests) and, once all checks pass, builds a self-contained `rbcopy-<version>.exe` using PyInstaller and publishes it as a GitHub Release.

**Jobs** (run in sequence):

1. **`lint`** — Code quality checks on Ubuntu:
   - Verifies the lockfile is up to date (`make lock-check`)
   - Checks formatting (`make black_check`)
   - Checks linting (`make ruff_check`)
   - Runs static type checking (`make mypy_check`)
   - Checks data file formatting (`make dapperdata_check`)
   - Checks TOML formatting (`make tomlsort_check`)

2. **`test`** — Test matrix (requires `lint` to pass):
   - Runs `make pytest` on **Windows** across Python **3.10, 3.11, 3.12, 3.13, and 3.14**
   - `fail-fast: false` — all matrix variants run even if one fails

3. **`build-windows`** — Windows executable (requires all `test` variants to pass):
   - Builds `dist/rbcopy-<version>.exe` via `uv run pyinstaller rbcopy.spec`
   - Creates a GitHub Release for the tag with auto-generated release notes
   - Uploads the versioned executable as the release asset (via `softprops/action-gh-release@v2`)

**Relevant files**: `rbcopy.spec` (PyInstaller spec), `pyproject.toml` (`[dependency-groups] dev` includes `pyinstaller>=6.19.0`)

## Disabled Workflows (`.old` files)

The following workflows exist as `*.yaml.old` reference files and are **not currently active**. They can be re-enabled by removing the `.old` extension.

### `ci.yaml.old` – Standalone CI Pipeline

A standalone CI workflow that, when active, would run on every push to `main` and on pull requests. The same quality checks are already covered by the `lint` and `test` jobs in `release.yaml`.

> **Note**: All quality checks must still be run locally with `make tests` before pushing to any branch.

### `pypi.yaml.old` – PyPI Publishing

When active, this workflow would build and publish the package to PyPI on version tag pushes using OIDC trusted publishing (no API tokens needed). See [pypi.md](./pypi.md) for full details.

## Automated Releases

### Creating a Release

1. Ensure your `main` branch is in a releasable state (`make tests` passes)
2. Push a version tag:

   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

3. GitHub automatically triggers `release.yaml`; after all lint and test jobs pass the `build-windows` job creates the release and attaches `rbcopy-v1.0.0.exe`

### Version Tag Format

Use semantic versioning: `vMAJOR.MINOR.PATCH` (e.g. `v1.0.0`, `v1.1.0`, `v1.1.1`). The `v` prefix is required for the workflow trigger.

### Automated Versioning with setuptools-scm

The package version is derived automatically from git tags — no manual version file edits needed:

```bash
# Check the current computed version
python -c "from rbcopy._version import version; print(version)"

# Development version format: 1.2.3.dev4+g5f8a7bc
# Released version format:    1.2.3
```

## Dependabot

`.github/dependabot.yml` configures Dependabot to check **weekly** for GitHub Actions updates. It automatically opens pull requests when actions (e.g. `actions/checkout`) have newer versions available.

### Managing Dependabot PRs

1. Review the PR description for changelog notes and breaking changes
2. Merge when the update looks safe; close if the update is not wanted

## Pull Request Template

`.github/PULL_REQUEST_TEMPLATE.md` provides a standard template for all pull requests. Fill in the relevant sections when opening a PR.

## Running Checks Locally

Always run the full check suite locally before pushing a tag:

```bash
# Run everything (tests + linting + type checking + formatting)
make tests

# Or run individual checks
make pytest         # Tests with coverage
make ruff_check     # Linting
make black_check    # Formatting
make mypy_check     # Type checking
make dapperdata_check
make tomlsort_check
```

## Re-enabling Standalone CI

To run quality checks on every push (not just on tag releases), rename the file:

```bash
git mv .github/workflows/ci.yaml.old .github/workflows/ci.yaml
git commit -m "chore: re-enable CI workflow"
git push
```

Similarly for PyPI publishing:

```bash
git mv .github/workflows/pypi.yaml.old .github/workflows/pypi.yaml
```

Before re-enabling PyPI publishing, configure OIDC trusted publishing in your PyPI project settings. See [pypi.md](./pypi.md) for instructions.

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [GitHub Actions Marketplace](https://github.com/marketplace?type=actions)
- [Workflow Syntax Reference](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions)
- [PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/)
