# GitHub Actions

This project uses GitHub Actions for automation. Workflow files live in `.github/workflows/`.

## Active Workflows

### `release.yaml` – Build Windows Executable

**Trigger**: Push of a version tag matching `v[0-9]+.[0-9]+.[0-9]+` (e.g. `v1.2.3`)

**Purpose**: Builds the application into a self-contained `rbcopy.exe` using PyInstaller and uploads it as a release asset.

**What it does**:

1. Checks out the repository
2. Installs uv and sets up Python 3.14
3. Installs all dependencies with `uv sync --group dev`
4. Runs `uv run pyinstaller rbcopy.spec` to produce `dist/rbcopy.exe`
5. Uploads `rbcopy.exe` to the GitHub release via `actions/upload-release-asset`

**Relevant files**: `rbcopy.spec` (PyInstaller spec), `pyproject.toml` (`[dependency-groups] dev` includes `pyinstaller>=6.19.0`)

## Disabled Workflows (`.old` files)

The following workflows exist as `*.yaml.old` reference files and are **not currently active**. They can be re-enabled by removing the `.old` extension.

### `ci.yaml.old` – CI Pipeline

When active, this workflow would run on every push to `main` and on pull requests:

- **Lint job**: formatting (black/ruff), linting (ruff), type checking (mypy), data formatting (dapperdata), TOML formatting (tombi)
- **Test matrix job**: runs `make pytest` on Ubuntu and Windows across Python 3.10, 3.11, 3.12, 3.13, and 3.14

> **Note**: Until this workflow is re-enabled, all quality checks must be run locally with `make tests` before pushing.

### `pypi.yaml.old` – PyPI Publishing

When active, this workflow would build and publish the package to PyPI on version tag pushes using OIDC trusted publishing (no API tokens needed). See [pypi.md](./pypi.md) for full details.

## Automated Releases

### Creating a Release

1. Ensure your `main` branch is in a releasable state (`make tests` passes)
2. Push a version tag:

   ```bash
   git tag v1.2.3
   git push origin v1.2.3
   ```

3. GitHub will automatically create a draft release; the `release.yaml` workflow builds `rbcopy.exe` and attaches it

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
2. CI checks (once re-enabled) will run automatically on Dependabot PRs
3. Merge when all checks pass; close if the update is not wanted

## Pull Request Template

`.github/PULL_REQUEST_TEMPLATE.md` provides a standard template for all pull requests. Fill in the relevant sections when opening a PR.

## Running Checks Locally

Because the CI workflow is currently disabled, always run the full check suite locally before pushing:

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

## Re-enabling CI

To re-enable the CI pipeline, rename the file:

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


8. **Keep dependencies updated**: Review and merge Dependabot PRs promptly

## Workflow Costs and Limits

GitHub Actions has usage limits:

- **Public repositories**: Unlimited minutes (with some restrictions)
- **Private repositories**: 2,000 minutes/month free, then paid
- **Storage**: 500 MB free, artifacts expire after 90 days

To optimize:

- Use caching to reduce build times
- Clean up old artifacts
- Use `concurrency` to cancel outdated runs

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [GitHub Actions Marketplace](https://github.com/marketplace?type=actions)
- [Workflow Syntax Reference](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions)
- [PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/)
- [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
