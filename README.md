# tinytapeout1

An open-silicon experimental platform on Tiny Tapeout. One chip, mostly a configurable physical fabric where the configuration controls things an FPGA bitstream cannot touch (cell drive strength and variant, node loading, inserted faults, feedback paths, coupling), plus a small patch of physics-as-computer structures (coupled oscillators, probabilistic bits) and a thin calibration strip so measurements mean something.

The thesis in one line. An open-PDK ASIC lets a search process select electrical realizations beneath the FPGA programming abstraction, lets physical dynamics act as the computer instead of clocked Boolean logic, and lets every pre-silicon prediction be checked publicly against the manufactured die.

Start with [PLAN.md](PLAN.md). Everything in `docs/` supports it.

- [PLAN.md](PLAN.md) — the plan, architecture, phases, risks
- [docs/FUNCTIONS.md](docs/FUNCTIONS.md) — what the fabric can compute or solve, and applications
- [docs/PRIOR_ART.md](docs/PRIOR_ART.md) — enumeration checklist; no novelty claim is written until its row here is closed
- [docs/THROUGHPUT.md](docs/THROUGHPUT.md) — evolution feasibility math (genome size, trials per second)
- [docs/TT_LOGISTICS.md](docs/TT_LOGISTICS.md) — shuttle facts, pricing, deadlines, sources
- [TODO.md](TODO.md) — phase 0 checklist, in order

Status (2026-08-26). Phase 0. Repo created, plan written, no RTL yet. The three gating unknowns are the prior-art enumeration, a trial place-and-route for real area numbers, and confirming the target shuttle deadline.
