# PLAN

Last updated 2026-08-26 (WP1 sweep folded in). This document is the source of truth for what we are building and why. It records the conclusions of the design discussion that produced this repo, including the claims that were narrowed or killed along the way, so we do not re-argue them.

## 1. Mission

Build one Tiny Tapeout chip that is a standing physical laboratory. It must clear a single bar. Every headline experiment must be impossible on an FPGA and unsettleable by simulation alone. FPGA-doable work is done on an FPGA, as the pilot and as the control arm, never presented as the reason for fabrication.

Two directions share the chip and reinforce each other.

1. **Below the abstraction.** A configurable fabric where the genome selects the electrical realization of logic, not just its truth table. Which drive strength and cell variant implements each gate, what capacitive load hangs on each node, which transistor-adjacent faults are inserted, which feedback edges close. Evolution and search run against the physical die.
2. **Physics as the computer.** Small dynamical structures that solve problems by settling rather than by clocked computation. Coupled ring oscillators with configurable coupling (Ising-style optimization), probabilistic bits built from deliberately marginal elements using true thermal noise, temporal classifiers, analog-time integration. See docs/FUNCTIONS.md.

Model validation (sky130 Liberty / extracted / SPICE against silicon) is one chapter and the calibration backbone, not the thesis. The fabric is the mission; the calibration strip makes its results defensible.

## 2. What survived four rounds of adversarial review

These are settled. Do not reopen without new evidence.

- Most evolvable-hardware experiments (Thompson replication, cross-device transfer, PUF/TRNG evolution, aging, coupling detection) are FPGA-doable and have prior art (Thompson 1996, JPL FPTA, Bitstream Evolution toolkit, FPGA long-wire side channels). They are pilot material, not fabrication justification.
- The genuinely ASIC-only levers are: cell-variant and drive-strength selection, designed and characterized loading, designed coupling geometry with shielded controls, transistor-internal faults, known-geometry replicas, analog observation of internal nodes, near/sub-threshold operation, and open-PDK white-box modeling of all of it.
- Parallel cell variants behind a mux all switch together. Energy claims from such a bank are invalid. Fix: fixed characterization macros for clean electrical claims; the reconfigurable fabric for evolution with overhead modeled, and fabric energy claims are OUT of scope (whole-chip current is the only instrument).
- A "disabled" tristate load is reduced capacitance, not zero. Characterize both states; never describe disabled as unloaded.
- Coupling-as-computation exists on FPGAs (side-channel literature). Our claim is designed geometry + extracted prediction + shielded/supply-separated controls, i.e. quantitative model tests of a designed channel, not first demonstration.
- sky130 open models are an experimental preview with documented Liberty issues. Phrase as "validating the publicly released open-PDK models", distinguish Liberty vs Liberty+extraction vs transistor-level SPICE. Disagreement at one layer does not indict another.
- Calibrate the on-chip TDC against bench equipment through pins, never against Liberty-predicted macro delays (circularity).
- **Added 2026-08-26 by the WP1 sweep, and it costs us.** WobblyBits (shuttle TTSKY26a, github.com/rats2012/WobblyBits) is an open sky130 Tiny Tapeout chip with 6 p-bits, an SPI-loadable 6x6 signed coupling matrix and neoTRNG entropy, sampling an Ising/Boltzmann distribution. It is described by its own authors as a digital probabilistic computing chip and its update rule is a synchronous threshold comparison, not phase settling. Consequences. (a) "open-silicon oscillator Ising machine, cheaply reproducible" is no longer an available claim. (b) The p-bit claim for tapeout one is dead outright; the p-bit mode stays as a measurement and cites WobblyBits. (c) Block P's residual is continuous-time phase dynamics with the coupling ladder searched in-loop, against a digitally-updated control on the same die. See docs/PRIOR_ART.md rows 3 and 4.
- Pre-registration: commit all pre-silicon predictions with uncertainty bounds to this repo before the shuttle deadline. Chips arriving is the reveal.
- Holdout discipline: dies, voltage/temperature points, input traces, and fabric regions never used during evolution, reserved for generalization tests.
- **Added 2026-08-27 by a design review of the WP2 vehicle. Four settled items, do not reopen.**
  1. *The tri-state output arrangement settles the output side of drive selection and says nothing about the input side.* In the first version all four drive variants shared one input net, so the upstream load was the sum of four and the three unselected variants switched on every transition. The timing consequence was a constant offset that cancelled in a difference, which is why it survived review once; the current and supply-noise consequences did not cancel. Fixed by gating each variant's input with its own enable (src/drive_node.v). Four sites are deliberately left un-isolated as controls, and src/char_paths.v carries a matched fixed pair that differ in nothing else, so the cost of isolation is measured rather than asserted.
  2. *Ring oscillators are the wrong instrument for a single edge.* A ring averages over millions of transitions and self-heats while it runs. Combinational path delay is now measured by the TDC (src/tdc.v) against fixed non-oscillating paths (src/char_paths.v), and the strip is a covariate rather than a reference for delay. The strip is never called a thermometer.
  3. *There is no independent fabric supply.* Tiny Tapeout's rails are shared infrastructure and a project cannot run at a different core voltage from the rest of the chip. "Lower the supply until a configuration fails" is not an experiment tapeout one can run, and it is retracted. The whole-chip sweep on the demo board is what remains, and it works only because the scan CRC and the reference paths report their own failure. A per-block supply is a tapeout-two requirement.
  4. *The fabric's feedback edge is not an Ising machine of any size.* No controllable coupling, no phase readout, no locking guarantee, no per-oscillator enable. Offering it as a weaker version of block P was an error. It can oscillate; that is a capability to characterize, not a claim to make in advance.
  See docs/MEASUREMENT_PROTOCOL.md for the four-stage protocol these imply, and the "Licensed and unlicensed language" section of docs/PRIOR_ART.md for the specific claim wordings that were withdrawn.
