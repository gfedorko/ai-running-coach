# Architecture

## Overview
The system is a local deterministic coaching engine with a bounded chat layer on top.

Flow:

1. Intervals sync pulls activities and wellness.
2. Normalized history is stored in SQLite.
3. Derived daily metrics are rebuilt.
4. The canonical running planner generates the next workout or next week.
5. The bounded chat layer can also generate one-off run, strength, and mobility sessions.
6. Running workouts render to text, FIT, or Intervals event payloads. One-off non-run sessions currently render to chat/markdown and local persistence.

## Core Modules

### Data And Metrics
- `coach/data_paths.py`
  - resolves `demo` vs `local` runtime data
  - seeds local profile and goal files for first-write flows
- `coach/storage.py`
  - SQLite schema and data access helpers
  - stores activities, wellness, check-ins, daily metrics, plans, plan items
  - stores one-off `training_sessions`, `planning_requests`, and `preference_events`
- `coach/metrics.py`
  - rebuilds derived daily metrics
  - builds training summaries and workout analyses
- `coach/readiness.py`
  - readiness buckets and caps

### Planning
- `coach/planner.py`
  - canonical planning API: `generate_plan(...)`
  - structured weekly plan models
  - readiness-aware next-workout generation
  - Monday-Sunday weekly planning
  - conservative fallback when history is thin or overloaded
- `coach/training_sessions.py`
  - bounded one-off session builders
  - running, strength, and mobility session rendering helpers

### Export And Integrations
- `coach/fit_export.py`
  - canonical FIT export
  - local weekly artifact export
- `coach/intervals.py`
  - Intervals sync
  - Intervals calendar event preparation and push helpers

### User-Facing Layer
- `coach/chat_tools.py`
  - bounded intent router over deterministic functions
  - one-off session generation and simple preference capture
- `scripts/chat_coach.py`
  - main CLI chat entrypoint

## Source Of Truth Hierarchy

### Canonical
- `data/demo/training.db`
- `data/workouts/structured_workout_library.md`
- `data/demo/goals/current_goal.md`
- `data/demo/athlete/base_profile.md`

### Active Local Runtime
- `data/local/training.db`
- `data/local/goals/current_goal.md`
- `data/local/athlete/base_profile.md`

### Generated Compatibility Artifacts
- `data/local/athlete/athlete_state.md`
- `data/local/athlete/recent_activities.json`

## Runtime Safety Rules

- Read flows auto-select `data/local/` first and fall back to `data/demo/` when local data is missing.
- Write flows must target `data/local/` only.
- `RUN_COACH_PROFILE=demo` is for read-only flows; mutating commands should still write to `data/local/`.
- `data/demo/` is a safe starter dataset, not a mutable planning target.

## Planner Contract

Public API:

`generate_plan(base_dir, mode="next"|"weekly", target_date=None, persist=False) -> dict`

Payload shape:
- `mode`
- `target_date`
- `context`
- `rationale`
- `items`
- optional `plan_id`

The planner is authoritative. Chat and scripts may explain or render plans, but should not invent workouts outside planner constraints.

## Current Capability Boundary

- Weekly planning remains running-first and lives in `coach/planner.py`.
- One-off strength and mobility sessions currently live beside the planner, not inside the weekly plan generator.
- Running FIT export and Intervals weekly push are canonical.
- Strength and mobility are persisted locally today but are not yet full Intervals workout-file exports.

## Workout Model
Canonical workout structures live in `coach/planner.py`:
- `StepDuration`
- `StepTarget`
- `WorkoutStep`
- `PlannedWorkout`
- `WeeklyPlan`

Use this model for:
- weekly previews
- daily workout rendering
- FIT export
- Intervals upload preparation

## Compatibility Wrappers
These should stay thin:
- `coach/weekly_planner.py`
- `coach/training_planner.py`
- `coach/export.py`

If logic grows here, move it back into the canonical module instead.
