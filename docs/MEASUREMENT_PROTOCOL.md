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
| **24 sites end to end, the size then shipped** | **about 84 ns, 22 times the span** |
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

## The drive series could not have produced a result either

Found in the same report, and worse than a range problem because no instrument
change would have fixed it.

The drive series was four inverter chains at drive variants 1, 2, 4 and 8. Every
stage of each chain was the same size, so the driver AND the load it drives both
scaled with the variant, and the delay hardly moved. Extraction measured 54, 45,
46 and 49 picoseconds per stage: **76 picoseconds of spread across an eightfold
change in drive, not monotonic, against a tap of 121 picoseconds.**

A drive series has to hold the LOAD fixed while the driver varies. Each stage is
now an inverter of the variant under study driving two dummy inv_1 sinks and a
strong inv_8 restorer, so the measured driver always faces the same load. The
restorer is the strongest inverter available on purpose: it has to drive the
next stage's input, which is the one load that still varies, and making it
strong keeps that back-term small rather than letting it cancel the effect.

The load series is shaped the opposite way, an inv_1 backbone with 0, 1, 2 and 4
extra sinks per stage, holding the DRIVER fixed while the load varies. They are
not the same structure and using one for both was the mistake.

The general form of the lesson, which is worth carrying into any later block:
**a series that varies one thing must hold everything the varied thing is
coupled to fixed, and in CMOS a driver is coupled to its own load.** That is not
visible in a logic simulation, it is not visible in a netlist review, and it is
visible in one column of an extracted timing report.

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

### The coarse count is Gray coded, and why that is not decoration

The coarse counter lives in the ring's own clock domain and is captured by the
arrival edge, which has no relationship to it whatever. A binary counter going
from 0111 to 1000 presents four simultaneously changing bits to that capture,
and a capture landing inside that window can return any of sixteen values,
including 1111, which is the saturation code. It is not a rare corner: the
counter is changing for a few tens of picoseconds out of every few nanoseconds
and this chip will take hundreds of thousands of readings.

So a Gray coded copy is registered beside the binary one and the Gray copy is
what crosses. Adjacent counts differ in one bit, so a capture taken mid
transition returns either the old count or the new one and nothing else. The
chip does not convert it back; `gray_to_bin()` does, for the same reason the
thermometer code leaves uncooked, and `readout_sel` 16 is named `tdc_gray` so
that a host reading it as binary is making a visible mistake rather than a
silent one.

This does not remove metastability. Nothing in an asynchronous capture can. It
confines the ambiguity to ADJACENT counts, which is what makes it resolvable.

### Not every capture is a measurement

`tdc_reading()` returns a status, and four of the five are not delays.

| status | what happened | what to do |
|---|---|---|
| `VALID` | an ordinary reading | use it |
| `NO_ARRIVAL` | the trial saw no arrival edge. The tap register still holds the PREVIOUS capture, which decodes to a perfectly plausible number | discard. Check `done` on the MEASURING trial, not after the readout trials |
| `COARSE_SATURATED` | the counter reached 0xFF, Gray 0x80 | discard, never scale. A wrapped count reads as a fast path |
| `BOUNDARY_AMBIGUOUS` | the arrival landed within a tap of the coarse counter's own clock edge | discard and REPEAT. Two candidates are returned and they differ by a whole ring period, so they must not be averaged |
| `THERMOMETER_INVALID` | the fine code has more runs than any bubble pattern can explain | discard and investigate. This is a sampling fault, not a bin width |

A decoder that always returns a number reports the converter's failures as
measurements, and on this converter two of those failures look exactly like
ordinary fast readings.

The rate of each status is itself data and is reported with every study. The
geometric prediction for `BOUNDARY_AMBIGUOUS` is about 3 percent, two guard taps
out of the 64 in a ring period; a rate far from that means the coarse capture is
not behaving the way the Gray coding assumes, and it would be visible in nothing
else.

One case the decoder cannot catch is stated here rather than discovered later. If
one of the four branches of the sampling tree never fires, its eight taps read
zero, and for many positions the surviving pattern is a well formed code for a
DIFFERENT position. What catches that is hardware: `src/tdc.v` ANDs the four
branch fired flags, so a partial capture reports `done` low and never reaches
the decoder at all.

