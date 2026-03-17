"""Compatibility wrapper around the canonical FIT export module."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from coach.fit_export import export_plan_fit


def export_week_plan(base_dir: Path, planned_week_or_payload: Any) -> Path:
    """Export a weekly plan and return the output directory path."""

    if hasattr(planned_week_or_payload, "start_date"):
        output_dir = base_dir / "output" / "plans" / planned_week_or_payload.start_date
    else:
        output_dir = base_dir / "output" / "plans" / planned_week_or_payload["target_date"]

    artifact_summary = export_plan_fit(planned_week_or_payload, output_dir=output_dir)
    return Path(artifact_summary["output_dir"])
