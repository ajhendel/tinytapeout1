# HANDOFF — implementation brief for a fresh Claude session

You are picking up a planned but unimplemented project. This brief is self-contained; do not assume any conversation history. Read PLAN.md, then docs/, then this file's work packages. The repo is https://github.com/ajhendel/tinytapeout1 (private, ajhendel), local checkout /Users/andrewhendel/CascadeProjects/tinytapeout1.

## What this project is
One Tiny Tapeout chip (sky130, target shuttle SKY26c or the next sky shuttle) that is a physical laboratory. Two halves. (1) An evolvable fabric whose configuration selects the ELECTRICAL realization of logic (drive strength, cell variant, node loading, inserted faults, feedback edges), searched in-loop against the physical die. (2) A physics-as-computer patch (coupled ring oscillators with configurable coupling = small Ising-style optimizer; jittery oscillators sampled = probabilistic bits). Plus a thin calibration strip of fixed reference macros. The bar for every headline experiment: impossible on an FPGA and unsettleable by simulation alone. FPGA-doable work is pilot + control arm, never the justification for fabrication. Full rationale, settled design decisions, and killed claims are in PLAN.md section 2 — do not re-litigate them.

## Operating rules (binding)
- NO heavy compute on this Mac. P&R and SPICE run in Tiny Tapeout's GitHub Actions CI (preferred, free, zero local load), or docker with nice 19 / --cpus 2 / one container, or a cheap cloud box. Never risk crashing the laptop.
- Everything in this repo is written as if already public (TT requires open source at submission). Nothing proprietary from Andrew's other programs ever enters it.
- American English. No em/en dashes, no colons in prose in documents. Full absolute paths when telling Andrew where things are.
- Report commits as `%h parent %p`. Stage explicit paths, never `git add -A`.
- Spending money (shuttle slot, boards, cloud), portal logins, and the actual shuttle submission are Andrew's actions. Prepare them, then stop and ask.
- Prior-art discipline: no novelty sentence is written anywhere until its row in docs/PRIOR_ART.md is CLOSED by enumeration.

## Work packages, in order

### WP1 — Prior-art sweep (no code, high value, do first)
Work docs/PRIOR_ART.md rows 1, 2, 3, 8, 9 to CLOSED per the sweep protocol at the bottom of that file. Rows 4, 5, 6, 7 to PARTIAL with queries logged. Especially row 8: sweep the Tiny Tapeout project index across all shuttles for characterization/RO/PUF/evolvable precedents. Deliverable: updated PRIOR_ART.md with residual claims written as single sentences.

### WP2 — TT submission skeleton + trial P&R (the area gate)
1. Fork/instantiate the TinyTapeout sky130 Verilog template as the future submission repo structure inside this repo (or as sibling repo tinytapeout1-tt if the flow demands its own repo; document the choice).
2. Write ONE fabric site in Verilog as hand-instantiated sky130_fd_sc_hd cells (function select NAND/NOR/XOR/INV/wire; drive select X1/X2/X4; load ladder via tristate-gated dummy inputs; sabotage mux stuck-0/stuck-1/bypass-A/bypass-B/invert; 12-bit config register on a scan chain). Include one deliberate combinational feedback path behind an enable.
3. Write one fixed calibration macro (X1/X2/X4 inverter chains with known loads, one path to output pins).
4. Push through the TT GitHub Actions hardening flow. Deliverables: does keep/dont_touch survive, does the feedback loop pass the flow, real cells-per-site and tiles-for-64-sites numbers written into docs/THROUGHPUT.md replacing the estimates. This gates all RTL scope decisions.

### WP3 — FPGA pilot (preliminary info that refines the ASIC plan)
Hardware: an iCE40 board (iCEstick or iCE40-UP5K breakout, ~$30–60; ask Andrew to order, give him the exact link). Open toolchain (yosys/nextpnr/icestorm) runs fine within the Mac compute limits. Each item below produces a number or verdict that feeds back into PLAN.md.

1. **Harness end-to-end.** GA/search loop, genome encode/decode, scan protocol frame format, results database (config hash, device id, temperature covariate, trial counter, firmware version), crash recovery, holdout discipline. Verdict: the firmware/host split and the real trials-per-second number (docs/THROUGHPUT.md says it must be firmware-side scoring; verify).
2. **Logical fabric emulation.** The 64-site fabric as LUTs, exact same genome format as the ASIC. Debugs mutation operators, the genome safety validator, and the scan controller RTL before any of it is frozen into silicon. This FPGA build later becomes the permanent control arm (same software, LUT genome vs physical genome).
3. **Real coupled ring oscillators on iCE40.** iCE40 permits combinational loops, so build actual ROs with coupling through shared routing/LUT injection and phase readout via sampling counters. This is genuinely informative for the physics patch: does phase readout via counters work, do oscillators injection-lock too easily or too weakly, what coupling-strength dynamic range does the ASIC tristate ladder need. Verdict: coupling ladder spec for the ASIC patch.
4. **p-bit prototype.** Sample a jittery RO for random bits; measure bias tunability and autocorrelation. Verdict: is RO jitter enough or does tapeout one need a marginal-bistable variant in the patch.
5. **TDC dry run.** Carry-chain TDC on the FPGA, calibrated against bench equipment through pins. Verdict: the calibration procedure and scripts, reusable for the ASIC TDC.
6. **Noise-floor methodology.** Repeat one configuration 1,000×, measure per-fitness-component σ, log thermal drift covariates. Verdict: minimum resolvable fitness difference; mutation operators sized above it.
7. **Sabotage-transfer pilot.** Put the sabotage muxes in the FPGA fabric, overclock until marginal, test whether sim-predicted mutant kills match FPGA behavior at the edge. Verdict: the experiment-E protocol, debugged before silicon.
8. **Evaluate the Bitstream Evolution toolkit** (open-source FPGA intrinsic-evolution platform) for reuse before building anything it already provides. Verdict: reuse/adapt/ignore, with reasons.

