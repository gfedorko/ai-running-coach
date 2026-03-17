# Fitness AI Training Coach

## Product Goal
Build a local AI training coach that uses Intervals.icu data, explicit coaching rules, and structured workout templates to help an athlete:
- understand recent training
- ask questions about fitness, readiness, fatigue, and workout history
- plan the next running workout or next running week
- create bounded one-off run, strength, and mobility sessions
- generate FIT files for Garmin-compatible execution

## What The Product Should Feel Like
The end experience should behave like a practical coaching chatbot, not a generic LLM toy.

The user should be able to say things like:
- "How did last week go?"
- "Am I ready for a workout tomorrow?"
- "Plan next week around my goal."
- "Why did you choose threshold instead of hard intervals?"
- "Create intervals tomorrow."
- "Create a strength workout today."
- "Create a mobility session tonight."
- "Generate FIT files for next week."

The system should answer from local data and deterministic coaching logic, then explain the result clearly.

## Canonical Product Shape

### Inputs
- Intervals.icu activity and wellness data
- checked-in demo athlete profile
- checked-in demo goal configuration
- local athlete profile overrides
- local goal overrides
- shared structured workout templates
- shared training rules
- optional manual check-ins

### Core Engine
- normalized SQLite history
- derived daily metrics
- readiness and recovery constraints
- deterministic next-workout and weekly planner
- bounded one-off session builders
- persisted planning requests and lightweight preference capture

### Outputs
- chat answers
- human-readable workout recommendations
- weekly markdown plan summaries
- FIT workout files
- optional Intervals calendar events

## Product Boundaries
- The AI layer explains and routes actions.
- The deterministic planner remains authoritative.
- The chatbot should not invent unsupported workouts outside planner constraints.
- Garmin device sync is out of scope in v1; local FIT generation is in scope.
- Intervals push is secondary to the core local planning and export workflow.
- Weekly planning is currently running-first.
- One-off strength and mobility sessions are supported today, but they are not yet full FIT or Intervals workout-file exports.

## Current Repo Mapping
- Canonical planner: `coach/planner.py`
- Canonical one-off session builder: `coach/training_sessions.py`
- Canonical FIT export: `coach/fit_export.py`
- Canonical chat/tool layer: `coach/chat_tools.py`
- Main chat CLI: `scripts/chat_coach.py`
- Runtime path resolver: `coach/data_paths.py`
- DB source of truth: `data/local/training.db` after sync, otherwise `data/demo/training.db`
- Canonical workout template source: `data/workouts/structured_workout_library.md`

## Near-Term Development Priorities
1. Keep the planner coherent and conservative when history is incomplete or recovery is poor.
2. Improve the chat interface so it answers supported training questions reliably.
3. Strengthen weekly planning against explicit race goals and recent training load.
4. Bring one-off non-run session generation under deeper load-aware constraints.
4. Keep FIT export stable and Garmin-friendly.
5. Avoid over-engineering. Favor readable deterministic code over agentic complexity.

## Agent Guidance
If you are an agent working on this repo, optimize for this product outcome:

"A local Intervals-backed training coach CLI that can talk about training, plan the running week, create bounded one-off workouts, and generate Garmin-ready FIT files for supported running workflows."

When in doubt:
- prefer the DB-backed planner path
- keep the chat layer bounded and explainable
- reuse the canonical workout model
- update docs when behavior changes
