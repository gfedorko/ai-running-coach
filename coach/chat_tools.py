"""Bounded chat helpers over the deterministic local coaching engine."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from coach.data_paths import resolve_runtime_paths
from coach.fit_export import build_plan_fit_bundle, write_plan_fit_bundle
from coach.goals import load_current_goal
from coach.intervals import IntervalsPushSummary, push_weekly_plan_to_intervals
from coach.metrics import analyze_workouts, build_training_summary
from coach.planner import (
    generate_forecast_plan,
    generate_plan,
    render_forecast_markdown,
    render_week_markdown,
    weekly_plan_from_payload,
)
from coach.render import render_training_summary_markdown, render_workout_analysis_markdown
from coach.training_sessions import build_one_off_session, render_training_session
from coach.storage import (
    PlanningRequestRecord,
    PreferenceEventRecord,
    TrainingSessionRecord,
    connect_database,
    fetch_activities,
    fetch_daily_metrics_between,
    fetch_latest_check_in,
    fetch_latest_daily_metric,
)


def summarize_training(base_dir: Path, *, days: int = 7, end_date: str | None = None) -> str:
    """Summarize recent training from the DB-backed history."""

    end_value = date.fromisoformat(end_date) if end_date else datetime.now().astimezone().date()
    start_value = end_value - timedelta(days=days - 1)
    paths = resolve_runtime_paths(base_dir)
    with connect_database(paths.training_db) as connection:
        activities = [
            dict(row)
            for row in fetch_activities(
                connection,
                start_date=start_value.isoformat(),
                end_date=end_value.isoformat(),
            )
        ]
        metric = fetch_latest_daily_metric(connection, end_value.isoformat())
    payload = build_training_summary(
        dict(metric) if metric is not None else None,
        activities,
        start_date=start_value.isoformat(),
        end_date=end_value.isoformat(),
    )
    return render_training_summary_markdown(payload)


def analyze_recent_workouts(base_dir: Path, *, days: int = 14) -> str:
    """Explain the role of recent workouts from normalized local history."""

    end_value = datetime.now().astimezone().date()
    start_value = end_value - timedelta(days=days - 1)
    paths = resolve_runtime_paths(base_dir)
    with connect_database(paths.training_db) as connection:
        activities = [
            dict(row)
            for row in fetch_activities(
                connection,
                start_date=start_value.isoformat(),
                end_date=end_value.isoformat(),
            )
        ]
        metrics_by_date = {
            row["local_date"]: dict(row)
            for row in fetch_daily_metrics_between(
                connection,
                start_value.isoformat(),
                end_value.isoformat(),
            )
        }
    return render_workout_analysis_markdown(analyze_workouts(activities, metrics_by_date))


def explain_readiness(base_dir: Path, *, on_date: str | None = None) -> str:
    """Explain readiness, fatigue, and recovery using the latest stored metrics."""

    target_date = on_date or datetime.now().astimezone().date().isoformat()
    paths = resolve_runtime_paths(base_dir)
    with connect_database(paths.training_db) as connection:
        metric = fetch_latest_daily_metric(connection, target_date)
        check_in = fetch_latest_check_in(connection, target_date)

    if metric is None:
        raise ValueError("No derived metrics available. Run sync_intervals.py first.")

    lines = [
        "Readiness Status",
        "",
        f"Date: {metric['local_date']}",
        f"Readiness: {metric['readiness']}",
        f"Recovery flag: {metric['recovery_flag']}",
        f"Form: {metric['form']}",
        f"Fatigue: {metric['fatigue']}",
        f"Sleep: {metric['sleep']}",
        f"Soreness: {metric['soreness']}",
        f"Acute/chronic ratio: {metric['acute_chronic_ratio']}",
        f"Days since threshold: {metric['days_since_threshold']}",
        f"Days since hard: {metric['days_since_hard']}",
        f"Days since long: {metric['days_since_long']}",
        "",
        "Why",
        _readiness_reason(metric),
    ]
    if check_in is not None:
        lines.extend(
            [
                "",
                "Latest Check-in",
                f"Energy: {check_in['energy'] or '(unset)'}",
                f"Sleep: {check_in['sleep'] or '(unset)'}",
                f"Soreness: {check_in['soreness'] or '(unset)'}",
                f"Notes: {check_in['notes'] or '(none)'}",
            ]
        )
    return "\n".join(lines)


def analyze_last_week_against_goal(base_dir: Path) -> str:
    """Compare the most recent completed 7 days against the stored weekly goal."""

    current_date = datetime.now().astimezone().date()
    end_value = current_date - timedelta(days=1)
    start_value = end_value - timedelta(days=6)
    paths = resolve_runtime_paths(base_dir)
    goal = load_current_goal(paths.current_goal)

    with connect_database(paths.training_db) as connection:
        activities = [
            dict(row)
            for row in fetch_activities(
                connection,
                start_date=start_value.isoformat(),
                end_date=end_value.isoformat(),
            )
        ]

    total_distance = round(sum(float(item.get("distance_km") or 0.0) for item in activities), 2)
    run_count = len(activities)
    quality_sessions = sum(
        1
        for item in activities
        if str(item.get("workout_type", "")).lower() in {"threshold", "hard"}
    )
    long_runs = [
        float(item.get("distance_km") or 0.0)
        for item in activities
        if str(item.get("workout_type", "")).lower() == "long"
    ]
    distance_delta = round(total_distance - goal.target_weekly_volume_km, 2)

    lines = [
        "Last Week vs Goal",
        "",
        f"Window: {start_value.isoformat()} to {end_value.isoformat()}",
        f"Goal weekly volume: {goal.target_weekly_volume_km} km",
        f"Actual distance: {total_distance} km",
        f"Distance delta: {distance_delta:+} km",
        f"Run count: {run_count} / target {goal.weekly_run_days}",
        f"Quality sessions: {quality_sessions}",
        f"Longest long run: {max(long_runs) if long_runs else 0.0} km",
        "",
        "Assessment",
        _goal_assessment(distance_delta, run_count, goal.weekly_run_days, quality_sessions),
    ]
    return "\n".join(lines)


def plan_next_week(base_dir: Path, *, persist: bool = True) -> str:
    """Generate and render next week's canonical plan."""

    payload = generate_plan(base_dir, mode="weekly", persist=persist)
    plan = weekly_plan_from_payload(payload)
    return "\n\n".join([render_week_markdown(plan), "Why This Week", *payload["rationale"]])


