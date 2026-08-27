# tinytapeout1

An open-silicon experimental platform on Tiny Tapeout. One chip: a configurable fabric where the configuration selects things an FPGA bitstream cannot touch (which prefabricated drive variant of a standard cell drives a node, how much load hangs on it, whether a fault is inserted, where a signal comes from), and the instruments needed to make measurements of it mean anything (fixed reference paths, ring oscillators, and a time-to-digital converter on the die).

It is an instrument, not a demonstration. Nothing on it is claimed to be fast or efficient; the point is to find out how far the open sky130 models are from the silicon they describe, on circuits chosen by a search running against the physical die, with the predictions committed publicly before the chip exists.

The thesis in one line. An open-PDK ASIC lets a search process select electrical realizations beneath the FPGA programming abstraction, lets physical dynamics act as the computer instead of clocked Boolean logic, and lets every pre-silicon prediction be checked publicly against the manufactured die.

Start with [PLAN.md](PLAN.md). Everything in `docs/` supports it.

- [PLAN.md](PLAN.md) — the plan, architecture, phases, risks
- [docs/FUNCTIONS.md](docs/FUNCTIONS.md) — what the fabric can compute or solve, and applications
- [docs/PRIOR_ART.md](docs/PRIOR_ART.md) — enumeration checklist; no novelty claim is written until its row here is closed
- [docs/THROUGHPUT.md](docs/THROUGHPUT.md) — evolution feasibility math (genome size, trials per second)
- [docs/MEASUREMENT_PROTOCOL.md](docs/MEASUREMENT_PROTOCOL.md) — the inference chain, which instrument answers which question, and the four-stage experiment order
- [docs/EXPERIMENT_MATRIX.md](docs/EXPERIMENT_MATRIX.md) — the fixed list of studies, committed before fabrication, including the ones deliberately absent
- [docs/AREA_GATE.md](docs/AREA_GATE.md) — what the flow actually said, twice, and why the chip ships at 24 sites
- [docs/TT_LOGISTICS.md](docs/TT_LOGISTICS.md) — shuttle facts, pricing, deadlines, sources
- [TODO.md](TODO.md) — phase 0 checklist, in order

Status (2026-08-27). RTL frozen at 24 sites on 6x2 tiles and built: DRC 0, LVS clean, antenna 0, setup slack +7.18 ns, precheck and gate-level test pass. 14 cocotb tests and 44 harness tests pass; the structural netlist and constraint checks pass and were sabotage-tested. Two findings from the build are recorded rather than smoothed over, one of which withdraws a planned experiment. See the Status section of [HANDOFF.md](HANDOFF.md), which is the live record.
