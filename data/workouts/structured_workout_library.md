# Structured Workout Library

This library is used for weekly planning and FIT export.
Each `step:` line uses:
`name | duration_kind | duration_value | target | note`

- `duration_kind`: `time`, `distance`, or `open`
- `duration_value`: seconds for `time`, metres for `distance`, `0` for `open`
- `target`: `easy`, `steady`, `threshold`, `hard`, `long`, or `open`

## Easy
name: Easy Aerobic Run
type: easy
notes: Comfortable aerobic maintenance run.
step: Warm up|time|600|easy|Relax into the run.
step: Aerobic running|time|2100|easy|Conversational effort throughout.
step: Cool down|open|0|open|Walk and mobility as needed.

## Easy 50
name: Easy Aerobic Run
type: easy
notes: Comfortable aerobic maintenance run.
step: Warm up|time|600|easy|Relax into the run.
step: Aerobic running|time|2400|easy|Conversational effort throughout.
step: Cool down|open|0|open|Walk and mobility as needed.

## Easy 55
name: Easy Aerobic Run
type: easy
notes: Comfortable aerobic maintenance run.
step: Warm up|time|600|easy|Relax into the run.
step: Aerobic running|time|2700|easy|Conversational effort throughout.
step: Cool down|open|0|open|Walk and mobility as needed.

## Steady
name: Steady Aerobic Run
type: steady
notes: Controlled aerobic work without drifting toward race effort.
step: Warm up|distance|2000|easy|Keep the first kilometres relaxed.
step: Steady running|time|1800|steady|Settle into controlled aerobic work.
step: Cool down|distance|2000|easy|Ease off gradually.

## Steady 35
name: Steady Aerobic Run
type: steady
notes: Controlled aerobic work without drifting toward race effort.
step: Warm up|distance|2000|easy|Keep the first kilometres relaxed.
step: Steady running|time|2100|steady|Settle into controlled aerobic work.
step: Cool down|distance|2000|easy|Ease off gradually.

## Steady 40
name: Steady Aerobic Run
type: steady
notes: Controlled aerobic work without drifting toward race effort.
step: Warm up|distance|2000|easy|Keep the first kilometres relaxed.
step: Steady running|time|2400|steady|Settle into controlled aerobic work.
step: Cool down|distance|2000|easy|Ease off gradually.

## Threshold
name: Threshold Session
type: threshold
notes: Strong aerobic quality without full race intensity.
step: Warm up|distance|2000|easy|Finish warm and ready to work.
step: Threshold rep 1|time|480|threshold|Smooth and controlled.
step: Recovery 1|time|120|open|Jog easy.
step: Threshold rep 2|time|480|threshold|Keep the pace even.
step: Recovery 2|time|120|open|Jog easy.
step: Threshold rep 3|time|480|threshold|Relax the shoulders and stay tall.
step: Recovery 3|time|120|open|Jog easy.
step: Threshold rep 4|time|480|threshold|Finish strong, not all-out.
step: Cool down|distance|2000|easy|Jog easy to reset.

## Threshold 3x8
name: Threshold Session
type: threshold
notes: Strong aerobic quality without full race intensity.
step: Warm up|distance|2000|easy|Finish warm and ready to work.
step: Threshold rep 1|time|480|threshold|Smooth and controlled.
step: Recovery 1|time|120|open|Jog easy.
step: Threshold rep 2|time|480|threshold|Keep the pace even.
step: Recovery 2|time|120|open|Jog easy.
step: Threshold rep 3|time|480|threshold|Relax the shoulders and stay tall.
step: Cool down|distance|2000|easy|Jog easy to reset.

## Hard
name: Hard Intervals
type: hard
notes: High-end aerobic work for clearly positive readiness days.
step: Warm up|distance|3000|easy|Include a few light strides before the first rep.
step: Hard rep 1|time|180|hard|Fast but controlled.
step: Recovery 1|time|120|open|Jog easy.
step: Hard rep 2|time|180|hard|Hold rhythm, not panic effort.
step: Recovery 2|time|120|open|Jog easy.
step: Hard rep 3|time|180|hard|Stay tall and relaxed.
step: Recovery 3|time|120|open|Jog easy.
step: Hard rep 4|time|180|hard|Keep the effort even.
step: Recovery 4|time|120|open|Jog easy.
step: Hard rep 5|time|180|hard|One more controlled rep.
step: Recovery 5|time|120|open|Jog easy.
step: Hard rep 6|time|180|hard|Finish sharp, not sprinting.
step: Cool down|distance|2000|easy|Ease down fully.

## Long
name: Long Run
type: long
notes: Durable aerobic volume with controlled pacing.
step: Settle in|time|1200|easy|Let the effort come to you.
step: Long aerobic running|time|4200|long|Stay relaxed and steady.
step: Finish easy|time|600|easy|Keep it smooth to the end.

## Long 90
name: Long Run
type: long
notes: Durable aerobic volume with controlled pacing.
step: Settle in|time|900|easy|Let the effort come to you.
step: Long aerobic running|time|3900|long|Stay relaxed and steady.
step: Finish easy|time|600|easy|Keep it smooth to the end.

## Long 110
name: Long Run
type: long
notes: Durable aerobic volume with controlled pacing.
step: Settle in|time|1200|easy|Let the effort come to you.
step: Long aerobic running|time|4800|long|Stay relaxed and steady.
step: Finish easy|time|600|easy|Keep it smooth to the end.

## Reduced Long
name: Reduced Long Run
type: long
notes: Conservative long aerobic session when readiness is limited.
step: Settle in|time|900|easy|Keep it light from the start.
step: Long easy running|time|3000|long|Stay aerobic throughout.
step: Finish easy|time|600|easy|Avoid pressing late.

## Reduced Long 85
name: Reduced Long Run
type: long
notes: Conservative long aerobic session when readiness is limited.
step: Settle in|time|900|easy|Keep it light from the start.
step: Long easy running|time|3600|long|Stay aerobic throughout.
step: Finish easy|time|600|easy|Avoid pressing late.
