# TT_LOGISTICS — shuttle facts (checked 2026-08-26, deadline resolved 2026-08-28)

## Currently open shuttles

**SKY26c closes 2026-09-07 at 20:00 UTC.** Resolved 2026-08-28 and no longer TBD.

That is **ten days from 2026-08-28**, and it is the single fact this whole
schedule hangs on. Every gate in docs/EXPERIMENT_MATRIX.md, the final build, and
the pre-registration in predictions/ have to be settled with room to spare
before it, because the pre-registration is worthless if it is committed in the
same hour as the submission.

- **SKY26c** (sky130, ChipFoundry) — closes **2026-09-07T20:00:00Z**, 80 subsidized PCBs
- **IHP26b** (IHP SG13G2 130nm) — closes 2026-09-21T20:00:00Z, 100 subsidized PCBs

### How that was found, because it is worth knowing for next time

The homepage countdown renders from JavaScript, so fetching the page gives a
placeholder reading "44 DAYS 44 HOURS 44 MINS 44 SECS" and tells you nothing.
The real value is in the markup that drives it:

    data-shuttle="ttsky26c" data-deadline="2026-09-07T20:00:00Z" data-pcbs="80"

So the deadline needs no portal login, contrary to what this file said for two
days. **The PRICE still does**: the calculator at app.tinytapeout.com is a
single-page app behind a login and the per-tile number is not in any public
page. That half stays Andrew's.
- 2026 shuttles so far: TTGF26a (Apr), TTSKY26c (May), TTGF26b (Jun), TTIHP26b (Jul); cadence is roughly every 1–2 months across PDKs

## Pricing (from tinytapeout.com; confirm in the calculator at app.tinytapeout.com/calculator before budgeting)
- ~70€ per tile; early-bird discounts exist, limited, individuals only
- Analog pins: 40€ each for the first 2, 100€ each beyond; analog projects must be 2 tiles high
- Example from their docs: 1×2 tiles + 2 analog pins = 220€
- Price covers shuttle inclusion only; ASIC + PCB + shipping are separate (subsidized PCBs mentioned for current shuttles); devkit purchase = demo board + breakout board

## PDK choice: sky130 vs IHP
- **sky130** — the open-model story is strongest here (skywater-pdk Liberty/SPICE fully public, documented issues to test against); most TT precedent; ChipFoundry operates the sky shuttles now
- **IHP SG13G2** — also open PDK, more modern models, SiGe options irrelevant to us
- **Decision: sky130** for tapeout one (model-validation chapter depends on the most-scrutinized open PDK; more community precedent for weird projects). Revisit for tapeout two if analog slots are scarcer on sky.

## Templates and flow
- Digital: tt Verilog template, OpenLane/LibreLane flow; hand-instantiated cells + keep/dont_touch for the fabric (ring-oscillator precedent exists on past shuttles, e.g. tt_um_ro_puf on ttgf26b)
- Analog/mixed: TinyTapeout/ttsky-analog-template (custom GDS)
- Demo board: RP2040-based, controlled via Tiny Tapeout Commander web app; our harness replaces/extends the firmware

## Lead time
- Submission → silicon in hand is many months (typically ~6–9 via shuttle aggregation). The FPGA control arm is scheduled into that window by design.

## Sources
- https://tinytapeout.com/ (open shuttles; the deadline is in the page's own `data-deadline` attribute, not in the rendered countdown)
- https://tinytapeout.com/specs/analog/ (analog pin pricing and 2-tile rule)
- https://tinytapeout.com/faq/
- https://app.tinytapeout.com/calculator (authoritative current pricing)
- https://github.com/TinyTapeout/ttsky-analog-template
