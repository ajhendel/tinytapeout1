# THROUGHPUT — is silicon-in-loop search feasible in wall-clock terms?

The question nobody computed during design review. Answer: yes, comfortably, PROVIDED the fitness loop lives in RP2040 firmware, not on the host. Numbers below are estimates to confirm in phase 1 on the FPGA pilot.

## Genome size
- 64 sites × ~12 config bits (3 function + 2 drive + 2 load + 3 sabotage + 2 route) ≈ 768 bits
- physics patch: 16 oscillators × ~6 coupling/config bits ≈ 96 bits
- control/observation select ≈ 100 bits
- **Total ≈ ~1,000 bits per configuration**

## Per-trial time budget (RP2040-managed)
- Scan-in at 1–10 MHz SPI-style: 0.1–1 ms
- CRC readback: 0.1–1 ms
- Settle + measure window (counters/TDC accumulate on-chip): 1–10 ms
- Firmware bookkeeping: ~1 ms
- **≈ 3–15 ms per trial → 60–300 trials/second**

## Search budget
- GA at population 50 × 2,000 generations = 100k evaluations → **6–30 minutes per run**
- 100 independent runs (statistics) → 10–50 hours → days, fine
- Even 10^6-evaluation searches complete overnight

## The trap to avoid
If every trial requires a host↔RP2040 USB round trip per input vector, add ~1–2 ms × vectors and throughput collapses ~10–100×. Therefore: stimulus generation, scoring, and GA inner loop in firmware; host handles logging, checkpointing, and outer-loop strategy. Validate this split in the FPGA pilot before RTL is frozen, because it constrains what the on-chip counters/TDC must expose.

## Measurement noise floor (to measure in phase 4, budgeted here)
- Repeat identical configuration N=1,000: report trial-to-trial σ of each fitness component
- Fitness differences smaller than 3σ are not resolvable; mutation operators should be sized so expected fitness steps exceed that
- Temperature drift during a run: log the on-chip RO monitors as covariates every trial (the M4-drift lesson: alternate arms within one thermal window or the comparison is fiction)

## Area sanity (to be replaced by trial P&R numbers)
- TT 1×1 tile ≈ 160×100 µm ≈ ~1,000 sky130 HD cells
- Site estimate: 12 config DFFs + muxes + 4 function cells + variants + load switches ≈ 40–80 cells → 64 sites ≈ 2,500–5,000 cells ≈ 3–5 tiles
- Infrastructure (scan, TDC ~64 taps + sampling FFs, counters, safety) ≈ 500–1,000 cells ≈ 1 tile
- Calibration strip ≈ 0.5–1 tile
- **Total ≈ 5–7 tiles.** If trial P&R says worse, cut sites to 48 or 32 before cutting the calibration strip.
