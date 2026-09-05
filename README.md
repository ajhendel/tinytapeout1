# Evolvable electrical-realization fabric

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22261255.svg)](https://doi.org/10.5281/zenodo.22261255)

> **Status** — Archived pre-silicon ASIC design, with recorded simulation and
> physical-design checks. It was not submitted for fabrication. There are no
> manufactured-silicon measurements, and no active development or submission plan.

This repository contains a SKY130 design developed for Tiny Tapeout. Its
20-site configurable fabric selects among prefabricated standard-cell drive
variants, loads, routes, and inserted faults. The design also includes reference
paths, ring oscillators, and a time-to-digital converter intended for measuring
the fabric if manufactured.

The proposed experiment was to compare model predictions with measurements
while searching configurations on a physical die. That experiment was not
performed. The archive preserves the design, host software, simulation work,
physical-design evidence, and proposed measurement protocols. It establishes
neither measured silicon behavior nor a performance advantage over other systems.

## Recorded engineering results

The README's 2026-08-28 build summary recorded 20 sites on 6x2 tiles,
63,627 µm² of standard cells, 28.2 percent utilization, zero reported DRC and
antenna violations, clean LVS, setup slack +5.60 ns, and hold slack +0.108 ns.
It also recorded passing precheck and gate-level tests, 21 cocotb tests, and
66 harness tests, plus structural-netlist, constraint, and TDC checks.

These are historical results from the documented tool flow, not measurements
from fabricated hardware. Build-specific records can differ; consult the
commit and build identities in [HANDOFF.md](HANDOFF.md) and
[SUBMIT/STATE.md](SUBMIT/STATE.md) when using a particular result. The September
2026 documentation cleanup did not rerun or independently audit those checks.

## Reuse and documentation

- [src/](src/) contains the RTL and standard-cell instantiations.
- [harness/README.md](harness/README.md) describes the host software and protocol.
- [docs/info.md](docs/info.md) describes the design and interface.
- [docs/AREA_GATE.md](docs/AREA_GATE.md) records the physical-design iterations
  and the decision to use 20 sites.
- [docs/CONSTANTS.md](docs/CONSTANTS.md) records constants derived from the RTL.
- [docs/PRIOR_ART.md](docs/PRIOR_ART.md) records the prior-art investigation and
  claim limitations; it is not a certification of novelty.
- [docs/MEASUREMENT_PROTOCOL.md](docs/MEASUREMENT_PROTOCOL.md) and
  [docs/EXPERIMENT_MATRIX.md](docs/EXPERIMENT_MATRIX.md) preserve proposed silicon
  experiments, which were not performed.

[PLAN.md](PLAN.md), [TODO.md](TODO.md), [HANDOFF.md](HANDOFF.md), and
[SUBMIT/](SUBMIT/) preserve development and submission history. Their tasks,
deadlines, future-tense statements, and proposed purchases are historical,
not current instructions. The same applies to shuttle information in
[docs/TT_LOGISTICS.md](docs/TT_LOGISTICS.md) and proposals in
[docs/FUNCTIONS.md](docs/FUNCTIONS.md). The latter includes ideas explicitly
excluded from this design, including a coupled-oscillator optimizer.
The [predictions/](predictions/) files remain archived predictions without a
silicon comparison.

Reuse is welcome under [Apache-2.0](LICENSE), without an ongoing support
commitment. Physical reproduction requires the documented external EDA tools
and PDK. Historical successful flow checks do not guarantee a new fabrication
submission will pass a different flow or shuttle's requirements.

## Citation

To cite this exact release:

> Hendel, A. (2026). *Evolvable electrical-realization fabric* (Version
> v0.1.0) [Computer software]. Zenodo.
> https://doi.org/10.5281/zenodo.22261255

The DOI for all versions is
[10.5281/zenodo.22261254](https://doi.org/10.5281/zenodo.22261254).

The DOI identifies the unchanged v0.1.0 archive. Scope clarifications on the
main branch were added afterward; the archived tag was not moved. Author
identifier — [Andrew Hendel, ORCID 0009-0000-9877-3623](https://orcid.org/0009-0000-9877-3623).
