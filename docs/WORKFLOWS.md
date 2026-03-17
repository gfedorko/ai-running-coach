# Workflows

## Standard User Flow

1. Fresh clone demo flow:
   - `python scripts/chat_coach.py --ask "summarize my recent training"`
   - `python scripts/chat_coach.py --ask "plan next week"`
   - `python scripts/chat_coach.py --ask "create intervals tomorrow"`
   - `python scripts/chat_coach.py --ask "create a strength workout today"`
   - `python scripts/plan_next_week.py --local-only`
2. After connecting Intervals:
   - `python scripts/sync_intervals.py`
3. Ask the coach questions:
   - `python scripts/chat_coach.py --ask "summarize my recent training"`
   - `python scripts/chat_coach.py --ask "explain my readiness"`
   - `python scripts/chat_coach.py --ask "plan next week"`
   - `python scripts/chat_coach.py --ask "create a mobility session tonight"`
   - `python scripts/chat_coach.py --ask "remember that I prefer strength on Thursdays"`
4. Export artifacts and push the same week to Intervals by default:
   - `python scripts/chat_coach.py --ask "generate fit files for next week"`
   - `python scripts/chat_coach.py --ask "generate fit files locally for next week"`
   - `python scripts/plan_next_week.py`
   - `python scripts/plan_next_week.py --week-of YYYY-MM-DD --local-only`
   - Publish only the next calendar week to Intervals.icu so projected fatigue stays tied to near-term, realistic training.
5. Preview or explicitly rerun the same plan on Intervals:
   - `python scripts/preview_week.py --week-of YYYY-MM-DD`
   - `python scripts/preview_week.py --weeks 4`
   - `python scripts/preview_week.py --weeks 4 --write-local`
   - `python scripts/push_intervals_week.py --week-of YYYY-MM-DD --dry-run`
   - `push_intervals_week.py --dry-run` is the safe preview path before real push credentials are configured

## Common Agent Tasks

### Add A New Coaching Rule
- Start in `coach/planner.py` or `coach/readiness.py`
- Add or update tests first if the rule changes visible behavior
- If the rule depends on derived data, extend `coach/metrics.py`
- Update docs if the behavior changes user-facing commands or planner outputs

### Add A New Chat Intent
- Start in `coach/chat_tools.py`
- Keep routing keyword-based and bounded
- Route to an existing deterministic function when possible
- If new data is needed, add it below the chat layer rather than embedding logic in the router

### Update First-Run Docs
- Update `README.md`, `docs/FIRST_RUN.md`, and `docs/START_HERE.md` together
- Keep demo-first and post-Intervals flows separate
- Be explicit about which commands push to Intervals and which stay local-only

### Change FIT Export Behavior
- Edit `coach/fit_export.py`
- Keep the planner model unchanged unless the new export requirement truly needs new fields
- Verify with:
  - `python scripts/plan_next_week.py`
  - `python scripts/plan_next_week.py --local-only`
  - `python scripts/push_intervals_week.py --week-of YYYY-MM-DD --dry-run`
  - `python3 -m unittest discover -s tests`

### Change Weekly Scheduling
- Edit `coach/planner.py`
- Check:
  - run-day counts
  - long-run day placement
  - readiness downgrades
  - conservative fallback behavior
- Update any tests that assert day/date placement

## Verification Checklist
- `python3 -m unittest discover -s tests`
- `python scripts/generate_workout.py`
- `python scripts/chat_coach.py --ask "plan next week"`
- `python scripts/chat_coach.py --ask "create intervals tomorrow"`
- `python scripts/chat_coach.py --ask "create a strength workout today"`
- `python scripts/chat_coach.py --ask "create a mobility session tonight"`
- `python scripts/chat_coach.py --ask "remember that I prefer strength on Thursdays"`
- `python scripts/chat_coach.py --ask "generate fit files for next week"`
- `python scripts/chat_coach.py --ask "generate fit files locally for next week"`
- `python scripts/plan_next_week.py --local-only`
- `python scripts/preview_week.py --weeks 4`
- `python scripts/preview_week.py --weeks 4 --write-local`
- `python scripts/push_intervals_week.py --week-of YYYY-MM-DD --dry-run`

## Decision Rules
- If DB metrics and markdown state disagree, trust the DB-backed path.
- If history coverage is thin, keep the plan conservative.
- If a change affects planning, update the canonical planner, not only the wrappers.
- If a change affects agent behavior, update both `AGENTS.md` and the relevant docs in `docs/`.