### The capture has to beat the kill, and that is now a number

The arrival edge does two things at once: it samples the whole line, and it kills
the ring. If the kill reached the line first the flip flops would latch a line
the arrival never saw, and the reading would be short by however far the kill had
walked. Short, which is the direction that looks like a result.

The design's argument for why the capture wins was that the capture is one buffer
from the arrival edge and the kill is a flip flop and three gates from it. That
is a short argument about a race, and a short argument about a race is not a
margin. `tools/tdc_race.py` reads both paths out of the extracted timing at every
corner, per delay line stage, and fails the build below a guard band.

**It measured the race as LOST at every fast corner.** From the shipped build:

| corners | margin |
|---|---|
| slow | +0.16 to +0.21 ns |
| typical | -0.02 to +0.01 ns |
| fast | -0.04 to -0.06 ns |

and the worst stage is always stage 0, because the kill reaches it first. A
negative margin means the flip flop sampling tap 0 can latch line[1] after the
kill has driven it back to its parked value, which reads as the launch edge not
having arrived yet. That is a reading short by a tap or two: systematic, corner
dependent, and in the direction that looks like a fast circuit.

Two things had to be true for this to be found at all. The tool had to ask the
question **per stage**, because the kill reaches stage 31 a whole traversal after
stage 0 and comparing every flip flop against stage 0's corruption charges the
late ones with a corruption that cannot reach them. And it had to read the
**fall** delays, which an earlier version of the parser silently discarded; with
rise only, the same build reported a comfortable positive margin.

**The fix is not more buffers.** More buffers buy margin and leave it a race.
The kill is now taken from `fired`, the AND of the four branches' own fired
flags, which are set by the same edges as the capture registers beside them. So
the kill cannot begin until every branch has clocked: the ordering is a
clock-to-Q plus an AND tree plus the guard buffers, all of it after the
captures, rather than a comparison between two paths that happen to start
together. What it gives up is that a trial where one branch fails to fire does
not stop the ring early; it still stops when the window closes, and that trial
was void anyway.

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

## What a tap's threshold actually is, and the hole that put in the range

A tapped delay line is usually described as if a tap's threshold were the delay
down the line to that tap. It is not. The tap fires when the launched edge has
passed it **at the moment the sampling edge arrives**, so the quantity that
orders the taps is the difference

    T(i) = line delay to stage i  minus  sampling tree delay to stage i's flop

Both halves are in the extracted timing of every build. The repository was
checking both, and subtracting neither. `tools/tdc_range.py` measured the line.
`tools/tdc_race.py` measured the tree. Nothing looked at T.

The build of 2026-08-28 is what that cost. The sampling root drove the four
branch buffers **and** the eight flip flops of the coarse capture, which is
twelve sinks against the flow's max fanout of ten, so the resizer repaired it by
inserting a repeater in front of two of the four branches and leaving the other
two direct. Taps 0 to 15 were sampled 0.52 ns later than taps 16 to 31 at the
typical corner and 1.02 ns later at the slow one. The line was fine. The race
margin was fine. Every other gate in the repository passed. The bin between tap
15 and tap 16 was **5.08 nominal taps wide at all nine corners**, which is about
fifteen percent of the converter's range sitting in one undivided bin, and the
pre-registered repeat counts are computed from the quantization variance of one
bin, so they were understated by a factor of twenty five for any path that
landed in it.

It was still monotone, and that was luck rather than design. The repeater landed
on the low half. Had it landed on the high half the same 0.52 ns would have run
the thresholds **backwards** across four bins, the set of taps reading one would
not have been a prefix, and the thermometer code would not have been a
thermometer code. Which two branches get a repeater is not something this design
was choosing.

