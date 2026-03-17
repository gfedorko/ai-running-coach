"""Helpers for importing small repo-local dependencies."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_local_vendor_path() -> None:
    """Add the repo-local `.vendor` directory to `sys.path` when present."""

    repo_root = Path(__file__).resolve().parents[1]
    vendor_dir = repo_root / ".vendor"
    if vendor_dir.exists() and str(vendor_dir) not in sys.path:
        sys.path.insert(0, str(vendor_dir))
