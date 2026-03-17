# First Run

## What This Repo Is

This project is a local CLI training coach.

Today it can:
- read and summarize Intervals-backed training history
- explain readiness and recent load
- plan the next running workout or next running week
- generate Garmin-ready FIT files for running workouts
- push the planned running week to Intervals
- create bounded one-off run, strength, and mobility sessions through chat
- save a few simple training preferences locally

It does not require a UI. The primary interface is the CLI, and it also works well as a Codex-style terminal workspace.

## Install

```bash
cd /path/to/Running-Plan
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Start On Demo Data

Fresh clones work immediately against the checked-in synthetic demo profile.

Try these first:

```bash
python scripts/chat_coach.py --ask "summarize my recent training"
python scripts/chat_coach.py --ask "explain my readiness"
python scripts/chat_coach.py --ask "plan next week"
python scripts/chat_coach.py --ask "create intervals tomorrow"
python scripts/chat_coach.py --ask "create a strength workout today"
python scripts/chat_coach.py --ask "create a mobility session tonight"
python scripts/generate_workout.py
python scripts/plan_next_week.py --local-only
```

By default, read-only flows use `data/local/` when present and fall back to `data/demo/` otherwise.

## Connect Your Own Intervals Account

Set your Intervals credentials:

```bash
export INTERVALS_ICU_ATHLETE_ID=your_athlete_id
export INTERVALS_ICU_API_KEY=your_api_key
export INTERVALS_LOOKBACK_DAYS=14
```

Then sync:

```bash
python scripts/sync_intervals.py
```

That command:
- seeds `data/local/` from demo data if needed
- writes your local athlete profile artifacts under `data/local/`
- updates `data/local/training.db`
- stores raw Intervals snapshots only under `data/local/raw/intervals/`

After the first sync, local data becomes the active runtime source automatically.

## Recommended First Personal Workflow

```bash
python scripts/chat_coach.py --ask "summarize my recent training"
python scripts/chat_coach.py --ask "explain my readiness"
python scripts/chat_coach.py --ask "plan next week"
python scripts/chat_coach.py --ask "generate fit files for next week"
python scripts/chat_coach.py --ask "remember that I prefer strength on Thursdays"
```

## Codex Starter Prompt

If you are using Codex or another coding agent in this repo, start with:

```text
Read README.md, docs/FIRST_RUN.md, and AGENTS.md. Treat this repo as a local training-coach CLI with demo data for fresh clones and local Intervals-backed data after sync. Keep the chat layer bounded, prefer the DB-backed planner path when local data exists, and tell me which commands to run next.
```

## Current Boundaries

- Weekly planning is currently running-first.
- One-off strength and mobility sessions are supported through chat, but they are not yet full FIT workout exports.
- Intervals-backed history is the key input for summaries, readiness, and running-plan decisions.
- One-off non-run sessions are profile-aware and persisted locally today, with deeper load-aware scheduling still to come.

## Privacy And Public Repo Behavior

- `data/demo/` is safe checked-in starter data.
- `data/local/` is for private mutable state and should stay ignored by git.
- Do not commit `.env`, `.env.local`, or anything under `data/local/`.
