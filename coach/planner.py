"""Canonical DB-backed planner and structured weekly plan models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from coach.athlete import AthleteProfile, load_athlete_profile
from coach.data_paths import resolve_runtime_paths
from coach.goals import load_current_goal
from coach.metrics import average_training_load, rebuild_daily_metrics_range, sum_distance, sum_duration
from coach.readiness import cap_readiness, determine_readiness
from coach.storage import (
    connect_database,
    fetch_all_activities,
    fetch_all_check_ins,
    fetch_activities,
    fetch_latest_check_in,
    fetch_latest_daily_metric,
    insert_plan,
)
from coach.workouts import StructuredWorkoutTemplate, load_structured_workout_library
from coach.zones import easy_range, hard_range, long_range, steady_range, threshold_range


DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
EASY_FILL_ORDER = ["Wednesday", "Sunday", "Friday", "Monday", "Thursday", "Tuesday", "Saturday"]
MARATHON_PRIMARY_QUALITY_MIN_VOLUME_RATIO = 0.75
MARATHON_FULL_LONG_MIN_VOLUME_RATIO = 0.80
FORECAST_DEFAULT_WEEKS = 4
FORECAST_WEEKLY_LOAD_GROWTH = 1.08
FORECAST_RECOVERY_CUTBACK = 0.90
FORECAST_PRIMARY_INTRO_RATIO = 0.75
FORECAST_LONG_RUN_STEP_MINUTES = 10
WORKOUT_NAME_TWISTS = {
    "easy": "Easy Aerobic Run",
    "steady": "Steady Aerobic Run",
    "threshold": "Threshold Session",
    "hard": "Hard Intervals",
    "long": "Long Run",
    "reduced_long": "Reduced Long Run",
}
WORKOUT_NOTE_TWISTS = {
    "easy": "Comfortable aerobic maintenance run with controlled effort throughout.",
    "steady": "Controlled aerobic work without drifting toward race effort.",
    "threshold": "Strong aerobic quality without full race intensity.",
    "hard": "High-end aerobic work reserved for clearly positive readiness days.",
    "long": "Durable aerobic volume with controlled pacing throughout.",
    "reduced_long": "Conservative long aerobic session when readiness is limited.",
}


@dataclass(slots=True)
class StepDuration:
    """A normalized workout step duration."""

    kind: str
    value: int


@dataclass(slots=True)
class StepTarget:
    """A normalized workout step target."""

    kind: str
    label: str
    display: str
    pace_fast_min_per_km: float | None = None
    pace_slow_min_per_km: float | None = None


@dataclass(slots=True)
class WorkoutStep:
    """A single structured step that can be previewed or exported to FIT."""

    name: str
    duration: StepDuration
    target: StepTarget
    note: str


@dataclass(slots=True)
class PlannedWorkout:
    """A planned workout for a calendar day."""

    date: str
    name: str
    workout_type: str
    steps: list[WorkoutStep]
    notes: str
    template_key: str
    source_template: str
    fit_exportable: bool

    @property
    def external_id(self) -> str:
        return f"run-coach:workout:{self.date}"


@dataclass(slots=True)
class WeeklyPlan:
    """A Monday-Sunday training plan."""

    anchor_date: str
    start_date: str
    end_date: str
    readiness: str
    workouts: list[PlannedWorkout]
    rest_dates: list[str]
    rationale: list[str]
    goal_summary: str

    def render(self) -> str:
        """Format the weekly plan for terminal preview."""

        workout_by_date = {workout.date: workout for workout in self.workouts}
        lines = [
            "Weekly Workout Preview",
            "",
            f"Week: {self.start_date} to {self.end_date}",
            f"Readiness: {self.readiness}",
            f"Goal: {self.goal_summary}",
            "",
        ]

        current_day = date.fromisoformat(self.start_date)
        for day_offset in range(7):
            workout_date = current_day + timedelta(days=day_offset)
            date_key = workout_date.isoformat()
            label = DAY_NAMES[workout_date.weekday()]
            workout = workout_by_date.get(date_key)
            if workout is None:
                lines.append(f"{label} {date_key}: Rest")
                continue

            lines.append(f"{label} {date_key}: {workout.name} ({workout.workout_type})")
            for step in workout.steps:
                lines.append(
                    f"  - {step.name}: {format_duration(step.duration)}"
                    f" | {step.target.display}"
                    f" | {step.note}"
                )
        return "\n".join(lines)


@dataclass(slots=True)
class ForecastWeekSummary:
    """Projected end-of-week state for one forecasted week."""

    week_index: int
    start_date: str
    end_date: str
    load_target_km: float
    projected_distance_km: float
    projected_duration_minutes: float
    projected_average_training_load: float | None
    projected_form: int
    projected_readiness: str
    projected_recovery_flag: str


@dataclass(slots=True)
class ForecastPlan:
    """A deterministic multiweek forecast built from actual plus projected load."""

    anchor_date: str
    start_date: str
    end_date: str
    weeks: list[WeeklyPlan]
    summaries: list[ForecastWeekSummary]
    rationale: list[str]
    goal_summary: str

    def render(self) -> str:
        """Format the multiweek forecast for terminal preview."""

        lines = [
            "Four-Week Forecast",
            "",
            f"Window: {self.start_date} to {self.end_date}",
            f"Goal: {self.goal_summary}",
            "",
        ]
        for summary, week in zip(self.summaries, self.weeks):
            lines.extend(
                [
                    f"Week {summary.week_index + 1}: {summary.start_date} to {summary.end_date}",
                    f"  Load target: {summary.load_target_km:.1f} km",
                    f"  Projected distance: {summary.projected_distance_km:.1f} km",
                    f"  Projected duration: {summary.projected_duration_minutes:.1f} min",
                    f"  Projected readiness: {summary.projected_readiness}",
                    f"  Projected recovery flag: {summary.projected_recovery_flag}",
                ]
            )
            workout_by_date = {workout.date: workout for workout in week.workouts}
            current_day = date.fromisoformat(week.start_date)
            for day_offset in range(7):
                workout_date = current_day + timedelta(days=day_offset)
                workout = workout_by_date.get(workout_date.isoformat())
                label = DAY_NAMES[workout_date.weekday()]
                if workout is None:
                    lines.append(f"  {label} {workout_date.isoformat()}: Rest")
                    continue
                lines.append(f"  {label} {workout.date}: {workout.name}")
            lines.append("")
        lines.append("Rationale")
        lines.extend(f"- {reason}" for reason in self.rationale)
        return "\n".join(lines).rstrip()


def generate_plan(
    base_dir: Path,
    *,
    mode: str = "next",
    target_date: str | None = None,
    persist: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Generate the canonical next-workout or weekly plan payload."""

    current_time = now if now is not None else datetime.now().astimezone()
    current_date = current_time.date()
    requested_date = date.fromisoformat(target_date) if target_date else current_date
    paths = resolve_runtime_paths(base_dir)
    should_persist = persist and paths.profile_name == "local"

    if mode == "weekly":
        forecast = generate_forecast_plan(
            base_dir,
            anchor_date=requested_date if target_date else None,
            weeks=1,
        )
        payload = weekly_plan_to_payload(forecast.weeks[0])
        if should_persist:
            with connect_database(paths.training_db) as connection:
                plan_id = insert_plan(
                    connection,
                    created_at=current_time.isoformat(timespec="seconds"),
                    mode=mode,
                    target_date=payload["target_date"],
                    summary="Weekly training plan",
                    rationale={"items": payload["rationale"], "rejected": payload["rejected_alternatives"]},
                    inputs={"context": payload["context"]},
                    output=payload,
                    items=payload["items"],
                )
                payload["plan_id"] = plan_id
                connection.commit()
        return payload

    if mode != "next":
        raise ValueError(f"Unsupported mode: {mode}")

    profile = load_athlete_profile(paths.athlete_profile)
    templates = load_structured_workout_library(paths.workout_library)
    week_start = monday_of(requested_date)
    context_date = min(requested_date, current_date)
    goal = load_current_goal(paths.current_goal)

    with connect_database(paths.training_db) as connection:
        metric = fetch_latest_daily_metric(connection, context_date.isoformat())
        if metric is None:
            raise ValueError("No derived metrics available. Run sync_intervals.py first.")

        context = dict(metric)
        context.update(
            build_history_context(
                connection,
                end_date=context_date,
                target_weekly_volume_km=goal.target_weekly_volume_km,
            )
        )
        context["current_phase"] = goal.current_phase
        context["target_race_distance_km"] = goal.target_race_distance_km
        context["target_weekly_volume_km"] = goal.target_weekly_volume_km
        context["target_weekly_run_days"] = goal.weekly_run_days
        latest_check_in = fetch_latest_check_in(connection, context_date.isoformat())
        if latest_check_in is not None:
            context["current_check_in"] = dict(latest_check_in)

        workout, rationale = build_next_workout(
            profile=profile,
            templates=templates,
            context=context,
            scheduled_date=requested_date,
        )
        payload = next_workout_to_payload(
            workout=workout,
            rationale=rationale,
            target_date=requested_date.isoformat(),
            context=context,
        )

        if should_persist:
            plan_id = insert_plan(
                connection,
                created_at=current_time.isoformat(timespec="seconds"),
                mode=mode,
                target_date=payload["target_date"],
                summary=payload["items"][0]["workout_name"],
                rationale={"items": payload["rationale"], "rejected": payload["rejected_alternatives"]},
                inputs={"context": payload["context"]},
                output=payload,
                items=payload["items"],
            )
            payload["plan_id"] = plan_id
            connection.commit()

    return payload


