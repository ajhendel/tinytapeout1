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
      calibration/               block A, one file per fixed macro
        ro_inv1_31stage.md
        ro_inv2_31stage.md
        ro_inv4_31stage.md
        ro_inv1_31stage_loaded.md
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
- the lowest supply voltage at which the configuration still computes its truth
  table correctly

Cross cutting:
- which of the three model layers is closest to silicon for each quantity, and
  by how much
