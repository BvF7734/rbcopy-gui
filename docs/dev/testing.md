# Testing

This project uses [pytest](https://docs.pytest.org/) as its testing framework, providing comprehensive test coverage for all features with async/await support, fixtures, and powerful assertion capabilities.

## Project Test Structure

Tests are organized in the `tests/` directory with a structure that mirrors the main package:

```
tests/
├── __init__.py
├── conftest.py                         # Shared fixtures and test configuration
├── helpers.py                          # Test helper utilities
├── test___main__.py                    # Package __main__ entry point tests
├── test_app_dirs.py                    # Application directories tests
├── test_bookmarks.py                   # Bookmark model and store tests
├── test_builder.py                     # Command builder (build_command) tests
├── test_builder_exit_codes.py          # Robocopy exit code handling tests
├── test_builder_scripts.py             # Batch/PowerShell script export tests
├── test_cli.py                         # CLI application tests
├── test_conf_settings.py               # Settings and configuration tests
├── test_dnd.py                         # Drag-and-drop module tests
├── test_e2e_filesystem.py              # End-to-end filesystem integration tests
├── test_gui.py                         # Core GUI component tests
├── test_gui_advanced_mode.py           # Advanced mode flag toggle tests
├── test_gui_async_bridge.py            # Background thread / queue bridge tests
├── test_gui_bookmark_manager.py        # Bookmark manager dialog tests
├── test_gui_bookmarks_browse.py        # Bookmark browse and selection tests
├── test_gui_execute.py                 # Robocopy job execution tests
├── test_gui_import_patterns.py         # Import/export patterns dialog tests
├── test_gui_interactions.py            # General GUI interaction tests
├── test_gui_job_history_actions.py     # Job history action tests
├── test_gui_job_history_filter_search.py # Job history filter/search tests
├── test_gui_job_history_parse.py       # Job history log parsing tests
├── test_gui_job_history_refresh.py     # Job history refresh tests
├── test_gui_main_window.py             # Main window layout and lifecycle tests
├── test_gui_presets.py                 # GUI preset load/save tests
├── test_gui_run.py                     # GUI run button and job lifecycle tests
├── test_gui_script_builder.py          # Script export dialog tests
├── test_gui_widget_states.py           # Widget enable/disable state tests
├── test_logger.py                      # Logging setup tests
├── test_notifications.py               # Notification system tests
├── test_path_history.py                # Path history store tests
├── test_preferences.py                 # Preferences / preferences store tests
├── test_presets.py                     # Preset management tests
├── test_rbcopy.py                      # Package-level tests
├── test_robocopy_parser.py             # Robocopy output parser tests
├── test_storage.py                     # JsonStore base class tests
├── test_system_check.py                # Pre-flight system check tests
└── services/
    └── __init__.py                     # (placeholder for future service tests)
```

### Test Organization Principles

- **Mirror package structure**: Test files mirror the structure of the main package
- **Feature-based testing**: Each major module has its own test file
- **Shared fixtures**: Common test setup is centralized in `conftest.py`

## Running Tests

### Basic Test Execution

```bash
# Run all tests and quality checks
make tests

# Run only pytest (skip linting and type checks)
make pytest

# Run tests with verbose/debug output
make pytest_loud

# Run specific test file
uv run pytest tests/test_builder.py

# Run specific test function
uv run pytest tests/test_builder.py::test_build_command_mir

# Run tests matching a pattern
uv run pytest -k "test_sync"
```

### Coverage Reports

The project is configured to generate test coverage reports automatically:

```bash
# Run tests with coverage (default for make pytest)
pytest --cov=./rbcopy --cov-report=term-missing tests

# Generate HTML coverage report
pytest --cov=./rbcopy --cov-report=html tests
# Open htmlcov/index.html in your browser

# Show coverage for a specific module
uv run pytest --cov=./rbcopy/builder.py tests/test_builder.py
```

### Running Specific Test Types

```bash
# Run only async tests
pytest -m asyncio

# Run tests in parallel (requires pytest-xdist)
pytest -n auto

# Stop on first failure
pytest -x

# Show local variables in tracebacks
pytest -l

# Disable captured output (see prints immediately)
pytest -s
```

## Test Fixtures

Test fixtures provide reusable test setup and teardown logic. This project uses fixtures extensively for database sessions, API clients, and other shared resources.

### Core Fixtures (in conftest.py)

| Fixture | Scope | Description |
|---------|-------|-------------|
| `log_dir` | function | Creates a fresh `rbcopy` logger writing to a temporary directory. Tears down all handlers after each test so tests are fully isolated. Yields the `Path` to the log directory. |

**Example usage**:

```python
def test_log_file_created(log_dir):
    """A session log file is written to the log directory."""
    from rbcopy.logger import setup_logging
    log_files = list(log_dir.glob("robocopy_job_*.log"))
    assert len(log_files) == 1
```

The `tmp_path` fixture (built in to pytest) is also used extensively for creating temporary files and directories in tests that need isolated file-system state. See the [pytest docs](https://docs.pytest.org/en/stable/how-to/tmp_path.html) for details.

This project extensively uses async/await. pytest-asyncio provides support for testing async functions.

### Async Test Functions

Mark async test functions with `@pytest.mark.asyncio`:

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    """Test an async function."""
    result = await some_async_function()
    assert result == expected_value
```

### Async Fixtures

Use `@pytest_asyncio.fixture` for async fixtures:

```python
import pytest_asyncio

@pytest_asyncio.fixture
async def async_resource():
    """Create an async resource for testing."""
    resource = await create_resource()
    yield resource
    await cleanup_resource(resource)
```

## Mocking and Patching

Use pytest's built-in mocking capabilities along with unittest.mock for mocking dependencies.

### Basic Mocking

```python
from unittest.mock import MagicMock, patch

def test_with_mock():
    """Test with a mocked dependency."""
    mock_store = MagicMock()
    mock_store.list.return_value = []

    result = get_items(mock_store)
    assert result == []
    mock_store.list.assert_called_once()
```

### Patching Functions

```python
from unittest.mock import patch

@patch("rbcopy.system_check.shutil.which", return_value="/usr/bin/robocopy")
def test_robocopy_found_on_path(mock_which):
    """Pre-flight check succeeds when robocopy is on PATH."""
    from rbcopy.system_check import run_preflight_checks
    result = run_preflight_checks()
    assert result.ok
    mock_which.assert_called_with("robocopy")
```

### Patching Environment Variables

```python
@pytest.mark.asyncio
@patch.dict(os.environ, {"RBCOPY_DATA_DIR": "/tmp/test-data"})
async def test_with_custom_env():
    """Test with custom environment variables."""
    from rbcopy.conf.settings import Settings
    settings = Settings()
    assert str(settings.data_dir) == "/tmp/test-data"
```

## Testing Patterns by Feature

### Testing Settings

```python
import os
from unittest.mock import patch
from rbcopy.conf.settings import Settings


def test_settings_data_dir_defaults_to_none():
    """Settings.data_dir is None when RBCOPY_DATA_DIR is not set."""
    with patch.dict(os.environ, {}, clear=True):
        s = Settings(_env_file=None)
        assert s.data_dir is None


def test_settings_data_dir_from_env(tmp_path):
    """RBCOPY_DATA_DIR env var is picked up by Settings."""
    with patch.dict(os.environ, {"RBCOPY_DATA_DIR": str(tmp_path)}):
        s = Settings()
        assert s.data_dir == tmp_path
```

See `tests/test_conf_settings.py` for the complete settings test suite.

## Test Isolation and Independence

### Principles

1. **Each test is independent**: Tests should not depend on the order of execution
2. **Clean state**: Fixtures ensure each test starts with a clean state
3. **No side effects**: Tests should not affect other tests or external systems
4. **Idempotent**: Running tests multiple times produces the same results

## Coverage Requirements and Best Practices

### Coverage Goals

- **Critical paths**: All business logic in `builder.py`, `robocopy_parser.py`, `cli.py` should have thorough coverage
- **New code**: Every new feature must include tests before merging

### Checking Coverage

```bash
# Generate coverage report (runs automatically with make pytest)
make pytest

# Coverage for a specific module
uv run pytest --cov=./rbcopy/builder.py tests/test_builder.py

# Fail if coverage drops below a threshold
uv run pytest --cov=./rbcopy --cov-fail-under=80 tests
```

### Coverage Configuration

Coverage is configured in `pyproject.toml`:

```toml
[tool.coverage.run]
concurrency = ["thread", "greenlet"]
omit = [
  "./rbcopy/_version.py",
  "./rbcopy/__init__.py",
  "./tests/*",
]
```

## Best Practices

1. **Write descriptive test names**: Test names should clearly describe what they test

   ```python
   # Good
   def test_user_creation_validates_email_format()

   # Bad
   def test_user()
   ```

2. **One assertion per test**: Keep tests focused on a single behavior

   ```python
   # Good
   def test_user_email_validation():
       assert validate_email("test@example.com") is True

   def test_user_email_validation_rejects_invalid():
       assert validate_email("invalid") is False

   # Bad (multiple unrelated assertions)
   def test_user_stuff():
       assert user.name == "Test"
       assert user.email_valid()
       assert user.age > 0
   ```

3. **Use fixtures for setup**: Avoid duplication by using fixtures

   ```python
   @pytest.fixture
   def sample_user():
       return User(name="Test", email="test@example.com")

   def test_user_name(sample_user):
       assert sample_user.name == "Test"
   ```

4. **Test both success and failure cases**: Test happy paths and error conditions

   ```python
   def test_divide_success():
       assert divide(10, 2) == 5

   def test_divide_by_zero_raises_error():
       with pytest.raises(ZeroDivisionError):
           divide(10, 0)
   ```

5. **Use parametrize for multiple test cases**: Test multiple inputs efficiently

   ```python
   @pytest.mark.parametrize("input,expected", [
       ("test@example.com", True),
       ("invalid", False),
       ("test@", False),
       ("@example.com", False),
   ])
   def test_email_validation(input, expected):
       assert validate_email(input) == expected
   ```

6. **Keep tests fast**: Use temporary directories (`tmp_path`), mock external processes, avoid sleep

   ```python
   # Good - uses pytest's tmp_path fixture for isolated file state
   def test_preset_persists(tmp_path):
       store = CustomPresetsStore(data_dir=tmp_path)
       store.add(CustomPreset(name="test", flags={}))
       assert store.get("test") is not None

   # Bad - sleeps unnecessarily
   def test_slow():
       import time
       time.sleep(5)  # Avoid this!
       assert True
   ```

7. **Test edge cases and boundary conditions**: Don't just test happy paths

   ```python
   @pytest.mark.parametrize("value", [0, -1, None, "", [], {}])
   def test_handles_edge_cases(value):
       result = process_value(value)
       assert result is not None
   ```

8. **Use async tests for async code**: Always use `@pytest.mark.asyncio` for async functions

   ```python
   # Good
   @pytest.mark.asyncio
   async def test_async_function():
       result = await async_operation()
       assert result == expected

   # Bad - won't work properly
   def test_async_function():
       result = async_operation()  # This returns a coroutine, not a result!
       assert result == expected
   ```

## Continuous Integration

Tests run automatically on every version tag push via GitHub Actions (see [github.md](./github.md)). The `release.yaml` pipeline runs before building the executable:

1. **Runs all tests** with coverage reporting on Windows, Python 3.10–3.14
2. **Checks code formatting** with ruff
3. **Performs type checking** with mypy
4. **Validates linting rules** with ruff
5. **Checks data formatting** with dapperdata
6. **Verifies TOML formatting** with tombi

See the [GitHub Actions documentation](./github.md) for more details on CI configuration.

## Troubleshooting Tests

### Common Issues

**Import Errors**

```bash
# Make sure the package is installed in development mode
make install
```

**Async Tests Not Running**

```python
# Make sure to mark async tests
@pytest.mark.asyncio
async def test_my_async_function():
    await async_operation()
```

**Database Fixture Issues**

```python
# Ensure you're using the correct fixture
@pytest.mark.asyncio
async def test_db_operation(db_session):  # Not db_session_maker
    result = await db_session.execute(query)
```

**Tests Pass Individually But Fail Together**

This usually indicates test isolation issues. Check:

- Are you cleaning up resources?
- Are tests sharing state through global variables?
- Are database transactions being rolled back?

**Coverage Not Including All Files**

Check `pyproject.toml` coverage configuration and ensure files aren't in the omit list.

## References

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio Documentation](https://pytest-asyncio.readthedocs.io/)
- [pytest-cov Documentation](https://pytest-cov.readthedocs.io/)
- [FastAPI Testing Guide](https://fastapi.tiangolo.com/tutorial/testing/)
- [SQLAlchemy Testing Documentation](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites)
