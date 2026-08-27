# AREA_GATE — what the trial place and route actually said

WP2 item 4. This is the gate that PLAN.md says every RTL scope decision waits on.
Written 2026-08-26 from real runs of the Tiny Tapeout GitHub Actions flow
(LibreLane 3.0.5, sky130A, tt-gds-action pinned at ttsky26c), which costs nothing
and loads this Mac not at all.

The trial vehicle is `tt_um_ajhendel_evofab` at 8 fabric sites on 2x2 tiles, plus
the four-ring calibration strip, the scan chain, the CRC, the safety controller,
the frequency counter and one enumerated combinational feedback edge.

## The four questions WP2 asked, answered

### Does keep and dont_touch survive the flow?

**Yes.** Every hand-instantiated cell is in the final netlist. All four drive
variants (`einvn_1`, `einvn_2`, `einvn_4`, `einvn_8`) survive, at one per site
each, which is the thing that would have quietly destroyed the fabric had it
failed. `tools/check_netlist.py` now asserts this in CI rather than leaving it to
be noticed.

### Does the deliberate combinational feedback loop pass the flow?

**Yes, and the worry was misplaced.** PLAN.md risk 2 was "OpenLane fights
combinational feedback". It did not fight it at all. The loop runs through
liberty blackbox cells, so yosys's `check` pass cannot see through them to find
the cycle, and the design placed, routed, passed DRC and passed LVS with the loop
present.

What the flow did object to was two things nobody had anticipated, and both are
recorded below because both are the design working as intended.

### What DID the flow object to?

**1. Multiple drivers on the tri-state nets.** Sixteen problems at 8 sites, one
pair per site: the four drive-stage tri-state inverters sharing the site output
node, and the three ladder elements plus the keeper sharing the ladder sink. That
is the fabric. Muxing the drive variants instead would put the mux between the
selected driver and the load and make the drive selection electrically invisible,
which is the whole point of the chip.

Resolution: `ERROR_ON_SYNTH_CHECKS` is false in `src/config.json`, with the
reasoning written into that file, and the guarantee is **replaced rather than
dropped**. `tools/check_netlist.py` runs in CI and fails if a tri-state enable
was constant folded, if a shared tri-state net has neither a common data input
nor distinct enables, or if a drive variant was optimized away. The drive enables
are also decoded one-hot in hardware, so contention is structurally impossible
rather than conventionally avoided.

**2. Timing the fabric as if it were a clocked path.** The worst setup path was
reported as `ui_in[5]` into the fabric, through every site, out at `uo_out[6]`,
at -36.4 ns against a 20 ns clock at the slow corner. Static timing analysis is
right that the path is long and wrong that it is a violation: the fabric's
propagation delay is the measurand, it sits in no clocked path, and the
measurement protocol waits between 16 and 524,288 clocks. Constraining it made
the flow insert 328 timing repair buffers into the very network we intend to
characterize against the open-PDK models.

Resolution: `src/timing.sdc` declares the fabric's data inputs and its three
observation outputs asynchronous, and names in the file which consumer makes each
one safe. Nothing else is relaxed; the scan chain, CRC, safety controller, window
and counters stay timed normally. `tools/check_constraints.py` ties the SDC to
the pin names in `info.yaml` and runs in CI, because remapping a pin would
otherwise leave a false path on the wrong pin and a synchronous path would never
have been timed.

### What are the real cells-per-site and tiles-for-64-sites numbers?

See the next two sections. The short answer is that the original estimate was
optimistic, the reason was infrastructure the estimate did not count, and fixing
the two deep paths the flow found also fixed most of the area miss.

## Cells per site, measured

`tools/area_sweep.sh` builds at 1, 2, 4, 8 and 16 sites and takes the slope,
because the marginal cost is the number that matters. Dividing a single build by
its site count charges the fixed infrastructure to the sites.

