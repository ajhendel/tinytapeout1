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
- 2026-08-26: repo created, plan written, no implementation yet. Next action is WP1.
