"""Rendering helpers for deterministic script outputs."""

from __future__ import annotations

import json
from typing import Any


def render_json(payload: dict[str, Any]) -> str:
    """Render a payload as stable pretty JSON."""

    return json.dumps(payload, indent=2, sort_keys=True)


def render_sync_markdown(payload: dict[str, Any]) -> str:
    """Render sync status as terminal-friendly markdown."""

    lines = [
        "Intervals Sync Complete",
        "",
        f"Date: {payload['state']['date']}",
        f"Form: {payload['state']['form']} ({payload['metadata']['form_source']})",
        f"Fatigue: {payload['state']['fatigue']}",
        f"Sleep: {payload['state']['sleep']}",
        f"Soreness: {payload['state']['soreness']}",
        f"Last workout type: {payload['state']['last_workout_type']}",
        f"Activities considered: {payload['metadata']['activities_considered']}",
        f"Sync mode: {payload['metadata']['sync_mode']}",
        f"Raw snapshot dir: {payload['metadata']['raw_snapshot_dir']}",
    ]
    if payload["metadata"]["last_activity_date"]:
        lines.append(f"Last run activity date: {payload['metadata']['last_activity_date']}")
    return "\n".join(lines)


def render_training_summary_markdown(payload: dict[str, Any]) -> str:
    """Render a recent training summary."""

    lines = [
        "Training Summary",
        "",
        f"Window: {payload['start_date']} to {payload['end_date']}",
        f"Activities: {payload['activity_count']}",
        f"Distance: {payload['total_distance_km']} km",
        f"Duration: {payload['total_duration_minutes']} min",
    ]
    if payload["average_training_load"] is not None:
        lines.append(f"Average load: {payload['average_training_load']}")

    current_state = payload.get("current_state")
    if current_state is not None:
        lines.extend(
            [
                "",
                "Current State",
                f"Readiness: {current_state['readiness']}",
                f"Recovery flag: {current_state['recovery_flag']}",
                f"Form: {current_state['form']}",
                f"Fatigue: {current_state['fatigue']}",
                f"Acute/chronic ratio: {current_state['acute_chronic_ratio']}",
                f"Days since threshold: {current_state['days_since_threshold']}",
                f"Days since hard: {current_state['days_since_hard']}",
                f"Days since long: {current_state['days_since_long']}",
            ]
        )

    workout_mix = payload.get("workout_mix", {})
    if workout_mix:
        lines.extend(["", "Workout Mix"])
        for workout_type, count in workout_mix.items():
            lines.append(f"- {workout_type}: {count}")

    recent_workouts = payload.get("recent_workouts", [])
    if recent_workouts:
        lines.extend(["", "Recent Workouts"])
        for workout in recent_workouts:
            lines.append(
                f"- {workout['date']}: {workout['name']} ({workout['workout_type']}, "
                f"{workout['distance_km']} km, load {workout['training_load']})"
            )

    return "\n".join(lines)


def render_workout_analysis_markdown(payload: dict[str, Any]) -> str:
    """Render session-level recent workout analysis."""

    lines = [
        "Recent Workout Analysis",
        "",
        f"Activities: {payload['activity_count']}",
    ]
    for item in payload.get("activities", []):
        lines.extend(
            [
                "",
                f"{item['date']} - {item['name']}",
                f"Type: {item['workout_type']}",
                f"Distance: {item['distance_km']} km",
                f"Duration: {item['duration_minutes']} min",
                f"Training load: {item['training_load']}",
                f"Avg pace: {item['avg_pace_min_per_km']}",
                f"Why it mattered: {item['why_it_mattered']}",
            ]
        )
    return "\n".join(lines)


def render_plan_markdown(payload: dict[str, Any]) -> str:
    """Render next-workout or weekly plan output."""

    lines = [
        "Plan Recommendation",
        "",
        f"Mode: {payload['mode']}",
        f"Target date: {payload['target_date']}",
        f"Readiness: {payload['context']['readiness']}",
        f"Recovery flag: {payload['context']['recovery_flag']}",
    ]

    rationale = payload.get("rationale", [])
    if rationale:
        lines.extend(["", "Rationale"])
        for item in rationale:
            lines.append(f"- {item}")

    items = payload.get("items", [])
    if items:
        lines.extend(["", "Suggested Workouts"])
        for item in items:
            lines.extend(
                [
                    f"{item['scheduled_date']} - {item['workout_name']} ({item['workout_type']})",
                    f"Warmup: {item['warmup']}",
                    f"Main set: {item['main_set']}",
                    f"Cooldown: {item['cooldown']}",
                    f"Notes: {item['notes']}",
                    f"Why: {item['rationale']}",
                    "",
                ]
            )
        if lines[-1] == "":
            lines.pop()

    rejected = payload.get("rejected_alternatives", [])
    if rejected:
        lines.extend(["", "Rejected Alternatives"])
        for item in rejected:
            lines.append(f"- {item}")

    return "\n".join(lines)


def render_check_in_markdown(payload: dict[str, Any]) -> str:
    """Render a saved check-in."""

    return "\n".join(
        [
            "Check-in Saved",
            "",
            f"Date: {payload['local_date']}",
            f"Energy: {payload['energy']}",
            f"Sleep: {payload['sleep']}",
            f"Soreness: {payload['soreness']}",
            f"Notes: {payload['notes'] or '(none)'}",
        ]
    )
