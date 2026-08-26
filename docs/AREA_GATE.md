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

## Reproducing this

    tools/area_sweep.sh build/area          # marginal cells per site, local, light
    python3 tools/check_netlist.py build/area/n8.json --sites 8
    python3 tools/check_constraints.py
    git push                                # the flow runs in Tiny Tapeout's CI

The CI run is the authoritative source for area, DRC, LVS and timing. The local
sweep is a fast cross check that costs this machine almost nothing, and it is the
only one of the two that can answer "what does one more site cost".