def generate_forecast_plan(
    base_dir: Path,
    anchor_date: date | None = None,
    *,
    weeks: int = FORECAST_DEFAULT_WEEKS,
) -> ForecastPlan:
    """Return a deterministic multiweek forecast anchored to one calendar week."""

    current_date = datetime.now().astimezone().date()
    requested_date = anchor_date or current_date
    week_start = monday_of(requested_date) if anchor_date is not None else next_monday(current_date)
    context_date = min(requested_date, current_date)

    paths = resolve_runtime_paths(base_dir)
    profile = load_athlete_profile(paths.athlete_profile)
    goal = load_current_goal(paths.current_goal)
    templates = load_structured_workout_library(paths.workout_library)

    with connect_database(paths.training_db) as connection:
        metric = fetch_latest_daily_metric(connection, context_date.isoformat())
        if metric is None:
            raise ValueError("No derived metrics available. Run sync_intervals.py first.")

        context = dict(metric)
        context.update(
            build_history_context(
                connection,
                end_date=context_date,
                target_weekly_volume_km=goal.target_weekly_volume_km,
            )
        )
        context["current_phase"] = goal.current_phase
        context["target_race_distance_km"] = goal.target_race_distance_km
        context["target_weekly_volume_km"] = goal.target_weekly_volume_km
        context["target_weekly_run_days"] = goal.weekly_run_days
        latest_check_in = fetch_latest_check_in(connection, context_date.isoformat())
        if latest_check_in is not None:
            context["current_check_in"] = dict(latest_check_in)

        activities = [
            dict(row)
            for row in fetch_all_activities(connection)
            if row["activity_date"] <= context_date.isoformat()
        ]
        check_ins = [
            dict(row)
            for row in fetch_all_check_ins(connection)
            if row["local_date"] <= context_date.isoformat()
        ]

    return build_forecast_plan(
        profile=profile,
        goal=goal,
        templates=templates,
        context=context,
        activities=activities,
        check_ins=check_ins,
        week_start=week_start,
        anchor_date=requested_date,
        weeks=weeks,
    )


def generate_weekly_plan(base_dir: Path, anchor_date: date | None = None) -> WeeklyPlan:
    """Return a structured weekly plan for preview, FIT export, or upload."""

    payload = generate_plan(
        base_dir,
        mode="weekly",
        target_date=anchor_date.isoformat() if anchor_date is not None else None,
        persist=False,
    )
    return weekly_plan_from_payload(payload)


