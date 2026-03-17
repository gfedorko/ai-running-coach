# Workout Library

## Threshold Session
type: Threshold
allowed_readiness: threshold_allowed,hard_allowed
fit_exportable: true
structure: repeats
warmup_distance_km: 2
repeats: 4
work_duration_min: 8
recovery_duration_min: 2
target: threshold
cooldown_distance_km: 2
notes: Strong aerobic quality session without full race intensity.

## Hard Intervals
type: Hard
allowed_readiness: hard_allowed
fit_exportable: true
structure: repeats
warmup_distance_km: 3
repeats: 6
work_duration_min: 3
recovery_duration_min: 2
target: hard
cooldown_distance_km: 2
notes: Use only when athlete form is clearly positive.

## Easy Run
type: Easy
allowed_readiness: easy_only,steady_allowed,threshold_allowed,hard_allowed
fit_exportable: false
structure: simple
duration_min: 45
target: easy
notes: Keep effort comfortable and conversational.

## Steady Run
type: Steady
allowed_readiness: steady_allowed,threshold_allowed
fit_exportable: true
structure: simple
warmup_distance_km: 2
duration_min: 30
target: steady
cooldown_distance_km: 2
notes: Controlled aerobic work when a harder session is not warranted.

## Long Progression Run
type: Long
allowed_readiness: steady_allowed,threshold_allowed,hard_allowed
fit_exportable: true
structure: long_progression
warmup_distance_km: 2
easy_duration_min: 50
steady_duration_min: 20
cooldown_distance_km: 1
notes: Start easy and finish with controlled pressure.

## Long Easy Run
type: Long
allowed_readiness: easy_only,steady_allowed,threshold_allowed,hard_allowed
fit_exportable: false
structure: simple
duration_min: 90
target: long
notes: Keep the long run easy when fatigue is elevated.
