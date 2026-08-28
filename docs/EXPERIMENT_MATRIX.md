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
| 2 | **TDC bin calibration** | TDC | code density with `tdc_src=calib`, a free-running ring as the stop, tens of thousands of trials; plus the six-point depth series | all | linearity of the depth series itself, which is an independent route to the same bin widths | a non-linear depth series, which would mean the fixed offset is not a constant and nothing else can be quoted; or a code density histogram with structure at the ring's own period, which would mean the two rings are not uncorrelated and the histogram is not a bin map |
| 3 | **Ring period** | frequency counter on the TDC ring | free-run, several window lengths | all | the depth series slope, independently | the two disagree, which invalidates every coarse-counted reading |
| 4 | **Drive-variant series** | TDC | paths 0 to 3, a fixed load with a varying driver, and the fabric at all four drive codes | all | ring oscillators 0 to 2, a different instrument on the same question | drive selection produces no resolvable delay difference |
| 5 | **Input-isolation cost** | TDC | paths 15 and 16 at all four drive variants; fabric sites 1,3,5,7 against 0,2,4,6 | all | the fixed pair against the fabric pair | fixed and fabric pairs disagree about the sign |
| 6 | **Load-ladder mechanism** | TDC | paths 17 and 18; fabric load field 0 to 3 | all | **Liberty predicts exactly zero**, SPICE predicts +144 to +371 ps, see src/load_ladder.v | no resolvable difference, which confirms Liberty, contradicts SPICE and is a publishable null either way |
| 7 | **Within-die variation floor** | frequency counter | calibration rings 0, 6, 7 | all | the three against each other | the floor exceeds the effects in rows 4 to 6, which retires those rows |
| 8 | **Per-site fabric delay** | TDC, stop-tap sweep | tap 0 to 19 at a fixed configuration, then per function and drive | all | the fixed-path prediction for the same cells, and the extracted per-tap selector offset from `tools/stop_tree.py`, subtracted before the fit | the per-site slope is not linear in tap index, or it moves by more than the selector correction when that correction is applied |
| 9 | **Model-disagreement search** | TDC | 10^4 to 10^6, stage 1 rules | **training only** | random configurations of matched depth | the search finds nothing that beats the random baseline's disagreement |
| 10 | **Transfer of finalists** | TDC | 20 to 100 finalists, exhaustive re-evaluation | **holdout** | the same finalists on training dies | winners do not transfer, which is the Thompson result and is a headline either way |
| 11 | **Fault campaign** | TDC and truth table | every site x every fault mode, on winners AND controls | winners and controls, several dies | the conventional control circuit | evolved and control degrade identically |
| 12 | **Feedback oscillation** | frequency counter | large sampled population, fb_en set | several | the calibration rings as a PVT covariate | the loop does not oscillate, or its frequency is not configuration dependent |
| 13 | **Converter reading integrity** | TDC | every trial of every row above, as a by-product | all | the four failure statuses the decoder can return | the rate of BOUNDARY_AMBIGUOUS readings differs from the geometric prediction of about 3 percent, which would mean the coarse capture is not behaving as the Gray coding assumes |
| 14 | **Voltage and temperature** | both | finalists only, stage 3 rules | several | scan CRC and reference paths as the instrument-failure control | the control fails before the fabric does, so nothing about the fabric was learned |

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

A comparison smaller than one tap cannot be read from one trial, and saying so
in advance is the difference between a study that needs repeats and a study that
quietly returns noise.

`tools/tdc_range.py` prints this table from every build's SDF and it is the
authority. The table below is that tool's output on the shipped build, at the
typical corner.

**Corner `nom_tt_025C_1v80`, build `32bd0b9`, mean tap 0.1166 ns, widest bin
0.1600 ns.** The corner and the build are named because this table was wrong
about both until 2026-08-28. It carried numbers from an older build, and it
carried them from the FAST corner while the paragraph below it said they were
quoted at the typical one. A tap of 78 ps is `max_ff`; the typical tap is 117.
The same mistake had been made independently by the pre-registration generator,
whose SDF selector matched every corner's filename and took the first, so this
is a class of error in this repository and not an incident. Regenerate with
`tools/tdc_range.py <sdf>` rather than editing the numbers here.