Sequencing note: WP3.1 and WP3.2 need no hardware purchase (simulate first), so start them while the board ships.

### WP4 — RTL freeze (only after WP1–WP3 verdicts)
Full fabric + physics patch + calibration strip + scan/CRC + counters + TDC + hardware safety controller (default-inert, one-hot tristate enforcement, trial duration and transition-rate limits, external kill; the fabric must never gate its own kill path). Full-chip simulation including every sabotage mode. Iterate P&R in CI to fit the tile budget from WP2. PLAN.md section 3 has the block priority order for area cuts.

### WP5 — Pre-registration + submission prep
predictions/ directory: Liberty-, extraction-, and SPICE-level predictions with uncertainty bounds for every calibration macro and a sample of fabric configurations, committed before the shuttle deadline, append-only afterward. Prepare the TT submission (info.md, pinout, docs) to the point where Andrew only has to review and click submit. Confirm deadline and price in the calculator at app.tinytapeout.com (Andrew's login) well ahead; docs/TT_LOGISTICS.md has current facts as of 2026-08-26.

## What done looks like for this handoff
WP1 and WP2 complete, WP3 items 1–3 running with real numbers written back into docs/, and a one-page status update in this file's Status section below. If a verdict from WP2 or WP3 contradicts PLAN.md, update PLAN.md in the same commit and say so plainly rather than making the plan look right.

## Status

### 2026-08-28, fifth round. Two independent reviews, and nine of the findings were real.

Two reviewers were run against the fourth round before any of its numbers were
written down: one adversarially checking the SPICE deck, one reading the whole
commit. Between them they found eleven real defects. Three were in the SPICE
tool, five in the SDF tools, one in the RTL, and the worst one was in a list.

**The deadline is 2026-09-07 at 20:00 UTC. Ten days.** It needed no portal
login: the tinytapeout.com countdown renders from JavaScript, so fetching the
page returns a placeholder, but the value driving it sits in the markup as
`data-shuttle="ttsky26c" data-deadline="2026-09-07T20:00:00Z"`. Recorded in
docs/TT_LOGISTICS.md, where this file said "TBD via the submission portal" for
two days. Pricing genuinely does need the login and stays Andrew's.

**The depth series was pre-registered against a depth the RTL does not build.**
harness/evofab/genome.py and tools/prereg.py both said depth 24 for `load_0`.
src/char_paths.v builds it at 16 and says so in a comment two lines above. The
per-stage slope from that series is the number every other delay on this chip is
quoted against, and fitting five real depths against six x values with one
wrong drags it low while inflating the very residual the pre-registration
predicts will stay under one tap. Measured rather than estimated, on two builds: the per-stage slope comes out 9.7 and 11.6 percent low, and the maximum residual of the straight line fit goes from 0.29 taps to 1.67 on one build and from 0.15 to 1.79 on the other. The pre-registration predicts that residual stays under one tap, so the wrong depth would have pre-registered a falsification of its own linearity claim.
Nothing failed: the RTL was right, the cocotb test was right by coincidence of
being written separately, and two copies of a list were wrong.
harness/tests/test_char_paths_match_rtl.py now parses the DEPTH, DRIVE, LOAD,
STAGES and SINKS parameters out of the Verilog and checks the depth series, the
repeat point, both series' shapes and both matched pairs against them.

**tdc_pol destroyed the capture on the asynchronous stop sources.** The arming
flip flop is cleared when the launch falls at the end of the window, and the
sampler is still armed then because tdc_wait is held by meas_gate, which stays
high through the readout tail. With the polarity bit applied AFTER the source
multiplexer, that falling edge arrived at the converter as a RISING one, re-fired
all four sampling groups on a parked delay line, and the capture pulse two clocks
later transferred it over the real reading. Measured with the old RTL: the same
injected edge reads 184 taps with tdc_pol clear and **9447 taps with it set**,
with done and valid both asserted. The polarity bit is now applied before the
multiplexer to the two MEASUREMENT sources only, where it means something; an
edge-armed source always presents a rising edge and polarity has nothing to say
about it. One extra xor2, and the class is gone rather than documented.

**The SDF tools were reading a graph that was not connected.** OpenSTA names an
INTERCONNECT endpoint as one string, instance and pin joined by a dot with the
dots already inside the hierarchical name escaped; an IOPATH names them
separately. So the same physical pin arrived as `...g4.u/X` from one record type
and `...g4.u.X` from the other, cell arcs and wire arcs landed in disjoint halves
of the graph, and no search ever crossed between them. The synthetic fixture used
the slash form for both, which is why four passing tests did not see it. The
fixture now writes the real encoding, escaping and all.

**And every IOPATH's fall delay was being discarded.** The regex stopped at the
second-to-last close paren, so the fall triple lost its bracket and the triple
matcher never saw it. Every delay was silently the rise delay. In a race that is
unsafe in both directions at once: the capture was taken from a max that omitted
the slower transition and the kill from a min that omitted the faster one, so
the margin was reported larger than any die has to honour. The tell was
tools/stop_tree.py printing rise-against-fall as exactly 0.0000 ns at every
corner. The fixture now writes rise and fall as different numbers, so a parser
that confuses them cannot pass.

**The three instrument gate steps in CI always exited 0.** `for ...; done | tee`
runs the loop in a subshell, so `rc=1` never reached the parent. They are the
same defect as the continue-on-error they had just been split out to avoid. An
empty find would have passed vacuously too; both now fail.

Also fixed: the race gate printed the tree's size and never gated it, so three
missing branches would have made its own margin look better; the stop-tree gate
dropped a tap's wire term silently whenever the driver was not unique, which it
never is, because a fabric site output is a four-driver tri-state node by
construction; the retraction half of the documentation audit had gone inert when
paragraph mode arrived, exempting 40 percent of all paragraphs and every single
one containing a retracted phrase; the audit never read .github at all, because
".git" is a substring of ".github"; the readout table named 0xFF as the coarse
saturation code where the wire carries 0x80; and the decoder's boundary guard
had a floor at zero and no ceiling, so a capture at 0xFE could be offered the
saturation code as a candidate delay.

**What the gates then said, on a real SDF, for the first time.**

    capture beats the ring kill    +0.445 ns margin, guard band 0.100
    sampling skew across 36 flops  0.033 ns
    branch balance                 4 branches, all fed from one node
    stop selector trend            -0.044 taps/site, limit 0.25
    stop selector rise vs fall     0.713 ns, six taps

The flow inserted a fanout repeater in front of the hand-built sampling tree,
and it feeds all four branches from one node, so the balance survived. The
selector's rise and fall offsets differ by six taps, which makes its correction
table polarity dependent; a per-site series must not mix the two.

**SPICE on the ladder pair came back at +220 ps, and then the reviewer found
three reasons not to publish that number yet.** The taps column divided a
corner-dependent delay by a fixed typical-corner tap, and on this build the tap
runs 0.078 ns fast to 0.219 ns slow, nearly three to one. The sweep varied one
factor at a time and never simulated the combination that MINIMISES the effect,
which is the one the category decision turns on. And the measurement was taken
on the first edge after the DC solution, in a circuit whose disabled arm has
genuinely floating internal nodes, so the least settled number in the table was
the one closest to the boundary. The deck now carries a reference buffer chain
that scales the tap to each corner, runs the two extreme combinations, measures
the third edge, and refuses to report anything until a NULL CONTROL with both
arms configured identically comes out at zero. It also sweeps the keeper
strength to separate the two mechanisms src/load_ladder.v names, which will say
whether that comment is right.

The extraction number for the same pair is now 3 ps, having been 7 and then 57
on the two previous builds of the unchanged circuit. Three values spanning
twentyfold settles it: extraction has no mechanism to report there.

Verification: 22 cocotb tests, 75 harness tests, verilator clean, netlist and
constraint checks pass. New sabotage runs this round: shipping binary instead of
Gray, the depth series set back to 24, the polarity XOR moved back after the
mux, a fixture whose rise and fall are equal, three of four sampling branches
removed, half the capture registers removed, and a fresh unqualified claim added
to README.md.

### 2026-08-28, fourth round. Hardening the instrument, and everything the last round owed.

The direction taken: **keep 20 sites, add the instrumentation, and let explicit
gates decide whether 16 is necessary.** Nothing was removed to protect the site
count, and nothing was cut preemptively to make room. At 28.2 percent there was
room; the work below adds about a dozen cells of RTL and a great deal of
checking, and the next build measures whether that judgement held.

**The coarse counter was an asynchronous binary capture, which is a real bug.**
The wrap counter lives in the ring's clock domain and is sampled by the arrival
edge, which has no relationship to it. A binary count crossing 0111 to 1000
presents four simultaneously changing bits to that capture, so a capture landing
inside the transition can return any of sixteen values, including 1111, which is
the saturation code. That is not a rare corner: the counter is changing for tens
of picoseconds out of every few nanoseconds and this chip will take hundreds of
thousands of readings. A Gray coded copy is now registered beside the binary one
and the Gray copy is what crosses; adjacent counts differ in one bit, so a
capture mid transition returns the old count or the new one and nothing else.
The conversion back is in software, for the same reason the thermometer code
leaves uncooked.

The test for it does not decode anything, because a decoding test would pass on
a binary counter. It sweeps the fabric tap, which lengthens the path
monotonically, and checks the ORDER the coarse codes first appear in: counting
up, that is 0, 1, 3, 2 and not 0, 1, 2, 3. Sabotaged by shipping the binary
value: the test fails with exactly that message and nothing else in the suite
notices.

**The decoder now refuses to answer.** `tdc_reading()` returns one of five
statuses and four of them are not delays. `NO_ARRIVAL` catches a stale read,
`COARSE_SATURATED` catches a wrapped counter, `THERMOMETER_INVALID` catches a
scattered fine code, and `BOUNDARY_AMBIGUOUS` catches a capture within a tap of
the counter's own carry and returns both candidates rather than picking. The two
candidates are a whole ring period apart, so the rule is repeat, never average.
`harness/tests/test_tdc_decode.py` runs it against synthesised captures: every
position of every traversal, bubbles, all-ones and all-zeros fields, the carry
boundary, saturation, a lost sampling branch and a ring with randomised bin
widths. One limitation is stated as a test rather than discovered later: a lost
sampling branch is often NOT visible in the code, and what catches it is the
hardware AND across the four branch fired flags.

**The capture-beats-kill race is now a number.** It was an argument: the capture
is one buffer from the arrival edge and the kill is a flip flop and three gates
from it. A short argument about a race is not a margin, and the failure it
guards is not a crash but a reading short by a tap or two, in the direction that
looks like a result. Two dont_touch buffers now sit in the kill path, delaying
only the shutdown of an instrument whose reading is already latched, and
`tools/tdc_race.py` reads both paths out of the extracted timing at every corner
and fails the build below a guard band. It finds the kill path by SEARCHING the
SDF as a graph rather than by naming cells, because the flip flop and the two
gates in that path were named by the tool and not by us.

**Code density had no honest stop source, and the fix is a mode.** Bin widths
come from how often the edge lands in each bin, which is a bin width only if the
arrival phase is uniform. A fixed path arrives in the same bin every time. A
fabric configuration arrives wherever that configuration puts it, and the
distribution over random configurations is unknown, which is not the same thing
as uniform. `tdc_src` is now two bits: a fixed path, a fabric tap, a free
running calibration ring, and the SCAN_IN pin. The last two are edge armed by a
flip flop held cleared while the launch is low, which matters more than it
sounds: the sampler is released eight clocks before the launch so the fabric can
settle, and a free running ring would trip it every time, while ANDing the ring
with the launch produces an edge AT the launch instant whenever the ring happens
to be high, which is a fixed reading masquerading as a random one for half of
all trials.

SCAN_IN costs nothing: the scan chain stops listening to it when SCAN_EN is low,
which it is for the whole window. It also gave the suite its best new test.
Injecting an edge at 1, 4 and 7 ns produced 130, 184 and 237 taps, which is the
converter measuring an interval the testbench chose, linear to within half a
tap, with the no-edge sabotage returning no arrival.

**The stop selector's offset is measured rather than assumed to cancel.** The
per-site result is a slope over the tap index, so anything varying WITH the tap
index is added to it and reported as the cost of a site: stable, reproducible
and wrong. A balanced tree removes the part caused by logic depth and not the
part caused by routing, because nothing in this design places a wire.
`tools/stop_tree.py` extracts the per-tap offset, reports mean, spread, rise
against fall and the LINEAR TREND with tap index, and fails above a quarter tap
per site. The phrasing everywhere is now equal logical selector depth with an
extracted per-code offset correction, never that the selector cancels.

**SPICE on the load ladder pair is set up and owed.** `tools/spice_ladder.py`
builds both chains in one deck so nothing about the solver can differ between
the arms of a matched pair, reads the cell pin order out of the PDK rather than
assuming it, and sweeps corners, supplies and temperatures. It prints which of
three categories row 6 of the matrix is allowed to be: resolvable measurement,
repeated statistical measurement, or upper bound. The third is a legitimate
result and the design will not be changed to amplify a secondary mechanism into
the first. The `spice` workflow runs it; **the number is not in yet.**

**The submission gate is one job and one exit code.** `tools/final_report.py`
runs every check against the artifacts of one build on one commit and prints a
single table. The old TDC range check lived in a job with continue-on-error,
which means it could never actually have failed a build; the reports job keeps
that flag and the gate job does not.

**The documentation is checked by a machine now.** `tools/gen_constants.py`
generates docs/CONSTANTS.md from the RTL and fails CI on drift.
`tools/doc_audit.py` checks arithmetic, retracted phrasing and present-tense
claims about the site count. It found a duplicated status paragraph in
README.md carrying two different timing numbers, a document still saying the
chip ships at 24 sites, a claim of 24 configurable sites in the matrix, and
FUNCTIONS.md presenting a physics tier as though it were on this tapeout. Its
first version was line based and reported the matrix clean, because prose here
wraps at eighty columns and the claim straddled a line break; it reads
paragraphs now, and that change alone found the one it had missed.

**The pre-registration is split in two.** predictions/RULES.md is the half that
cannot be generated: the decode procedure, the exclusion rules, what happens to
an ambiguous reading, the repeat counts and the dither precondition they rest
on, the multiple comparison correction for the search (50 finalists fixed in
advance, a matched random baseline as the null, Bonferroni on the holdout, and
the full ranked list published including the failures), and the die split.
tools/prereg.py generates the numbers from the shipped build's own SDF and
refuses to give the ladder pair a prediction from extraction.

Verification: 21 cocotb tests, 67 harness tests, verilator clean, netlist and
constraint checks pass. Every new gate was sabotage-tested and the sabotage
output is in this session's record: binary instead of Gray, a kill that beats
the capture, a stop tree that trends with the tap, a selector split into two mux
levels, a missing guard buffer, and a document with bad arithmetic.

Owed, in order:

1. **The SPICE number.** It decides how row 6 is written and nothing else can.
2. **The next build**, which is what decides 20 against 16. The gates are
   written down in the matrix and in tools/final_report.py: utilization at or
   below 33 percent, clean routing, positive timing, and no instrument feature
   weakened to make area. If it asks for 16, cut to 16.
3. **The generated pre-registration**, committed against the final submission
   commit, once 1 and 2 have settled.

### 2026-08-27, third round. The drive series could not have worked either. Fixed, 20 sites, built clean.

The 24-site build with the ring converter came back clean and its own extracted
timing said the chip's headline drive experiment was structurally unable to
produce a result.

**The drive series measured 54, 45, 46 and 49 picoseconds per stage for drive
variants 1, 2, 4 and 8.** Seventy-six picoseconds of spread across an eightfold
change in drive, not monotonic, against a converter tap of 121. The chains were
uniform, so each stage's driver AND the load it drove both scaled with the
variant and the delay barely moved. No instrument change would have fixed it. It
is invisible in logic simulation, invisible in a netlist review, and visible in
one column of an extracted timing report.

A drive series has to hold the LOAD fixed while the driver varies. Each stage is
now the variant under study driving two dummy inv_1 sinks and a strong inv_8
restorer; the restorer is the strongest available on purpose, because it drives
the one load that still varies. The load series is shaped the opposite way, an
inv_1 backbone with 0, 1, 2 and 4 sinks. Using one structure for both was the
mistake, and the general form is worth carrying into any later block: **a series
that varies one thing has to hold fixed everything that thing is coupled to, and
in CMOS a driver is coupled to its own load.**

**It works.** From the 20-site build's extracted timing, typical corner:

| comparison | before | after |
|---|---|---|
| drive x1 vs x8 | 76 ps, not monotonic | **1035 ps, 12.6 taps** |
| drive x1 vs x2 | within noise | 607 ps, 7.4 taps |
| load, 0 vs 4 sinks | not a series | 919 ps, 11.2 taps |
| input isolation pair | 372 ps | 216 ps, 2.6 taps, needs a few trials |
| load ladder pair | 7 ps | 57 ps, 0.69 taps, needs SPICE |

**The ladder pair cannot use these numbers and that is itself the finding.** The
same unchanged circuit measured 7 ps on one build and 57 on the next, an
eightfold change from routing alone. The SDF is Liberty plus extraction and
Liberty's pin capacitance has no enable dependence at all, so what moves between
builds is wire, not the mechanism. **The SPICE prediction is owed before that
row's prediction is written.** If SPICE also puts it far below a tap, the row
becomes an upper bound reported with its repeat count, which is still a result.

**20 sites, and the build is clean.** 63,627 um2, 28.2 percent utilization
against a 33.3 projection, DRC 0, antenna 0, setup +5.60 ns, hold +0.108 ns,
precheck and gate-level passing. The redesign plus the ladder pair put about 900
cells into the fixed column and 24 sites would have projected past the 34.8
percent that has ever routed clean here. Four sites is the price of an
instrument that works, and it is the third application of "cut sites before
cutting the strip".

One free thing: the load series' zero-sink arm and the depth series' 16-stage
point are the same circuit built twice under different select codes, so a
disagreement between them is the converter and not the circuit. They agree
exactly in simulation and it is now an assertion.

**Owed next, in order.**
1. **SPICE on the load-ladder pair.** It decides whether that row is a
   measurement or a bound, and it cannot be answered from Liberty or the SDF.
2. **WP5 pre-registration**, against docs/EXPERIMENT_MATRIX.md row by row. The
   depth-series slope is what makes the converter falsifiable; the repeat counts
   in that file are what make the marginal rows honest.
3. Andrew still owns the SKY26c deadline and price, the 6x2 spend, and a board.

I consider the instrument design converged here. Three rounds of review each
found a real defect, and each was found by reading what the build itself
reported rather than by a test.

### 2026-08-27, second design review. The instrument did not work, and now it does.

Read this before anything else. A review of the built design found two things
that a completed, DRC-clean, LVS-clean build had not mentioned, and one of them
meant the chip could not perform its central measurement.

**1. The TDC had no usable range for the fabric. This was the real defect.**

Bounded from the post place-and-route SDF, which is extraction and not a guess:
the 32 tap line spanned 3.835 ns at the typical corner, ONE fabric site's series
path was 3.515 ns of that, and the whole 24 site column was about 84 ns, 22
times the span. One of the converter's own reference paths, mux4_d8 at 5.28 ns,
saturated too. A linear delay line would have returned all ones for every fabric
configuration; every slow configuration would have looked identical to every
other one; and none of that would have been visible until dies arrived.

The question was answerable before fabrication from an artifact the build
already produced, and it had not been asked. `tools/tdc_range.py` now asks it
automatically from any build's SDF and FAILS if a reference path leaves the fine
range, and it runs in CI.

Four changes fixed it:
  - the delay line is a GATED RING and the wraps are counted, so range is the
    counter's rather than the line's, at unchanged 0.12 ns resolution. The ring
    runs only between launch and arrival, so the instrument is not oscillating
    beside the rest of the measurement window.
  - a PER-SITE STOP TAP, so the converter can be stopped by any site's output.
    The per-site delay now comes out as the SLOPE of a tap sweep rather than as
    one unusable total. The tree is balanced three cells deep for every input,
    because an unbalanced one puts a per-tap offset straight into that slope.
  - the output select became a one-hot tri-state merge rather than three levels
    of mux, recovering about a nanosecond that was being spent on every reading.
  - mux4_d8 became mux4_d4, so no reference path depends on the coarse counter.

It works. In simulation the depth series now returns 6, 8, 11, 17 and 28 taps
for depths 2, 4, 8, 16 and 32, a slope of 0.733 taps per stage against an exact
expected 0.727; and the fabric tap sweep returns 19, 29, 48, 88 and 172 taps for
1, 2, 4, 8 and 16 sites, a slope of 10.2 taps per site with a linear fit. That
second series is the measurement this chip exists to make and it could not be
made at all a day ago.

**2. The load ladder was described wrongly, and the correct description is a
better experiment.**

The config comment said "0 = switch parasitic only, then +1, +2, +4", which
reads as four added unit loads. It is not. The sky130 einvn netlist settles it:
the A-input devices have their DRAINS on the output and their SOURCES on
internal nodes that the enable devices tie to the rails. So part of the input
capacitance faces the output in every state and never disconnects, and part
faces a node that floats when disabled. The effect is real, partial and bias
dependent, which is what src/fabric_site.v's header had said all along while the
field description said something else.

The sharp part: the released Liberty view gives this pin ONE capacitance, 0.002382 pF
for einvn_1, with no dependence on the enable, because the format cannot express
one. **So the Liberty-layer prediction for the entire load field is exactly
zero.** That is not a gap to apologize for, it is the cleanest
model-discrimination test on the chip: one layer says the knob does nothing,
extraction and SPICE say it does something specific, silicon arbitrates.

The ladder is now its own module, src/load_ladder.v, shared by the fabric and by
two new fixed characterization paths that carry the same ladder with its enables
tied high and tied low. The mechanism is measured in isolation, and the pair
joins the drive-isolation pair as a construction choice this chip measures
rather than argues about.

**Two bugs the new tests found before silicon did.** Both silent, both would
have produced numbers.
  - A PHANTOM WRAP. Killing the ring drives its input high, and that edge walks
    the line and produces one more counter posedge after the measurement is
    over. Reading the counter later added 64 taps of delay that never happened
    to every reading. The count is now latched by the arrival edge.
  - CAPTURING THE SETTLING TRANSIENT. Configuration and window open on the same
    clock edge, so the sampler was armed while the fabric was still settling; it
    captured the transient, reported success, and returned something that looked
    like a very fast path. The window is now divided: eight clocks settling,
    arm, four more, launch.

**Scope claims corrected.** A full adder cannot be expressed on this chip; the
fabric is a serial column with two inputs and one output and no per-site state,
and that example is removed from docs/FUNCTIONS.md. Sabotage is exhaustive
single-site OUTPUT fault injection and never gate deletion, because the function
bank inside a site is always active. PLAN.md's stale 48-64 site and physics
patch language is fixed and its tapeout-two list is now specific.

**docs/EXPERIMENT_MATRIX.md is new**: thirteen studies with their instrument,
configuration count, die pool, control arm and falsification condition, plus the
six studies deliberately absent. Same rule as predictions/, committed before the
deadline and append only, because a study list assembled after the dies arrive
is a list of whatever turned out to work.

**State.** 17 cocotb tests and 44 harness tests pass. Netlist, constraint and
range checks pass and were sabotage-tested. Verilator clean across src/. The
fixed instrumentation is now about half the cell count at 24 sites, which
projects to roughly 33 percent utilization on 6x2 against 28.4 measured last
build and 34.8 that routed clean. If the build comes back congested the answer
is fewer sites, not less instrument.

**Owed next.** Re-run tools/tdc_range.py on the new SDF and paste the table into
docs/MEASUREMENT_PROTOCOL.md; then WP5. Andrew still owns the deadline, the
price and the board.

### 2026-08-27, the build at 24 sites. Measured, not projected.

LibreLane completed at commit becb941. gds, precheck and gl_test all pass; the
viewer job still fails and will keep failing until the repo is public, because
GitHub Pages is not available on a private repo.

**The area projection held to 0.3 percent.** 64,124 um2 of standard cells
against 64,300 projected, 28.4 percent utilization against 29.5 projected, DRC 0,
Magic DRC 0, LVS matches uniquely, antenna 0.

**Timing got better while the fabric tripled.** Setup WNS went from -4.49 ns at 8
sites to **+7.18 ns** at 24, hold +0.107 ns, violator list empty. That is the
`u_mon_iso` false path: the path it cuts was the one that scaled with the site
count, so cutting it removed a class rather than an endpoint.

**Two findings that no one asked for and both are worth having.**

1. *The fabric violates the max transition rule on every site, and that is the
   fabric.* 1,010 slew violations at the slow corner, of which 202 are the same
   violation repeated on all 24 sites: drive 1 and drive 2 cannot slew the site
   output node inside 0.75 ns because the load ladder and the next site hang on
   it. The load ladder exists to make that true. Path 14 and ring 5 violate the
   same way, which is evidence the replicas really replicate. None of it is a
   timing violation and nothing in signoff gates on it.
   **The owed half of this is now answered, from the PDK, before any prediction
   was written.** The sky130 library's own `max_transition` is 1.5 ns, exactly
   twice LibreLane's 0.75 house rule, and the worst slew in any measured
   structure is 1.320 ns on calibration ring 5. So every fabric, characterization
   path and calibration node is INSIDE the characterized range and their delay
   predictions are interpolations. The opposite assumption, that violating a rule
   means the model is out of range, would have been wrong and would have quietly
   weakened every prediction on the chip. Eight pins in the design do exceed
   1.5 ns; all eight are on the rst_n distribution chain, which OpenROAD repaired
   with delay buffers, at the slow corner only, with 7.18 ns of setup margin and
   the worst hold path at a different corner on a different network. Recorded,
   not fixed; fixing it would be a fourth deviation from the stock template
   bought for nothing.
   What remains is not a check but a prediction: input slew is now a variable the
   inference chain carries. A fabric site is driven by slower edges than a
   characterization path is, so the delay that slew alone accounts for has to be
   predicted, or the cost of configurability gets credited with something that
   was slew. In docs/MEASUREMENT_PROTOCOL.md and predictions/README.md.

2. *The spatial experiment did not happen.* `tools/check_placement.py` on the
   final DEF puts calibration rings 0, 6 and 7 within **43 um of each other on a
   1,023 um die**, 4 percent of the diagonal, all three inside the fabric
   column's own footprint. The placer minimizes wirelength, the three rings share
   an enable decode and an output multiplexer, and the Tiny Tapeout flow exposes
   no placement regions. **No spatial result will be reported from tapeout one.**
   Three frequencies that differed would have looked like data and the layout
   would not have supported the sentence; finding that out from a DEF rather than
   from a reviewer is the entire reason the tool exists. The triple survives as
   the within-die variation floor, which was always its first purpose. Floorplan
   control joins the per-block supply on the tapeout-two list.

**One tooling bug found and fixed.** The placement job downloaded the wrong
artifact: the DEF lives in GDS_logs, and tt_submission carries only the GDS, LEF,
SPEF and netlist, none of which say where a cell is. The report script also
matched instance names against DEF-escaped text, so every group whose name
contains a bracket silently found nothing, which reads exactly like "the flow
optimized that block away". Both fixed; the next run verifies them.

**Owed next, in order.**
1. WP5 pre-registration. predictions/README.md lists what has to be predicted;
   the depth-series slope is the one that makes the TDC falsifiable.
2. Blocked on Andrew and only on Andrew: the SKY26c deadline and pricing at
   app.tinytapeout.com, the 6x2 tile spend at about 840 EUR, and an iCE40 board.
   The 32-sites-on-8x2 option at about 1,120 EUR is also his call and stays open.

### 2026-08-27, design-review session. WP4 RTL freeze, at 24 sites.

Read this first. It changes the shipped size, adds two blocks, and withdraws
four claims.

**What the review found, and what was done about it.**

1. **The drive stage was half right.** There is no output multiplexer, so the
   selected variant really does drive the load and the drive selection is
   electrically visible, which was the whole reason the site is shaped that way.
   But all four variants shared one input net. Upstream load was the sum of four
   variants regardless of selection, and the three unselected variants switched
   their input stages on every transition. The timing effect was a CONSTANT
   offset that cancels in a difference between two drive settings, which is why
   it survived four rounds of review; the current and supply-noise effects did
   not cancel and were real.
   Fixed in `src/drive_node.v`, which the fabric and the characterization block
   now share so the replica is literally the same circuit. Sites 1, 3, 5 and 7
   are deliberately left un-isolated, paired with their isolated even
   neighbours, and `src/char_paths.v` paths 14 and 15 are a matched fixed pair
   differing in nothing else. The cost of isolation is a measurement on this die.

2. **The calibration strip was too thin, and partly the wrong instrument.** A
   ring oscillator averages over millions of transitions and self-heats while it
   runs, so it cannot report the delay of a single edge, which is what a
   combinational path actually does. Added `src/char_paths.v`, sixteen fixed
   non-oscillating paths, and `src/tdc.v`, a 32-tap delay-line converter that
   measures one transition. The strip grew from four rings to eight, including
   three IDENTICAL ones whose spread is the within-die variation floor and whose
   difference is placement and nothing else.

3. **Placement cannot be requested.** Tiny Tapeout's LibreLane configuration
   exposes no standard-cell placement regions, so "near the fabric" and "far
   from it" are not properties this design can assert. `tools/check_placement.py`
   reads the placed DEF and reports what the flow actually did, and every
   spatial statement is quoted against that report. A clustered build cannot
   support a spatial claim and the report says so.

4. **There is no independent fabric supply.** Confirmed against Tiny Tapeout's
   analog specification: individual projects cannot run at a different core
   voltage from the rest of the chip. "Drop the supply until a configuration
   fails" is retracted. The whole-chip sweep is what remains and it works only
   because the scan CRC and the reference paths report their own failure.

5. **Four claim wordings were withdrawn**, recorded in the new "Licensed and
   unlicensed language" section of docs/PRIOR_ART.md, along with the one
   sentence now licensed for the chip as a whole. The repo was already more
   careful than the conversation had been, which is the failure mode the rule
   exists to prevent, so the specific wordings are written down.

**The size changed. 24 sites on 6x2, not 32.** The new blocks put about 650
cells into the FIXED column, a little over two tiles of overhead that no site
count amortises, and the isolation gates raised the marginal cost per site from
69.75 to 73.75. At 24 sites a 6x2 build projects to 29.5 percent utilization
against the 34.8 percent that already routed clean. At 32 sites the same 6x2
projects to 35.2 percent, which is not a margin, it is landing exactly on the
only data point we have. The full working, and the 32-on-8x2 option at about
1,120 EUR, are in docs/AREA_GATE.md. This applies PLAN.md section 3's "cut sites
before cutting the strip" rule for the first time, and it cost eight sites.

**A timing problem was found that had nothing to do with the review.** The path
from any config register through `inert` to every drive enable, down the whole
column, to the safety monitor's synchronizer is linear in the site count. It met
timing at 8 sites and would not at 24. It should never have been timed at all,
because the monitor's input is asynchronous by construction, which is why it has
a three-stage synchronizer. Saying that in SDC needs a name that survives the
flow, so `u_mon_iso` is a hand-instantiated buffer that exists only to be named.
`tools/check_netlist.py` fails if the cell is gone and `tools/check_constraints.py`
fails if the two files stop agreeing, because the failure it prevents is silent:
a constraint that matches nothing produces no error anywhere.

**State.** 14 cocotb tests and 44 harness tests pass. The structural netlist
check and the constraint check pass, and both were sabotage-tested rather than
inspected. The Python model still agrees with the Verilog on 64 random and 36
sabotaged genomes through the widened 32-bit global word.

**Owed next, in order.**
1. Push and let Tiny Tapeout's CI build at 24 sites. The utilization column in
   docs/AREA_GATE.md is a projection until it comes back. This is free and
   nothing else should be decided before it.
2. Run `tools/check_placement.py` on the resulting DEF and write the achieved
   separation into docs/AREA_GATE.md. It decides whether the spatial experiment
   is available on this die at all.
3. Write the pre-registered predictions (WP5) against docs/MEASUREMENT_PROTOCOL.md
   stage by stage. In particular the depth series has to have a predicted slope
   before silicon, or the TDC calibration is unfalsifiable.
4. Blocked on Andrew and only on Andrew: the SKY26c deadline and pricing at
   app.tinytapeout.com, the 6x2 tile spend, and an iCE40 board.

### 2026-08-26, implementation session

**WP1 CLOSED.** docs/PRIOR_ART.md rows 1, 2, 3, 8 and 9 are CLOSED, rows 4 to 7
PARTIAL with queries logged. The Tiny Tapeout index was enumerated in full, all
27 shuttles and 4,572 projects, reproducibly via `tools/tt_index_sweep.py` with
the raw evidence committed under docs/sweeps/. Two findings changed the plan and
PLAN.md was corrected in the same commit.
- WobblyBits on TTSKY26a is an open sky130 Ising and Boltzmann p-bit sampler
  with an SPI-loadable coupling matrix. That kills the row 4 p-bit claim for
  tapeout one outright and narrows row 3 to continuous-time phase dynamics with
  an on-die digital control mode for comparison.
- Zero of 4,572 projects match any evolvable-hardware keyword, so rows 1 and 2
  survive. Row 2's strength depends entirely on the search-against-the-die
  qualifier, which is now recorded as load bearing.
- Outstanding: step 3 of the sweep protocol, the FOSSi, ORConf and Latch-Up talk
  archives, was not run. Recorded in the file rather than quietly skipped.

**WP2 mostly done.** This repo is now the Tiny Tapeout project repo; the stock
flow needs info.yaml, src/, test/ and the workflows at the root, and the
tt-gds-action is pinned at @ttsky26c, the target shuttle. One fabric site, a
four-ring calibration strip, the scan chain with CRC-gated load, the frequency
counter and the hardware safety controller are written and tested. 10 cocotb
tests and 17 harness tests pass in CI.
- The flow's first real answer: LibreLane rejected the design on multiple-driver
  nets, not on the combinational feedback edge. The loop runs through liberty
  blackbox cells so yosys's check cannot see it. `ERROR_ON_SYNTH_CHECKS` is now
  false with the reasoning in src/config.json, and the lost guarantee is
  replaced by `tools/check_netlist.py` running in CI.
- Marginal area measured at 99.5 cells per site against a 40 to 80 estimate,
  projecting 7,200 cells at 64 sites. docs/THROUGHPUT.md is corrected and names
  the saving to take first if area runs short.
- **WP2 CLOSED.** The LibreLane run completed: DRC 0, LVS 0, hold clean, setup
  clean at tt and ff. 8 sites on 2x2 tiles is 25,263 um2 of standard cells at
  34.8 percent utilization. The verdict is in docs/AREA_GATE.md and it changes
  the plan: **64 sites does not fit**, wanting about 17 tiles against a maximum
  of 16, and the recommendation is 32 sites on 6x2. That is roughly 840 EUR of
  tiles against the 300 to 450 EUR sketched in PLAN.md section 6, so it is a
  budget decision for Andrew rather than a design decision.

**WP3 items 1 and 2 done in simulation.** harness/ implements the genome, the
validator, the operators, the search, the results database and two devices. The
Python model and the actual Verilog agree on 64 random and 36 sabotaged genomes,
which is what makes the encoder trustworthy rather than merely self-consistent.
Three defects that all produce reasonable-looking numbers were found and fixed
along the way; see the commit for a7d494b.
- Simulation rate is 121 trials per second, which is a simulation rate and is
  labelled as one. The hardware number needs a board.
- docs/FPGA_PILOT.md assigns each WP3 item to iCE40 or AWS F2 and explains why
  six of the eight need a physical part on a bench. tools/aws/launch_f2.sh is
  ready but deliberately not run.

**Verification state, 2026-08-27.** The whole pipeline is green on commit
87bd3bd except one cosmetic job.

| job | result |
|---|---|
| `test` (10 cocotb RTL, 44 harness, netlist and constraint checks) | pass |
| `docs` | pass |
| `gds` (LibreLane: routing DRC 0, Magic DRC 0, LVS 0, hold 0) | pass |
| `precheck` (Tiny Tapeout submission gate) | pass |
| `gl_test` (against the extracted netlist) | 8 pass, 0 fail, 2 skip, 1.29 s |
| `viewer` | fails, needs GitHub Pages, unavailable while the repo is private |

The two gate-level skips are the tests that start a ring oscillator, and the
reason is in docs/AREA_GATE.md: the sky130 FUNCTIONAL cell models carry no delay,
so a ring built from them is a zero-delay combinational loop that an event
simulator cannot advance through. Measured rather than assumed, by a run that
froze at 38,547 ns and was killed at GitHub's six hour limit. Do not try to
re-enable them; fix the models or accept that this is silicon-only, which is the
bar PLAN.md sets anyway.

`viewer` will start passing on its own once the repo is made public, which it is
intended to be. Nothing depends on it.

**WP4 and WP5 not started.**

**WP3 item 8 CLOSED**, see docs/BITSTREAM_EVOLUTION_EVAL.md. Adapt two things,
do not adopt the core, do not link against it (they are GPL-3.0 and this repo is
Apache-2.0). Their intrinsic loop runs at about one evaluation per second against
the 60 to 300 we need, which is inherent to reflashing a bitstream rather than a
defect, and it is one of the few concrete advantages of our approach that has
nothing to do with electrical realization.

### Next action, in order
1. **Andrew decides the site count**, which is really a budget decision. See
   docs/AREA_GATE.md. 32 sites on 6x2 is the recommendation.
2. **Andrew orders an iCE40 board.** docs/FPGA_PILOT.md names the exact parts and
   recommends the iCEstick, because the published replications target it and we
   inherit their working configuration. Six of the eight WP3 items are blocked on
   this and none of them are blocked on anything else.
3. **Andrew confirms the SKY26c deadline and pricing** in the calculator at
   app.tinytapeout.com. docs/TT_LOGISTICS.md has what is known without a login.
4. Then WP4, which must re-run the area gate once block P, block C and the TDC
   exist, because the numbers in docs/AREA_GATE.md bound the fabric and the
   calibration strip and nothing else.