Three things changed.

  - The coarse capture gets its own branch buffer, so the root drives five
    buffer inputs and nothing else and the flow has no fanout to repair. The
    coarse count is now latched at the same tree depth as the fine taps, which
    it should have been anyway: before this the two halves of one reading were
    taken about a tenth of a nanosecond apart.
  - The counter and the ring observation output moved behind a buffer, off the
    last delay stage. That stage was driving sixteen flip flops and a chip
    output on top of the ring, and it measured 0.393 ns against a 0.124 ns
    typical stage, so the bin at the top of the range was 3.2 taps wide before
    anything else was wrong with it.
  - `tools/tdc_bins.py` computes T at every corner and gates it. A non-monotone
    code is a hard fail, because the decoder, the code density calibration and
    the coarse/fine boundary rule all assume a prefix. A bin wider than 2.0
    nominal taps is a fail, because quantization variance goes as the square of
    the width and a factor of four in repeats is inside the trial budget while a
    factor of twenty five is not.

`tools/check_netlist.py` gates the two structures from the synthesized netlist
as well, and it gates the **fanout** rather than the presence of the buffers.
Counting buffers was not enough and the count proved it: the buffers carry
`dont_touch`, so a coarse branch buffer left driving nothing survives synthesis
and the count still reads six.

`tools/tdc_range.py` now sizes its repeat counts from the widest bin instead of
the mean tap, so the counts that reach `predictions/` hold wherever an arrival
lands rather than on average.

## The launch tree is balanced in gates and not in delay

The same question one block over, asked because the first one had an answer.

src/char_paths.v launches all twenty fixed paths from one hand-built tree, a
root buffer into five branch buffers into four launch gates each, and merges
them back through a one-hot tri-state onto a single node. Every path is the same
number of gates from the launch register. That is not the same delay, because
the wires are the placer's decision.

Where it lands is the problem. **The depth series is paths 8, 9, 10, 11 and 19.
The four short points are all on launch branch 2 and the 32 stage point is on
branch 4.** So a per-branch difference falls almost entirely on the longest lever
arm, which moves the SLOPE rather than the intercept, and that slope is the unit
every delay on this chip is quoted in.

Measured at all nine corners of the 2026-08-28 build by `tools/char_offsets.py`:
the per-path launch plus merge offset spans 102 to 251 ps, and the bias it puts
on the depth series slope is **3.2 to 4.5 percent**. The residual it injects is
0.07 to 0.17 taps, so linearity survives and only the unit moves. Several of the
model-to-silicon gaps this chip exists to size are themselves ten to twenty five
percent, so four percent on the unit is not in the noise.

Nothing is redesigned for it. The offsets are a fixed property of the build, they
are in the extraction, and they are **subtracted before the fit**, exactly the way
`tools/stop_tree.py`'s per-tap selector offsets are subtracted before the
per-site fit. What is claimed is therefore *equal logical launch and merge depth
with an extracted per-path offset correction*, and not *a balanced tree*.
`tools/prereg.py` writes both slopes, because the raw one is what a host that did
not know about the tree would measure and the gap between them is itself a
prediction.

Two things are gated. The raw slope bias must stay under ten percent, because a
correction worth more than a tenth of the quantity it corrects is doing too much
of the work to be called a correction. And the offsets must scatter less than
0.25 tap about their own straight line, because a large scatter means they are
not a per-path constant plus noise and subtracting them models nothing.

One property worth stating because the intuition runs the other way. With five
points, loading branch 4 and loading branch 2 produce the **same magnitude** of
slope bias and the **opposite sign**. Branch 2 carries four of the five points
and branch 4 carries one, and it makes no difference: the two are complements.
A tool that reported only the spread of the offsets would say nothing about
which way the unit had moved.

## The TDC is not calibrated until it is calibrated on the die

The converter reports raw tap counts. It is sampled by the arrival edge of the
path under test, and the tree that carries that edge to 32 flip flops has skew.
The tree is built by hand and balanced so that every flop is the same number of
gates from the edge, which removes the part of the skew that was ours, and the
wire delay is still the placer's decision.