| | estimate | first build | after the fixes |
|---|---|---|---|
| marginal hand-instantiated cells per site | (not separated) | 34 | 34 |
| marginal synthesized cells per site | 40 to 80 total | 65.5 | 35.75 |
| **marginal total per site** | **40 to 80** | **99.5** | **69.75** |
| fixed hand cells (calibration strip) | | 156 | 156 |
| fixed synthesized cells (scan, CRC, safety, counters) | | 676 | 493 |
| projected cells at 32 sites | | 4,016 | 2,881 |
| projected cells at 48 sites | | 5,608 | 3,997 |
| **projected cells at 64 sites** | 2,500 to 5,000 | **7,200** | **5,113** |

Where the estimate went wrong, and it is worth knowing because the same blind
spot will recur in WP4.

- The config path is double buffered. A shadow chain bit plus a live register bit
  per config bit is 24 flops per site, not the 12 the estimate assumed. The
  second copy is what makes a partially shifted or corrupt frame unable to reach
  the fabric, so it is not removable without giving up the safety property.
- The CRC was a combinational tree over the whole payload, so it grew with the
  site count and landed in the marginal column, at roughly 12 cells per site.

Both are costs of the safety story, and both were invisible to an estimate that
counted only the fabric.

The CRC is now computed serially, one LFSR step per scan clock. That was
originally listed as an area saving and turned out to be the timing fix as well,
which is the usual sign that the first version computed something it did not need.

## Tiles and area, measured

From the LibreLane run that completed (Flow complete, DRC 0, LVS 0, hold WNS 0):

| quantity | 8 sites, 2x2 tiles |
|---|---|
| die area | 75,602 um2 |
| core area | 72,565 um2 |
| standard cell area (excluding fill and tap) | 25,263 um2 |
| standard cell instances | 3,234 |
| sequential cells | 351 |
| fill cells | 13,406 |
| tap cells | 1,037 |
| timing repair buffers | 441 |
| standard cell utilization | 34.8 % |
| total power, nominal corner | 1.56 mW |
| routing DRC errors | 0 |
| Magic DRC errors | 0 |
| LVS errors | 0 |
| hold WNS | 0 ns, every corner |
| setup WNS | 0 ns at tt and ff; -4.53 ns at ss only, one endpoint |

The one remaining endpoint was `ena` reaching the fabric's inert gating. `ena` is
Tiny Tapeout's project-select line and is static while the project is in use, so
it is now declared asynchronous in `src/timing.sdc` as well. `rst_n` is
deliberately not, because reset recovery and removal are real checks that the
safety controller depends on, and `tools/check_constraints.py` refuses a false
path on it.

### What this projects to at 64 sites

Two independent estimates, because one number with no cross check is a guess.

**From cells.** 5,113 yosys cells projected at 64 sites against 1,207 at 8, so
4.24 times. Standard cell area 25,263 um2 at 8 sites gives roughly 107,000 um2
at 64. At the flow's 60 percent target density that wants about 178,000 um2 of
core.

**From utilization.** The 2x2 build sits at 34.8 percent utilization, so it has
headroom of about 1.7 times before it hits the 60 percent target. That covers
roughly 14 sites on 2x2. Scaling to 64 sites needs about 4.6 times the core area.

Both land in the same place. A 2x2 tile core is 72,565 um2, and a Tiny Tapeout
tile is a quarter of that, about 18,140 um2.

| sites | projected core needed | tiles | fits in |
|---|---|---|---|
| 8 | 72,565 um2 (measured) | 4 | 2x2 |
| 16 | about 100,000 um2 | 5.5 | 3x2 |
| 32 | about 170,000 um2 | 9.4 | 6x2 |
| 48 | about 240,000 um2 | 13.2 | 8x2 |
| 64 | about 310,000 um2 | 17.1 | beyond the 8x2 maximum |

