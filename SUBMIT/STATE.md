# STATE — what is verified, on one page

> **Historical document** — This page preserves development plans or records.
> The design was not submitted for fabrication, no silicon experiments were
> performed, and no submission or development work is currently planned.
> Tasks, deadlines, and future-tense statements below are historical.
> See the repository README for the final project status.

This historical snapshot records results from the physical-design tool flow.
Timing values depend on the extraction and timing models; they are not silicon
measurements. No purchase or submission is pending.

**Commit** `b101dc3`. **Build** `32bd0b9` (the RTL is identical; the only change
since is a comment). **Verified** 2026-08-28.

## Is it done?

**The work ended at the pre-silicon stage. The design was not submitted.**
The adjacent checklist records the abandoned submission plan.

## The physical build

| | measured | required |
|---|---|---|
| standard cell utilization | **28.4 %** | at or under about 32 % |
| placed instances | 54,874 | |
| routing DRC errors | **0** | 0 |
| antenna violations | **0** | 0 |
| setup slack, worst corner | **+7.10 ns** | positive |
| hold slack, worst corner | **+0.108 ns** | positive |
| tiles | 6x2 | |
| sites | 20 | |

## The instrument, at all nine process corners

| gate | measured | limit |
|---|---|---|
| converter range, every reference path inside one ring period | pass | |
| capture beats the ring kill | **+1.09 ns** at typical | positive |
| thermometer code monotone | pass | hard requirement |
| widest bin | **1.32 to 1.41 taps** | under 2.0 |
| sampling tree skew | **0.18 to 0.31 taps** | |
| stop selector trend with tap index | **0.044 taps/site** | under 0.25 |
| launch and merge slope bias | **3.0 to 4.5 %** | under 10 % |
| worst measured node inside the Liberty table | **88 %** of the range | under 100 % |

Local dry run of the full gate against the build artifacts: **57 of 57 pass.**

## What was fixed in the last round, and why it mattered

Four defects, none of which any test failed on, all of which would have shipped:

1. **The coarse counter was an asynchronous binary capture.** Gray coded now.
2. **The capture was losing its race against the ring kill at every fast
   corner**, by 0.04 to 0.06 ns. Readings would have come back one to two taps
   short, systematically, in the direction that looks like a fast circuit. The
   kill is now caused by the capture rather than raced against it.
3. **A 5.08 tap hole in the middle of the converter's range**, from a repeater
   the placer inserted on two of four sampling branches. Fifteen percent of the
   range in one undivided bin. It stayed monotone by luck; the other coin flip
   would have stopped the thermometer code being a thermometer code.
4. **The depth series was pre-registered against a depth the RTL does not
   build**, biasing the slope every other number is quoted against by 9.7 to
   11.6 percent.

The round cost **0.2 points of utilization**. Nothing was removed to pay for it.

## What is known and unresolved, on purpose

- **The load ladder.** Liberty says the effect is exactly zero, SPICE says +144
  to +371 ps, extraction has said 3, 7, 13, 45 and 57 ps for the same unchanged
  circuit and cannot represent the mechanism at all. Silicon arbitrates. This is
  the sharpest model-discrimination test on the chip and it is meant to be open.
- **The three identical calibration rings landed within 39 um of each other**, so
  their spread is a within-die variation floor and **not** a spatial claim. Do
  not let anyone write it as one.
- **Whether the die dithers.** Every comparison below one tap depends on it.
  It is study 2 and it is answered by the chip, not before.
