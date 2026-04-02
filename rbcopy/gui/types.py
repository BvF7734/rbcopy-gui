"""Shared type definitions for rbcopy GUI widgets."""

from __future__ import annotations

from typing import TypedDict


class _PackPadding(TypedDict):
    """Keyword arguments for ttk widget .pack() calls that add consistent spacing."""

    padx: int
    pady: int
