"""Application settings for rbcopy.

Manages environment-level configuration via :class:`pydantic_settings.BaseSettings`.
Settings are read from environment variables and from a ``.env`` file in the
working directory (if present).

The primary settings class is :class:`Settings`.  Instantiate it fresh wherever
you need a runtime-resolved value — pydantic-settings reads from the environment
at construction time, so there is no need for a module-level singleton.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the rbcopy application.

    Values are populated (in priority order) from:
    1. Explicitly passed keyword arguments (useful in tests).
    2. Environment variables matching the ``RBCOPY_`` prefix.
    3. A ``.env`` file in the current working directory.
    4. Field defaults declared below.

    Attributes:
        data_dir: Override the application data directory.  When ``None`` the
            directory is resolved by the platform-default or bootstrap-file
            logic in :mod:`rbcopy.app_dirs`.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # All project env vars are prefixed with RBCOPY_; pydantic-settings
        # strips the prefix when mapping to field names, so RBCOPY_DATA_DIR
        # maps automatically to `data_dir`.
        env_prefix="RBCOPY_",
        extra="ignore",
    )

    data_dir: Path | None = Field(
        default=None,
        description="Override the application data directory (env: RBCOPY_DATA_DIR).",
    )
