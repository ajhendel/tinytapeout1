# MEASUREMENT PROTOCOL

How the blocks on this chip are meant to be used together, what each instrument
can and cannot answer, and the order the experiments have to run in.

Written 2026-08-27, from a design review of the WP2 vehicle. It replaces an
earlier and looser habit of quoting a single throughput number and a single
calibration reference, both of which were doing more work than they could carry.

## The inference chain

Every claim this chip can support is a claim that one level behaves like the
level below it plus something identifiable. There are four levels and each one
has its own hardware.

    individual library cells
       -> fixed paths of known cells and known loading      src/char_paths.v
       -> configurable sites built from those same cells    src/fabric_site.v
       -> evolved circuits made of those sites              the search

Without the middle rung a disagreement between the open-PDK models and an
evolved circuit has nowhere to be attributed. It could be the cell models, the
extraction, the cost of configurability, or the search finding something
uninteresting. With it, the disagreement can be localized to a level.

The rule that follows from this: **no result about an evolved circuit is
reported before the fixed path that isolates its mechanism has been measured on
the same die in the same session.** If the mechanism has no fixed path, either
build one on tapeout two or do not make the claim.

## The two instruments, and which question each one answers

| | frequency counter | time-to-digital converter |
|---|---|---|
| where | `src/freq_counter.v` | `src/tdc.v` |
| what it watches | a ring oscillator or the closed fabric loop | one transition through one path |
| what it reports | edges per measurement window | a raw thermometer code, 32 taps |
| transitions per trial | millions | one |
| self-heating during the measurement | yes, and it is part of the reading | no |
| good for | PVT and activity covariates, oscillation | combinational path delay |
| bad for | the delay of a single edge | anything averaged |

The counter and the converter are never used to answer the same question, and a
trial never runs both. `Genome.validate()` in `harness/evofab/genome.py` refuses
a configuration with `tdc_en` and `calib_en` set together, because a ring
running beside the converter is a supply disturbance of about the size the
converter is trying to resolve.

## What the calibration strip is

A joint monitor of process, voltage, temperature and its own switching activity,
reported as one number. It is **a covariate, not a correction oracle**, and this
is not a quibble. Nothing on this chip can separate a die that got warmer from a
supply that sagged, and running a ring is itself one of the things that makes
the die warmer.

So the strip is logged beside every measurement and conditioned on in the
analysis. No measurement is ever divided by a ring frequency, and the strip is
never called a thermometer.

Rings 0, 6 and 7 are the same circuit three times. Their spread is the
within-die variation floor: **any effect smaller than that spread is not a
result**.

Their difference was also meant to be a placement effect, because nothing else
about them differs. **It is not, on this build.** `tools/check_placement.py` on
the placed DEF puts all three within 43 um of each other on a 1,023 um die, 4
percent of the diagonal, all inside the fabric column's own footprint. The
placer minimizes wirelength, the three rings share an enable decode and an
output multiplexer, and nothing in the Tiny Tapeout LibreLane configuration lets
us ask for anything else.

So **there is no spatial experiment on tapeout one and no spatial result will be
reported.** Three frequencies that differ would have looked like data; the
layout would not have supported the sentence. Finding that out from the DEF
rather than from a reviewer is what the tool was written for. Floorplan control
moves to tapeout two.

The variation floor survives unchanged and does not depend on where the rings
landed.

## The TDC had no usable range, and now it does

Added 2026-08-27, from a design review that asked the question nobody had asked:
how does the converter's span compare with the paths it is pointed at?

Answered from the post place-and-route SDF of the 24 site build, which is
extraction and not a guess:

| | typical corner |
|---|---|
| tap delay | 0.120 ns |
| 32 tap line span | 3.835 ns |
| **one fabric site, series path** | **3.515 ns, 92 percent of the span** |
| **24 sites end to end** | **about 84 ns, 22 times the span** |
| `mux4_d8`, a fixed reference path | 5.28 ns, **saturated** |
| fixed launch and 16:1 select overhead | 1.404 ns, 37 percent of the span |

A linear delay line would have returned all ones for every fabric configuration
and for one of its own reference paths, and every sufficiently slow
configuration would have looked identical to every other one. The chip would
have come back and the fabric would have been unmeasurable.

Four changes, all in this repo's discipline of replacing a guarantee rather than
dropping it:

1. **The line is a gated ring and the wraps are counted.** Range becomes the
   counter's, about 2 us, at unchanged 0.12 ns resolution. The ring runs only
   between launch and arrival and is killed by the arrival edge, so the
   instrument does not oscillate beside the rest of the measurement window.
