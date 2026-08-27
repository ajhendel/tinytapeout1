# EXPERIMENT MATRIX

The fixed list of studies this chip will run, written before fabrication.

## Why this is fixed in advance

Everything else in `predictions/` commits to what we think the ANSWERS will be.
This file commits to what the QUESTIONS are, and it is the more important of the
two. A study list assembled after the dies arrive is a list of whatever turned
out to be measurable, and the studies that did not work get quietly dropped
rather than reported as null results.

So this file is under the same rule as `predictions/`: **committed before the
shuttle deadline, append only afterwards.** A study that turns out to be
impossible on silicon stays in the table with its outcome recorded as
impossible, and why. That is a result.

Every row names its instrument, because the two instruments on this chip answer
different questions and a row that does not say which one it uses has not been
thought about. See docs/MEASUREMENT_PROTOCOL.md.

## The die budget

Dies are split before any measurement is taken, and the split is recorded here
rather than decided later.

| pool | purpose |
|---|---|
| **training** | everything in stage 1 of the protocol. Search runs here and only here. |
| **holdout** | never seen by any search. Finalists are re-measured here and that is the only thing it is used for. |
| **all** | studies with no search component, which cannot overfit and therefore run everywhere. |

The holdout guard lives on the DEVICE, in `harness/evofab/holdout.py`, not
inside the search loop, because a check inside the search is a check that a
second search, or a script someone writes at midnight, will not have.

## The matrix

| # | study | instrument | configurations | dies | control arm | what would falsify the headline |
|---|---|---|---|---|---|---|
| 1 | **Fixed-path model validation** | TDC | all 20 characterization paths, every drive variant where applicable | all | the three model layers against each other | agreement within noise at every layer, i.e. no gap to report |
| 2 | **TDC bin calibration** | TDC | the five-point depth series plus code density from the fabric | all | linearity of the depth series itself | a non-linear depth series, which would mean the fixed offset is not a constant and nothing else can be quoted |
| 3 | **Ring period** | frequency counter on the TDC ring | free-run, several window lengths | all | the depth series slope, independently | the two disagree, which invalidates every coarse-counted reading |
| 4 | **Drive-variant series** | TDC | paths 0 to 3, a fixed load with a varying driver, and the fabric at all four drive codes | all | ring oscillators 0 to 2, a different instrument on the same question | drive selection produces no resolvable delay difference |
| 5 | **Input-isolation cost** | TDC | paths 15 and 16 at all four drive variants; fabric sites 1,3,5,7 against 0,2,4,6 | all | the fixed pair against the fabric pair | fixed and fabric pairs disagree about the sign |
| 6 | **Load-ladder mechanism** | TDC | paths 17 and 18; fabric load field 0 to 3 | all | **Liberty predicts exactly zero**, see src/load_ladder.v | no resolvable difference, which confirms Liberty and is a publishable null |
| 7 | **Within-die variation floor** | frequency counter | calibration rings 0, 6, 7 | all | the three against each other | the floor exceeds the effects in rows 4 to 6, which retires those rows |
| 8 | **Per-site fabric delay** | TDC, stop-tap sweep | tap 0 to 19 at a fixed configuration, then per function and drive | all | the fixed-path prediction for the same cells | the per-site slope is not linear in tap index |
| 9 | **Model-disagreement search** | TDC | 10^4 to 10^6, stage 1 rules | **training only** | random configurations of matched depth | the search finds nothing that beats the random baseline's disagreement |
| 10 | **Transfer of finalists** | TDC | 20 to 100 finalists, exhaustive re-evaluation | **holdout** | the same finalists on training dies | winners do not transfer, which is the Thompson result and is a headline either way |
| 11 | **Fault campaign** | TDC and truth table | every site x every fault mode, on winners AND controls | winners and controls, several dies | the conventional control circuit | evolved and control degrade identically |
| 12 | **Feedback oscillation** | frequency counter | large sampled population, fb_en set | several | the calibration rings as a PVT covariate | the loop does not oscillate, or its frequency is not configuration dependent |
| 13 | **Voltage and temperature** | both | finalists only, stage 3 rules | several | scan CRC and reference paths as the instrument-failure control | the control fails before the fabric does, so nothing about the fabric was learned |

## Rows deliberately absent

Named so that their absence is a decision on the record rather than an
oversight.

- **Independent fabric undervolting.** No per-block supply exists on Tiny
  Tapeout. See docs/MEASUREMENT_PROTOCOL.md.
- **Spatial placement effects.** The three identical rings landed within 43 um
  of each other on a 1,023 um die. See docs/AREA_GATE.md.
- **Anything Ising or p-bit.** Blocks P and D are not on this chip.
- **Three-input functions, and therefore a full adder.** The fabric is a serial
  column with two Boolean inputs and one output. A full adder needs three in and
  two out and cannot be expressed. This was an example in an earlier draft of
  docs/FUNCTIONS.md and it was wrong.
- **Gate-level fault deletion.** Sabotage acts on a site's output, not on
  individual gates inside a site; the function bank is always active. The
  correct name is exhaustive single-site output fault injection.
- **Energy per configuration.** Whole-chip current is the only instrument and
  PLAN.md section 2 rules the claim out.

## Which comparisons a single trial can resolve

The converter's tap is about 0.121 ns. A comparison smaller than that cannot be
read from one trial, and saying so in advance is the difference between a study
that needs repeats and a study that quietly returns noise.

`tools/tdc_range.py` prints this table from every build's SDF and it is the
authority; the numbers below are from the 24-site build and are indicative.

| comparison | difference | taps | single trial? |
|---|---|---|---|
| input isolation pair | 372 ps | 3.1 | yes |
| load series, 0 vs 4 sinks | see the tool | | expected yes |
| drive series, x1 vs x8 | see the tool | | expected yes, after the redesign |
| load ladder pair | 7 ps at Liberty plus extraction | 0.06 | **no, and that is the point** |

The ladder pair is the interesting row. Liberty predicts exactly zero and
extraction predicts 7 ps, which is a twentieth of a tap, so the physical effect
this pair exists to find is one that neither of those layers can see. **The SPICE
prediction is not yet computed and it is what decides whether row 6 is a
measurement or a bound.** That is owed before the predictions are written, and
if SPICE also says the effect is far below a tap, row 6 becomes an upper-bound
result reported with its repeat count, which is still worth having.

## The rule that makes this a dataset rather than a demonstration

Rows 1 to 8 produce a structured public measurement set **whether or not the
search in row 9 finds anything interesting**. That is deliberate. A chip whose
value depends on an evolved circuit turning out to be surprising is a bet on
spectacle; a chip that publishes a calibrated model-to-silicon comparison across
20 fixed paths, four drive variants, two matched construction pairs and 24
configurable sites has produced something useful either way.

If row 9 comes back empty, that is itself worth publishing, and it is worth
publishing *because* rows 1 to 8 establish that the instrument could have seen
an effect had there been one.
