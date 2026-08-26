# TODO — phase 0, in order

Gate: nothing in phase 2 (RTL) starts until items 1–4 are done, because each can reshape the architecture.

1. [x] **Prior-art sweep** (done 2026-08-26) — work docs/PRIOR_ART.md rows 1, 2, 3, 8, 9 to CLOSED (the rows the tapeout-one papers depend on). Rows 4–7 to PARTIAL-with-queries-logged.
2. [ ] **Trial P&R** — one fabric site + one calibration macro through OpenLane/LibreLane against sky130. Real cells/site number replaces the estimate in docs/THROUGHPUT.md. Verify keep/dont_touch survives the TT flow and that a deliberate combinational loop passes. (Docker, light-compute limits on the Mac, or a cheap cloud box.)
3. [ ] **Deadline + price check** — log into app.tinytapeout.com calculator; record SKY26c deadline and exact tile pricing in docs/TT_LOGISTICS.md. Decide tile count ceiling and analog pins yes/no.
4. [ ] **Throughput validation plan** — write the FPGA pilot spec: which iCE40 board, scan protocol frame format, firmware/host split, results DB schema (config hash, chip id, temp covariates, trial counter — the reproducibility metadata list from design review).
5. [ ] **Order FPGA board** (~$50) + confirm bench inventory (scope? frequency counter?) for the TDC anchoring plan.
6. [ ] **Site design doc** — pin down the per-site config word (function/drive/load/sabotage/route bits), the feedback-edge topology (feed-forward columns + enumerated feedback edges), and the safety controller's limit registers.
7. [ ] **Physics patch design doc** — oscillator count, coupling ladder (parallel tristate drivers), phase readout method, MAX-CUT instance encoding, and the p-bit sampling mode.
8. [ ] **Pre-registration scaffold** — predictions/ directory layout + the rule that its contents are committed before the shuttle deadline and never edited after (append-only corrections).

Standing rules for this repo
- American English. Full absolute paths when telling Andrew where things are.
- Public by intention: everything here is written as if already published (TT requires open source at submission anyway). Nothing mambik-proprietary (no D-002 structures) ever enters this repo.
- Heavy compute (P&R runs, SPICE sweeps) off the Mac or inside the docker limits (nice 19, --cpus 2, one container).
