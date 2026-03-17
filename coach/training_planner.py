"""Compatibility wrapper for the canonical DB-backed planner."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from coach.planner import generate_plan as canonical_generate_plan


def generate_plan(
    base_dir: Path,
    *,
    mode: str,
    target_date: str | None = None,
    persist: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Preserve the historical import path for the canonical planner."""

    return canonical_generate_plan(
        base_dir,
        mode=mode,
        target_date=target_date,
        persist=persist,
        now=now,
    )