def explain_plan_choice(base_dir: Path) -> str:
    """Explain why each workout in next week's plan was chosen."""

    payload = generate_plan(base_dir, mode="weekly", persist=False)
    lines = ["Plan Rationale", ""]
    for item in payload["items"]:
        lines.append(f"{item['scheduled_date']} - {item['workout_name']}")
        lines.append(f"Why: {item['rationale']}")
        lines.append("")
    lines.append("Week Logic")
    lines.extend(f"- {reason}" for reason in payload["rationale"])
    return "\n".join(lines).rstrip()


def export_fit(
    base_dir: Path,
    *,
    anchor_date: date | None = None,
    local_only: bool = False,
) -> str:
    """Generate next week, export FIT artifacts, and optionally push to Intervals."""

    payload = generate_plan(
        base_dir,
        mode="weekly",
        target_date=anchor_date.isoformat() if anchor_date is not None else None,
        persist=True,
    )
    plan = weekly_plan_from_payload(payload)
    bundle = build_plan_fit_bundle(
        payload,
        output_dir=base_dir / "output" / "plans" / plan.start_date,
    )
    artifacts = write_plan_fit_bundle(bundle)
    push_summary = None if local_only else push_weekly_plan_to_intervals(
        plan,
        bundle.fit_exports_by_external_id,
    )

    lines = [
        "FIT Export Complete" if local_only or (push_summary and push_summary.success) else "FIT Export Partial Success",
        "",
        f"Output directory: {artifacts['output_dir']}",
        f"Weekly plan: {artifacts['weekly_plan_markdown']}",
        f"FIT files written: {len(artifacts['fit_files'])}",
        f"Validation passed: {artifacts['validation_summary']['passed']}",
        *render_intervals_push_lines(plan.start_date, push_summary, local_only=local_only),
        "FIT files:",
    ]
    lines.extend(f"- {path}" for path in artifacts["fit_files"])
    return "\n".join(lines)


