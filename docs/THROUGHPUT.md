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

## Area, measured (WP2, 2026-08-26)

The estimates below the line are what this section used to say. They are kept so
that the size of the error is visible rather than quietly overwritten.

### What was measured

`tools/area_sweep.sh` builds the design at 1, 2, 4, 8 and 16 sites and takes the
slope, because the number that matters is the MARGINAL cost of a site. Dividing
one build by its site count charges the fixed infrastructure to the sites and
makes the fabric look far more expensive than it is.

| quantity | measured |
|---|---|
| marginal hand-instantiated cells per site | 34 |
| marginal synthesized cells per site | 65.5 |
| marginal total per site | 99.5 |
| fixed hand-instantiated cells | 156 (the calibration strip) |
| fixed synthesized cells | 676 (scan, CRC, safety, counters) |
| projected total at 32 sites | 4,016 |
| projected total at 48 sites | 5,608 |
| projected total at 64 sites | 7,200 |

### Where the old estimate went wrong

The estimate was 40 to 80 cells per site. The measurement is 99.5, and the miss
is entirely in the synthesized half, which the estimate put at "12 config DFFs".

- The config path is double buffered. A shadow chain bit and a live register bit
  per config bit is 24 flops per site, not 12. The second copy is what makes a
  partially shifted frame unable to reach the fabric, so it is not removable
  without giving up the property that a corrupt or truncated frame is harmless.
- The CRC is a combinational tree over the whole payload, so it grows with the
  site count and lands in the marginal column rather than the fixed one, at
  roughly 12 cells per site.

Both are real costs of the safety story, and both were invisible to an estimate
that only counted the fabric.

### The one obvious saving, if area runs short

Computing the CRC serially as the frame shifts in, instead of combinationally
over the assembled payload, removes about 12 cells per site, so about 770 cells
at 64 sites. It costs nothing in safety because the check still gates the load.
Do this before cutting sites, and cut sites before touching the calibration
strip.

### Still outstanding

Cells are not area. Tiles come from the LibreLane run in Tiny Tapeout's CI. That
number, and the utilization it implies, goes in docs/AREA_GATE.md.

---

## Area sanity, the ORIGINAL ESTIMATE, superseded above and kept for the record
- TT 1×1 tile ≈ 160×100 µm ≈ ~1,000 sky130 HD cells
- Site estimate: 12 config DFFs + muxes + 4 function cells + variants + load switches ≈ 40–80 cells → 64 sites ≈ 2,500–5,000 cells ≈ 3–5 tiles
- Infrastructure (scan, TDC ~64 taps + sampling FFs, counters, safety) ≈ 500–1,000 cells ≈ 1 tile
- Calibration strip ≈ 0.5–1 tile
- **Total ≈ 5–7 tiles.** If trial P&R says worse, cut sites to 48 or 32 before cutting the calibration strip.
