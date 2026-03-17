# Marathon Training Logic

This planner keeps marathon weeks intentionally conservative and explainable.

## Rules encoded in `coach/planner.py`

- Most marathon weeks use one primary quality session, one controlled aerobic support day, and one long run.
- Threshold is preferred over faster interval work during marathon phases.
- Marathon-specific quality only appears when the recent week is reasonably close to the target build.
- Full long runs require recent consistency; otherwise the planner uses `reduced_long`.
- Easy and rest days stay between stressful sessions.

## Why these rules exist

These rules match common guidance from established coaches:

- Hal Higdon's marathon plans center the week on long runs and steady aerobic progression rather than stacking multiple hard interval sessions.
- Greg McMillan recommends letting stress and recovery alternate across the week and keeping easy runs genuinely easy.
- Marathon coaching literature consistently treats threshold or marathon-specific aerobic work as more relevant than frequent high-end interval sessions for the event.

## Online references

- Hal Higdon, marathon training guides and long-run guidance: <https://www.halhigdon.com/training/marathon-training/>
- Greg McMillan, stress + rest and easy-runs-easy guidance: <https://www.mcmillanrunning.com/the-marathon-training-academy-5-the-stress-rest-balance-in-running/> and <https://www.mcmillanrunning.com/run-your-easy-runs-easy/>
- Runner's World, marathon-specific workout guidance: <https://www.runnersworld.com/advanced/a20811902/marathon-training-tempo-workouts/>

## Current implementation boundary

The planner uses these sources as guardrails, not as an attempt to clone any one public plan. The code still stays local-first, deterministic, and biased toward caution when DB history is incomplete or recent load is already high.