def preview_forecast(base_dir: Path, *, weeks: int = 4) -> str:
    """Render the next forecast window without writing or pushing anything."""

    return render_forecast_markdown(generate_forecast_plan(base_dir, weeks=weeks))


def export_forecast_locally(base_dir: Path, *, weeks: int = 4) -> str:
    """Write local-only FIT artifacts for the forecast window."""

    forecast = generate_forecast_plan(base_dir, weeks=weeks)
    output_dirs: list[str] = []
    fit_count = 0
    validation_passed = True
    for week in forecast.weeks:
        artifacts = write_plan_fit_bundle(
            build_plan_fit_bundle(
                week,
                output_dir=base_dir / "output" / "plans" / week.start_date,
            )
        )
        output_dirs.append(str(artifacts["output_dir"]))
        fit_count += len(artifacts["fit_files"])
        validation_passed = validation_passed and bool(artifacts["validation_summary"]["passed"])

    lines = [
        "Forecast FIT Export Complete",
        "",
        f"Weeks generated: {len(forecast.weeks)}",
        f"FIT files written: {fit_count}",
        f"Validation passed: {validation_passed}",
        "Output directories:",
    ]
    lines.extend(f"- {path}" for path in output_dirs)
    return "\n".join(lines)


def answer_chat_query(base_dir: Path, query: str) -> str:
    """Route a bounded natural-language query to the supported local tools."""

    normalized = query.strip().lower()
    if not normalized:
        return supported_actions_text()
    if _looks_like_preference_save(normalized):
        return save_preference(base_dir, normalized)
    if _looks_like_one_off_session_request(normalized):
        return create_one_off_session(base_dir, normalized)
    if _looks_like_last_week_review(normalized):
        return analyze_last_week_against_goal(base_dir)
    if _mentions_four_week_forecast(normalized) and any(token in normalized for token in ("generate", "fit", "export")):
        return export_forecast_locally(base_dir)
    if _mentions_four_week_forecast(normalized) and any(token in normalized for token in ("preview", "plan", "forecast")):
        return preview_forecast(base_dir)
    if "fit" in normalized and "next week" in normalized:
        local_only = "local" in normalized or "locally" in normalized
        return export_fit(base_dir, local_only=local_only)
    if "why" in normalized and ("workout" in normalized or "week" in normalized):
        return explain_plan_choice(base_dir)
    if "plan" in normalized and "next week" in normalized:
        return plan_next_week(base_dir)
    if "last week" in normalized and "goal" in normalized:
        return analyze_last_week_against_goal(base_dir)
    if any(token in normalized for token in ("readiness", "ready", "fatigue", "recovery")):
        on_date = None
        if "tomorrow" in normalized:
            on_date = (datetime.now().astimezone().date() + timedelta(days=1)).isoformat()
        return explain_readiness(base_dir, on_date=on_date)
    if "analy" in normalized and "workout" in normalized:
        return analyze_recent_workouts(base_dir)
    if any(token in normalized for token in ("summarize", "summary", "recent training", "how was my")):
        return summarize_training(base_dir)
    return (
        "I can help with a fixed set of coaching actions.\n\n"
        f"{supported_actions_text()}\n\n"
        "Try one of:\n"
        "- summarize my recent training\n"
        "- explain my readiness\n"
        "- analyze last week against my goal\n"
        "- plan next week\n"
        "- explain why each workout was chosen\n"
        "- generate FIT files for next week\n"
        "- generate FIT files locally for next week\n"
        "- preview the next 4 weeks\n"
        "- generate the next 4 weeks locally\n"
        "- create intervals tomorrow\n"
        "- create a strength workout today\n"
        "- create a mobility session tonight\n"
        "- remember that I prefer strength on Thursdays"
    )