2. **A per-site stop tap.** The converter can be stopped by any site's output,
   so the per-site delay comes out as the SLOPE of a tap sweep rather than as
   one unusable total. The tree is balanced three cells deep for every input,
   because an unbalanced one puts a per-tap offset directly into that slope.
3. **The output select is a one-hot tri-state merge**, not three levels of mux.
   Only one path is ever launched, so the merge only has to be one-hot.
4. **`mux4_d8` became `mux4_d4`.** The ring means saturation is no longer fatal,
   but a REFERENCE path must sit inside one ring period so that nothing the
   other measurements are quoted against depends on the coarse counter.

`tools/tdc_range.py` reruns this check from any build's SDF and **exits nonzero
if a reference path leaves the fine range**. Run it on every corner of every
build before the submission; the typical and slow corners do not move together,
because the line and the paths scale differently.

The wrap counter SATURATES at 0xFF rather than rolling over. A rolled-over count
is indistinguishable from a fast path, which is the one failure mode that would
publish a slow circuit as a fast one. The host discards a saturated reading; it
never scales it.

### Reading a ring capture

The tap register is not a thermometer code that grows. The ring parks with every
tap high, the launch edge walks a 1 to 0 transition down it, then a 0 to 1, and
so on. Taps below the edge carry the new value and the parity of the traversal
decides which that is.

A population count is therefore the WRONG decode, and it is wrong in a way that
looks plausible: it decreases as the path gets longer on odd traversals. The
first run of the depth series test reported a perfectly ordered series running
backwards. `tdc_decode()` in `harness/evofab/genome.py` is the correct one, and
`test/test.py` carries an independent reimplementation rather than importing it.

### The two bugs the tests found before silicon did

Recorded because both were silent and both would have produced numbers.

- **A phantom wrap.** Killing the ring drives its input high, and that edge walks
  down the line and produces one more counter posedge AFTER the measurement is
  over. Reading the counter later reported one extra ring period, 64 taps of
  delay that never happened, on every single reading. The count is now latched
  by the arrival edge, exactly like the taps.
- **Capturing the settling transient.** The configuration registers and the
  measurement window open on the same clock edge, so at the start of every trial
  the fabric is still settling and its outputs are transitioning. The sampler,
  armed at that moment, captured the transient, reported a successful
  measurement, and returned a number that looked like a very fast path. The
  window is now divided: eight clocks of settling, then arm, then four more,
  then launch.

## The TDC is not calibrated until it is calibrated on the die

The converter reports raw tap counts. It is sampled by the arrival edge of the
path under test, and the tree that carries that edge to 32 flip flops has skew.
The tree is built by hand and balanced so that every flop is the same number of
gates from the edge, which removes the part of the skew that was ours, and the
wire delay is still the placer's decision.

That residual is a **per-tap distortion, not a constant offset, and it does not
cancel in a difference.** It is handled the way delay-line converters are always
handled: the bins are calibrated on the die.

  - The depth series, characterization paths 8, 9, 0 and 10, is the same cell at
    depths 2, 4, 8 and 16. A straight line through the four gives the per-stage
    delay and the fixed offset contributed by the launch gate, the select tree
    and the converter input.
  - The series is four points and not two on purpose. Two points give a slope
    with no way to check that the relationship is linear, and if it is not
    linear then the offset is not a constant and nothing else can be quoted
    against it.
  - The fabric column is a continuously variable delay source, so bin widths can
    be recovered by code density.

**Until that is done, delays from this chip are quoted in raw tap counts and say
so.** No hardware bin-width table exists and none should be added; it would be a
guess baked into metal.

## Input slew is a variable, not a constant

Added 2026-08-27 from the signoff report of the 24 site build, where it turned up
as 202 max transition violations spread evenly over all 24 fabric sites.

Every site's output node carries four tri-state drivers, four load ladder
elements and the next site's route multiplexer. At the slow corner, drive 1 and
drive 2 cannot slew that node inside the 0.75 ns design rule. That is the fabric
working: the ladder exists to make the drive selection matter, and if drive 1
could slew it comfortably there would be less to measure.