| comparison | difference | taps | single trial? |
|---|---|---|---|
| drive series, x1 vs x8 | 1330 ps | 11.41 | yes |
| load series, 0 vs 4 sinks | 1244 ps | 10.67 | yes |
| drive series, x1 vs x2 | 763 ps | 6.54 | yes |
| input isolation pair | 296 ps | 2.54 | marginal, about 1 trial per arm |
| load series, 0 vs 1 sink | 248 ps | 2.13 | marginal, about 1 trial per arm |
| **load ladder pair** | **45 ps** | **0.39** | **no; and not from this table at all** |

The repeat counts are sized from the WIDEST bin, not the mean tap, because
quantization variance goes as the square of the bin an arrival actually lands
in. That is why the two marginal rows now need about one trial each where the
older table said two: the comparisons got larger in taps, not the statistics
weaker.

**The tap is not one number.** On this build it is 0.0781 ns at the fast corner
and 0.2173 ns at the slow one, nearly three to one, because the delay line is
built from the same cells as everything else and moves with them. A comparison
must be re-quoted against its own corner's tap before it is believed. A tool
that divided a slow-corner delay by a typical-corner tap would overstate its own
resolution by a factor of nearly three, and one of ours did. So did this table,
in the other direction, by carrying fast-corner numbers under a sentence saying
they were typical, which is why the corner is now in the caption rather than in
the prose underneath.

**The ladder pair cannot use these numbers, and five builds now say so.** The
same unchanged circuit extracted at 7 ps, then 57 ps, then 3 ps, then 13 ps,
then 45 ps.
That is not a measurement converging, it is routing noise around a structural
zero: the released Liberty view gives that pin one capacitance with no enable
dependence, so extraction has no mechanism there to report and what varies
between builds is wire.

**The prediction for row 6 comes from SPICE, and it now exists.** Nine corners,
`tools/spice_ladder.py`, 2026-08-28. The category was chosen before the deck ran
and the answer landed in the first of the three: **resolvable measurement,
single trial**. Enabling the ladder costs +144 to +371 ps over the eight stage
chain, 2.38 to 3.07 taps against each corner's own tap, 18.8 to 24.6 percent of
the disabled chain, same sign at every corner, with a null control of exactly
+0.0000 ps. The near-constant fraction across corners whose absolute delays span
threefold is the evidence the mechanism is real rather than a solver artefact,
because a floating node artefact would not track the base delay.

Two things came out of it that the RTL comment had not claimed. The four codes
are not four equal steps: +88.2, +73.6 and +59.8 ps, shrinking as elements are
added. And sweeping the keeper strength splits the effect about 16 percent
gate-to-source and 84 percent Miller, so the mechanism named first in
src/load_ladder.v is the smaller one. That comment is corrected rather than
defended.

The repeat counts assume DITHER. Averaging only beats quantization if the
arrival time moves across tap boundaries between trials; if it does not, every
trial returns the same code and no number of them helps. Whether this die
dithers is study 2, code density, and it gates every row above that depends on
averaging.

## The rule that makes this a dataset rather than a demonstration

Rows 1 to 8 produce a structured public measurement set **whether or not the
search in row 9 finds anything interesting**. That is deliberate. A chip whose
value depends on an evolved circuit turning out to be surprising is a bet on
spectacle; a chip that publishes a calibrated model-to-silicon comparison across
20 fixed paths, four drive variants, two matched construction pairs and 20
configurable sites has produced something useful either way.

If row 9 comes back empty, that is itself worth publishing, and it is worth
publishing *because* rows 1 to 8 establish that the instrument could have seen
an effect had there been one.