def supported_actions_text() -> str:
    """List supported chat actions."""

    return (
        "Supported actions: summarize recent training, explain readiness, "
        "analyze last week against goal, plan next week, explain plan rationale, "
        "preview the next 4 weeks, export FIT files with optional local-only export, "
        "create one-off run/strength/mobility sessions, and save simple training preferences."
    )


def _mentions_four_week_forecast(normalized: str) -> bool:
    return ("4 week" in normalized or "four week" in normalized) and "next" in normalized


def render_intervals_push_lines(
    week_start: str,
    push_summary: IntervalsPushSummary | None,
    *,
    local_only: bool,
) -> list[str]:
    """Render Intervals push status for chat or CLI output."""

    if local_only:
        return ["Intervals push: skipped (local-only export)"]
    if push_summary is None:
        return ["Intervals push: skipped"]
    if push_summary.success:
        return [
            "Intervals push: complete",
            f"Deleted stale managed events: {push_summary.deleted_count}",
            f"Workouts upserted to Intervals: {push_summary.upserted_count}",
        ]
    return [
        "Intervals push: failed",
        f"Deleted stale managed events before failure: {push_summary.deleted_count}",
        f"Workouts upserted before failure: {push_summary.upserted_count}",
        f"Failure: {push_summary.failure_message}",
        f"Retry with: python scripts/push_intervals_week.py --week-of {week_start}",
    ]


def _readiness_reason(metric) -> str:
    if metric["recovery_flag"] == "needs_recovery":
        return "Recovery is capped by current fatigue, sleep, soreness, or load ratio, so the planner stays conservative."
    if metric["recovery_flag"] == "caution":
        return "You can still train, but the planner should avoid stacking high stress until recovery markers improve."
    return "Recovery markers are stable enough for the current readiness bucket."


def _goal_assessment(distance_delta: float, run_count: int, target_run_days: int, quality_sessions: int) -> str:
    if distance_delta < -10:
        return "You were materially under target volume, so next week should rebuild gradually instead of forcing intensity."
    if distance_delta > 10:
        return "You overshot the weekly volume target, so the next plan should be careful about adding more stress."
    if run_count < target_run_days:
        return "Volume was near target, but consistency lagged the intended run frequency."
    if quality_sessions >= 2:
        return "The week already carried meaningful quality stress, so the next plan should protect recovery spacing."
    return "The week was reasonably aligned with the current goal and can progress normally."


def create_one_off_session(base_dir: Path, normalized: str) -> str:
    """Create and render a bounded one-off session request."""

    paths = resolve_runtime_paths(base_dir)
    target_date = _requested_session_date(normalized)
    profile = _load_profile(paths)

    if "strength" in normalized:
        session = build_one_off_session(
            profile,
            domain="strength",
            request_type="strength",
            scheduled_date=target_date,
        )
    elif "mobility" in normalized or "recovery" in normalized:
        session = build_one_off_session(
            profile,
            domain="mobility",
            request_type="mobility",
            scheduled_date=target_date,
        )
    elif "interval" in normalized:
        session = build_one_off_session(
            profile,
            domain="run",
            request_type="intervals",
            scheduled_date=target_date,
        )
    else:
        return supported_actions_text()

    _persist_one_off_session(paths.training_db, normalized, session)
    return render_training_session(session)


def save_preference(base_dir: Path, normalized: str) -> str:
    """Persist a simple bounded training preference when storage support exists."""

    paths = resolve_runtime_paths(base_dir)
    payload = _preference_payload(normalized)
    _persist_preference(paths.training_db, normalized, payload)
    return (
        "Saved preference\n\n"
        f"Key: {payload['key']}\n"
        f"Value: {payload['value']}\n"
        "This has been stored locally for future training-session and planning integrations."
    )


