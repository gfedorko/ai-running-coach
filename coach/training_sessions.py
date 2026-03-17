"""Generic one-off training session helpers for the broader training coach."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(slots=True)
class TrainingSession:
    """A single scheduled training session across supported workout domains."""

    scheduled_date: str
    domain: str
    session_type: str
    title: str
    duration_minutes: int
    load_category: str
    export_capabilities: tuple[str, ...]
    goal_tags: tuple[str, ...]
    notes: str
    details: dict[str, Any]


def build_one_off_session(
    profile,
    *,
    domain: str,
    request_type: str,
    scheduled_date: date,
) -> TrainingSession:
    """Build a deterministic one-off session for a supported domain."""

    if domain == "run":
        return _build_run_session(profile, request_type=request_type, scheduled_date=scheduled_date)
    if domain == "strength":
        return _build_strength_session(profile, scheduled_date=scheduled_date)
    if domain == "mobility":
        return _build_mobility_session(profile, scheduled_date=scheduled_date)
    raise ValueError(f"Unsupported one-off session domain: {domain}")


def render_training_session(session: TrainingSession) -> str:
    """Render a training session for chat or calendar-oriented previews."""

    lines = [
        "One-Off Session",
        "",
        f"Date: {session.scheduled_date}",
        f"Domain: {session.domain}",
        f"Type: {session.session_type}",
        f"Title: {session.title}",
        f"Duration: {session.duration_minutes} min",
        f"Export: {', '.join(session.export_capabilities)}",
        f"Goals: {', '.join(session.goal_tags)}",
        "",
        "Details",
    ]
    for key, value in session.details.items():
        lines.append(f"- {key.replace('_', ' ').title()}: {value}")
    lines.extend(["", "Notes", session.notes])
    return "\n".join(lines)


def _build_run_session(profile, *, request_type: str, scheduled_date: date) -> TrainingSession:
    easy_pace = _pace_display(getattr(profile, "easy_pace_min_per_km", 6.0))
    threshold_pace = _pace_display(getattr(profile, "threshold_pace_min_per_km", 5.0))
    if request_type == "intervals":
        details = {
            "focus": "speed_support",
            "warmup": f"12 min easy @ {easy_pace}",
            "main_set": f"6 x 3 min @ {threshold_pace} with 2 min easy jog",
            "cooldown": f"10 min easy @ {easy_pace}",
        }
        return TrainingSession(
            scheduled_date=scheduled_date.isoformat(),
            domain="run",
            session_type="intervals",
            title="One-Off Interval Session",
            duration_minutes=52,
            load_category="hard",
            export_capabilities=("fit", "calendar", "markdown"),
            goal_tags=("speed", "running_economy"),
            notes="Bounded one-off run session generated from profile pace anchors.",
            details=details,
        )
    raise ValueError(f"Unsupported run request type: {request_type}")


def _build_strength_session(profile, *, scheduled_date: date) -> TrainingSession:
    strength_profile = getattr(profile, "strength_profile", None)
    duration = int(getattr(strength_profile, "preferred_session_duration_min", None) or 40)
    equipment = getattr(strength_profile, "equipment", None) or "bodyweight, dumbbells"
    focus = getattr(strength_profile, "preferred_split_style", None) or "durability"
    details = {
        "focus": focus,
        "equipment": equipment,
        "block_1": "Goblet squat 3 x 8, single-leg RDL 3 x 8/side",
        "block_2": "Split squat 3 x 8/side, calf raise 3 x 12",
        "core": "Dead bug 3 x 8/side, side plank 2 x 30 sec/side",
    }
    return TrainingSession(
        scheduled_date=scheduled_date.isoformat(),
        domain="strength",
        session_type="strength",
        title="Strength Support Session",
        duration_minutes=duration,
        load_category="moderate",
        export_capabilities=("calendar", "markdown"),
        goal_tags=("durability", "strength"),
        notes="Keep the work smooth and controlled. Stop 2 reps shy of failure.",
        details=details,
    )


def _build_mobility_session(profile, *, scheduled_date: date) -> TrainingSession:
    mobility_profile = getattr(profile, "mobility_profile", None)
    duration = int(getattr(mobility_profile, "preferred_session_duration_min", None) or 20)
    focus_area = getattr(mobility_profile, "focus_area", None) or "ankles, hips"
    details = {
        "focus_area": focus_area,
        "flow": "Ankle rocks, 90/90 transitions, hip flexor stretch, thoracic rotations",
        "rounds": "2 rounds, easy breathing throughout",
    }
    return TrainingSession(
        scheduled_date=scheduled_date.isoformat(),
        domain="mobility",
        session_type="mobility",
        title="Recovery Mobility Session",
        duration_minutes=duration,
        load_category="light",
        export_capabilities=("calendar", "markdown"),
        goal_tags=("recovery", "mobility"),
        notes="Stay relaxed and use the session to downshift rather than chase range.",
        details=details,
    )


def _pace_display(minutes_per_km: float) -> str:
    total_seconds = round(minutes_per_km * 60)
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d}/km"