That residual is a **per-tap distortion, not a constant offset, and it does not
cancel in a difference.** It is handled the way delay-line converters are always
handled: the bins are calibrated on the die.

  - The depth series is the same cell at five depths, 2, 4, 8, 16 and 32,
    across characterization paths 8, 9, 10, 11 and 19. A straight line through
    them gives the per-stage delay and the fixed offset contributed by the
    launch gate, the select merge and the converter input.
  - Five points and a 16:1 lever arm, not two. Two points give a slope with no
    way to check that the relationship is linear, and if it is not linear then
    the offset is not a constant and nothing else can be quoted against it.
  - Path 4 is depth 16 built a SECOND time under another name, deliberately not
    deduplicated. Two names for one measurement is a free repeatability check
    and it is not a sixth point on the fit. This document said depth 24 for it
    until 2026-08-28, and so did the harness and the pre-registration generator,
    while the RTL built 16 and said so in a comment. Fitting five delays against
    six x values, one of them wrong, drags the per-stage slope low and inflates
    the very residual the pre-registration predicts will stay under a tap.
    Measured rather than estimated, on two builds: the per-stage slope comes out 9.7 and 11.6 percent low, and the maximum residual of the straight line fit goes from 0.29 taps to 1.67 on one build and from 0.15 to 1.79 on the other. The pre-registration predicts that residual stays under one tap, so the wrong depth would have pre-registered a falsification of its own linearity claim. Nothing failed. The depths are now parsed out of
    src/char_paths.v by harness/tests/test_char_paths_match_rtl.py.
  - Bin widths come from CODE DENSITY, and the stop source for it is a free
    running calibration ring (`tdc_src = calib`), not the fabric. This matters
    and the earlier version of this document had it wrong. Code density recovers
    a bin width from how often the edge lands in that bin, which is only a bin
    width if the arrival phase is UNIFORM. A fixed path arrives in the same bin
    every time. A fabric configuration arrives wherever that configuration puts
    it, and the distribution over random configurations is unknown, which is not
    the same thing as uniform and must not be used as though it were. A
    calibration ring is uncorrelated with the converter's own ring by
    construction: different structure, different length, no shared gate.
  - The gating of that stop source is part of the design and not a detail. The
    sampler is released eight clocks before the launch so the fabric can settle,
    and a free running ring would trip it during that window every time; ANDing
    the ring with the launch does not fix it either, because whenever the ring is
    high as the launch rises the AND produces an edge at the launch instant,
    which is a fixed reading masquerading as a random one for half of all trials.
    So the asynchronous sources are edge armed by a flip flop held cleared while
    the launch is low. Exactly one edge per trial, at a phase uniform over the
    source's period.
  - There is a fourth stop source, the SCAN_IN pin, for a stop whose time the
    host chooses rather than measures. It is for bring up and for deliberate
    stimulus, and it is not for quoting a delay against: board timing at a
    hundred picoseconds is not something to trust.

**Measured on the shipped build, typical corner:** the selector's mean offset is
1.649 ns, about 14 taps, with a standard deviation of 1.01 taps across the
twenty inputs and a worst residual of 1.30 taps about a straight line. Its TREND
with tap index, which is the only part that lands in a fitted slope, is
**-0.044 taps per site**, against a limit of 0.25. The offsets are grouped in
fours, which is the level-one multiplexer's own structure, and within a group
they agree to a few picoseconds.

**The rise and fall offsets differ by 0.713 ns, six taps.** That is the largest
single correction on this instrument and it means the selector table is
polarity dependent: a measurement taken with tdc_pol set is quoted against a
different offset than one taken without it. Study 8 applies the correction for
the polarity actually used, and a per-site series must not mix the two.

**The selector offset is measured, not assumed to cancel.** The per-site result
is a SLOPE over the stop tap index, so anything that varies WITH the tap index is
added to it and is reported as the cost of a site: stable, reproducible and
wrong. The tree is balanced three cells deep for every input, which removes the
part of that effect caused by logic depth, and it does NOT remove the part caused
by routing, because nothing in this design places a wire. `tools/stop_tree.py`
extracts the per-tap offset, reports its mean, spread, rise-fall difference and
its LINEAR TREND with tap index, and fails the build if that trend exceeds a
quarter of a tap per site. The per-code offsets it prints are the correction, and
study 8 applies them before fitting. The right phrasing for this is equal logical
selector depth with an extracted per-code offset correction, and never that the
selector delay cancels.

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
