# Local AI Training Coach

This repository contains a local-first training coach that can:
- sync athlete state from Intervals.icu
- persist normalized history and derived metrics in SQLite
- generate a deterministic next running workout or next running week from the DB-backed state
- create bounded one-off run, strength, and mobility sessions through the chat interface
- export Garmin-ready FIT workouts locally
- preview and dry-run an Intervals weekly workout push
- answer bounded coaching questions through a local CLI chat surface

## Canonical Repo
- Active development for the dev run coach happens in this repository root.
- Do not use `~/Development/run-coach` as the working copy going forward.

## Agent Docs
- Start here if you are editing the repo as an agent: `docs/START_HERE.md`
- First-run human and Codex onboarding: `docs/FIRST_RUN.md`
- Product brief: `docs/FITNESS_AI_RUN_COACH.md`
- Architecture map: `docs/ARCHITECTURE.md`
- Task and verification playbook: `docs/WORKFLOWS.md`
- Marathon-planning rationale: `docs/MARATHON_TRAINING_LOGIC.md`

## Install
```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Requirements:
- Python 3.11+
- `python -m pip install -r requirements.txt`

Dependency note:
- Public setup uses `requirements.txt`.
- Fresh public users should treat that as the supported install path.

## Working Commands
- `python scripts/sync_intervals.py`
  - pulls Intervals activities and wellness
  - seeds `data/local/` from the checked-in demo profile on first write
  - updates `data/local/athlete/athlete_state.md`
  - refreshes `data/local/athlete/recent_activities.json`
  - writes raw snapshots under `data/local/raw/intervals/`
  - maintains `data/local/training.db` and derived `daily_metrics`
- `python scripts/chat_coach.py`
  - main user-facing entrypoint
  - routes supported questions to deterministic local tools
  - reads `data/local/` when available, otherwise falls back to `data/demo/`
  - can summarize training, explain readiness, analyze last week, plan next week, explain plan choices, create one-off run/strength/mobility sessions, save simple training preferences, and export FIT files with automatic Intervals calendar push
- `python scripts/plan_next_week.py`
  - builds the canonical next Monday-Sunday plan
  - writes markdown and validated FIT exports under `output/plans/<week-start>/`
  - pushes the same planned workouts to Intervals.icu by default
  - recommended publish cadence is one week at a time so Intervals fatigue projections stay near-term and adjustable
  - accepts `--week-of YYYY-MM-DD` and `--local-only`
  - records a richer `artifacts.json` manifest with checksums and validation results
- `python scripts/inspect_fit.py path/to/workout.fit --manifest path/to/artifacts.json`
  - decodes one exported FIT workout
  - prints workout/file metadata and step structure
  - cross-checks the file against the artifact manifest when provided
- `python scripts/generate_workout.py`
  - renders today's or the next planned workout as a daily compatibility view
  - falls back to a conservative markdown-based recommendation if DB metrics are unavailable
- `python scripts/preview_week.py --week-of YYYY-MM-DD`
- `python scripts/preview_week.py --weeks 4`
- `python scripts/preview_week.py --weeks 4 --write-local`
  - previews the canonical weekly plan
- `python scripts/push_intervals_week.py --week-of YYYY-MM-DD --dry-run`
  - previews or explicitly reruns the Intervals upload path without rewriting the local export workflow

## Supported Chat Prompts

Exact bounded prompts that work today include:
- `python scripts/chat_coach.py --ask "summarize my recent training"`
- `python scripts/chat_coach.py --ask "explain my readiness"`
- `python scripts/chat_coach.py --ask "am I ready for a workout tomorrow?"`
- `python scripts/chat_coach.py --ask "how did last week go?"`
- `python scripts/chat_coach.py --ask "plan next week"`
- `python scripts/chat_coach.py --ask "why was this week chosen?"`
- `python scripts/chat_coach.py --ask "preview the next 4 weeks"`
- `python scripts/chat_coach.py --ask "create intervals tomorrow"`
- `python scripts/chat_coach.py --ask "create a strength workout today"`
- `python scripts/chat_coach.py --ask "create a mobility session tonight"`
- `python scripts/chat_coach.py --ask "remember that I prefer strength on Thursdays"`
- `python scripts/chat_coach.py --ask "generate fit files locally for next week"`

The chat layer is intentionally bounded. Prefer these exact or near-exact phrases over open-ended requests.

## Public-Safe Data Layout
- `data/demo/`
  - checked-in synthetic starter data
  - safe for fresh clones and tests
- `data/local/`
  - local-only personal profile, goal, DB, snapshots, and generated compatibility files
  - ignored by git and created or updated by write flows
- `data/workouts/`
  - shared canonical workout templates used by both demo and local profiles
- `RUN_COACH_PROFILE=demo|local`
  - optional override for read-only flows
  - default behavior is `local` when present, otherwise `demo`
  - write flows always target `data/local/`

## Current Product Boundary
- Weekly planning is currently running-first and driven by the canonical planner in `coach/planner.py`.
- One-off strength and mobility sessions are supported through the bounded chat layer and are persisted locally.
- Running workouts are FIT-exportable today.
- Strength and mobility sessions are currently chat/markdown/calendar-oriented only; they are not yet full FIT or Intervals workout-file exports.
- Intervals data is the authoritative source for synced training history, readiness context, and running-plan decisions. One-off non-run sessions are profile-aware today and will move under deeper load-aware constraints over time.

## Project Structure
```text
.
├── .env.example
├── .gitignore
├── AGENTS.md
├── README.md
├── docs
│   ├── ARCHITECTURE.md
│   ├── FIRST_RUN.md
│   ├── FITNESS_AI_RUN_COACH.md
│   ├── MARATHON_TRAINING_LOGIC.md
│   ├── START_HERE.md
│   └── WORKFLOWS.md
├── coach
│   ├── athlete.py
│   ├── data_paths.py
│   ├── export.py
│   ├── chat_tools.py
│   ├── fit_export.py
│   ├── generator.py
│   ├── goals.py
│   ├── history.py
│   ├── intervals.py
│   ├── metrics.py
│   ├── models.py
│   ├── planner.py
│   ├── readiness.py
│   ├── render.py
│   ├── storage.py
│   ├── training_sessions.py
│   ├── vendor.py
│   ├── weekly_planner.py
│   ├── workouts.py
│   └── zones.py
├── data
│   ├── demo
│   │   ├── athlete
│   │   │   ├── athlete_state.md
│   │   │   ├── base_profile.md
│   │   │   └── recent_activities.json
│   │   ├── goals
│   │   │   └── current_goal.md
│   │   └── training.db
│   ├── coaching
│   │   └── training_rules.md
│   ├── local
│   │   ├── athlete
│   │   ├── goals
│   │   ├── raw
│   │   │   └── intervals
│   │   └── training.db
│   └── workouts
│       ├── structured_workout_library.md
│       └── workout_library.md
├── output
│   └── plans
├── scripts
│   ├── analyze_recent_workouts.py
│   ├── generate_plan.py
│   ├── generate_workout.py
│   ├── chat_coach.py
│   ├── check_in.py
│   ├── inspect_fit.py
│   ├── plan_next_week.py
│   ├── preview_week.py
│   ├── push_intervals_week.py
│   ├── summarize_training.py
│   └── sync_intervals.py
└── tests
```

## Intervals Environment
```bash
export INTERVALS_ICU_ATHLETE_ID=i123456
export INTERVALS_ICU_API_KEY=replace_me
export INTERVALS_LOOKBACK_DAYS=14
```

## Fresh Clone Workflow
```bash
cd /path/to/Running-Plan
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/chat_coach.py --ask "summarize my recent training"
python scripts/chat_coach.py --ask "plan next week"
python scripts/chat_coach.py --ask "create intervals tomorrow"
python scripts/chat_coach.py --ask "create a strength workout today"
python scripts/generate_workout.py
python scripts/plan_next_week.py --local-only
```

These commands run against the synthetic demo profile until you sync your own Intervals account.

## First-Time Local Sync Workflow
```bash
cp .env.example .env.local
export INTERVALS_ICU_ATHLETE_ID=your_athlete_id
export INTERVALS_ICU_API_KEY=your_api_key
export INTERVALS_LOOKBACK_DAYS=14
python scripts/sync_intervals.py
python scripts/chat_coach.py --ask "summarize my recent training"
python scripts/chat_coach.py --ask "plan next week"
python scripts/chat_coach.py --ask "generate fit files for next week"
```

The first personal sync seeds `data/local/` from the demo profile when needed, then writes all mutable state locally.

## Intervals Sync Safety
- `python scripts/sync_intervals.py` requires exported `INTERVALS_ICU_*` environment variables.
- Missing credentials fail fast with a clear error.
- Sync writes only to `data/local/`; it never mutates `data/demo/`.
- Read flows auto-select `data/local/` when it is complete, otherwise they fall back to `data/demo/`.
- Use local-only export paths until you actually intend to push to Intervals:
  - `python scripts/chat_coach.py --ask "generate fit files locally for next week"`
  - `python scripts/plan_next_week.py --local-only`
  - `python scripts/push_intervals_week.py --week-of YYYY-MM-DD --dry-run`
- `plan_next_week.py` and the non-local-only FIT chat command push to Intervals by default.

## Codex Starter Prompt
If you open this repo in Codex or another terminal-first coding agent, a good first prompt is:

```text
Read README.md, docs/FIRST_RUN.md, and AGENTS.md, then help me use this as a local training-coach CLI. Start on demo data unless I have already synced Intervals. Keep the chat layer bounded, treat Intervals-backed SQLite data as authoritative when present, and explain what commands I should run next.
```

For end-user coaching through the CLI, start with:
- `python scripts/chat_coach.py --ask "summarize my recent training"`
- `python scripts/chat_coach.py --ask "explain my readiness"`
- `python scripts/chat_coach.py --ask "plan next week"`
- `python scripts/chat_coach.py --ask "create intervals tomorrow"`
- `python scripts/chat_coach.py --ask "create a strength workout today"`
- `python scripts/chat_coach.py --ask "remember that I prefer strength on Thursdays"`

## Recommended Workflow
```bash
cd /path/to/Running-Plan
python scripts/sync_intervals.py
python scripts/chat_coach.py --ask "plan next week"
python scripts/plan_next_week.py
python scripts/inspect_fit.py output/plans/<week-start>/<fit-file>.fit --manifest output/plans/<week-start>/artifacts.json
python scripts/preview_week.py --week-of 2026-03-23
python scripts/push_intervals_week.py --week-of 2026-03-23 --dry-run
python scripts/generate_workout.py
```

## GitHub Publishing Notes
- Publish the repo with `data/demo/` and without `data/local/`.
- Verify `data/local/` stays untracked before the first public commit.
- Add a `LICENSE` file before sharing publicly so reuse terms are explicit.
- If you want outside contributions, also add `CONTRIBUTING.md` and any preferred Python version pin file before announcing the repo broadly.

## Canonical Architecture
- `coach/storage.py`, `coach/metrics.py`, `coach/readiness.py`, and `coach/planner.py` are the canonical DB-backed coaching stack.
- `coach/planner.py` owns the single public planning API: `generate_plan(base_dir, mode="next"|"weekly", target_date=None, persist=False)`.
- `coach/data_paths.py` resolves the active profile paths and enforces the demo/local split.
- `coach/training_sessions.py` owns bounded one-off session generation for running, strength, and mobility.
- `coach/fit_export.py` is the canonical FIT export path for both local artifacts and Intervals upload preparation.
- FIT export validates generated workout files after writing and records per-workout checksums and validation results in `artifacts.json`.
- `coach/chat_tools.py` is the bounded chat layer. It explains and orchestrates deterministic tools, one-off session generation, and lightweight preference capture; it does not invent unsupported plans.
- Chat FIT export and `scripts/plan_next_week.py` now export locally and push the same weekly workouts to Intervals by default unless `--local-only` or an explicit local-only chat phrase is used.
- Operationally, keep Intervals calendar publishing to one week at a time; preview farther ahead locally with `preview_week.py --weeks 4` or regenerate local forecast artifacts with `--write-local`.
- `data/demo/training.db` is the checked-in starter dataset.
- `data/local/training.db` becomes the active source of truth after the first personal sync.
- `data/local/athlete/athlete_state.md` and `data/local/athlete/recent_activities.json` remain generated compatibility artifacts, not the primary planning source of truth.
- `data/workouts/structured_workout_library.md` is the canonical structured workout template source.

## Notes
- `coach/weekly_planner.py`, `coach/training_planner.py`, and `coach/export.py` remain as compatibility wrappers over the canonical planner/export modules.
- The planner explicitly becomes conservative when DB history coverage is thin or recent load is excessive.
- Marathon build weeks also require recent volume/run-frequency support before adding threshold work or a full long run.
- FIT export and Intervals weekly push include every planned workout day, including easy runs.
- One-off strength and mobility sessions are persisted locally in SQLite but do not yet become full Intervals workout-file uploads.
- The vendored `.vendor/fit_tool` dependency is wrapped in repo modules; do not scatter direct vendor imports across the codebase.
- The Intervals weekly push flow uses deterministic `external_id` values so week reruns can replace managed events instead of duplicating them.
