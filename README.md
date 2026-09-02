# tinytapeout1

> **Status:** Complete and verified pre-silicon design, published as a research
> artifact. It was not submitted for fabrication and is not actively maintained.
> The physical-design and simulation results below have not been validated on
> manufactured silicon.

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
- [docs/AREA_GATE.md](docs/AREA_GATE.md) — what the flow actually said, at every size, and why the chip ships at 20 sites
- [docs/CONSTANTS.md](docs/CONSTANTS.md) — the numbers, generated from the RTL; CI fails if they drift
- [docs/TT_LOGISTICS.md](docs/TT_LOGISTICS.md) — shuttle facts, pricing, deadlines, sources
- [TODO.md](TODO.md) — phase 0 checklist, in order

Status (2026-08-28). RTL frozen at 20 sites on 6x2 tiles and built: 63,627 um2 of standard cells, 28.2 percent utilization, DRC 0, LVS clean, antenna 0, setup slack +5.60 ns, hold slack +0.108 ns, precheck and gate-level test passing. 21 cocotb tests and 66 harness tests pass; the structural netlist, constraint, TDC range, TDC race and stop-selector checks pass and were each sabotage-tested. Three rounds of review each found a real defect and each was found by reading what the build itself reported rather than by a test failing. See the Status section of [HANDOFF.md](HANDOFF.md), which is the live record, and [docs/EXPERIMENT_MATRIX.md](docs/EXPERIMENT_MATRIX.md) for what the chip is for.
