# Dependencies

This project uses modern Python packaging standards with `pyproject.toml` as the central configuration file for all dependencies, build settings, and tool configurations. All dependency operations use `uv` for fast, reproducible installs.

## Dependency Management Structure

Dependencies are organized in `pyproject.toml` using PEP 621 for runtime deps and PEP 735 dependency groups for dev deps:

```toml
[project]
name = "rbcopy"
dependencies = [
  # Runtime dependencies required to run the application
]

[dependency-groups]
dev = [
  # Development dependencies for testing, linting, etc.
]
```

### Main Dependencies vs Dev Dependencies

**Main Dependencies** (`[project] dependencies`):

- Required to run the application in production
- Installed when a user runs `pip install rbcopy` or `uv add rbcopy`
- Includes frameworks, libraries, and all runtime requirements

**Dev Dependencies** (`[dependency-groups] dev`):

- Only needed during development and testing
- Installed via `uv sync --group dev` (used by `make install` and `make sync`)
- Includes testing tools, linters, formatters, and build tools
- Uses PEP 735 dependency groups (the `[dependency-groups]` table), **not** `[project.optional-dependencies]`

## Project Dependencies

### Core Runtime Dependencies

```toml
dependencies = [
  "pydantic~=2.0",          # Data validation and settings management
  "pydantic-settings>=2.0", # Environment variable / .env file loading
  "rich",                   # Rich terminal output and logging handler
  "tkinterdnd2",            # Drag-and-drop support for Tkinter
  "typer",                  # CLI framework
]
```

### Development Dependencies

```toml
[dependency-groups]
dev = [
  "build",                  # PEP 517 build frontend for distribution packages
  "dapperdata",             # JSON/YAML data file formatting
  "glom",                   # Nested data access and transformation
  "greenlet",               # Required for coverage reporting with threads
  "mypy",                   # Static type checker
  "pyinstaller>=6.19.0",   # Windows executable builder
  "pytest",                 # Testing framework
  "pytest-asyncio",         # Async/await test support
  "pytest-cov",             # Coverage reporting plugin
  "pytest-pretty",          # Beautiful test output formatting
  "ruamel.yaml",            # YAML parsing (used by dapperdata)
  "ruff",                   # Fast linter and formatter (replaces Black, isort, Flake8)
  "setuptools-scm>=9.2.2",  # Version derivation from git tags
  "tombi",                  # TOML linting and formatting
  "uv",                     # Package installer / lockfile generator
]
```

## Adding New Dependencies

### Add a Runtime Dependency

Use `uv add` – it edits `pyproject.toml` and updates `uv.lock` atomically:

```bash
uv add requests
```

Verify it was added to `[project] dependencies` in `pyproject.toml`, then run `make install` to sync.

### Add a Development Dependency

```bash
uv add --group dev black
```

This adds the package to `[dependency-groups] dev` in `pyproject.toml` and updates `uv.lock`.

## Removing Dependencies

```bash
# Remove a runtime dependency
uv remove requests

# Remove a dev dependency
uv remove --group dev black
```

After removal, run `make sync` to update the local environment.

## Version Pinning Strategies

### Compatible Release (Recommended)

Use the `~=` operator for compatible versions:

```toml
"pydantic~=2.0"  # Allows >=2.0.0, <3.0.0
```

**Benefits**: Gets bug fixes and minor updates automatically while avoiding breaking changes from major version bumps.

### Minimum Version

```toml
"pydantic-settings>=2.0"  # Any version >= 2.0
```

**Use cases**: When you need a specific feature added in a version.

### Exact Version (Not Recommended)

```toml
"requests==2.31.0"  # Only version 2.31.0 exactly
```

**Warning**: Prevents security updates and bug fixes. Only use temporarily for debugging.

## Lockfile Management

This project uses `uv.lock` for deterministic, reproducible dependency resolution across all environments. The lockfile is version-controlled and must be committed to git.

### Generate/Update Lockfile

```bash
# Regenerate lockfile (after editing pyproject.toml)
make lock

# Update all packages to their latest compatible versions
uv lock --upgrade

# Check if lockfile is in sync with pyproject.toml
make lock-check
```

### Installing from Lockfile

**Development** (with dev dependencies):

```bash
# What make install / make sync do internally
uv sync --group dev
```

**Production** (runtime only, no dev tools):

```bash
uv sync --frozen --no-dev
```

### Why uv.lock over requirements.txt?

- **Multi-platform**: A single lockfile covers Linux, macOS, Windows, ARM64, and AMD64
- **Rust-powered**: Much faster resolution and installation than pip/pip-tools
- **Complete dependency tree**: Every transitive dependency is pinned with hashes
- **Conflict detection**: Catches dependency conflicts earlier with clearer messages

## Updating Dependencies

After modifying `pyproject.toml` (or running `uv add`/`uv remove`), sync the lockfile and environment:

```bash
# Regenerate lockfile and install
make lock
make sync
```

## Virtual Environment Management

This project uses a virtual environment at `.venv` in the project root.

