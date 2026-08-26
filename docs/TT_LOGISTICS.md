# TT_LOGISTICS — shuttle facts (checked 2026-08-26)

## Currently open shuttles
- **SKY26c** (sky130, ChipFoundry) — open now, countdown running on tinytapeout.com; exact deadline TBD via the submission portal
- **IHP26b** (IHP SG13G2 130nm) — open now, same
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
- https://tinytapeout.com/ (open shuttles)
- https://tinytapeout.com/specs/analog/ (analog pin pricing and 2-tile rule)
- https://tinytapeout.com/faq/
- https://app.tinytapeout.com/calculator (authoritative current pricing)
- https://github.com/TinyTapeout/ttsky-analog-template