**Verdict. 64 sites does not fit a Tiny Tapeout project on this shuttle.** The
largest standard tile geometry is 8x2, which is 16 tiles, and 64 sites wants
about 17. The honest options, in the order PLAN.md section 3 says to take them:

1. **32 sites on 6x2.** Comfortable, leaves routing headroom, and 32 sites is
   still four times what the trial vehicle proves. This is the recommendation.
2. **48 sites on 8x2.** Fits with very little margin, and the projection has real
   uncertainty in it because routing congestion is not linear in cell count. Only
   attempt this after a trial build at 48.
3. Cutting the calibration strip is NOT on this list. PLAN.md calls it a
   non-negotiable floor and the prior-art sweep is the reason: block A is what
   makes block B's measurements defensible, and it claims nothing itself.

At roughly 70 EUR per tile, 6x2 is about 840 EUR, which is above the 300 to 450
EUR sketched in PLAN.md section 6. That is a real budget decision for Andrew, and
it is a decision about how many sites the science needs rather than about how
many tiles the design happens to want.

### What is NOT settled by this

- These are 8 site measurements extrapolated. Routing congestion is not linear in
  cell count and the extrapolation will be optimistic somewhere. A trial build at
  the chosen site count is required before the submission, and it is free.
- The physics patch (block P) and the geometry replicas (block C) are not in the
  trial vehicle at all. Their area is unmeasured and is on top of every number
  above.
- The TDC is not in the trial vehicle either.

So the numbers here bound the fabric and the calibration strip, and nothing else.
WP4 has to re-run this gate once the full block list exists.

## WP4 RE-GATE, 2026-08-27. The answer moved, and it moved down.

Everything above this heading is the WP2 gate on the trial vehicle. This section
is the re-gate the section immediately above demanded, run after the design
review added the blocks it said were missing.

### What was added, and why each one is not optional

| block | file | why |
|---|---|---|
| drive-variant input isolation | `src/drive_node.v` | The tri-state output arrangement settled the OUTPUT side of drive selection and said nothing about the input side. All four variants shared one input net, so upstream load was the sum of four and three unselected variants switched on every transition. |
| four un-isolated control sites | `src/project.v` | So the cost of isolation is a measurement on the die instead of an argument in a comment. |
| sixteen fixed characterization paths | `src/char_paths.v` | The missing rung of the inference chain. Cells -> fixed paths -> configurable sites -> evolved circuits. |
| a time-to-digital converter | `src/tdc.v` | A ring reports an average over millions of transitions and self-heats while it runs. A combinational path delay is one transition, and needed its own instrument. |
| four more calibration rings | `src/calib_macro.v` | A compact ring, a ring built from the fabric's own output stage, and two more copies of ring 0 whose spread is the within-die variation floor and whose difference is placement. |
| a timing anchor cell | `src/project.v` | `u_mon_iso`, so `src/timing.sdc` can cut the fabric-to-safety-monitor path by naming something that survives the flow. That path grows linearly with the site count and would violate at the submission size. |

### The new numbers

`tools/area_sweep.sh`, same method, slope between the 8 and 16 site builds.

| | WP2, after the fixes | WP4, after the review |
|---|---|---|
| marginal hand cells per site | 34 | **38** |
| marginal synthesized cells per site | 35.75 | 35.75 |
| **marginal total per site** | **69.75** | **73.75** |
| fixed hand cells | 156 | **576** |
| fixed synthesized cells | 493 | **726** |
| **fixed total** | **649** | **1,302** |
| cells at 8 sites | 1,207 | 1,892 |
| cells at 24 sites | | **3,072** |
| cells at 32 sites | 2,881 | 3,662 |

The marginal rise is exactly the four isolation AND gates per site, which is what
it was predicted to be. The fixed rise is the whole story: **the review roughly
doubled the fixed cost**, and fixed cost is the one thing a site count cannot
amortise.

### What that does to the tile count