```bash
# Create the virtual environment and install all dependencies (first-time setup)
make install

# On macOS/Linux - activate manually if needed
source .venv/bin/activate

# On Windows
.venv\Scripts\activate
```

uv automatically reads `.python-version` and installs the correct Python version if it is not already present on the system.

## Security

Regularly check for known vulnerabilities in dependencies. GitHub's Dependabot is configured in `.github/dependabot.yml` to automatically open PRs for outdated or vulnerable packages.


## Optional Dependency Groups

You can create multiple optional dependency groups:

```toml
[project.optional-dependencies]
dev = [
  "pytest",
  "ruff",
]

docs = [
  "sphinx",
  "sphinx-rtd-theme",
]

performance = [
  "uvloop",
  "orjson",
]
```

Install specific groups:

```bash
# Install dev dependencies
uv pip install -e .[dev]

# Install multiple groups
uv pip install -e .[dev,docs]

# Install all optional dependencies
uv pip install -e .[dev,docs,performance]
```

## Build System Configuration

The build system is configured at the top of `pyproject.toml`:

```toml
[build-system]
build-backend = "setuptools.build_meta"
requires = ["setuptools>=67.0", "setuptools_scm[toml]>=7.1"]
```

**Components**:

- **build-backend**: Uses setuptools for building packages
- **setuptools**: Modern Python build system
- **setuptools_scm**: Automatic versioning from git tags

### Building Distribution Packages

```bash
# Build source and wheel distributions
make build

# Or manually
python -m build

# Creates:
# dist/rbcopy-X.Y.Z.tar.gz (source)
# dist/rbcopy-X.Y.Z-py3-none-any.whl (wheel)
```

## Best Practices

1. **Use pyproject.toml as single source of truth**: Don't mix with `setup.py` or `setup.cfg`

2. **Pin major versions with ~=**: Allows updates while preventing breaking changes

   ```toml
   "pydantic~=2.0"  # Good
   "pydantic"       # Bad - no version constraint
   "pydantic==2.5.0"  # Bad - too restrictive
   ```

3. **Separate runtime and dev dependencies**: Keep production images lean

4. **Use editable installs for development**: `-e` flag for faster iteration

   ```bash
   pip install -e .[dev]
   ```

5. **Keep dependencies updated**: Regular updates prevent security issues

6. **Test after updates**: Run full test suite after dependency updates

   ```bash
   pip install --upgrade -e .[dev]
   make test
   ```

7. **Document why dependencies are needed**: Add comments in pyproject.toml

   ```toml
   dependencies = [
     "pydantic~=2.0",  # Settings and validation
     "requests~=2.31",  # HTTP client for external APIs
   ]
   ```

8. **Use virtual environments**: Always work in virtual environments

9. **Lock dependencies for production**: Use requirements files or pip-compile for exact reproducibility

10. **Review dependency licenses**: Ensure compatibility with your project's license

## Troubleshooting

### "ModuleNotFoundError" After Adding Dependency

```bash
# Reinstall to pick up new dependencies
uv pip install -e .[dev]

# Verify package is installed
uv pip show package-name
```

### "No module named 'setuptools_scm'"

```bash
# Update uv and install build dependencies
pip install --upgrade uv
uv pip install -e .[dev]
```

### uv Not Found

```bash
# Install uv via pip
pip install uv

# Or use the standalone installer (recommended)
curl -LsSf https://astral.sh/uv/install.sh | sh

# On Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex
```

### Conflicting Dependencies

```bash
# Show dependency tree
uv pip install pipdeptree
pipdeptree

# Find conflicts
pipdeptree --warn conflicts
```

## Why uv?

This project uses [uv](https://docs.astral.sh/uv/) as the primary package manager for several compelling reasons:

### Performance

- **10-100x faster** than pip for package installation
- Written in Rust for maximum performance
- Parallel downloads and installations
- Advanced caching strategies

### Convenience

- **Automatic Python management**: Downloads and installs Python versions as needed
- **Drop-in pip replacement**: Compatible with existing pip commands
- **Integrated virtual environments**: Built-in venv management
- **Cross-platform**: Works on Linux, macOS, and Windows

### Reliability

- **Better dependency resolution**: More accurate conflict detection
- **Lockfile generation**: Create reproducible environments
- **Offline mode**: Cache packages for offline installation

### Commands Comparison

| Task | pip | uv |
|------|-----|-----|
| Install package | `pip install package` | `uv pip install package` |
| Create venv | `python -m venv .venv` | `uv venv` |
| Install Python | Requires pyenv/installer | `uv venv --python 3.14` (auto-downloads) |
| Compile requirements | Requires pip-tools | `uv pip compile` (built-in) |
| Speed | Baseline | 10-100x faster |

## References

- [PEP 621 - Project Metadata](https://peps.python.org/pep-0621/)
- [Python Packaging User Guide](https://packaging.python.org/)
- [uv Documentation](https://docs.astral.sh/uv/)
- [uv GitHub Repository](https://github.com/astral-sh/uv)
