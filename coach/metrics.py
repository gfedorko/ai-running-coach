"""Derived metrics and summary helpers built from normalized training history."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, timedelta
from typing import Any

from coach.readiness import cap_readiness, determine_readiness
from coach.storage import DailyMetricRecord


def rebuild_daily_metrics(
    activities: list[dict[str, Any]],
    wellness_entries: list[dict[str, Any]],
    check_ins: list[dict[str, Any]],
    *,
    end_date: str,
    default_last_workout_type: str = "easy",
    seed_form: int = 0,
    seed_sleep: str = "good",
    seed_soreness: str = "low",
) -> list[DailyMetricRecord]:
    """Recompute all daily metrics from normalized inputs."""

    end_day = date.fromisoformat(end_date)
    all_dates = [
        date.fromisoformat(item["activity_date"])
        for item in activities
        if item.get("activity_date")
    ]
    all_dates.extend(
        date.fromisoformat(item["local_date"])
        for item in wellness_entries
        if item.get("local_date")
    )
    all_dates.extend(
        date.fromisoformat(item["local_date"])
        for item in check_ins
        if item.get("local_date")
    )
    if all_dates:
        start_day = min(all_dates)
    else:
        start_day = end_day

    return rebuild_daily_metrics_range(
        activities,
        wellness_entries,
        check_ins,
        start_date=start_day.isoformat(),
        end_date=end_date,
        default_last_workout_type=default_last_workout_type,
        seed_form=seed_form,
        seed_sleep=seed_sleep,
        seed_soreness=seed_soreness,
    )


def rebuild_daily_metrics_range(
    activities: list[dict[str, Any]],
    wellness_entries: list[dict[str, Any]],
    check_ins: list[dict[str, Any]],
    *,
    start_date: str,
    end_date: str,
    default_last_workout_type: str = "easy",
    seed_form: int = 0,
    seed_sleep: str = "good",
    seed_soreness: str = "low",
    initial_latest_wellness: dict[str, Any] | None = None,
) -> list[DailyMetricRecord]:
    """Recompute derived metrics for a bounded date range."""

    start_day = date.fromisoformat(start_date)
    end_day = date.fromisoformat(end_date)
    if start_day > end_day:
        return []

    activity_buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for activity in activities:
        activity_buckets[activity["activity_date"]].append(activity)

    wellness_by_date = {entry["local_date"]: entry for entry in wellness_entries}
    check_in_by_date = {entry["local_date"]: entry for entry in check_ins}

    metrics: list[DailyMetricRecord] = []
    latest_wellness: dict[str, Any] | None = initial_latest_wellness
    last_workout_type = default_last_workout_type

    current = start_day
    while current <= end_day:
        local_date = current.isoformat()
        todays_activities = activity_buckets.get(local_date, [])
        window_7 = _window_activities(activity_buckets, current, 7)
        window_14 = _window_activities(activity_buckets, current, 14)
        window_28 = _window_activities(activity_buckets, current, 28)

        quality_sessions_7d = sum(
            1 for item in window_7 if item["workout_type"] in {"threshold", "hard"}
        )
        quality_sessions_14d = sum(
            1 for item in window_14 if item["workout_type"] in {"threshold", "hard"}
        )
        if todays_activities:
            last_workout_type = todays_activities[-1]["workout_type"]

        if local_date in wellness_by_date:
            latest_wellness = wellness_by_date[local_date]
        current_check_in = check_in_by_date.get(local_date)

        form, form_source = derive_form(
            latest_wellness=latest_wellness,
            recent_activities=window_7[:3],
            fallback_form=seed_form if not metrics else metrics[-1].form,
        )
        fatigue = derive_fatigue(
            form=form,
            latest_wellness=latest_wellness,
            recent_activities=window_7[:3],
        )
        sleep = derive_sleep(
            latest_wellness=latest_wellness,
            current_check_in=current_check_in,
            fallback_sleep=seed_sleep if not metrics else metrics[-1].sleep,
        )
        soreness = derive_soreness(
            latest_wellness=latest_wellness,
            current_check_in=current_check_in,
            fallback_soreness=seed_soreness if not metrics else metrics[-1].soreness,
        )
        readiness = determine_readiness(form)
        acute_load = average_training_load(window_7)
        chronic_load = average_training_load(window_28)
        acute_chronic_ratio = (
            round(acute_load / chronic_load, 2)
            if acute_load is not None and chronic_load not in (None, 0)
            else None
        )
        recovery_flag = derive_recovery_flag(
            fatigue=fatigue,
            sleep=sleep,
            soreness=soreness,
            acute_chronic_ratio=acute_chronic_ratio,
            current_check_in=current_check_in,
        )
        if recovery_flag == "needs_recovery":
            readiness = cap_readiness(readiness, "easy_only")
        elif recovery_flag == "caution":
            readiness = cap_readiness(readiness, "steady_allowed")

        metrics.append(
            DailyMetricRecord(
                local_date=local_date,
                total_distance_7d=round(sum_distance(window_7), 2),
                total_duration_7d=round(sum_duration(window_7), 1),
                total_distance_14d=round(sum_distance(window_14), 2),
                total_duration_14d=round(sum_duration(window_14), 1),
                total_distance_28d=round(sum_distance(window_28), 2),
                total_duration_28d=round(sum_duration(window_28), 1),
                avg_load_7d=acute_load,
                avg_load_14d=average_training_load(window_14),
                avg_load_28d=chronic_load,
                acute_load=acute_load,
                chronic_load=chronic_load,
                acute_chronic_ratio=acute_chronic_ratio,
                days_since_threshold=days_since_workout_type(
                    activity_buckets, current, "threshold"
                ),
                days_since_hard=days_since_workout_type(activity_buckets, current, "hard"),
                days_since_long=days_since_workout_type(activity_buckets, current, "long"),
                quality_sessions_7d=quality_sessions_7d,
                quality_sessions_14d=quality_sessions_14d,
                longest_run_14d=round(longest_distance(window_14), 2),
                longest_run_28d=round(longest_distance(window_28), 2),
                form=form,
                form_source=form_source,
                fatigue=fatigue,
                sleep=sleep,
                soreness=soreness,
                readiness=readiness,
                recovery_flag=recovery_flag,
                last_workout_type=last_workout_type,
            )
        )
        current += timedelta(days=1)

    return metrics


def build_training_summary(
    metrics_row: dict[str, Any] | None,
    activities: list[dict[str, Any]],
    *,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Assemble a summary payload for recent training chat."""

    total_distance = round(sum_distance(activities), 2)
    total_duration = round(sum_duration(activities), 1)
    total_load = [item["training_load"] for item in activities if item["training_load"] is not None]
    workout_counts: dict[str, int] = defaultdict(int)
    for activity in activities:
        workout_counts[activity["workout_type"]] += 1

    recent = [
        {
            "date": item["activity_date"],
            "name": item["name"],
            "workout_type": item["workout_type"],
            "distance_km": item["distance_km"],
            "duration_minutes": item["duration_minutes"],
            "training_load": item["training_load"],
        }
        for item in activities[:5]
    ]
    summary = {
        "start_date": start_date,
        "end_date": end_date,
        "activity_count": len(activities),
        "total_distance_km": total_distance,
        "total_duration_minutes": total_duration,
        "average_training_load": round(sum(total_load) / len(total_load), 1) if total_load else None,
        "workout_mix": dict(sorted(workout_counts.items())),
        "recent_workouts": recent,
    }
    if metrics_row is None:
        summary["current_state"] = None
        return summary

    summary["current_state"] = {
        "form": metrics_row["form"],
        "readiness": metrics_row["readiness"],
        "recovery_flag": metrics_row["recovery_flag"],
        "fatigue": metrics_row["fatigue"],
        "sleep": metrics_row["sleep"],
        "soreness": metrics_row["soreness"],
        "acute_load": metrics_row["acute_load"],
        "chronic_load": metrics_row["chronic_load"],
        "acute_chronic_ratio": metrics_row["acute_chronic_ratio"],
        "days_since_threshold": metrics_row["days_since_threshold"],
        "days_since_hard": metrics_row["days_since_hard"],
        "days_since_long": metrics_row["days_since_long"],
        "quality_sessions_7d": metrics_row["quality_sessions_7d"],
        "quality_sessions_14d": metrics_row["quality_sessions_14d"],
        "longest_run_14d": metrics_row["longest_run_14d"],
    }
    return summary