Same method as the WP2 gate: standard cell area scales with the yosys cell
count, calibrated against the one completed LibreLane run, which placed 1,207
yosys cells as 25,263 um2 of standard cells in a 4 tile core of 72,565 um2 at
34.8 percent utilization.

| sites | yosys cells | standard cell um2 | utilization in 6x2 | utilization in 8x2 |
|---|---|---|---|---|
| 8 | 1,892 | 39,600 | 18.2 % | 13.6 % |
| 16 | 2,482 | 51,900 | 23.9 % | 17.9 % |
| **24** | **3,072** | **64,300** | **29.5 %** | 22.2 % |
| 32 | 3,662 | 76,600 | 35.2 % | 26.4 % |
| 48 | 4,842 | 101,300 | 46.6 % | 34.9 % |

**Verdict. 24 sites on 6x2.** At 29.5 percent projected utilization it sits below
the 34.8 percent that already routed clean, DRC clean and LVS clean.

32 sites on 6x2 projects to 35.2 percent, which is not a margin, it is a
coincidence: it lands on the one density we have evidence for, with nothing
either side of it. Routing congestion is not linear in cell count, the new
blocks are keep and dont_touch and so cannot be resized to relieve it, and the
projection is an extrapolation from a build four times smaller. Sitting exactly
on the only data point is not the same as having headroom.

The alternatives, honestly:

1. **24 sites on 6x2, about 840 EUR.** The recommendation, and the same money
   Andrew already approved for 32.
2. **32 sites on 8x2, about 1,120 EUR.** Buys the site count back for 280 EUR and
   lands at a comfortable 26.4 percent. A real option, and a budget decision
   rather than a design one.
3. **32 sites on 6x2.** Only after the 24 site build comes back from CI and shows
   real headroom. The build is free; the extrapolation is not evidence.
4. Cutting the calibration strip is still not on this list. PLAN.md section 3
   says cut sites before cutting the strip, and this is the first time that rule
   has actually cost something, which is exactly when a rule is worth having.

### What is still NOT settled by this

- These are 8 and 16 site yosys builds extrapolated through one LibreLane run of
  a smaller and different design. **A trial build at 24 sites is required before
  submission and it is free.** Until it comes back, the utilization column above
  is a projection and nothing more.
- Block P (the physics patch) and block D (the coupling matrix) are still not in
  the vehicle at all and their area is on top of every number here.
- The TDC's delay line is 32 buffers plus 32 flip flops plus a five buffer
  sampling tree. Its area is in the numbers; its RESOLUTION is not known and
  cannot be until silicon. If the tap delay turns out much larger than expected,
  the 32 tap span may not cover the longer characterization paths, and the fix is
  a shorter reference path rather than more taps.
- Placement is not settled and cannot be requested. `tools/check_placement.py`
  reports what the flow actually did with the three identical rings and every
  spatial statement is quoted against that report.

## THE BUILD AT 24 SITES, MEASURED. 2026-08-27, commit becb941.

The projection above is now a measurement. LibreLane completed, precheck passed,
gate-level test passed.

### Area, and the projection held

| quantity | projected | **measured** |
|---|---|---|
| standard cell area | 64,300 um2 | **64,124 um2** |
| standard cell utilization | 29.5 % | **28.4 %** |
| standard cell instances | | 8,952 |
| sequential cells | | 833 |
| timing repair buffers | | 1,095 |
| die area | | 232,623 um2 |
| core area | | 225,802 um2 |
| total power, nominal | | 3.87 mW |

Within 0.3 percent on cell area. That is luckier than the method deserves and
should not be read as the method being that good; it is one point.

### Timing, DRC, LVS

| | 8 sites, WP2 | **24 sites, WP4** |
|---|---|---|
| setup WNS, worst corner | **-4.49 ns** | **+7.18 ns** |
| hold WNS, worst corner | 0 ns | **+0.107 ns** |
| violator list | one endpoint | **empty** |
| routing DRC | 0 | **0** |
| Magic DRC | 0 | **0** |
| LVS | clean | **circuits match uniquely** |
| antenna violations | | **0** |

