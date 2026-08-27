# TODO — phase 0, in order

Gate: nothing in phase 2 (RTL) starts until items 1–4 are done, because each can reshape the architecture.

1. [x] **Prior-art sweep** (done 2026-08-26) — work docs/PRIOR_ART.md rows 1, 2, 3, 8, 9 to CLOSED (the rows the tapeout-one papers depend on). Rows 4–7 to PARTIAL-with-queries-logged.
2. [x] **Trial P&R** (done 2026-08-26, re-gated 2026-08-27, see docs/AREA_GATE.md) — one fabric site + one calibration macro through OpenLane/LibreLane against sky130. Real cells/site number replaces the estimate in docs/THROUGHPUT.md. Verify keep/dont_touch survives the TT flow and that a deliberate combinational loop passes. (Docker, light-compute limits on the Mac, or a cheap cloud box.)
3. [ ] **Deadline + price check** — log into app.tinytapeout.com calculator; record SKY26c deadline and exact tile pricing in docs/TT_LOGISTICS.md. Decide tile count ceiling and analog pins yes/no.
4. [x] **Throughput validation plan** (done 2026-08-26: harness/ implements it, harness/README.md states the firmware/host split, evofab/store.py is the results DB schema) — write the FPGA pilot spec: which iCE40 board, scan protocol frame format, firmware/host split, results DB schema (config hash, chip id, temp covariates, trial counter — the reproducibility metadata list from design review).
5. [ ] **Order FPGA board** (~$50) + confirm bench inventory (scope? frequency counter?) for the TDC anchoring plan.
6. [x] **Site design doc** (done 2026-08-26: the design IS src/fabric_site.v with the rationale in its header; docs/info.md is the readable version) — pin down the per-site config word (function/drive/load/sabotage/route bits), the feedback-edge topology (feed-forward columns + enumerated feedback edges), and the safety controller's limit registers.
7. [ ] **Physics patch design doc** (NOT on tapeout one; the area went to blocks A, C and T instead, see docs/AREA_GATE.md) — oscillator count, coupling ladder (parallel tristate drivers), phase readout method, MAX-CUT instance encoding, and the p-bit sampling mode.
8. [x] **Pre-registration scaffold** (done 2026-08-26: predictions/README.md carries the rule and the fixed list of quantities) — predictions/ directory layout + the rule that its contents are committed before the shuttle deadline and never edited after (append-only corrections).

Added 2026-08-27, after the design review that froze the RTL, now at 20 sites.

9. [x] **Drive-variant input isolation** (src/drive_node.v) with four deliberately un-isolated control sites and a matched fixed pair in src/char_paths.v, so the cost of isolation is measured rather than asserted.
10. [x] **Fixed non-oscillating characterization paths** (src/char_paths.v) and a **time-to-digital converter** (src/tdc.v). The missing rung of the inference chain, and the right instrument for a single edge.
11. [x] **Measurement protocol** (docs/MEASUREMENT_PROTOCOL.md) — the four stages, which instrument answers which question, and what the supply sweep can actually be.
12. [x] **Claim language corrected** (docs/PRIOR_ART.md, "Licensed and unlicensed language") — the withdrawn wordings recorded, and the one sentence licensed for the chip as a whole.
13. [ ] **CI build at 24 sites.** Free, and nothing else about the size should be decided before it lands. Then run tools/check_placement.py on the DEF and write the achieved separation into docs/AREA_GATE.md.
14. [ ] **WP5 pre-registration.** predictions/README.md now lists what has to be predicted; the depth-series slope is the one that makes the TDC falsifiable.

Standing rules for this repo
- American English. Full absolute paths when telling Andrew where things are.
- Public by intention: everything here is written as if already published (TT requires open source at submission anyway). Nothing mambik-proprietary (no D-002 structures) ever enters this repo.
- Heavy compute (P&R runs, SPICE sweeps) off the Mac or inside the docker limits (nice 19, --cpus 2, one container).