def _load_profile(paths):
    from coach.athlete import load_athlete_profile

    return load_athlete_profile(paths.athlete_profile)


def _requested_session_date(normalized: str) -> date:
    current_date = datetime.now().astimezone().date()
    if "tomorrow" in normalized:
        return current_date + timedelta(days=1)
    return current_date


def _looks_like_one_off_session_request(normalized: str) -> bool:
    if "create" not in normalized:
        return False
    return any(token in normalized for token in ("interval", "strength", "mobility", "recovery"))


def _looks_like_preference_save(normalized: str) -> bool:
    return normalized.startswith("remember ") or normalized.startswith("remember that ")


def _looks_like_last_week_review(normalized: str) -> bool:
    if "last week" not in normalized:
        return False
    return any(token in normalized for token in ("how did", "how was", "review", "analy", "go"))


def _preference_payload(normalized: str) -> dict[str, str]:
    if "strength" in normalized and "thursday" in normalized:
        return {"key": "preferred_strength_days", "value": "Thursdays"}
    return {"key": "saved_preference", "value": normalized.removeprefix("remember that ").removeprefix("remember ").strip()}


def _persist_one_off_session(training_db: Path, normalized: str, session) -> None:
    """Persist request/session records when the generic storage helpers exist."""

    import coach.storage as storage

    insert_request = getattr(storage, "insert_planning_request", None)
    insert_session = getattr(storage, "insert_training_session", None)
    if insert_request is None and insert_session is None:
        return

    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    session_id = f"session:{session.domain}:{session.scheduled_date}:{session.session_type}"
    request_id = f"request:{session.domain}:{session.scheduled_date}:{session.session_type}"
    with connect_database(training_db) as connection:
        if insert_request is not None:
            insert_request(
                connection,
                PlanningRequestRecord(
                    request_id=request_id,
                    created_at=stamp,
                    intent="create_one_off_session",
                    parameters={
                        "query": normalized,
                        "domain": session.domain,
                        "session_type": session.session_type,
                        "scheduled_date": session.scheduled_date,
                    },
                ),
            )
        if insert_session is not None:
            insert_session(
                connection,
                TrainingSessionRecord(
                    session_id=session_id,
                    created_at=stamp,
                    scheduled_date=session.scheduled_date,
                    domain=session.domain,
                    session_type=session.session_type,
                    title=session.title,
                    payload={
                        "duration_minutes": session.duration_minutes,
                        "load_category": session.load_category,
                        "source": "chat",
                        "export_capabilities": list(session.export_capabilities),
                        "goal_tags": list(session.goal_tags),
                        "notes": session.notes,
                        "details": session.details,
                        "planning_request_id": request_id,
                    },
                ),
            )
        connection.commit()


def _persist_preference(training_db: Path, normalized: str, payload: dict[str, str]) -> None:
    """Persist preference records when the generic storage helpers exist."""

    import coach.storage as storage

    insert_preference = getattr(storage, "insert_preference_event", None)
    insert_request = getattr(storage, "insert_planning_request", None)
    if insert_preference is None and insert_request is None:
        return

    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with connect_database(training_db) as connection:
        if insert_request is not None:
            insert_request(
                connection,
                PlanningRequestRecord(
                    request_id=f"request:preference:{payload['key']}:{stamp}",
                    created_at=stamp,
                    intent="save_preference",
                    parameters={"query": normalized, **payload},
                ),
            )
        if insert_preference is not None:
            insert_preference(
                connection,
                PreferenceEventRecord(
                    event_id=f"preference:{payload['key']}:{stamp}",
                    created_at=stamp,
                    preference_type=payload["key"],
                    details={"value": payload["value"], "source": "chat"},
                ),
            )
        connection.commit()