def build_forecast_plan(
    *,
    profile: AthleteProfile,
    goal,
    templates: dict[str, StructuredWorkoutTemplate],
    context: dict[str, Any],
    activities: list[dict[str, Any]],
    check_ins: list[dict[str, Any]],
    week_start: date,
    anchor_date: date,
    weeks: int,
) -> ForecastPlan:
    """Build a rolling multiweek forecast from actual plus projected workouts."""

    forecast_weeks: list[WeeklyPlan] = []
    summaries: list[ForecastWeekSummary] = []
    rationale = [
        f"Forecast starts from {week_start.isoformat()} and uses projected workouts as completed.",
        "Future readiness and fatigue are derived from projected activities plus the latest known subjective recovery signals.",
        "Publish cadence stays one week at a time even when previewing farther ahead locally.",
    ]

    projected_activities = list(activities)
    projected_check_ins = list(check_ins)
    latest_check_in = check_ins[-1] if check_ins else None
    seed_form = int(context["form"])
    seed_sleep = str(context["sleep"])
    seed_soreness = str(context["soreness"])
    previous_load_target = float(context.get("recent_total_distance_km") or 0.0) or float(goal.target_weekly_volume_km) * 0.6
    current_context = dict(context)
    current_context["forecast_previous_long_minutes"] = 0

    for week_index in range(weeks):
        current_week_start = week_start + timedelta(days=week_index * 7)
        current_context["forecast_enabled"] = True
        current_context["hard_intervals_disabled"] = marathon_build_context(current_context)
        current_context["forecast_week_index"] = week_index
        current_context["forecast_load_target_km"] = forecast_load_target_km(
            previous_load_target,
            current_context,
        )

        weekly_plan = build_weekly_plan(
            profile=profile,
            goal=goal,
            templates=templates,
            context=current_context,
            week_start=current_week_start,
            anchor_date=anchor_date,
        )
        forecast_weeks.append(weekly_plan)

        projected_week_activities = [
            synthetic_activity_from_workout(workout, profile=profile, sequence=index)
            for index, workout in enumerate(weekly_plan.workouts, start=1)
        ]
        projected_activities.extend(projected_week_activities)
        projected_check_ins.extend(
            frozen_check_ins_for_range(
                latest_check_in,
                start_date=current_week_start,
                end_date=current_week_start + timedelta(days=6),
            )
        )
        projected_metrics = rebuild_daily_metrics_range(
            projected_activities,
            [],
            projected_check_ins,
            start_date=min(
                [item["activity_date"] for item in projected_activities]
                + [current_week_start.isoformat()]
            ),
            end_date=(current_week_start + timedelta(days=6)).isoformat(),
            default_last_workout_type=str(context.get("last_workout_type") or "easy"),
            seed_form=seed_form,
            seed_sleep=seed_sleep,
            seed_soreness=seed_soreness,
        )
        metric_by_date = {row.local_date: row for row in projected_metrics}
        week_end = (current_week_start + timedelta(days=6)).isoformat()
        end_metric = metric_by_date[week_end]
        week_distance = round(sum_distance(projected_week_activities), 2)
        week_duration = round(sum_duration(projected_week_activities), 1)
        summaries.append(
            ForecastWeekSummary(
                week_index=week_index,
                start_date=current_week_start.isoformat(),
                end_date=week_end,
                load_target_km=float(current_context["forecast_load_target_km"]),
                projected_distance_km=week_distance,
                projected_duration_minutes=week_duration,
                projected_average_training_load=average_training_load(projected_week_activities),
                projected_form=end_metric.form,
                projected_readiness=end_metric.readiness,
                projected_recovery_flag=end_metric.recovery_flag,
            )
        )

        previous_long_minutes = max(
            (
                estimate_workout_duration_minutes(workout)
                for workout in weekly_plan.workouts
                if workout.workout_type == "long"
            ),
            default=int(current_context.get("forecast_previous_long_minutes") or 0),
        )
        previous_load_target = week_distance or float(current_context["forecast_load_target_km"])
        current_context = metric_context_from_forecast(
            metric=end_metric,
            activities=projected_activities,
            end_date=date.fromisoformat(week_end),
            goal=goal,
            current_check_in=latest_check_in,
            previous_long_minutes=previous_long_minutes,
        )

    return ForecastPlan(
        anchor_date=anchor_date.isoformat(),
        start_date=forecast_weeks[0].start_date,
        end_date=forecast_weeks[-1].end_date,
        weeks=forecast_weeks,
        summaries=summaries,
        rationale=rationale,
        goal_summary=goal_summary_text(goal),
    )


def build_weekly_plan(
    *,
    profile: AthleteProfile,
    goal,
    templates: dict[str, StructuredWorkoutTemplate],
    context: dict[str, Any],
    week_start: date,
    anchor_date: date,
    forecast_summary: ForecastWeekSummary | None = None,
) -> WeeklyPlan:
    """Build a Monday-Sunday plan from DB-derived context and local goal settings."""

    schedule = build_week_schedule(goal)
    current_context = dict(context)
    workouts: list[PlannedWorkout] = []
    rest_dates: list[str] = []
    rationale: list[str] = [
        f"Weekly plan anchored to {week_start.isoformat()} with readiness {adjusted_readiness(current_context)}.",
        goal_summary_text(goal),
    ]

    for day_offset in range(7):
        workout_date = week_start + timedelta(days=day_offset)
        day_name = workout_date.strftime("%A")
        role = schedule.get(day_name)
        if role is None:
            rest_dates.append(workout_date.isoformat())
            current_context = advance_context_for_rest(current_context)
            rationale.append(f"{workout_date.isoformat()} {day_name}: rest day to protect recovery/load balance.")
            continue

        template_key, reason = choose_template_key_for_role(
            role=role,
            context=current_context,
        )
        template_key = resolve_template_key(
            template_key,
            context=current_context,
            templates=templates,
        )
        workout = instantiate_workout(templates[template_key], workout_date, profile)
        workouts.append(workout)
        rationale.append(f"{workout_date.isoformat()} {day_name}: {reason}")
        current_context = advance_context(current_context, workout.workout_type)

    if forecast_summary is not None:
        rationale.append(
            "Projected week target "
            f"{forecast_summary.load_target_km:.1f} km with end-state "
            f"{forecast_summary.projected_readiness}/{forecast_summary.projected_recovery_flag}."
        )

    return WeeklyPlan(
        anchor_date=anchor_date.isoformat(),
        start_date=week_start.isoformat(),
        end_date=(week_start + timedelta(days=6)).isoformat(),
        readiness=adjusted_readiness(context),
        workouts=workouts,
        rest_dates=rest_dates,
        rationale=rationale,
        goal_summary=goal_summary_text(goal),
    )


def build_next_workout(
    *,
    profile: AthleteProfile,
    templates: dict[str, StructuredWorkoutTemplate],
    context: dict[str, Any],
    scheduled_date: date,
) -> tuple[PlannedWorkout, list[str]]:
    """Build the next recommended workout from DB-derived readiness and spacing."""

    template_key, reason = choose_template_key_for_role(
        role="next",
        context=context,
    )
    workout = instantiate_workout(templates[template_key], scheduled_date, profile)
    rationale = [
        f"Next workout for {scheduled_date.isoformat()} uses readiness {adjusted_readiness(context)}.",
        reason,
    ]
    return workout, rationale


def weekly_plan_to_payload(plan: WeeklyPlan) -> dict[str, Any]:
    """Convert a structured weekly plan into the canonical plan payload."""

    items = []
    for workout in plan.workouts:
        warmup, main_set, cooldown = render_workout_blocks(workout)
        items.append(
            {
                "scheduled_date": workout.date,
                "workout_name": workout.name,
                "workout_type": workout.workout_type,
                "warmup": warmup,
                "main_set": main_set,
                "cooldown": cooldown,
                "notes": workout.notes,
                "rationale": next(
                    (reason for reason in plan.rationale if workout.date in reason),
                    plan.rationale[-1],
                ),
                "template_key": workout.template_key,
                "source_template": workout.source_template,
                "fit_exportable": workout.fit_exportable,
                "structured_workout": serialize_planned_workout(workout),
            }
        )

    return {
        "mode": "weekly",
        "target_date": plan.start_date,
        "context": {
            "readiness": plan.readiness,
            "recovery_flag": "weekly_plan",
            "goal_summary": plan.goal_summary,
        },
        "rationale": list(plan.rationale),
        "rejected_alternatives": [],
        "items": items,
    }


