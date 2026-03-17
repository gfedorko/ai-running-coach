# Agent Start Here

If you are an agent working in this repo, read these files in this order:

1. `AGENTS.md`
2. `README.md`
3. `docs/FIRST_RUN.md`
4. `docs/FITNESS_AI_RUN_COACH.md`
5. `docs/ARCHITECTURE.md`
6. `docs/WORKFLOWS.md`

## Primary Goal
Help an athlete use local Intervals.icu data to:
- understand recent training
- plan the next workout or next week
- generate bounded one-off run, strength, and mobility sessions
- explain coaching decisions
- export FIT files for Garmin workflows and push the planned week to Intervals

## Canonical Source Of Truth
- Training history and derived state: `data/local/training.db` after a personal sync, otherwise `data/demo/training.db`
- Canonical planner API: `coach/planner.py`
- Canonical FIT export: `coach/fit_export.py`
- Canonical chat/tool layer: `coach/chat_tools.py`
- Runtime profile resolution: `coach/data_paths.py`
- Canonical workout templates: `data/workouts/structured_workout_library.md`

Read flows auto-select `data/local/` first and fall back to `data/demo/` when local data is missing. Write flows must target `data/local/`.

Do not create a second planning engine.

## Compatibility Files
These exist to preserve old entrypoints. Prefer not to build new logic here:
- `coach/weekly_planner.py`
- `coach/training_planner.py`
- `coach/export.py`

## Main Commands
- `python scripts/chat_coach.py --ask "create intervals tomorrow"`
- `python scripts/chat_coach.py --ask "create a strength workout today"`
- `python scripts/chat_coach.py --ask "create a mobility session tonight"`
- `python scripts/chat_coach.py --ask "remember that I prefer strength on Thursdays"`
- `python scripts/sync_intervals.py`
- `python scripts/chat_coach.py --ask "plan next week"`
- `python scripts/plan_next_week.py`
- `python scripts/plan_next_week.py --local-only`
- `python scripts/preview_week.py --week-of YYYY-MM-DD`
- `python scripts/preview_week.py --weeks 4`
- `python scripts/preview_week.py --weeks 4 --write-local`
- `python scripts/push_intervals_week.py --week-of YYYY-MM-DD --dry-run`
- `python scripts/generate_workout.py`
- `python3 -m unittest discover -s tests`

## Safe Change Pattern
When making a feature change:

1. Update or extend canonical logic in `coach/planner.py`, `coach/chat_tools.py`, `coach/fit_export.py`, or the DB/metrics layer.
2. Keep wrapper modules thin.
3. Update tests.
4. Update `README.md` and `AGENTS.md` if the command surface or architecture changed.

## Common Mistakes To Avoid
- Do not plan from `athlete_state.md` when DB metrics are available.
- Do not write into `data/demo/`; write flows must target `data/local/`.
- Do not let chat or wrappers bypass the planner/export decision that every planned workout day, including easy runs, is exported.
- Do not claim mixed-domain weekly planning or non-run FIT export already exists; today those are one-off bounded chat flows only.
- Do not add another workout model unless the canonical one cannot be extended.
- Do not treat `recent_activities.json` as the primary planner input.
- Do not bypass readiness/recovery caps in chat responses.