- Safety is hardware, outside the fabric: default-inert configuration, one-hot enforcement for tristates, trial duration and transition-rate limits, cooldown, external kill. Fault modes use weak/series-resistance devices sized in SPICE, never hard bridges. A host-side genome validator rejects structurally unsafe configurations before load.

## 3. Chip architecture (tapeout one)

Tier discipline: overwhelmingly tier 1 (standard digital flow, hand-instantiated sky130 cells with keep/dont-touch), a small nonessential slice of tier 2 (constrained routing geometry), tier 3 (custom transistor-level cells, analog probe buffers) deferred to tapeout two except possibly 2 analog pins if cheap on the chosen shuttle.

Blocks, in priority order (later blocks are dropped first if area runs out):

- **B. Evolvable electrical-realization fabric** (the mission). Target ~48–64 sites, **shipped at 24 after two area gates; see docs/AREA_GATE.md**. Per site: function select (NAND/NOR/XOR/INV/wire), drive variant select (X1/X2/X4 from sky130_fd_sc_hd, one library only), load ladder (switch-parasitic / 1 / 2 / 4 dummy inputs), sabotage mux (stuck-0, stuck-1, bypass-A, bypass-B, invert), local routing select with explicitly enabled feedback edges (feed-forward columns + strategic feedback, not full mesh). Scan-chain config with readback + CRC.
- **P. Physics patch. NOT ON TAPEOUT ONE.** The area went to blocks A, C and T instead; see docs/AREA_GATE.md and docs/EXPERIMENT_MATRIX.md. Kept here as the tapeout-two design.  8–16 coupled ring oscillators with mux-selectable coupling strength via parallel tristate drivers (digital-flow-compatible), phase readout via counters/sampling. Doubles as p-bit substrate (jittery oscillator sampled = tunable random bit), which after the WP1 sweep is a measurement rather than a claim. This is the flagship demo target: configure couplings to a MAX-CUT instance, let phase dynamics settle, read the cut. The patch must also carry a digitally-updated Ising control mode on the same die, because that is the only thing separating this from WobblyBits and the comparison has to be on-chip and same-instance to mean anything.
- **A. Calibration strip.** Fixed macros: each drive variant and structural alternative on a clean dedicated path with known load; replicas for within-die spread; one path routed to pins for bench-instrument TDC anchoring; ring-oscillator PVT monitors. ~15% of area, non-negotiable floor. **Built 2026-08-27 as two blocks rather than one, because rings and single edges are different instruments: eight rings in src/calib_macro.v and sixteen fixed non-oscillating paths in src/char_paths.v. Together with the TDC they are now roughly 40 percent of the cell count, and the "cut sites before cutting the strip" rule was applied for the first time, costing eight sites.**
- **C. Geometry replicas** (small). 2–3 logically identical paths with mirrored/spread placement, for netlist-vs-geometry transfer. **Partly built 2026-08-27 as calibration rings 0, 6 and 7, three identical circuits, and then MEASURED. Placement cannot be requested in the Tiny Tapeout flow, and the placed DEF puts all three within 43 um on a 1,023 um die, 4 percent of the diagonal. So block C's spatial half does not exist on tapeout one and no spatial result will be reported from it; the triple survives as the within-die variation floor, which every other difference on the chip has to beat. Floorplan control joins the per-block supply on the tapeout-two list. Working in docs/AREA_GATE.md.**
- **D. Coupling matrix** (smallest, tier 2, droppable). One unshielded pair, one shielded control, one separated baseline.
- **Infrastructure serving all blocks.** Scan controller, trial counter, sticky brownout flag, transition counters, tapped-delay-line TDC, safety controller (hardware, conventional synchronous logic, fabric can never gate its own kill path).

