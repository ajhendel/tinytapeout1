# THROUGHPUT — is silicon-in-loop search feasible in wall-clock terms?

The question nobody computed during design review. Answer: yes, comfortably,
PROVIDED the fitness loop lives in RP2040 firmware, not on the host. Numbers
below are estimates to confirm in phase 1 on the FPGA pilot.

## Read this before quoting any number from this file

Nothing here has been measured on hardware. The 60 to 300 trials per second is
an arithmetic budget, and it is the budget for the SEARCH stage only. Two things
follow and both were got wrong in conversation before they were written down.

**A throughput figure is not a measurement figure.** docs/MEASUREMENT_PROTOCOL.md
splits the work into four stages, and only the first of them runs at this rate.
Stage 1 searches fast at one operating point and publishes nothing. Stages 2, 3
and 4 re-evaluate finalists exhaustively, sweep the operating point, and sabotage
winners and controls, and they run orders of magnitude slower per configuration
because each configuration is measured many times with the noise floor
established. Quoting the search rate as though it were the rate at which results
are produced overstates the throughput of the actual science by a large factor.

**The only rate measured so far is a simulation rate.** The harness reaches about
121 configurations per second against the Verilog under iverilog, on this
machine, at 8 sites. That number bounds nothing about silicon: it does not
include the scan link, the settle time, the measurement window, or the repeats
that stage 2 requires. Do not put it in a sentence beside the word "chip".

The first honest closed-loop number will come from the FPGA pilot, measured on
the shipped 24-site design and reported here with the window length and repeat
count beside it. Until then this file states a budget.

## Genome size

Updated 2026-08-27 to the shipped frame. The old estimate is kept below the line.

- 20 sites x 12 config bits (3 function + 2 drive + 2 load + 3 sabotage + 2 route) = 288 bits
- global word 48 bits (feedback, calibration select, counter source, readout select, window and trip limits, TDC enable, TDC source and polarity, characterization path and drive select)
- CRC 8 bits
- **Total 296 bits per configuration**, against the ~1,000 the estimate assumed

Smaller than budgeted, and the reason is that the site count fell from 64 to 20
and the physics patch is not on tapeout one. The scan time per trial therefore
falls with it, which moves the per-trial budget below toward its fast end.

### The original estimate, superseded
- 64 sites × ~12 config bits ≈ 768 bits
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

## Reading the TDC costs four trials, not one

Thirty-two taps do not fit in an eight bit readout port, so one converter
measurement takes one measuring trial plus three read-only trials. That is only
sound because src/tdc.v transfers a capture into the readout register solely
when an arrival edge actually occurred, so a read-only trial cannot destroy the
result it is reading.

It matters for the budget in exactly one place: the TDC is a characterization
instrument, used for tens or hundreds of measurements, not inside the search
loop. Multiplying the search rate by four would be answering a question nobody
asked.

## Area, measured (WP2, 2026-08-26; re-gated WP4, 2026-08-27)

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

### Tiles

Settled 2026-08-26 by a completed LibreLane run. 8 sites on 2x2 tiles uses
25,263 um2 of standard cells at 34.8 percent utilization, DRC and LVS clean.
Projecting to 64 sites wants about 17 tiles, and the largest Tiny Tapeout tile
geometry is 8x2, which is 16. **64 sites does not fit.**

**Re-gated 2026-08-27, and the answer moved again.** The design review added the
fixed characterization paths, the TDC and four more calibration rings, which put
about 650 cells into the FIXED column, a little over two tiles of overhead that
no site count amortises. The marginal cost per site also rose from 69.75 to
73.75 because of the drive-variant input isolation gates. The shipped size is
**20 sites on 6x2**. Full working and the alternatives are in
docs/AREA_GATE.md.

---

## Area sanity, the ORIGINAL ESTIMATE, superseded above and kept for the record
- TT 1×1 tile ≈ 160×100 µm ≈ ~1,000 sky130 HD cells
- Site estimate: 12 config DFFs + muxes + 4 function cells + variants + load switches ≈ 40–80 cells → 64 sites ≈ 2,500–5,000 cells ≈ 3–5 tiles
- Infrastructure (scan, TDC ~64 taps + sampling FFs, counters, safety) ≈ 500–1,000 cells ≈ 1 tile
- Calibration strip ≈ 0.5–1 tile
- **Total ≈ 5–7 tiles.** If trial P&R says worse, cut sites to 48 or 32 before cutting the calibration strip.
