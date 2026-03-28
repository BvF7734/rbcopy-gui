# Settings

This project uses [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) for type-safe configuration management with environment variable support.

## Configuration File

All settings live in a single class:

- **`rbcopy/conf/settings.py`**: The `Settings` class (the only settings module)

There is no module-level singleton. Instantiate `Settings()` wherever you need a value — pydantic-settings reads the environment at construction time, so each instance reflects the current environment.

```python
from rbcopy.conf.settings import Settings

settings = Settings()
print(settings.data_dir)
```

## Current Settings

```python
# rbcopy/conf/settings.py
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="RBCOPY_",  # All env vars must be prefixed with RBCOPY_
        extra="ignore",
    )

    data_dir: Path | None = Field(
        default=None,
        description="Override the application data directory (env: RBCOPY_DATA_DIR).",
    )
```

## Environment Variables

All environment variables use the `RBCOPY_` prefix. pydantic-settings strips the prefix automatically when mapping to field names.

| Environment Variable | Field | Default | Description |
|---|---|---|---|
| `RBCOPY_DATA_DIR` | `data_dir` | `None` | Override the application data directory |

### Setting Values

```bash
# Override the data directory
export RBCOPY_DATA_DIR="/custom/path/to/data"

# Or in a .env file
echo 'RBCOPY_DATA_DIR=/custom/path/to/data' > .env
```

When `data_dir` is `None` (default), the application resolves the path using platform defaults in `rbcopy/app_dirs.py`.

## Developer Environment

Copy `.env.example` to `.env` and edit the values for your local setup:

```bash
cp .env.example .env
```

The `.env` file is listed in `.gitignore` — never commit it to the repository.

## Adding New Settings

Add fields to the `Settings` class in `rbcopy/conf/settings.py`. Follow these rules:

- Use `Field(description=...)` so the setting is self-documenting
- Use `SecretStr` / `SecretBytes` for any sensitive value (passwords, tokens)
- Default optional fields to `None`, not to empty strings
- Update `tests/test_conf_settings.py` to cover the new field

```python
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="RBCOPY_",
        extra="ignore",
    )

    data_dir: Path | None = Field(
        default=None,
        description="Override the application data directory (env: RBCOPY_DATA_DIR).",
    )

    # Example: adding a new optional setting
    log_level: str = Field(
        default="INFO",
        description="Logging level (env: RBCOPY_LOG_LEVEL).",
    )

    # Example: adding a sensitive setting
    api_token: SecretStr | None = Field(
        default=None,
        description="Optional API token (env: RBCOPY_API_TOKEN).",
    )
```

The corresponding env vars would be `RBCOPY_LOG_LEVEL` and `RBCOPY_API_TOKEN`.

## Testing Settings

Override settings in tests using environment variable patching via `monkeypatch` or `unittest.mock.patch.dict`:

```python
import os
from unittest.mock import patch
from rbcopy.conf.settings import Settings


def test_data_dir_from_env(tmp_path):
    """RBCOPY_DATA_DIR is picked up from the environment."""
    with patch.dict(os.environ, {"RBCOPY_DATA_DIR": str(tmp_path)}):
        s = Settings()
        assert s.data_dir == tmp_path


def test_data_dir_defaults_to_none():
    """data_dir is None when RBCOPY_DATA_DIR is not set."""
    with patch.dict(os.environ, {}, clear=True):
        s = Settings(_env_file=None)  # skip .env file for isolation
        assert s.data_dir is None
```

See `tests/test_conf_settings.py` for the full test suite.