## 4. Phases

- **Phase 0 (now).** Prior-art enumeration (docs/PRIOR_ART.md). Trial P&R of one fabric site + one calibration macro for real area numbers (OpenLane/LibreLane, runs in Docker under the light-compute rule, or on a cloud box). Throughput spreadsheet confirmed against RP2040 realities (docs/THROUGHPUT.md). Pick shuttle + deadline (docs/TT_LOGISTICS.md). Decide analog pins yes/no.
- **Phase 1. FPGA pilot.** iCE40 board (~$50). Same GA/search harness, scan protocol, results database, holdout discipline, crash recovery. The FPGA is also the permanent control arm (same software, LUT/routing genome vs physical genome).
- **Phase 2. RTL.** Fabric site as hand-instantiated cells, safety controller, scan+CRC, counters, TDC, physics patch. Full-chip simulation incl. every sabotage mode. Trial P&R iterations to fit tile budget.
- **Phase 3. Pre-register + submit.** Commit Liberty/extracted/SPICE predictions with uncertainty bounds. Submit to shuttle. During the wait, run the FPGA control-arm studies to completion.
- **Phase 4. Bring-up and measurement.** Order: calibration strip across dies and PVT → TDC bench anchoring → repeatability/noise floor → sabotage and safety validation → only then evolution and physics experiments. Otherwise search optimizes measurement flaws.
- **Phase 5. Tapeout two.** Tier-3 custom primitives (transistor-internal faults, current-starved cells, dynamic nodes, analog taps, real p-bit cells), designed from tapeout-one evidence, on an analog-capable shuttle slot. **The list of things tapeout one proved it cannot do, and which therefore belong here, is now specific: a genuinely switchable capacitive load (needs a series pass device, not a tri-state input), an independent fabric supply, floorplan control for the spatial replicas, three-input functions with per-site state, and gate-level rather than site-output fault injection.**

## 5. Papers / outputs

1. Platform + physics-patch result (does physical settling solve instances the same fabric clocked as logic solves slower/worse, measured against the on-die digital control mode). The public pitch: a chip where the physics is the computer.
2. Electrical-realization evolution vs open-PDK model predictions (the abstraction-gap chapter), with pre-registered predictions.
3. Everything open: RTL, GDS, harness, predictions, raw measurements. Reproducible for a few hundred euros.

Claims hygiene: every novelty sentence must cite the closed enumeration row in docs/PRIOR_ART.md that licenses it. "First X" is banned until its row is closed.

## 6. Budget (rough, to verify in phase 0)

~4–6 tiles at ~70€ = 300–450€, +80€ if 2 analog pins, + devkit/demo board + bench (already-owned scope assumed; source meter and Peltier rig deferred to phase 4 decision). Total well under 1k€ for tapeout one.

## 7. Risks

- ~~Area estimate optimistic~~ → **MEASURED 2026-08-26.** The estimate of 40 to 80 cells per site was optimistic, at 99.5 measured, and the miss was entirely in the infrastructure the estimate did not count: shadow-plus-live double buffering at 24 flops per site, and a CRC tree that grew with the payload. Making the CRC serial and the limit tests bit tests brought it to 69.75 cells per site and 5,113 cells projected at 64 sites. See docs/THROUGHPUT.md.
- ~~OpenLane fights combinational feedback~~ → **SETTLED 2026-08-26 by the trial place and route, and it was the wrong worry.** The flow did not object to the combinational feedback edge at all; the loop runs through liberty blackbox cells, so yosys's check cannot see through it, and the design routed, passed DRC and passed LVS with the loop present. `keep` and `dont_touch` survived; all four drive variants and every calibration ring cell are in the final netlist. What the flow actually objected to was (a) multiple drivers on the tri-state nets, which is the fabric working as designed and is now handled by `ERROR_ON_SYNTH_CHECKS` plus our own `tools/check_netlist.py`, and (b) timing the fabric's combinational chain as if it were a clocked path, which is now handled by `src/timing.sdc` declaring the measurand asynchronous. Both are recorded in docs/AREA_GATE.md.
- Physics patch phase dynamics too weak/too synchronized through digital coupling → tristate-strength coupling ladder is the mitigation; worst case the patch degrades to a TRNG/temporal-classifier study, still publishable.
- Shuttle slip / lead time (~months to silicon) → FPGA control arm fills the wait by design.
- Someone already did a sky130 characterization chip → confirmed 2026-08-26, four of them (docs/PRIOR_ART.md row 8). Block A claims nothing, cites them, and the paper leans on B and P.