The consequence for measurement is that **a stage driven by a slow edge is
slower than the same stage driven by a fast one**, so input slew has to be
carried through the inference chain rather than assumed away.

  - The characterization paths all launch from the same balanced tree, so they
    share an input slew and differences BETWEEN them stay clean.
  - A comparison between a characterization path and a fabric site does NOT
    share it, and has to account for the difference. Quoting a fabric delay
    against a reference path without that accounting attributes the slew to
    whatever else was varying.
  - The 0.75 ns limit is ours, from `set_max_transition` in `src/timing.sdc`,
    not the library's. **Answered 2026-08-27 from the PDK: the sky130 library's
    own limit is 1.5 ns, exactly twice ours, and the worst slew in any measured
    structure is 1.320 ns.** Every fabric, characterization path and calibration
    strip node is inside the characterized range, so their delay predictions are
    interpolations. Eight pins in the design do exceed 1.5 ns and all eight are
    on the reset distribution network, which no measurement touches. Working in
    docs/AREA_GATE.md.

## The four-stage experiment protocol

Stated in this order because running them in a different order produces numbers
that cannot be defended.

### Stage 1. Search, fast, at ONE operating point

One supply, one temperature, one clock. The search runs at whatever throughput
the link supports and its results are treated as candidate generation, not as
measurement. Nothing from this stage is published as a number.

Rationale: search throughput and measurement quality trade against each other,
and the trade is fine as long as the two are never confused. A fitness value
taken once at one operating point is a ranking signal.

### Stage 2. Re-evaluate the finalists exhaustively

Take the top candidates and the controls, and measure them properly at the same
single operating point: every input vector, many repeats, interleaved so that
drift is shared rather than assigned. The noise floor comes from repeating one
identical configuration and reporting the trial-to-trial spread of every fitness
component. **A difference smaller than the floor is not reported as a
difference.**

Interleaving is not optional. Measuring all of arm A and then all of arm B
assigns any drift during the session to the arm difference.

### Stage 3. Sweep voltage and temperature, FINALISTS ONLY

A sweep is expensive and only means something on configurations that survived
stage 2. What can actually be swept is stated in the next section, because it is
less than we first assumed.

### Stage 4. Exhaustive sabotage, on winners AND controls

Every site, every sabotage mode, on the evolved circuit and on the conventional
control, at the same operating point. Sabotage on winners alone measures
nothing: the interesting quantity is whether the evolved circuit degrades
differently from the control, and that needs both.

Sabotage is never a move the search is allowed to make. A search free to insert
faults would learn to hide behind them. `apply_sabotage()` is deliberately not
in `OPERATORS`.

## What the supply sweep can actually be

Tiny Tapeout's power rails are shared infrastructure. From the analog pin
specification: individual projects cannot run at different core voltages from
the rest of the chip. VDPWR is 1.8 V for everything, VGND is common, and the
optional VAPWR 3.3 V rail needs the `_3v3` templates and is not what this design
uses.

So there is **no independent fabric supply on this chip and no per-block
undervolting**. An earlier framing of this experiment as "lower the supply until
a configuration fails" is wrong as stated and is retracted.

What is available is varying the whole-chip supply on the demo board, which
takes the scan chain, the CRC, the safety controller and the counters down with
the fabric. That is usable, and it is usable precisely because those blocks are
instrumented:

  - `CRC_OK` proves the scan path still works at the operating point. A frame
    that fails to check is a control failure, not a fabric result.
  - The reference paths and the calibration rings move with the supply too, so a
    fabric result is quoted as a RATIO against a reference measured at the same
    point rather than as an absolute number.
  - A configuration that fails at a supply where a reference path also fails has
    told us about the chip, not about the configuration.

The claim this supports is "characterize the supported whole-chip range and the
order in which things fail inside it". It does not support "the fabric fails at
X volts", because at X volts the instrument fails too.

A per-block supply is a tapeout-two requirement and is now on that list.

## What the feedback edge is

One combinational edge from the column output back to the head of the column,
behind a global enable. It lets the fabric oscillate.

It is **not** a coupled-oscillator machine and not a weaker Ising machine. There
is no controllable coupling, no phase readout, no locking guarantee and no
independent enable per oscillator. Offering it as a smaller version of one was
an error and is retracted. What it can do is oscillate, which is a capability to
characterize on silicon and not a claim to make in advance.

## What is licensed to be said, and what is not

The prior-art rule stands: no novelty sentence is written until its row in
`docs/PRIOR_ART.md` is CLOSED by enumeration, and the row text is the only
sentence licensed. See the "Licensed and unlicensed language" section there,
which now also records the specific overreaches this review caught.

The one that matters most, because it is the easiest to slip into: the Tiny
Tapeout enumeration is **ecosystem evidence, not a literature review**. It says
what has and has not been built on this shuttle programme. It does not say what
has been published.
