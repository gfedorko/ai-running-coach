"""Intervals.icu sync and workout upload support for the local running coach."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
import base64
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from coach.athlete import AthleteState, load_athlete_state
from coach.data_paths import CoachPaths, ensure_local_profile_seed, ensure_local_write_mode, resolve_local_write_paths, resolve_runtime_paths
from coach.fit_export import FitExport
from coach.metrics import rebuild_daily_metrics_range
from coach.storage import (
    ActivityRecord,
    WellnessRecord,
    connect_database,
    fetch_activities_between_ascending,
    fetch_check_ins_between,
    fetch_latest_daily_metric,
    fetch_latest_wellness,
    fetch_wellness_between,
    latest_history_date,
    replace_daily_metrics,
    replace_daily_metrics_from,
    upsert_activities,
    upsert_wellness,
)


BASE_URL = "https://intervals.icu/api/v1"
DEFAULT_LOOKBACK_DAYS = 14
METRIC_LOOKBACK_DAYS = 90
RUN_COACH_EXTERNAL_ID_PREFIX = "run-coach:workout:"


class IntervalsSyncError(RuntimeError):
    """Raised when Intervals.icu sync cannot complete safely."""


@dataclass(slots=True)
class IntervalsConfig:
    """Runtime config loaded from environment variables."""

    athlete_id: str
    api_key: str
    lookback_days: int = DEFAULT_LOOKBACK_DAYS


@dataclass(slots=True)
class SyncMetadata:
    """Small sync summary used in the CLI and notes."""

    synced_at: str
    oldest: str
    newest: str
    activities_considered: int
    last_activity_date: str | None
    last_workout_type: str
    form_source: str
    raw_snapshot_dir: str
    sync_mode: str


@dataclass(slots=True)
class SyncResult:
    """The derived athlete state and a readable summary."""

    state: AthleteState
    metadata: SyncMetadata

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": asdict(self.state),
            "metadata": asdict(self.metadata),
        }


@dataclass(slots=True)
class IntervalsPushSummary:
    """Structured result for a weekly Intervals calendar push."""

    success: bool
    deleted_count: int
    upserted_count: int
    upserted_events: list[dict[str, Any]]
    failure_message: str | None = None


URLOpener = Callable[..., Any]


def load_intervals_config(env: dict[str, str] | None = None) -> IntervalsConfig:
    """Load Intervals.icu credentials from environment variables."""

    values = env if env is not None else os.environ
    athlete_id = values.get("INTERVALS_ICU_ATHLETE_ID", "").strip()
    api_key = values.get("INTERVALS_ICU_API_KEY", "").strip()
    lookback_raw = values.get("INTERVALS_LOOKBACK_DAYS", str(DEFAULT_LOOKBACK_DAYS)).strip()

    if not athlete_id:
        raise IntervalsSyncError("Missing INTERVALS_ICU_ATHLETE_ID.")
    if not api_key:
        raise IntervalsSyncError("Missing INTERVALS_ICU_API_KEY.")

    try:
        lookback_days = int(lookback_raw)
    except ValueError as exc:
        raise IntervalsSyncError("INTERVALS_LOOKBACK_DAYS must be an integer.") from exc

    if lookback_days < 1:
        raise IntervalsSyncError("INTERVALS_LOOKBACK_DAYS must be at least 1.")

    return IntervalsConfig(
        athlete_id=athlete_id,
        api_key=api_key,
        lookback_days=lookback_days,
    )


def sync_repo_state(
    repo_root: Path,
    *,
    env: dict[str, str] | None = None,
    opener: URLOpener = urlopen,
    now: datetime | None = None,
    mode: str = "incremental",
) -> SyncResult:
    """Fetch Intervals data and refresh local markdown, JSON, and SQLite state."""

    try:
        ensure_local_write_mode(env)
    except ValueError as exc:
        raise IntervalsSyncError(str(exc)) from exc

    config = load_intervals_config(env)
    write_paths = ensure_local_profile_seed(repo_root)
    seed_paths = resolve_runtime_paths(repo_root, profile_name="demo")
    state_path = write_paths.athlete_state
    db_path = write_paths.training_db
    if state_path.exists():
        existing_state = load_athlete_state(state_path)
        manual_notes = extract_manual_notes(state_path)
    else:
        existing_state = load_athlete_state(seed_paths.athlete_state)
        manual_notes = []

    current_time = now if now is not None else datetime.now().astimezone()
    oldest, newest = _determine_sync_window(config, db_path, current_time, mode)

    activities = fetch_recent_activities(
        config,
        oldest=oldest,
        newest=newest,
        opener=opener,
    )
    wellness = fetch_recent_wellness(
        config,
        oldest=oldest,
        newest=newest,
        opener=opener,
    )

    raw_snapshot_dir = _write_raw_snapshots(write_paths, current_time, mode, activities, wellness)

    result = derive_athlete_state(
        existing_state=existing_state,
        activities=activities,
        wellness=wellness,
        now=current_time,
        oldest=oldest,
        newest=newest,
        raw_snapshot_dir=raw_snapshot_dir,
        sync_mode=mode,
    )

    normalized_activities = _normalize_activities(activities, raw_snapshot_dir, result.metadata.synced_at)
    normalized_wellness = _normalize_wellness(wellness, raw_snapshot_dir, result.metadata.synced_at)
    _write_recent_activity_history(write_paths.recent_activities, activities)
    _update_database(
        db_path,
        activities=normalized_activities,
        wellness=normalized_wellness,
        result=result,
    )
    write_athlete_state(state_path, result, manual_notes)
    return result


def fetch_recent_activities(
    config: IntervalsConfig,
    *,
    oldest: str,
    newest: str,
    opener: URLOpener = urlopen,
) -> list[dict[str, Any]]:
    """Fetch recent activity rows from the Intervals.icu activities endpoint."""

    return _fetch_list(
        f"/athlete/{config.athlete_id}/activities",
        config,
        params={"oldest": oldest, "newest": newest},
        opener=opener,
        endpoint_name="activities",
    )


def fetch_recent_wellness(
    config: IntervalsConfig,
    *,
    oldest: str,
    newest: str,
    opener: URLOpener = urlopen,
) -> list[dict[str, Any]]:
    """Fetch recent wellness rows, including freshness/load fields when available."""

    return _fetch_list(
        f"/athlete/{config.athlete_id}/wellness",
        config,
        params={"oldest": oldest, "newest": newest},
        opener=opener,
        endpoint_name="wellness",
    )


def list_calendar_events(
    config: IntervalsConfig,
    *,
    oldest: str,
    newest: str,
    opener: URLOpener = urlopen,
) -> list[dict[str, Any]]:
    """List Intervals calendar events for the target week."""

    return _fetch_list(
        f"/athlete/{config.athlete_id}/events",
        config,
        params={"oldest": oldest, "newest": newest},
        opener=opener,
        endpoint_name="events",
    )


def upsert_events_bulk(
    config: IntervalsConfig,
    events: list[dict[str, Any]],
    *,
    opener: URLOpener = urlopen,
) -> list[dict[str, Any]]:
    """Create or update workout calendar events in one call."""

    if not events:
        return []

    data = _request_json(
        "POST",
        f"/athlete/{config.athlete_id}/events/bulk",
        config,
        params={"upsert": "true"},
        payload=events,
        opener=opener,
        endpoint_name="events bulk upsert",
    )
    if not isinstance(data, list):
        raise IntervalsSyncError(
            "Intervals returned an unexpected payload for events bulk upsert: expected a list."
        )
    return [item for item in data if isinstance(item, dict)]


def delete_events_bulk(
    config: IntervalsConfig,
    events: list[dict[str, Any]],
    *,
    opener: URLOpener = urlopen,
) -> int:
    """Delete stale managed events in one call."""

    if not events:
        return 0

    delete_items = []
    for event in events:
        if event.get("id") is not None:
            delete_items.append({"id": event["id"]})
        elif event.get("external_id"):
            delete_items.append({"external_id": event["external_id"]})

    if not delete_items:
        return 0

    data = _request_json(
        "PUT",
        f"/athlete/{config.athlete_id}/events/bulk-delete",
        config,
        payload=delete_items,
        opener=opener,
        endpoint_name="events bulk delete",
    )
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict) and "deleted" in data:
        try:
            return int(data["deleted"])
        except (TypeError, ValueError):
            return len(delete_items)
    return len(delete_items)


def filter_managed_events(
    events: list[dict[str, Any]],
    *,
    active_external_ids: set[str],
) -> list[dict[str, Any]]:
    """Return stale run-coach-managed events that should be deleted."""

    stale_events = []
    for event in events:
        external_id = _string_value(event, "external_id")
        if not external_id.startswith(RUN_COACH_EXTERNAL_ID_PREFIX):
            continue
        if external_id in active_external_ids:
            continue
        stale_events.append(event)
    return stale_events


def push_weekly_plan_to_intervals(
    plan,
    fit_exports_by_external_id: dict[str, FitExport],
    *,
    env: dict[str, str] | None = None,
    opener: URLOpener = urlopen,
) -> IntervalsPushSummary:
    """Push one weekly plan to Intervals and report structured success or failure."""

    event_payloads = []
    for workout in plan.workouts:
        fit_export = fit_exports_by_external_id.get(workout.external_id)
        if fit_export is None:
            raise ValueError(f"Missing FIT export for planned workout {workout.external_id}.")
        event_payloads.append(make_event_payload(workout, fit_export))

    deleted_count = 0
    upserted_events: list[dict[str, Any]] = []
    try:
        config = load_intervals_config(env)
        existing_events = list_calendar_events(
            config,
            oldest=plan.start_date,
            newest=plan.end_date,
            opener=opener,
        )
        stale_events = filter_managed_events(
            existing_events,
            active_external_ids={workout.external_id for workout in plan.workouts},
        )
        deleted_count = delete_events_bulk(
            config,
            stale_events,
            opener=opener,
        )
        upserted_events = upsert_events_bulk(
            config,
            event_payloads,
            opener=opener,
        )
    except IntervalsSyncError as exc:
        return IntervalsPushSummary(
            success=False,
            deleted_count=deleted_count,
            upserted_count=len(upserted_events),
            upserted_events=upserted_events,
            failure_message=str(exc),
        )

    return IntervalsPushSummary(
        success=True,
        deleted_count=deleted_count,
        upserted_count=len(upserted_events),
        upserted_events=upserted_events,
    )


def make_event_payload(workout, fit_export) -> dict[str, Any]:
    """Build the Intervals workout event payload for a planned workout."""

    encoded_fit = base64.b64encode(fit_export.data).decode("ascii")
    workout_date = workout.date if isinstance(workout.date, str) else workout.date.isoformat()
    workout_name = getattr(workout, "name", None) or getattr(workout, "title", "Workout")
    workout_steps = getattr(workout, "steps", [])
    description = render_workout_description(workout_name, workout_steps, getattr(workout, "notes", ""))

    return {
        "external_id": getattr(workout, "external_id", f"{RUN_COACH_EXTERNAL_ID_PREFIX}{workout_date}"),
        "name": workout_name,
        "description": description,
        "category": "WORKOUT",
        "type": "Run",
        "start_date_local": f"{workout_date}T00:00:00",
        "filename": fit_export.filename,
        "file_contents_base64": encoded_fit,
    }


def render_workout_description(workout_name: str, workout_steps: list[Any], workout_notes: str) -> str:
    """Build a readable workout summary for the Intervals calendar entry."""

    lines = [workout_name, ""]
    for step in workout_steps:
        note = getattr(step, "note", None) or getattr(step, "notes", "")
        target_display = getattr(getattr(step, "target", None), "display", None)
        if target_display is None and getattr(step, "target_type", None) == "speed":
            target_display = "pace target"
        if target_display is None:
            target_display = "Open"
        step_name = getattr(step, "name", None) or getattr(step, "kind", "step").title()
        lines.append(f"- {step_name}: {target_display} | {note}")
    if workout_notes:
        lines.extend(["", workout_notes])
    return "\n".join(lines)


def derive_athlete_state(
    *,
    existing_state: AthleteState,
    activities: list[dict[str, Any]],
    wellness: list[dict[str, Any]],
    now: datetime,
    oldest: str,
    newest: str,
    raw_snapshot_dir: str = "",
    sync_mode: str = "incremental",
) -> SyncResult:
    """Convert Intervals payloads into the markdown-backed athlete state."""

    run_activities = _sorted_run_activities(activities)
    latest_wellness = _latest_wellness_entry(wellness)
    latest_run = run_activities[0] if run_activities else None

    form, form_source = _derive_form(existing_state, latest_wellness, run_activities)
    fatigue = _derive_fatigue_bucket(form, latest_wellness, run_activities)
    sleep = _derive_sleep(existing_state, latest_wellness)
    soreness = _derive_soreness(existing_state, latest_wellness)
    last_workout_type = (
        classify_run_activity(latest_run)
        if latest_run is not None
        else existing_state.last_workout_type
    )

    metadata = SyncMetadata(
        synced_at=now.isoformat(timespec="seconds"),
        oldest=oldest,
        newest=newest,
        activities_considered=len(run_activities),
        last_activity_date=_activity_date_string(latest_run) if latest_run else None,
        last_workout_type=last_workout_type,
        form_source=form_source,
        raw_snapshot_dir=raw_snapshot_dir,
        sync_mode=sync_mode,
    )
    state = AthleteState(
        date=now.date().isoformat(),
        form=form,
        fatigue=fatigue,
        sleep=sleep,
        soreness=soreness,
        last_workout_type=last_workout_type,
    )
    return SyncResult(state=state, metadata=metadata)


def derive_state_from_storage(
    *,
    existing_state: AthleteState,
    metrics: list[dict[str, Any]],
    all_activities: list[dict[str, Any]],
    now: datetime,
    oldest: str,
    newest: str,
    sync_mode: str,
    raw_snapshot_dir: str,
    activities_considered: int,
) -> SyncResult:
    """Build the sync-style athlete state from already stored rows."""

    latest_metric = metrics[-1] if metrics else None
    run_activities = _sorted_run_activities(all_activities)
    latest_run = run_activities[0] if run_activities else None
    last_workout_type = (
        classify_run_activity(latest_run)
        if latest_run is not None
        else existing_state.last_workout_type
    )

    metadata = SyncMetadata(
        synced_at=now.isoformat(timespec="seconds"),
        oldest=oldest,
        newest=newest,
        activities_considered=activities_considered,
        last_activity_date=_activity_date_string(latest_run) if latest_run else None,
        last_workout_type=last_workout_type,
        form_source=(
            str(latest_metric["form_source"])
            if latest_metric is not None and latest_metric.get("form_source")
            else "Persisted state"
        ),
        raw_snapshot_dir=raw_snapshot_dir,
        sync_mode=sync_mode,
    )
    state = AthleteState(
        date=now.date().isoformat(),
        form=int(latest_metric["form"]) if latest_metric is not None else existing_state.form,
        fatigue=str(latest_metric["fatigue"]) if latest_metric is not None else existing_state.fatigue,
        sleep=str(latest_metric["sleep"]) if latest_metric is not None else existing_state.sleep,
        soreness=str(latest_metric["soreness"]) if latest_metric is not None else existing_state.soreness,
        last_workout_type=last_workout_type,
    )
    return SyncResult(state=state, metadata=metadata)


def refresh_daily_metrics_from(
    connection,
    *,
    start_date: str,
    end_date: str,
    default_last_workout_type: str,
    seed_form: int,
    seed_sleep: str,
    seed_soreness: str,
):
    """Rebuild only the affected tail of daily metrics after a local data change."""

    start_day = date.fromisoformat(start_date)
    end_day = date.fromisoformat(end_date)
    if start_day > end_day:
        return []

    lookback_start = (start_day - timedelta(days=METRIC_LOOKBACK_DAYS)).isoformat()
    prior_day = (start_day - timedelta(days=1)).isoformat()
    prior_metric = fetch_latest_daily_metric(connection, prior_day)
    latest_wellness = fetch_latest_wellness(connection, prior_day)

    metrics = rebuild_daily_metrics_range(
        [dict(row) for row in fetch_activities_between_ascending(connection, start_date=lookback_start, end_date=end_date)],
        [dict(row) for row in fetch_wellness_between(connection, start_date=start_date, end_date=end_date)],
        [dict(row) for row in fetch_check_ins_between(connection, start_date=start_date, end_date=end_date)],
        start_date=start_date,
        end_date=end_date,
        default_last_workout_type=(
            str(prior_metric["last_workout_type"])
            if prior_metric is not None
            else default_last_workout_type
        ),
        seed_form=int(prior_metric["form"]) if prior_metric is not None else seed_form,
        seed_sleep=str(prior_metric["sleep"]) if prior_metric is not None else seed_sleep,
        seed_soreness=str(prior_metric["soreness"]) if prior_metric is not None else seed_soreness,
        initial_latest_wellness=dict(latest_wellness) if latest_wellness is not None else None,
    )
    replace_daily_metrics_from(
        connection,
        start_date=start_date,
        metrics=metrics,
    )
    return metrics


def write_athlete_state(path: Path, result: SyncResult, manual_notes: list[str]) -> None:
    """Atomically rewrite the markdown state file after a successful sync."""

    state = result.state
    metadata = result.metadata
    generated_notes = [
        f"- Synced from Intervals.icu at {metadata.synced_at}",
        f"- Lookback window: {metadata.oldest} to {metadata.newest}",
        f"- Activities considered: {metadata.activities_considered}",
        (
            f"- Last run activity: {metadata.last_activity_date} ({metadata.last_workout_type})"
            if metadata.last_activity_date
            else "- Last run activity: none returned by Intervals.icu; preserved prior workout type"
        ),
        f"- Form source: {metadata.form_source}",
    ]

    body_lines = [
        "# Athlete State",
        "",
        f"date: {state.date}",
        f"form: {state.form}",
        f"fatigue: {state.fatigue}",
        f"sleep: {state.sleep}",
        f"soreness: {state.soreness}",
        f"last_workout_type: {state.last_workout_type}",
        "",
        "## Notes",
        *generated_notes,
    ]
    if manual_notes:
        body_lines.extend(["", "## Manual Notes", *manual_notes])
    body_lines.append("")

    temp_file: tempfile.NamedTemporaryFile[str] | None = None
    try:
        temp_file = tempfile.NamedTemporaryFile(
            "w",
            delete=False,
            dir=path.parent,
            encoding="utf-8",
        )
        temp_file.write("\n".join(body_lines))
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_file.close()
        os.replace(temp_file.name, path)
    finally:
        if temp_file is not None:
            temp_name = temp_file.name
            try:
                Path(temp_name).unlink()
            except FileNotFoundError:
                pass


def extract_manual_notes(path: Path) -> list[str]:
    """Keep human-entered notes across machine syncs."""

    lines = path.read_text(encoding="utf-8").splitlines()
    manual_notes: list[str] = []
    current_heading = ""

    for raw_line in lines:
        line = raw_line.strip()
        if line.startswith("## "):
            current_heading = line
            continue
        if not line.startswith("- "):
            continue
        if current_heading == "## Manual Notes":
            manual_notes.append(line)
            continue
        if current_heading == "## Notes" and not _is_generated_note(line):
            manual_notes.append(line)

    return manual_notes


def classify_run_activity(activity: dict[str, Any]) -> str:
    """Convert a run activity into the coarse workout types used by the coach."""

    text_parts = [
        _string_value(activity, "name"),
        _string_value(activity, "description"),
        _string_value(activity, "type"),
        _string_value(activity, "sport"),
    ]
    lowered = " ".join(part.lower() for part in text_parts if part)

    if any(token in lowered for token in ("long run", "longrun", "long")):
        return "long"
    if any(token in lowered for token in ("threshold", "tempo", "cruise")):
        return "threshold"
    if any(token in lowered for token in ("interval", "repetition", "track", "vo2", "hill")):
        return "hard"
    if "steady" in lowered or "aerobic" in lowered:
        return "steady"

    distance_km = _distance_km(activity)
    duration_minutes = _duration_minutes(activity)
    training_load = _number_value(activity, "icu_training_load", "load", "training_load")

    if distance_km is not None and distance_km >= 18:
        return "long"
    if duration_minutes is not None and duration_minutes >= 90:
        return "long"
    if training_load is not None and training_load >= 80:
        return "hard"
    if training_load is not None and training_load >= 50:
        return "threshold"
    if duration_minutes is not None and duration_minutes >= 45:
        return "steady"
    return "easy"


def _request_json(
    method: str,
    path: str,
    config: IntervalsConfig,
    *,
    params: dict[str, str] | None = None,
    payload: Any = None,
    opener: URLOpener,
    endpoint_name: str,
) -> Any:
    query = urlencode(params) if params else ""
    url = f"{BASE_URL}{path}"
    if query:
        url = f"{url}?{query}"

    data = None
    headers = _build_headers(config.api_key)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(url, headers=headers, data=data, method=method)

    try:
        response = opener(request, timeout=20)
        with response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        raise IntervalsSyncError(
            f"Intervals request failed for {endpoint_name} ({exc.code}): {body or exc.reason}"
        ) from exc
    except URLError as exc:
        raise IntervalsSyncError(
            f"Intervals request failed for {endpoint_name}: {exc.reason}"
        ) from exc

    if not body.strip():
        return None

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise IntervalsSyncError(
            f"Intervals returned invalid JSON for {endpoint_name}: {exc}"
        ) from exc


def _fetch_list(
    path: str,
    config: IntervalsConfig,
    *,
    params: dict[str, str],
    opener: URLOpener,
    endpoint_name: str,
) -> list[dict[str, Any]]:
    data = _request_json(
        "GET",
        path,
        config,
        params=params,
        opener=opener,
        endpoint_name=endpoint_name,
    )
    if not isinstance(data, list):
        raise IntervalsSyncError(
            f"Intervals returned an unexpected payload for {endpoint_name}: expected a list."
        )
    return [item for item in data if isinstance(item, dict)]


def _build_headers(api_key: str) -> dict[str, str]:
    credentials = base64.b64encode(f"API_KEY:{api_key}".encode("utf-8")).decode("ascii")
    return {
        "Authorization": f"Basic {credentials}",
        "Accept": "application/json",
        "User-Agent": "run-coach/0.3",
    }


def _determine_sync_window(
    config: IntervalsConfig,
    db_path: Path,
    current_time: datetime,
    mode: str,
) -> tuple[str, str]:
    newest = current_time.date()
    default_oldest = newest - timedelta(days=config.lookback_days - 1)
    if mode == "backfill":
        oldest = newest - timedelta(days=max(config.lookback_days * 8, 56))
        return oldest.isoformat(), newest.isoformat()

    with connect_database(db_path) as connection:
        latest_date = latest_history_date(connection)

    if latest_date is None:
        return default_oldest.isoformat(), newest.isoformat()

    incremental_oldest = date.fromisoformat(latest_date) - timedelta(days=2)
    if incremental_oldest > newest:
        incremental_oldest = newest
    if incremental_oldest < default_oldest:
        incremental_oldest = default_oldest
    return incremental_oldest.isoformat(), newest.isoformat()


def _write_raw_snapshots(
    paths: CoachPaths,
    current_time: datetime,
    mode: str,
    activities: list[dict[str, Any]],
    wellness: list[dict[str, Any]],
) -> str:
    stamp = current_time.strftime("%Y%m%dT%H%M%S%z")
    relative_dir = Path("data") / paths.profile_name / "raw" / "intervals" / f"{stamp}-{mode}"
    snapshot_dir = paths.base_dir / relative_dir
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (snapshot_dir / "activities.json").write_text(json.dumps(activities, indent=2) + "\n", encoding="utf-8")
    (snapshot_dir / "wellness.json").write_text(json.dumps(wellness, indent=2) + "\n", encoding="utf-8")
    return relative_dir.as_posix()


def _normalize_activities(
    activities: list[dict[str, Any]],
    raw_snapshot_dir: str,
    synced_at: str,
) -> list[ActivityRecord]:
    snapshot_path = f"{raw_snapshot_dir}/activities.json"
    normalized: list[ActivityRecord] = []
    for activity in activities:
        start_time = _string_value(activity, "start_date_local", "start_date")
        activity_date = _activity_date_string(activity)
        if not activity_date or not start_time:
            continue
        sport = _string_value(activity, "sport", "type") or "Run"
        distance_km = _distance_km(activity)
        duration_minutes = _duration_minutes(activity)
        normalized.append(
            ActivityRecord(
                external_id=_string_value(activity, "id") or f"{activity_date}:{_string_value(activity, 'name')}",
                activity_date=activity_date,
                start_time=start_time,
                name=_string_value(activity, "name") or "Intervals activity",
                sport=sport,
                activity_type=_string_value(activity, "type") or sport,
                distance_km=distance_km,
                duration_minutes=duration_minutes,
                training_load=_number_value(activity, "icu_training_load", "load", "training_load"),
                workout_type=classify_run_activity(activity) if _looks_like_run(activity) else "other",
                avg_pace_min_per_km=(duration_minutes / distance_km) if duration_minutes and distance_km else None,
                raw_snapshot_path=snapshot_path,
                last_seen_sync=synced_at,
            )
        )
    return normalized


def _normalize_wellness(
    wellness: list[dict[str, Any]],
    raw_snapshot_dir: str,
    synced_at: str,
) -> list[WellnessRecord]:
    snapshot_path = f"{raw_snapshot_dir}/wellness.json"
    rows: list[WellnessRecord] = []
    for entry in wellness:
        local_date = _string_value(entry, "id")
        if not local_date:
            continue
        rows.append(
            WellnessRecord(
                local_date=local_date,
                freshness=_number_value(entry, "freshness"),
                form=_number_value(entry, "form"),
                tsb=_number_value(entry, "tsb"),
                atl_load=_number_value(entry, "atl_load", "atlLoad"),
                sleep_secs=_number_value(entry, "sleep_secs", "sleepSecs"),
                soreness=_number_value(entry, "soreness"),
                fatigue=_number_value(entry, "fatigue"),
                raw_snapshot_path=snapshot_path,
                last_seen_sync=synced_at,
            )
        )
    return rows


def _write_recent_activity_history(history_path: Path, activities: list[dict[str, Any]]) -> None:
    normalized_history = []
    for activity in _sorted_run_activities(activities):
        distance_km = _distance_km(activity)
        duration_minutes = _duration_minutes(activity)
        normalized_history.append(
            {
                "date": _activity_date_string(activity),
                "sport": _string_value(activity, "sport", "type") or "Run",
                "workout_type": classify_run_activity(activity),
                "distance_m": float(distance_km * 1000) if distance_km is not None else 0.0,
                "moving_time_s": float(duration_minutes * 60) if duration_minutes is not None else 0.0,
                "training_load": _number_value(activity, "icu_training_load", "load", "training_load") or 0.0,
                "name": _string_value(activity, "name") or "Intervals activity",
            }
        )
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(normalized_history, indent=2) + "\n", encoding="utf-8")


def _update_database(
    db_path: Path,
    *,
    activities: list[ActivityRecord],
    wellness: list[WellnessRecord],
    result: SyncResult,
) -> None:
    with connect_database(db_path) as connection:
        upsert_activities(connection, activities)
        upsert_wellness(connection, wellness)
        changed_dates = [
            record.activity_date
            for record in activities
            if record.activity_date
        ]
        changed_dates.extend(
            record.local_date
            for record in wellness
            if record.local_date
        )
        rebuild_start = min(changed_dates) if changed_dates else result.state.date
        metrics = refresh_daily_metrics_from(
            connection,
            start_date=rebuild_start,
            end_date=result.state.date,
            default_last_workout_type=result.state.last_workout_type,
            seed_form=result.state.form,
            seed_sleep=result.state.sleep,
            seed_soreness=result.state.soreness,
        )
        if not metrics:
            replace_daily_metrics(connection, [])
        connection.commit()


def _derive_form(
    existing_state: AthleteState,
    latest_wellness: dict[str, Any] | None,
    run_activities: list[dict[str, Any]],
) -> tuple[int, str]:
    for key, label in (
        ("freshness", "Intervals wellness freshness"),
        ("form", "Intervals wellness form"),
        ("tsb", "Intervals wellness TSB"),
    ):
        value = _number_value(latest_wellness, key)
        if value is not None:
            return int(round(value)), label

    recent_loads = [
        load
        for activity in run_activities[:3]
        if (load := _number_value(activity, "icu_training_load", "load", "training_load")) is not None
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

    return min(existing_state.form, 0), "Fallback existing state clamp"


def _derive_fatigue_bucket(
    form: int,
    latest_wellness: dict[str, Any] | None,
    run_activities: list[dict[str, Any]],
) -> str:
    atl_load = _number_value(latest_wellness, "atlLoad", "atl_load")
    subjective_fatigue = _number_value(latest_wellness, "fatigue")
    recent_loads = [
        load
        for activity in run_activities[:3]
        if (load := _number_value(activity, "icu_training_load", "load", "training_load")) is not None
    ]
    average_load = (sum(recent_loads) / len(recent_loads)) if recent_loads else None

    severity = 0
    if form <= -20:
        severity = max(severity, 2)
    elif form <= -5:
        severity = max(severity, 1)

    if atl_load is not None:
        if atl_load >= 90:
            severity = max(severity, 2)
        elif atl_load >= 45:
            severity = max(severity, 1)

    if average_load is not None:
        if average_load >= 90:
            severity = max(severity, 2)
        elif average_load >= 45:
            severity = max(severity, 1)

    if subjective_fatigue is not None:
        if subjective_fatigue >= 4:
            severity = max(severity, 2)
        elif subjective_fatigue >= 2:
            severity = max(severity, 1)

    return ("low", "moderate", "high")[severity]


def _derive_sleep(
    existing_state: AthleteState,
    latest_wellness: dict[str, Any] | None,
) -> str:
    sleep_secs = _number_value(latest_wellness, "sleepSecs", "sleep_secs")
    if sleep_secs is None:
        return existing_state.sleep
    if sleep_secs >= 7 * 60 * 60:
        return "good"
    if sleep_secs >= 6 * 60 * 60:
        return "okay"
    return "poor"


def _derive_soreness(
    existing_state: AthleteState,
    latest_wellness: dict[str, Any] | None,
) -> str:
    soreness = _number_value(latest_wellness, "soreness")
    if soreness is None:
        return existing_state.soreness
    if soreness <= 2:
        return "low"
    if soreness <= 3:
        return "moderate"
    return "high"


def _sorted_run_activities(activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    run_activities = [activity for activity in activities if _looks_like_run(activity)]
    return sorted(
        run_activities,
        key=lambda activity: _activity_sort_key(activity) or datetime.min,
        reverse=True,
    )


def _latest_wellness_entry(wellness: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not wellness:
        return None
    return max(
        wellness,
        key=lambda entry: _wellness_sort_key(entry) or date.min,
    )


def _looks_like_run(activity: dict[str, Any]) -> bool:
    for key in ("type", "sport", "category", "sub_type"):
        value = _string_value(activity, key).lower()
        if "run" in value:
            return True
    return False


def _distance_km(activity: dict[str, Any]) -> float | None:
    distance = _number_value(activity, "distance", "distance_m", "distanceMeters", "distance_metres")
    if distance is None:
        distance = _number_value(activity, "distanceKm", "distance_km")
        if distance is not None:
            return distance
        return None
    return distance / 1000 if distance > 100 else distance


def _duration_minutes(activity: dict[str, Any]) -> float | None:
    seconds = _number_value(activity, "moving_time", "elapsed_time", "duration", "movingTime", "elapsedTime")
    if seconds is None:
        return None
    return seconds / 60


def _activity_date_string(activity: dict[str, Any]) -> str | None:
    raw = _string_value(activity, "start_date_local", "start_date", "id")
    if not raw:
        return None
    if "T" in raw:
        return raw.split("T", 1)[0]
    return raw


def _activity_sort_key(activity: dict[str, Any]) -> datetime | None:
    for key in ("start_date_local", "start_date", "updated"):
        value = _string_value(activity, key)
        if not value:
            continue
        parsed = _parse_datetime(value)
        if parsed is not None:
            return parsed
    return None


def _wellness_sort_key(entry: dict[str, Any]) -> date | None:
    for key in ("id", "updated"):
        value = _string_value(entry, key)
        if not value:
            continue
        if "T" in value:
            parsed = _parse_datetime(value)
            if parsed is not None:
                return parsed.date()
            continue
        try:
            return date.fromisoformat(value)
        except ValueError:
            continue
    return None


def _parse_datetime(raw_value: str) -> datetime | None:
    normalized = raw_value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass

    for pattern in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw_value, pattern)
        except ValueError:
            continue
    return None


def _number_value(payload: dict[str, Any] | None, *keys: str) -> float | None:
    if payload is None:
        return None
    for key in keys:
        value = payload.get(key)
        if value in (None, "", -1):
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value))
        except ValueError:
            continue
    return None


def _string_value(payload: dict[str, Any] | None, *keys: str) -> str:
    if payload is None:
        return ""
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        return str(value)
    return ""


def _is_generated_note(line: str) -> bool:
    generated_prefixes = (
        "- Synced from Intervals.icu",
        "- Lookback window:",
        "- Activities considered:",
        "- Last run activity:",
        "- Form source:",
    )
    return line.startswith(generated_prefixes)