def analyze_workouts(
    activities: list[dict[str, Any]],
    metrics_by_date: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Assemble session-level analysis for recent workouts."""

    entries = []
    for activity in activities:
        metric = metrics_by_date.get(activity["activity_date"])
        entries.append(
            {
                "date": activity["activity_date"],
                "name": activity["name"],
                "workout_type": activity["workout_type"],
                "distance_km": activity["distance_km"],
                "duration_minutes": activity["duration_minutes"],
                "training_load": activity["training_load"],
                "avg_pace_min_per_km": activity["avg_pace_min_per_km"],
                "why_it_mattered": explain_workout_role(activity, metric),
            }
        )
    return {
        "activity_count": len(entries),
        "activities": entries,
    }


def explain_workout_role(
    activity: dict[str, Any],
    metric: dict[str, Any] | None,
) -> str:
    """Explain the role of a workout in the recent training context."""

    workout_type = activity["workout_type"]
    if workout_type == "long":
        return "Anchored endurance and weekly long-run cadence."
    if workout_type == "hard":
        return "Delivered top-end quality and should be protected with recovery spacing."
    if workout_type == "threshold":
        return "Supported aerobic quality without full hard-session cost."
    if workout_type == "steady":
        return "Added controlled aerobic work between easier or higher-stress sessions."
    if metric is not None and metric["recovery_flag"] == "needs_recovery":
        return "Served as a low-stress run during a recovery-leaning period."
    return "Added low-risk aerobic volume."


def derive_form(
    *,
    latest_wellness: dict[str, Any] | None,
    recent_activities: list[dict[str, Any]],
    fallback_form: int,
) -> tuple[int, str]:
    """Determine form from wellness or recent load history."""

    if latest_wellness is not None:
        for key, label in (
            ("freshness", "Intervals wellness freshness"),
            ("form", "Intervals wellness form"),
            ("tsb", "Intervals wellness TSB"),
        ):
            value = latest_wellness.get(key)
            if value is not None:
                return int(round(float(value))), label

    recent_loads = [
        item["training_load"]
        for item in recent_activities
        if item["training_load"] is not None
    ]
    if recent_loads:
        average_load = sum(recent_loads) / len(recent_loads)
        if average_load >= 80:
            return -22, "Fallback load trend (heavy recent load)"
        if average_load >= 50:
            return -10, "Fallback load trend (moderate recent load)"
        if average_load >= 25:
            return -3, "Fallback load trend (light recent load)"
        return 0, "Fallback load trend (very light recent load)"

    return min(fallback_form, 0), "Fallback existing state clamp"


def derive_fatigue(
    *,
    form: int,
    latest_wellness: dict[str, Any] | None,
    recent_activities: list[dict[str, Any]],
) -> str:
    """Bucket fatigue from current form plus wellness/load signals."""

    severity = 0
    if form <= -20:
        severity = max(severity, 2)
    elif form <= -5:
        severity = max(severity, 1)

    atl_load = _numeric_value(latest_wellness, "atl_load", "atlLoad")
    if atl_load is not None:
        if atl_load >= 90:
            severity = max(severity, 2)
        elif atl_load >= 45:
            severity = max(severity, 1)

    average_load = average_training_load(recent_activities)
    if average_load is not None:
        if average_load >= 90:
            severity = max(severity, 2)
        elif average_load >= 45:
            severity = max(severity, 1)

    subjective_fatigue = _numeric_value(latest_wellness, "fatigue")
    if subjective_fatigue is not None:
        if subjective_fatigue >= 4:
            severity = max(severity, 2)
        elif subjective_fatigue >= 2:
            severity = max(severity, 1)

    return ("low", "moderate", "high")[severity]


def derive_sleep(
    *,
    latest_wellness: dict[str, Any] | None,
    current_check_in: dict[str, Any] | None,
    fallback_sleep: str,
) -> str:
    """Derive a human-readable sleep bucket."""

    if current_check_in is not None and current_check_in.get("sleep"):
        return str(current_check_in["sleep"])

    sleep_secs = _numeric_value(latest_wellness, "sleep_secs", "sleepSecs")
    if sleep_secs is None:
        return fallback_sleep
    if sleep_secs >= 7 * 60 * 60:
        return "good"
    if sleep_secs >= 6 * 60 * 60:
        return "okay"
    return "poor"


def derive_soreness(
    *,
    latest_wellness: dict[str, Any] | None,
    current_check_in: dict[str, Any] | None,
    fallback_soreness: str,
) -> str:
    """Derive a human-readable soreness bucket."""

    if current_check_in is not None and current_check_in.get("soreness"):
        return str(current_check_in["soreness"])

    soreness = _numeric_value(latest_wellness, "soreness")
    if soreness is None:
        return fallback_soreness
    if soreness <= 2:
        return "low"
    if soreness <= 3:
        return "moderate"
    return "high"


def derive_recovery_flag(
    *,
    fatigue: str,
    sleep: str,
    soreness: str,
    acute_chronic_ratio: float | None,
    current_check_in: dict[str, Any] | None,
) -> str:
    """Turn fatigue and recovery signals into a planning guardrail."""

    severity = 0
    if fatigue == "high":
        severity = max(severity, 2)
    elif fatigue == "moderate":
        severity = max(severity, 1)

    if sleep == "poor":
        severity = max(severity, 2)
    elif sleep == "okay":
        severity = max(severity, 1)

    if soreness == "high":
        severity = max(severity, 2)
    elif soreness == "moderate":
        severity = max(severity, 1)

    if acute_chronic_ratio is not None:
        if acute_chronic_ratio >= 1.35:
            severity = max(severity, 2)
        elif acute_chronic_ratio >= 1.15:
            severity = max(severity, 1)

    if current_check_in is not None:
        energy = current_check_in.get("energy")
        if energy == "low":
            severity = max(severity, 2)
        elif energy == "okay":
            severity = max(severity, 1)

    return ("good", "caution", "needs_recovery")[severity]


def average_training_load(activities: list[dict[str, Any]]) -> float | None:
    """Average non-null training load values."""

    loads = [item["training_load"] for item in activities if item["training_load"] is not None]
    if not loads:
        return None
    return round(sum(loads) / len(loads), 1)


def sum_distance(activities: list[dict[str, Any]]) -> float:
    """Total distance in km across activities."""

    return sum(item["distance_km"] or 0 for item in activities)


def sum_duration(activities: list[dict[str, Any]]) -> float:
    """Total duration in minutes across activities."""

    return sum(item["duration_minutes"] or 0 for item in activities)


def longest_distance(activities: list[dict[str, Any]]) -> float:
    """Largest single-run distance in a list."""

    return max((item["distance_km"] or 0 for item in activities), default=0.0)


def days_since_workout_type(
    activities_by_date: dict[str, list[dict[str, Any]]],
    current_day: date,
    workout_type: str,
) -> int | None:
    """Return days since the last matching workout type on or before current day."""

    cursor = current_day
    while cursor >= current_day - timedelta(days=90):
        current_items = activities_by_date.get(cursor.isoformat(), [])
        if any(item["workout_type"] == workout_type for item in current_items):
            return (current_day - cursor).days
        cursor -= timedelta(days=1)
    return None


def as_dicts(records: list[DailyMetricRecord]) -> list[dict[str, Any]]:
    """Convert metric dataclasses to plain dicts for storage and output."""

    return [asdict(record) for record in records]


def _window_activities(
    buckets: dict[str, list[dict[str, Any]]],
    current_day: date,
    days: int,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for offset in range(days):
        day = (current_day - timedelta(days=offset)).isoformat()
        items.extend(buckets.get(day, []))
    return items


def _numeric_value(payload: dict[str, Any] | None, *keys: str) -> float | None:
    if payload is None:
        return None
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        return float(value)
    return None
