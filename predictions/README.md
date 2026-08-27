# predictions — pre-registration

The rule, from PLAN.md section 2 and section 4.

**Everything in this directory is committed before the shuttle deadline and is
append only afterwards.** Chips arriving is the reveal. A prediction edited after
the die exists is not a prediction.

A correction after the deadline is a NEW file that names the file it corrects
and says what was wrong. The original is never edited and never deleted. If that
feels uncomfortable at the time, that discomfort is the entire point of doing
this in advance.

## Why this exists

The chip's second paper is about the gap between what the open-PDK models say
and what the silicon does. That claim is worth nothing if the predictions were
written after the measurements, and nobody can tell the difference from the
outside unless the predictions are timestamped in public before the fact. Git
history in a public repository is the cheapest credible timestamp available.

## Layout

    predictions/
      README.md                  this file, the rule
      calibration/               block A, one file per fixed ring
        ro_inv1_31stage.md
        ro_inv2_31stage.md
        ro_inv4_31stage.md
        ro_inv1_31stage_loaded.md
        ro_inv1_11stage_compact.md
        ro_drive_node.md
        ro_twin_spread.md
      char/                      block C, one file per fixed path and the fits
        depth_series.md
        drive_series.md
        load_series.md
        isolation_pair.md
      tdc/                       block T
        tap_delay.md
      fabric/                    block B, a sampled set of configurations
        <config_hash>.md
      patch/                     block P, once the physics patch exists
      corrections/               post-deadline corrections, append only

## What every prediction file must contain

1. **What is predicted**, as a named quantity with units. "Ring frequency at
   1.80 V, 25 C, typical corner, in MHz."
2. **The value, with an uncertainty interval, and what the interval means.**
   A number without an interval cannot be wrong, so it cannot be a prediction.
3. **Which model layer produced it**, and separately for each layer we have:
   Liberty, Liberty plus extraction, transistor-level SPICE. These are allowed
   to disagree with each other and with silicon, and disagreement at one layer
   does not indict another. Recording them separately is what makes that
   distinction available later.
4. **The exact command and commit** that produced the number, so it can be
   regenerated.
5. **What would falsify it.** If nothing would, it is not a prediction.

## What must NOT go in a prediction file

Any quantity we can already measure some other way and therefore are not really
predicting. Any hedge broad enough to cover every outcome. Any claim about the
fabric's energy, which PLAN.md section 2 puts out of scope for tapeout one
because whole-chip current is the only instrument we will have.

## Status

Scaffold only, 2026-08-26. Nothing is predicted yet, because the RTL is not
frozen and predicting the behaviour of a design that is still moving is a way
of predicting nothing. The predictions are written in WP5, after WP4 freezes
the RTL, and before the shuttle deadline in docs/TT_LOGISTICS.md.

The one thing that IS fixed already is the list of quantities. Writing that list
now, before any of them are known, is what stops the list quietly becoming
"whatever turned out to be predictable".

### Quantities added 2026-08-27, when the RTL froze at 24 sites

The blocks that produce these did not exist when the list below was fixed. They
are added rather than substituted, and the original list stands.

Fixed characterization paths (src/char_paths.v), measured by the TDC:

- **The depth series slope and intercept.** Paths 8, 9, 0 and 10 are inv_1 at
  depths 2, 4, 8 and 16. Predict the per-stage delay (the slope) and the fixed
  offset from the launch gate, the select tree and the converter input (the
  intercept), separately, with intervals. **This one is load bearing: without a
  predicted slope the TDC calibration is unfalsifiable**, because any measured
  tap count can be turned into any delay by choosing a tap width afterwards.
- **The linearity of that series.** Predict the residual of a straight-line fit.
  If the relationship is not linear the intercept is not a constant and nothing
  else on the chip can be quoted against it, so predict the case that would
  invalidate the method.
- The drive series, paths 0 to 3, as ratios against path 0.
- The load series, paths 4 to 7 against 0 to 3, as the delay cost of one inv_1
  sink per stage at each drive variant.
- **The isolation pair.** Paths 14 and 15 differ only in whether each drive
  variant's input is gated. Predict the delay difference and its sign at each of
  the four drive variants. A prediction of "no difference" is allowed and is a
  real prediction here.

Calibration strip additions (src/calib_macro.v):

- The compact 11-stage ring against the 31-stage ring, as a per-stage ratio,
  which is a prediction about whether stage count and geometry are separable.
- The ring built from the fabric's own output stage against the plain inverter
  ring, which is the cost of configurability expressed as a frequency.
- **The spread of rings 0, 6 and 7**, which are the same circuit three times.
  This is the within-die variation floor, so it is the number every other
  difference on this chip has to beat. Predict it before seeing it, or the
  temptation to accept whatever floor makes a result significant is left
  standing. Note that on the 2026-08-27 build these three landed within 43 um of
  each other, so this is a spread over a small region and not across the die,
  and it must be described that way. There is no spatial prediction to make;
  see docs/AREA_GATE.md.

Input slew, which the same build turned into a live variable rather than a
detail:

- ~~Whether the site output node's transition at the slow corner is inside the
  sky130 Liberty characterization range.~~ **Answered 2026-08-27 before any
  prediction was written, which was the point of asking it then.** The library
  limit is 1.5 ns and the worst measured structure slews at 1.320 ns, so every
  fabric delay prediction is an interpolation. Not a prediction, therefore, and
  it does not belong in this directory; it is recorded in docs/AREA_GATE.md.
- What IS still a prediction, and a harder one: **the delay penalty of the slow
  input edge itself**. A fabric site is driven by a slower edge than a
  characterization path is, so predict the difference that slew alone accounts
  for when a fabric delay is quoted against a reference path. Getting this wrong
  is how the cost of configurability gets attributed to configurability when it
  was slew.

TDC (src/tdc.v):

- The mean tap delay, and the spread of bin widths across the 32 taps. The
  second is a prediction about how badly place and route distorts a delay line
  in this flow, and we currently have no basis for it beyond an order of
  magnitude, which is exactly the kind of thing worth writing down before
  finding out.

### Quantities to be predicted, fixed 2026-08-26

Calibration strip, per fixed ring oscillator, at nominal and at both supply
extremes, at 25 C:
- oscillation frequency
- the ratio between the inv_1 and inv_2 rings, and between inv_1 and inv_4
- the ratio between the loaded and unloaded inv_1 rings
- die-to-die spread of each of the above across the dies we receive

Fabric, for a sampled set of configurations that will be named before the
deadline:
- propagation delay from FAB_A to the column output, per drive variant setting
- the change in that delay per step of the load ladder
- the lowest WHOLE-CHIP supply voltage at which the configuration still computes
  its truth table correctly, quoted beside the voltage at which the scan CRC
  fails and the voltage at which the reference paths fail. Corrected 2026-08-27:
  there is no independent fabric supply on Tiny Tapeout, so the fabric's failure
  point is only meaningful relative to the instrument's failure point. See
  docs/MEASUREMENT_PROTOCOL.md.

Cross cutting:
- which of the three model layers is closest to silicon for each quantity, and
  by how much
