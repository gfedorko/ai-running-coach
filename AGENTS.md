# AGENTS.md

## Repo Goal
Build a local Intervals-backed AI training coach that syncs athlete data from Intervals.icu, maintains normalized local history in SQLite, generates deterministic running recommendations, exposes a bounded chat interface for plans and one-off sessions, and exports/pushes structured running workouts through FIT files.

## Canonical Workspace
- This repository root is the canonical workspace for the dev run coach.
- Do not move active development back to `~/Development/run-coach`.
- Keep project code, data, scripts, tests, and documentation aligned to this repo.
- Read `docs/START_HERE.md`, `docs/FITNESS_AI_RUN_COACH.md`, `docs/ARCHITECTURE.md`, and `docs/WORKFLOWS.md` before larger changes.

## Product Scope
- Keep the system local-first and easy to understand.
- Use markdown as the editable knowledge base where practical.
- Support Intervals.icu sync into local files and SQLite.
- Support DB-backed readiness, goal-aware next-workout generation, and Monday-Sunday weekly planning.
- Support a bounded CLI chatbot for talking to training data, triggering supported actions, generating one-off run/strength/mobility sessions, and capturing lightweight preferences.
- Support local FIT export and an Intervals weekly workout upload flow.
- Leave clear extension points for Garmin activity ingestion, race-goal refinement, and richer load modeling.

## Engineering Expectations
- Prefer Python 3.11+ with standard library solutions first.
- Keep files small, readable, and heavily commented where logic is not obvious.
- Use simple functions and light data models instead of deep abstractions.
- Avoid heavy frameworks.
- Preserve a straightforward folder layout so an AI agent can navigate the project quickly.

## Coding Guidance
- Keep parsing logic tolerant of simple markdown and JSON formats.
- Make coaching rules explicit in code instead of hiding them behind generic engines.
- Wrap vendored dependencies such as `.vendor/fit_tool` behind repo-local modules.
- When adding new features, preserve the existing readable structure before introducing new layers.
- Add TODO comments for future external integrations instead of speculative implementations.

## Current System Intent
- Sync Intervals.icu activities and wellness through `python scripts/sync_intervals.py`.
- Keep checked-in starter data under `data/demo/` and personal mutable data under `data/local/`.
- Read flows auto-select `data/local/` when it is complete and fall back to `data/demo/` otherwise.
- Write synced state to `data/local/athlete/athlete_state.md`, `data/local/athlete/recent_activities.json`, `data/local/raw/intervals/`, and `data/local/training.db`.
- Treat `coach/storage.py`, `coach/metrics.py`, `coach/readiness.py`, and `coach/planner.py` as the canonical coaching stack.
- Use `python scripts/chat_coach.py` as the main user-facing entrypoint for supported coaching questions and actions.
- Support one-off run, strength, and mobility session generation through the bounded chat path.
- Keep `python scripts/generate_workout.py` as a compatibility view over the canonical planner, with a conservative no-DB fallback.
- Support calendar-week preview/export/push through `python scripts/plan_next_week.py`, `python scripts/preview_week.py`, and `python scripts/push_intervals_week.py`, with `plan_next_week.py` exporting locally and pushing to Intervals by default.

## Current Implementation Notes
- `coach/planner.py` owns the canonical planning API: `generate_plan(base_dir, mode="next"|"weekly", target_date=None, persist=False)`.
- `coach/fit_export.py` owns the canonical FIT export path for local artifacts and Intervals push preparation.
- `coach/fit_export.py` validates generated FIT workouts and writes artifact manifests with checksums and validation results.
- `coach/chat_tools.py` owns the bounded chat tool layer. Keep it deterministic and intent-routed rather than open-ended.
- `coach/training_sessions.py` owns bounded one-off session generation for running, strength, and mobility.
- `coach/data_paths.py` owns demo/local profile resolution and local-write bootstrapping.
- `coach/weekly_planner.py`, `coach/training_planner.py`, and `coach/export.py` are compatibility wrappers only.
- `coach/intervals.py` owns both Intervals sync and Intervals weekly calendar upload helpers.
- `coach/storage.py` now also stores `training_sessions`, `planning_requests`, and `preference_events` for chat-driven session generation and preference capture.
- `data/workouts/structured_workout_library.md` is the canonical structured workout template source.
- `data/workouts/workout_library.md` is legacy compatibility input and should not become the primary planner path again.
- `data/demo/` is checked-in synthetic starter data for public clones and tests.
- `data/local/` is local-only runtime data and must stay ignored by git.
- `data/local/athlete/athlete_state.md` and `data/local/athlete/recent_activities.json` are compatibility artifacts generated from the DB-backed sync; do not treat them as the planning source of truth.
- The planner must stay conservative when DB history is incomplete or recent load is excessive.
- FIT export and Intervals weekly push should include every planned workout day, including easy runs.
- `python scripts/chat_coach.py --ask "generate fit files for next week"` and `python scripts/plan_next_week.py` should export locally and auto-push to Intervals unless the user explicitly requests a local-only export.
- One-off strength and mobility sessions are persisted locally but are not yet full FIT or Intervals workout-file exports.
- Publish only the next calendar week to Intervals by default; use local previews for farther-ahead planning so Intervals fatigue projections remain realistic.