Timing got BETTER while the fabric tripled. That is the `u_mon_iso` false path
doing its job: the path it cuts was the one that scaled with the site count, and
cutting it removed the whole class rather than one endpoint.

### The slew report, which is the interesting finding

The run reports **1,010 max transition violations at the slow corner**, against
246 at 8 sites. They are not timing violations, there are none of those, and
nothing in the Tiny Tapeout signoff gates on them. They still matter here,
because this chip's entire purpose is comparing measured delay against predicted
delay, and a transition outside the range a model was characterized over is a
prediction on thin ice.

Categorized, at `max_ss_100C_1v60`:

| where | count | worst slack |
|---|---|---|
| synthesized infrastructure (scan, CRC, safety, counters) | 556 | -0.48 ns |
| buffers the flow inserted to repair fanout | 226 | -1.06 ns |
| **fabric sites** | **202** | **-0.43 ns** |
| **characterization path 14, the isolated drive replica** | **17** | **-0.26 ns** |
| **calibration ring 5, the drive-node ring** | **6** | **-0.57 ns** |
| three singletons on the feedback gate and the launch mux | 3 | -0.27 ns |

The 782 in the first two rows are in blocks that are static or clocked during a
measurement, and they cost setup margin we have 7.18 ns of. They are not worth
fighting the flow over.

The 225 in the middle three rows are the ones worth reading, and they are all
**the same violation**. The violating pins are, per site and on every one of the
24 sites: `u_drive.drv1/Z`, `u_drive.drv2/Z`, the three ladder element inputs,
the ladder keeper input, and the next site's route multiplexer input. All of
those are the same net. **The drive-1 and drive-2 tri-state inverters cannot
slew the site output node inside 0.75 ns, because the load ladder and the next
site are hanging on it.**

That is not a defect. That is the fabric. The load ladder exists to put a
configurable, deliberately significant load on that node so that the drive
variant selection has something to matter about. If drive 1 could slew it
comfortably, the drive variants would barely differ and there would be less to
measure. Path 14 and ring 5 violate for the same reason and by construction:
they are replicas of that structure, and the fact that they violate in the same
way is evidence that the replicas really do replicate.

Two things follow, and they are owed rather than done.

1. **The 0.75 ns limit is ours, not the library's.** `set_max_transition 0.75`
   in `src/timing.sdc` is the stock Tiny Tapeout value, and every limit in the
   report is 0.75, so the run does not say whether the sky130 Liberty's own
   characterization range was exceeded. That has to be checked against the PDK
   Liberty before any prediction is quoted for those nodes, and it changes what
   the prediction means: inside the range it is an interpolation, outside it is
   an extrapolation and should say so.
2. **Input slew is now a variable the fixed paths have to carry.** A stage driven
   by a slow edge is slower than the same stage driven by a fast one. The
   characterization paths are all launched from the same balanced tree, so they
   share an input slew and their differences are still clean, but any comparison
   between a characterization path and a fabric site has to account for the
   fabric's slower edges. This is exactly the sort of thing the middle rung of
   the inference chain exists to expose, and it turned up before silicon rather
   than after, which is the point of running the gate.

The 47 max fanout violations are all clock tree leaf buffers at 13 or 14 loads
against a limit of 10. That is CTS behaving normally and is not ours.

### The placement report, which says the spatial experiment did not happen

`tools/check_placement.py` on the final DEF:

    placed extent: 1023.5 x 217.6 um, diagonal 1046.4 um

    group                             cells         centroid (um)   radius
    calib ro0 (reference twin)           31        (183.7, 161.5)     13.1
    calib ro_twin_a                      31        (202.6, 122.6)     14.5
    calib ro_twin_b                      31        (189.0, 120.0)     10.9
    calib ro5 (drive replica)           121         (101.2, 88.9)     49.8
    TDC delay line                       32         (31.1, 174.4)     55.2
    TDC sampling tree                     5         (27.1, 134.4)     44.8
    characterization paths              280         (107.6, 43.3)     55.4
    fabric column                       968        (358.4, 95.5)     212.9

    largest twin separation 43.3 um, 4 percent of the placed diagonal
    VERDICT: CLUSTERED