def next_workout_to_payload(
    *,
    workout: PlannedWorkout,
    rationale: list[str],
    target_date: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Convert one structured workout into the canonical payload shape."""

    warmup, main_set, cooldown = render_workout_blocks(workout)
    return {
        "mode": "next",
        "target_date": target_date,
        "context": {
            "readiness": adjusted_readiness(context),
            "recovery_flag": context["recovery_flag"],
            "form": context["form"],
            "days_since_threshold": context["days_since_threshold"],
            "days_since_hard": context["days_since_hard"],
            "days_since_long": context["days_since_long"],
            "history_complete": context.get("history_complete"),
            "overloaded": context.get("overloaded"),
        },
        "rationale": rationale,
        "rejected_alternatives": [],
        "items": [
            {
                "scheduled_date": workout.date,
                "workout_name": workout.name,
                "workout_type": workout.workout_type,
                "warmup": warmup,
                "main_set": main_set,
                "cooldown": cooldown,
                "notes": workout.notes,
                "rationale": rationale[-1],
                "template_key": workout.template_key,
                "source_template": workout.source_template,
                "fit_exportable": workout.fit_exportable,
                "structured_workout": serialize_planned_workout(workout),
            }
        ],
    }


def build_week_schedule(goal) -> dict[str, str | None]:
    """Build the Monday-Sunday role schedule from goal preferences."""

    schedule = {day_name: None for day_name in DAY_NAMES}
    preferred_quality_days = goal.preferred_quality_days or ["Tuesday", "Thursday"]
    is_marathon_phase = marathon_build_goal(goal)

    assign_role(schedule, preferred_quality_days[0], "primary_quality")
    if goal.weekly_run_days >= 4:
        assign_role(
            schedule,
            preferred_quality_days[1] if len(preferred_quality_days) > 1 else "Thursday",
            "secondary_support" if is_marathon_phase else "secondary_quality",
        )
    if goal.weekly_run_days >= 3:
        assign_role(schedule, goal.preferred_long_run_day, "long")

    run_days = sum(role is not None for role in schedule.values())
    for day_name in EASY_FILL_ORDER:
        if run_days >= goal.weekly_run_days:
            break
        if schedule[day_name] is None:
            schedule[day_name] = "easy"
            run_days += 1

    return schedule


def assign_role(schedule: dict[str, str | None], preferred_day: str, role: str) -> None:
    """Assign a weekly role, falling back to the next open day if needed."""

    desired = normalize_day_name(preferred_day)
    if schedule.get(desired) is None:
        schedule[desired] = role
        return
    for fallback in DAY_NAMES:
        if schedule[fallback] is None:
            schedule[fallback] = role
            return


def choose_template_key_for_role(*, role: str, context: dict[str, Any]) -> tuple[str, str]:
    """Select the structured workout template key for a weekly role."""

    readiness = adjusted_readiness(context)
    conservative = bool(context.get("conservative_week"))
    marathon_phase = marathon_build_context(context)
    last_workout = str(context["last_workout_type"]).lower()
    days_since_threshold = context["days_since_threshold"]
    days_since_hard = context["days_since_hard"]
    days_since_long = context["days_since_long"]
    supports_primary_quality = marathon_primary_quality_supported(context)
    supports_full_long = marathon_full_long_supported(context)

    if role == "long":
        if conservative or readiness == "easy_only" or context["recovery_flag"] == "needs_recovery":
            return "reduced_long", "Readiness is constrained, so the long run stays reduced and fully aerobic."
        if marathon_phase and not supports_full_long:
            return (
                "reduced_long",
                "Recent marathon-build volume is short of the target week, so the long run stays reduced until the aerobic base is more consistent.",
            )
        return "long", "Long-run cadence is due and current readiness supports the full long-run template."

    if role == "primary_quality":
        if conservative and readiness != "easy_only":
            return "steady", "Recent history is incomplete or overloaded, so the main quality slot is capped at steady."
        if marathon_phase and not supports_primary_quality:
            return (
                "steady",
                "Marathon quality stays aerobic until recent run frequency and weekly volume are closer to the target build.",
            )
        if marathon_phase and readiness in {"hard_allowed", "threshold_allowed"} and (
            days_since_threshold is None or days_since_threshold >= 3
        ) and last_workout not in {"hard", "threshold"}:
            return "threshold", "Marathon build weeks prioritize threshold-style quality over harder interval work."
        if context.get("hard_intervals_disabled"):
            return "steady", "Hard interval work stays disabled in the forecasted marathon build, so quality remains aerobic."
        if readiness == "hard_allowed" and (days_since_hard is None or days_since_hard >= 8) and last_workout not in {"hard", "threshold"}:
            return "hard", "Form is positive and enough spacing exists for a hard primary session."
        if readiness in {"hard_allowed", "threshold_allowed"} and (days_since_threshold is None or days_since_threshold >= 3) and last_workout not in {"hard", "threshold"}:
            return "threshold", "Threshold work fits the current readiness and recent quality spacing."
        if readiness == "easy_only":
            return "easy", "Recovery limits quality work, so the primary slot becomes an easy run."
        return "steady", "Primary quality is downgraded to steady aerobic work by current readiness."

    if role == "secondary_support":
        if conservative or readiness == "easy_only" or context["recovery_flag"] == "needs_recovery":
            return "easy", "The marathon support day stays easy because recovery is limited."
        if marathon_phase and not supports_primary_quality:
            return "easy", "Recent volume is still catching up, so the support day stays easy rather than adding more marathon-specific stress."
        return "steady", "The marathon support day stays aerobic and controlled rather than becoming a second hard session."

    if role == "secondary_quality":
        if conservative or readiness == "easy_only" or context["recovery_flag"] == "needs_recovery":
            return "easy", "The supporting quality day stays easy because recovery is limited."
        return "steady", "The supporting quality day becomes steady aerobic work instead of another hard session."

    if role == "next":
        if readiness == "easy_only":
            return "easy", "The next workout stays easy because readiness is capped by recovery."
        if conservative:
            if days_since_long is None or days_since_long >= 6:
                return "reduced_long", "History coverage is limited, so the next recommendation stays conservative with a reduced long aerobic run."
            return "steady", "History coverage is limited, so the next recommendation stays steady rather than quality."
        if days_since_long is None or days_since_long >= 6:
            if last_workout not in {"hard", "threshold"}:
                if marathon_phase and not supports_full_long:
                    return (
                        "reduced_long",
                        "The long-run slot is due, but recent weekly volume is still below the marathon-build target, so the recommendation stays reduced.",
                    )
                return "long", "Long-run cadence is due and recent quality spacing allows it."
        if marathon_phase and not supports_primary_quality:
            if last_workout in {"hard", "threshold", "long"}:
                return "easy", "Recent training already carried meaningful stress, so the next session stays easy while the marathon base catches up."
            return "steady", "Marathon quality stays aerobic until recent weekly volume and frequency are more consistent."
        if marathon_phase and readiness in {"hard_allowed", "threshold_allowed"} and (
            days_since_threshold is None or days_since_threshold >= 3
        ) and last_workout not in {"hard", "threshold"}:
            return "threshold", "Marathon build weeks favor threshold work before harder interval sessions."
        if context.get("hard_intervals_disabled"):
            return "steady", "Forecasted marathon build weeks keep the next quality session below hard-interval intensity."
        if readiness == "hard_allowed" and (days_since_hard is None or days_since_hard >= 8) and last_workout not in {"hard", "threshold"}:
            return "hard", "Form supports a hard session and enough time has passed since the last one."
        if readiness in {"hard_allowed", "threshold_allowed"} and (days_since_threshold is None or days_since_threshold >= 3) and last_workout not in {"hard", "threshold"}:
            return "threshold", "Threshold work is due and fits the current readiness better than another easy day."
        if last_workout in {"hard", "threshold", "long"}:
            return "easy", "The most recent workout was stressful, so the next session stays easy."
        return "steady", "A steady aerobic run is the best low-risk next session."

    return "easy", "Remaining run days stay easy to protect recovery and total load."


def adjusted_readiness(context: dict[str, Any]) -> str:
    """Apply recovery and check-in caps to the stored readiness bucket."""

    readiness = str(context["readiness"])
    if context["recovery_flag"] == "needs_recovery":
        readiness = cap_readiness(readiness, "easy_only")
    elif context["recovery_flag"] == "caution":
        readiness = cap_readiness(readiness, "steady_allowed")

    current_check_in = context.get("current_check_in")
    if current_check_in is not None:
        if current_check_in.get("energy") == "low":
            readiness = cap_readiness(readiness, "easy_only")
        elif current_check_in.get("energy") == "okay":
            readiness = cap_readiness(readiness, "steady_allowed")
        if current_check_in.get("sleep") == "poor" or current_check_in.get("soreness") == "high":
            readiness = cap_readiness(readiness, "easy_only")
    return readiness


def advance_context(context: dict[str, Any], workout_type: str) -> dict[str, Any]:
    """Simulate context progression after a planned workout."""

    next_context = dict(context)
    normalized_type = workout_type.lower()
    next_context["last_workout_type"] = normalized_type
    for key in ("days_since_threshold", "days_since_hard", "days_since_long"):
        if next_context.get(key) is not None:
            next_context[key] += 1

    if normalized_type == "threshold":
        next_context["days_since_threshold"] = 0
        next_context["recovery_flag"] = "caution"
    elif normalized_type == "hard":
        next_context["days_since_hard"] = 0
        next_context["recovery_flag"] = "caution"
        next_context["readiness"] = cap_readiness(str(next_context["readiness"]), "threshold_allowed")
    elif normalized_type == "long":
        next_context["days_since_long"] = 0
        next_context["recovery_flag"] = "caution"
    else:
        if next_context["recovery_flag"] == "caution":
            next_context["recovery_flag"] = "good"

    return next_context


def advance_context_for_rest(context: dict[str, Any]) -> dict[str, Any]:
    """Simulate one rest day inside the planned week."""

    next_context = dict(context)
    for key in ("days_since_threshold", "days_since_hard", "days_since_long"):
        if next_context.get(key) is not None:
            next_context[key] += 1
    if next_context["recovery_flag"] in {"caution", "needs_recovery"}:
        next_context["recovery_flag"] = "good"
    return next_context


def instantiate_workout(
    template: StructuredWorkoutTemplate,
    workout_date: date,
    profile: AthleteProfile,
) -> PlannedWorkout:
    """Convert a structured template into a concrete workout instance."""

    steps = [
        WorkoutStep(
            name=step_template.name,
            duration=StepDuration(step_template.duration_kind, step_template.duration_value),
            target=resolve_target(profile, step_template.target),
            note=stylize_step_note(step_template.name, step_template.note),
        )
        for step_template in template.steps
    ]
    return PlannedWorkout(
        date=workout_date.isoformat(),
        name=stylize_workout_name(template.key, template.name),
        workout_type=template.workout_type,
        steps=steps,
        notes=stylize_workout_notes(template.key, template.notes),
        template_key=template.key,
        source_template=template.name,
        fit_exportable=True,
    )


def stylize_workout_name(template_key: str, fallback_name: str) -> str:
    """Return the display title for a planned workout."""

    return WORKOUT_NAME_TWISTS.get(template_key_family(template_key), fallback_name)


def stylize_workout_notes(template_key: str, fallback_notes: str) -> str:
    """Return display notes for a planned workout."""

    return WORKOUT_NOTE_TWISTS.get(template_key_family(template_key), fallback_notes)


def template_key_family(template_key: str) -> str:
    """Collapse forecast template variants back to their family key."""

    for family in ("reduced_long", "threshold", "steady", "easy", "long", "hard"):
        if template_key == family or template_key.startswith(f"{family}_"):
            return family
    return template_key


def resolve_template_key(
    template_key: str,
    *,
    context: dict[str, Any],
    templates: dict[str, StructuredWorkoutTemplate],
) -> str:
    """Resolve a workout family key to an explicit forecast variant when enabled."""

    if not context.get("forecast_enabled"):
        return template_key

    candidate = choose_forecast_variant(template_key, context)
    if candidate in templates:
        return candidate
    return template_key


def choose_forecast_variant(template_key: str, context: dict[str, Any]) -> str:
    """Pick an explicit workout template variant for the forecast week."""

    target_volume = float(context.get("forecast_load_target_km") or context.get("recent_total_distance_km") or 0.0)
    goal_volume = float(context.get("target_weekly_volume_km") or 0.0)
    volume_ratio = (target_volume / goal_volume) if goal_volume > 0 else 1.0
    previous_long_minutes = int(context.get("forecast_previous_long_minutes") or 0)

    if template_key == "easy":
        if volume_ratio >= 0.9:
            return "easy_55"
        if volume_ratio >= 0.75:
            return "easy_50"
        return "easy"
    if template_key == "steady":
        if volume_ratio >= 0.9:
            return "steady_40"
        if volume_ratio >= 0.75:
            return "steady_35"
        return "steady"
    if template_key == "threshold":
        if context.get("recovery_flag") == "good" and volume_ratio >= 0.9:
            return "threshold"
        return "threshold_3x8"
    if template_key == "reduced_long":
        return "reduced_long_85" if volume_ratio >= 0.75 else "reduced_long"
    if template_key == "long":
        preferred = "long_90"
        if volume_ratio >= 0.95:
            preferred = "long_110"
        elif volume_ratio >= 0.8:
            preferred = "long"

        if previous_long_minutes > 0:
            max_allowed = previous_long_minutes + FORECAST_LONG_RUN_STEP_MINUTES
            for candidate in ("long_90", "long", "long_110"):
                minutes = forecast_template_minutes(candidate)
                if minutes <= max_allowed and minutes <= forecast_template_minutes(preferred):
                    preferred = candidate
        return preferred
    return template_key


def forecast_template_minutes(template_key: str) -> int:
    """Return total minutes for forecast-sensitive templates."""

    return {
        "easy": 45,
        "easy_50": 50,
        "easy_55": 55,
        "steady": 53,
        "steady_35": 58,
        "steady_40": 63,
        "threshold_3x8": 40,
        "threshold": 50,
        "reduced_long": 75,
        "reduced_long_85": 85,
        "long_90": 90,
        "long": 100,
        "long_110": 110,
    }.get(template_key, 0)




def stylize_step_note(step_name: str, fallback_note: str) -> str:
    """Add a consistent, deterministic tone to step notes without changing the workout logic."""

    lowered = step_name.lower()
    if "warm" in lowered:
        suffix = " Settle in gradually."
    elif "cool" in lowered:
        suffix = " Ease down gradually."
    elif "recovery" in lowered:
        suffix = " Stay relaxed between efforts."
    elif "threshold rep" in lowered:
        suffix = " Smooth and controlled."
    elif "hard rep" in lowered:
        suffix = " Fast but controlled."
    elif "steady running" in lowered:
        suffix = " Hold a controlled aerobic rhythm."
    elif "long aerobic running" in lowered or "long easy running" in lowered:
        suffix = " Keep the effort steady and aerobic."
    elif "aerobic running" in lowered:
        suffix = " Keep the effort relaxed and efficient."
    elif "settle in" in lowered:
        suffix = " Let the effort build gradually."
    elif "finish easy" in lowered:
        suffix = " Finish under control."
    else:
        suffix = " Keep the effort controlled."

    if fallback_note.endswith(suffix.strip()):
        return fallback_note
    return f"{fallback_note}{suffix}"


def resolve_target(profile: AthleteProfile, target_key: str) -> StepTarget:
    """Resolve a target key into a pace display and optional numeric range."""

    target = target_key.strip().lower()
    if target == "open":
        return StepTarget(kind="open", label="open", display="Open")
    if target == "easy":
        fast = profile.easy_pace_min_per_km
        slow = profile.easy_pace_min_per_km + (15 / 60)
        display = easy_range(profile.easy_pace_min_per_km)
    elif target == "steady":
        fast = profile.threshold_pace_min_per_km + (20 / 60)
        slow = profile.threshold_pace_min_per_km + (35 / 60)
        display = steady_range(profile.threshold_pace_min_per_km)
    elif target == "threshold":
        fast = profile.threshold_pace_min_per_km
        slow = profile.threshold_pace_min_per_km + (5 / 60)
        display = threshold_range(profile.threshold_pace_min_per_km)
    elif target == "hard":
        fast = profile.threshold_pace_min_per_km - (10 / 60)
        slow = profile.threshold_pace_min_per_km - (5 / 60)
        display = hard_range(profile.threshold_pace_min_per_km)
    elif target == "long":
        fast = profile.long_run_pace_min_per_km
        slow = profile.long_run_pace_min_per_km + (20 / 60)
        display = long_range(profile.long_run_pace_min_per_km)
    else:
        raise ValueError(f"Unsupported target key: {target_key}")

    return StepTarget(
        kind="pace_range",
        label=target,
        display=display,
        pace_fast_min_per_km=fast,
        pace_slow_min_per_km=slow,
    )


def render_workout_blocks(workout: PlannedWorkout) -> tuple[str, str, str]:
    """Render a workout into warmup/main-set/cooldown text blocks."""

    warmup_lines: list[str] = []
    main_lines: list[str] = []
    cooldown_lines: list[str] = []
    for step in workout.steps:
        line = f"{step.name}: {format_duration(step.duration)} @ {step.target.display}".replace(" @ Open", "")
        if "warm" in step.name.lower():
            warmup_lines.append(line)
        elif "cool" in step.name.lower():
            cooldown_lines.append(line)
        else:
            main_lines.append(line)

    return (
        "\n".join(warmup_lines) or "None",
        "\n".join(main_lines) or "None",
        "\n".join(cooldown_lines) or "None",
    )


def render_week_markdown(plan: WeeklyPlan) -> str:
    """Render the weekly plan as markdown."""

    lines = [
        f"# Weekly Plan ({plan.start_date} to {plan.end_date})",
        "",
        f"Readiness: {plan.readiness}",
        f"Goal: {plan.goal_summary}",
        "",
    ]

    workout_by_date = {workout.date: workout for workout in plan.workouts}
    current_day = date.fromisoformat(plan.start_date)
    for day_offset in range(7):
        workout_date = current_day + timedelta(days=day_offset)
        day_name = workout_date.strftime("%A")
        date_key = workout_date.isoformat()
        lines.append(f"## {day_name} ({date_key})")
        workout = workout_by_date.get(date_key)
        if workout is None:
            lines.extend(["Status: off", ""])
            continue
        lines.append(f"Workout: {workout.name} ({workout.workout_type})")
        for step in workout.steps:
            lines.append(f"- {step.name}: {format_duration(step.duration)} | {step.target.display} | {step.note}")
        lines.append("")

    lines.extend(["## Rationale", *[f"- {reason}" for reason in plan.rationale]])
    return "\n".join(lines).rstrip() + "\n"


def render_forecast_markdown(plan: ForecastPlan) -> str:
    """Render the multiweek forecast as markdown."""

    lines = [
        f"# Four-Week Forecast ({plan.start_date} to {plan.end_date})",
        "",
        f"Goal: {plan.goal_summary}",
        "",
    ]
    for summary, week in zip(plan.summaries, plan.weeks):
        lines.extend(
            [
                f"## Week {summary.week_index + 1} ({summary.start_date} to {summary.end_date})",
                f"Projected load target: {summary.load_target_km:.1f} km",
                f"Projected distance: {summary.projected_distance_km:.1f} km",
                f"Projected duration: {summary.projected_duration_minutes:.1f} min",
                f"Projected readiness: {summary.projected_readiness}",
                f"Projected recovery flag: {summary.projected_recovery_flag}",
                "",
            ]
        )
        workout_by_date = {workout.date: workout for workout in week.workouts}
        current_day = date.fromisoformat(week.start_date)
        for day_offset in range(7):
            workout_date = current_day + timedelta(days=day_offset)
            day_name = workout_date.strftime("%A")
            workout = workout_by_date.get(workout_date.isoformat())
            lines.append(f"### {day_name} ({workout_date.isoformat()})")
            if workout is None:
                lines.extend(["Status: off", ""])
                continue
            lines.append(f"Workout: {workout.name} ({workout.workout_type})")
            for step in workout.steps:
                lines.append(f"- {step.name}: {format_duration(step.duration)} | {step.target.display} | {step.note}")
            lines.append("")

    lines.extend(["## Rationale", *[f"- {reason}" for reason in plan.rationale]])
    return "\n".join(lines).rstrip() + "\n"


def format_duration(duration: StepDuration) -> str:
    """Render a duration into readable text."""

    if duration.kind == "time":
        minutes = duration.value // 60
        seconds = duration.value % 60
        if seconds == 0:
            return f"{minutes} min"
        return f"{minutes}:{seconds:02d}"
    if duration.kind == "distance":
        if duration.value % 1000 == 0:
            return f"{duration.value // 1000} km"
        return f"{duration.value} m"
    return "Open"


def monday_of(value: date) -> date:
    """Return the Monday of the date's calendar week."""

    return value - timedelta(days=value.weekday())


def next_monday(value: date) -> date:
    """Return the Monday of the next calendar week."""

    delta = 7 - value.weekday()
    if delta == 0:
        delta = 7
    return value + timedelta(days=delta)


def normalize_day_name(raw_day: str) -> str:
    """Normalize a weekday label to title case."""

    lowered = raw_day.strip().lower()
    for day_name in DAY_NAMES:
        if day_name.lower() == lowered:
            return day_name
    return "Saturday"


def goal_summary_text(goal) -> str:
    """Render a compact goal summary for weekly plan context."""

    return (
        f"{goal.target_race_name} on {goal.target_race_date}, "
        f"{goal.target_race_distance_km:.1f} km, "
        f"{goal.target_weekly_volume_km} km target, "
        f"{goal.weekly_run_days} run days"
    )


def marathon_build_goal(goal) -> bool:
    """Return whether the goal should use marathon-build scheduling defaults."""

    return goal.target_race_distance_km >= 40 or "marathon" in goal.current_phase.lower()


def marathon_build_context(context: dict[str, Any]) -> bool:
    """Return whether the current plan context represents a marathon build."""

    phase = str(context.get("current_phase", "")).lower()
    distance = float(context.get("target_race_distance_km") or 0.0)
    return distance >= 40 or "marathon" in phase


def marathon_primary_quality_supported(context: dict[str, Any]) -> bool:
    """Return whether recent consistency supports marathon-build quality work."""

    target_volume = float(context.get("target_weekly_volume_km") or 0.0)
    recent_volume = float(context.get("recent_total_distance_km") or 0.0)
    recent_run_days = int(context.get("recent_run_days") or 0)
    required_run_days = min(4, max(3, int(context.get("target_weekly_run_days") or 3)))

    if target_volume <= 0:
        return True
    volume_ratio = recent_volume / target_volume
    return recent_run_days >= required_run_days and volume_ratio >= MARATHON_PRIMARY_QUALITY_MIN_VOLUME_RATIO


def marathon_full_long_supported(context: dict[str, Any]) -> bool:
    """Return whether recent consistency supports the full marathon long run."""

    target_volume = float(context.get("target_weekly_volume_km") or 0.0)
    recent_volume = float(context.get("recent_total_distance_km") or 0.0)
    recent_run_days = int(context.get("recent_run_days") or 0)
    required_run_days = min(4, max(3, int(context.get("target_weekly_run_days") or 3)))

    if target_volume <= 0:
        return True
    volume_ratio = recent_volume / target_volume
    return recent_run_days >= required_run_days and volume_ratio >= MARATHON_FULL_LONG_MIN_VOLUME_RATIO


def forecast_load_target_km(previous_load_target: float, context: dict[str, Any]) -> float:
    """Apply balanced forecast progression rules to the next week's volume target."""

    goal_volume = float(context.get("target_weekly_volume_km") or previous_load_target or 0.0)
    base_target = previous_load_target or (goal_volume * 0.6)
    recovery_flag = str(context.get("recovery_flag") or "good")

    if recovery_flag == "needs_recovery":
        return round(max(0.0, min(goal_volume, base_target * FORECAST_RECOVERY_CUTBACK)), 1)
    if recovery_flag == "caution":
        return round(max(0.0, min(goal_volume, base_target)), 1)
    return round(max(0.0, min(goal_volume, base_target * FORECAST_WEEKLY_LOAD_GROWTH)), 1)


def synthetic_activity_from_workout(
    workout: PlannedWorkout,
    *,
    profile: AthleteProfile,
    sequence: int,
) -> dict[str, Any]:
    """Turn a planned workout into a deterministic synthetic activity record."""

    duration_minutes = float(estimate_workout_duration_minutes(workout))
    distance_km = round(estimate_workout_distance_km(workout, profile=profile), 2)
    training_load = round(estimate_workout_training_load(workout, duration_minutes), 1)

    return {
        "external_id": f"forecast:{workout.external_id}:{sequence}",
        "activity_date": workout.date,
        "start_time": f"{workout.date}T06:{sequence:02d}:00",
        "name": workout.name,
        "sport": "Run",
        "activity_type": "Run",
        "distance_km": distance_km,
        "duration_minutes": duration_minutes,
        "training_load": training_load,
        "workout_type": workout.workout_type,
        "avg_pace_min_per_km": round(duration_minutes / distance_km, 2) if distance_km > 0 else None,
        "raw_snapshot_path": "",
        "last_seen_sync": "forecast",
    }


def frozen_check_ins_for_range(
    latest_check_in: dict[str, Any] | None,
    *,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Repeat the latest subjective recovery state across future forecast days."""

    if latest_check_in is None:
        return []

    rows: list[dict[str, Any]] = []
    current = start_date
    while current <= end_date:
        row = dict(latest_check_in)
        row["local_date"] = current.isoformat()
        rows.append(row)
        current += timedelta(days=1)
    return rows


def metric_context_from_forecast(
    *,
    metric,
    activities: list[dict[str, Any]],
    end_date: date,
    goal,
    current_check_in: dict[str, Any] | None,
    previous_long_minutes: Any,
) -> dict[str, Any]:
    """Build the next week's planning context from forecasted metrics."""

    context = {
        "readiness": metric.readiness,
        "recovery_flag": metric.recovery_flag,
        "form": metric.form,
        "fatigue": metric.fatigue,
        "sleep": metric.sleep,
        "soreness": metric.soreness,
        "days_since_threshold": metric.days_since_threshold,
        "days_since_hard": metric.days_since_hard,
        "days_since_long": metric.days_since_long,
        "last_workout_type": metric.last_workout_type,
        "current_phase": goal.current_phase,
        "target_race_distance_km": goal.target_race_distance_km,
        "target_weekly_volume_km": goal.target_weekly_volume_km,
        "target_weekly_run_days": goal.weekly_run_days,
        "forecast_previous_long_minutes": int(previous_long_minutes or 0),
    }
    context.update(
        build_history_context_from_activities(
            activities,
            end_date=end_date,
            target_weekly_volume_km=goal.target_weekly_volume_km,
        )
    )
    if current_check_in is not None:
        context["current_check_in"] = dict(current_check_in)
    return context


def estimate_workout_duration_minutes(workout: PlannedWorkout) -> int:
    """Estimate total workout duration for synthetic projection."""

    total_minutes = 0.0
    for step in workout.steps:
        if step.duration.kind == "time":
            total_minutes += step.duration.value / 60
            continue
        if step.duration.kind == "distance":
            pace = representative_pace_for_step(step, workout_type=workout.workout_type)
            total_minutes += (step.duration.value / 1000) * pace
    return int(round(total_minutes))


def estimate_workout_distance_km(workout: PlannedWorkout, *, profile: AthleteProfile) -> float:
    """Estimate total workout distance for synthetic projection."""

    total_distance = 0.0
    for step in workout.steps:
        if step.duration.kind == "distance":
            total_distance += step.duration.value / 1000
            continue
        if step.duration.kind == "time":
            pace = representative_pace_for_step(step, workout_type=workout.workout_type)
            if pace <= 0:
                pace = profile.easy_pace_min_per_km
            total_distance += (step.duration.value / 60) / pace
    return total_distance


def estimate_workout_training_load(workout: PlannedWorkout, duration_minutes: float) -> float:
    """Estimate a stable synthetic training load from duration and session type."""

    multiplier = {
        "easy": 0.8,
        "steady": 1.0,
        "threshold": 1.2,
        "hard": 1.35,
        "long": 0.75,
    }.get(workout.workout_type, 1.0)
    return duration_minutes * multiplier


def representative_pace_for_step(step: WorkoutStep, *, workout_type: str) -> float:
    """Choose one representative pace per step for synthetic duration and distance estimates."""

    if step.target.pace_fast_min_per_km is not None and step.target.pace_slow_min_per_km is not None:
        return (step.target.pace_fast_min_per_km + step.target.pace_slow_min_per_km) / 2
    if step.target.pace_fast_min_per_km is not None:
        return step.target.pace_fast_min_per_km
    if step.target.label == "long" or workout_type == "long":
        return 5.83
    return 5.92


def build_history_context(
    connection,
    *,
    end_date: date,
    target_weekly_volume_km: int,
) -> dict[str, Any]:
    """Summarize recent DB coverage so the planner can stay conservative when history is thin."""

    start_date = end_date - timedelta(days=6)
    recent_activities = [
        dict(row)
        for row in fetch_activities(
            connection,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )
    ]
    return build_history_context_from_activities(
        recent_activities,
        end_date=end_date,
        target_weekly_volume_km=target_weekly_volume_km,
    )


def build_history_context_from_activities(
    activities: list[dict[str, Any]],
    *,
    end_date: date,
    target_weekly_volume_km: int,
) -> dict[str, Any]:
    """Summarize one rolling seven-day history window from a list of activity dicts."""

    start_date = end_date - timedelta(days=6)
    recent_activities = [
        item
        for item in activities
        if start_date.isoformat() <= str(item["activity_date"]) <= end_date.isoformat()
    ]
    run_days = {item["activity_date"] for item in recent_activities if str(item.get("sport", "")).lower() == "run"}
    total_distance = sum(float(item.get("distance_km") or 0.0) for item in recent_activities)
    quality_sessions = sum(
        1
        for item in recent_activities
        if str(item.get("workout_type", "")).lower() in {"threshold", "hard"}
    )
    history_complete = len(run_days) >= 3
    overloaded = quality_sessions >= 2 or total_distance >= (target_weekly_volume_km * 1.2)
    conservative_week = (not history_complete) or overloaded
    volume_ratio = round(total_distance / target_weekly_volume_km, 2) if target_weekly_volume_km > 0 else None

    return {
        "history_complete": history_complete,
        "recent_run_days": len(run_days),
        "recent_total_distance_km": round(total_distance, 2),
        "recent_volume_ratio": volume_ratio,
        "recent_quality_sessions": quality_sessions,
        "overloaded": overloaded,
        "conservative_week": conservative_week,
    }


def serialize_planned_workout(workout: PlannedWorkout) -> dict[str, Any]:
    """Serialize one structured workout into JSON-safe payload data."""

    return {
        "date": workout.date,
        "name": workout.name,
        "workout_type": workout.workout_type,
        "notes": workout.notes,
        "template_key": workout.template_key,
        "source_template": workout.source_template,
        "fit_exportable": workout.fit_exportable,
        "steps": [
            {
                "name": step.name,
                "duration": {
                    "kind": step.duration.kind,
                    "value": step.duration.value,
                },
                "target": {
                    "kind": step.target.kind,
                    "label": step.target.label,
                    "display": step.target.display,
                    "pace_fast_min_per_km": step.target.pace_fast_min_per_km,
                    "pace_slow_min_per_km": step.target.pace_slow_min_per_km,
                },
                "note": step.note,
            }
            for step in workout.steps
        ],
    }


def planned_workout_from_payload(item: dict[str, Any]) -> PlannedWorkout:
    """Rebuild a structured workout directly from canonical payload data."""

    structured = item.get("structured_workout")
    if not isinstance(structured, dict):
        raise ValueError("Weekly payload item is missing structured_workout data.")

    return PlannedWorkout(
        date=str(structured["date"]),
        name=str(structured["name"]),
        workout_type=str(structured["workout_type"]),
        steps=[
            WorkoutStep(
                name=str(step["name"]),
                duration=StepDuration(
                    kind=str(step["duration"]["kind"]),
                    value=int(step["duration"]["value"]),
                ),
                target=StepTarget(
                    kind=str(step["target"]["kind"]),
                    label=str(step["target"]["label"]),
                    display=str(step["target"]["display"]),
                    pace_fast_min_per_km=_float_or_none(step["target"].get("pace_fast_min_per_km")),
                    pace_slow_min_per_km=_float_or_none(step["target"].get("pace_slow_min_per_km")),
                ),
                note=str(step["note"]),
            )
            for step in structured.get("steps", [])
        ],
        notes=str(structured["notes"]),
        template_key=str(structured["template_key"]),
        source_template=str(structured["source_template"]),
        fit_exportable=bool(structured["fit_exportable"]),
    )


def weekly_plan_from_payload(payload: dict[str, Any]) -> WeeklyPlan:
    """Rebuild a structured weekly plan directly from canonical payload data."""

    if payload.get("mode") != "weekly":
        raise ValueError("Weekly plan reconstruction only supports weekly payloads.")

    workouts = [planned_workout_from_payload(item) for item in payload.get("items", [])]
    scheduled_dates = {workout.date for workout in workouts}
    start_date = str(payload["target_date"])
    start_day = date.fromisoformat(start_date)
    rest_dates = [
        (start_day + timedelta(days=offset)).isoformat()
        for offset in range(7)
        if (start_day + timedelta(days=offset)).isoformat() not in scheduled_dates
    ]
    return WeeklyPlan(
        anchor_date=start_date,
        start_date=start_date,
        end_date=(start_day + timedelta(days=6)).isoformat(),
        readiness=str(payload["context"]["readiness"]),
        workouts=workouts,
        rest_dates=rest_dates,
        rationale=list(payload.get("rationale", [])),
        goal_summary=str(payload["context"].get("goal_summary", "")),
    )


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def plan_week(
    profile: AthleteProfile,
    state,
    templates: dict[str, StructuredWorkoutTemplate],
    *,
    anchor_date: date,
) -> WeeklyPlan:
    """Compatibility wrapper retained for older tests and scripts."""

    paths = resolve_runtime_paths(Path(__file__).resolve().parents[1], profile_name="demo")
    goal = load_current_goal(paths.current_goal)
    context = {
        "readiness": determine_readiness(int(state.form)),
        "recovery_flag": "good",
        "form": int(state.form),
        "current_phase": goal.current_phase,
        "target_race_distance_km": goal.target_race_distance_km,
        "target_weekly_volume_km": goal.target_weekly_volume_km,
        "target_weekly_run_days": goal.weekly_run_days,
        "days_since_threshold": 4 if state.last_workout_type != "threshold" else 0,
        "days_since_hard": 8 if state.last_workout_type != "hard" else 0,
        "days_since_long": 7 if state.last_workout_type != "long" else 0,
        "last_workout_type": str(state.last_workout_type).lower(),
        "history_complete": True,
        "recent_run_days": goal.weekly_run_days,
        "recent_total_distance_km": float(goal.target_weekly_volume_km),
        "recent_quality_sessions": 1 if determine_readiness(int(state.form)) in {"threshold_allowed", "hard_allowed"} else 0,
        "overloaded": False,
        "conservative_week": determine_readiness(int(state.form)) == "easy_only",
    }
    week_start = monday_of(anchor_date)
    return build_weekly_plan(
        profile=profile,
        goal=goal,
        templates=templates,
        context=context,
        week_start=week_start,
        anchor_date=anchor_date,
    )