**The three identical rings landed within 43 um of each other on a 1,023 um
die**, and all three sit inside the fabric column's own footprint. There is no
"near the fabric" and "far from it" on this build. The placer minimizes
wirelength, the three rings share an enable decode and an output multiplexer,
and nothing in the Tiny Tapeout LibreLane configuration lets us ask for
anything else.

So **the spatial experiment is not available on tapeout one and no spatial
result will be reported from it.** That is the correct outcome of building the
tool: the alternative was measuring three frequencies, finding they differed,
and writing a sentence about position that the layout would not have supported.

What survives, and is arguably the more useful half anyway: three identical
circuits still give the **within-die, same-design variation floor**, which is
the number every other difference measured on this chip has to beat. That was
always the first purpose of the triple and it does not depend on where they
landed.

Floorplan control for the spatial experiment moves to tapeout two, where it
needs either placement regions or hard macros, and it joins the per-block supply
on that list.

## Reproducing this

    tools/area_sweep.sh build/area          # marginal cells per site, local, light
    python3 tools/check_netlist.py build/area/n8.json --sites 8
    python3 tools/check_constraints.py
    git push                                # the flow runs in Tiny Tapeout's CI

    # after the CI run, from the gds artifact
    python3 tools/check_placement.py <placed.def> --json placement.json

The CI run is the authoritative source for area, DRC, LVS and timing. The local
sweep is a fast cross check that costs this machine almost nothing, and it is the
only one of the two that can answer "what does one more site cost".

## What gate-level simulation can and cannot verify here

Added 2026-08-27, after the first gate-level run against the extracted netlist.
This matters for WP4, because the RTL freeze will want to lean on gate-level
simulation and there is a limit to how far it can be leaned on.

**What it verified.** Eight of the ten cocotb tests run against the real netlist
and pass in 1.3 seconds. That covers the scan chain, the CRC-gated load, the ARM
interlock, the full function truth table across all eight codes, every sabotage
mode, the load-ladder reach witness and default-inert behaviour, all against
hand-instantiated sky130 cells rather than behavioural models. This is the check
that would catch the flow having quietly rewritten the fabric.

**What it cannot do: run a ring oscillator.** The sky130 FUNCTIONAL cell models
are combinational and carry no delay, so a ring built from them is a zero-delay
combinational loop and an event simulator cannot advance time through one. The
first test to enable a calibration ring froze simulation time at 38,547 ns and
ran until GitHub killed the job at its six hour limit with vvp still spinning.

That is a fact about event simulators and not about the chip. It is also, exactly,
the bar PLAN.md sets: what the calibration strip measures is unsettleable by
simulation alone, which is why the strip is on the die rather than in a testbench.
The two tests that start a ring are therefore skipped under `GATES=yes`, with the
reason written where a future reader will hit it.

A second limit sits behind the first. Even if the loop could be advanced, unit
delay makes every cell take the same time regardless of drive variant, so a
gate-level run could not distinguish the inv_1, inv_2 and inv_4 rings. That
difference is a silicon measurement and is listed in `predictions/` as one.

**One testbench bug found by the gate-level run.** The suite sampled outputs 1 ns
after the clock edge. At RTL an output assignment is instantaneous so that works;
in the netlist the path from a flip-flop to an output pin takes real time, and
the sample read the previous value. It presented as the scan chain appearing to
be one bit short, which is precisely the failure the scan test exists to catch,
so a testbench bug was wearing the costume of a design bug. Everything now drives
and samples at mid-period, which is correct in both modes.
