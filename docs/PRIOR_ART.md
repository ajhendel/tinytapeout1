# PRIOR ART — enumeration checklist

Rule (inherited from mambik discipline): novelty is verified by enumeration, never by a proxy. No claim ships until its row is CLOSED with the searches run, the papers read, and the residual claim written. "First X" is banned while the row is OPEN.

Status legend: OPEN = not yet enumerated. PARTIAL = known items listed, systematic sweep not done. CLOSED = swept, residual claim recorded.

| # | Topic | Known prior art (so far) | Status | Residual claim (draft) |
|---|-------|--------------------------|--------|------------------------|
| 1 | Intrinsic evolvable hardware | Thompson 1996 tone discriminator (FPGA); Layzell's evolvable motherboard; JPL Stoica FPTA-1/2 custom evolvable ASICs incl. extreme-temperature recovery; field dormant ~2005+; Bitstream Evolution open-source FPGA toolkit (2025?); active iCEstick tone-discriminator replication (evolvablehardware.github.io) | PARTIAL | Not "first intrinsic evolution on ASIC". Candidate residual: first controlled comparison against SAT-exact/Liberty baselines on an open PDK with pre-registered predictions |
| 2 | Evolving electrical realization (drive strength, loading) below the netlist | Unknown; approximate-computing literature sizes cells but via synthesis, not silicon-in-loop | OPEN | Possibly the strongest genuinely-open row |
| 3 | Oscillator Ising machines | Wang & Roychowdhury OIM; Toshiba/NTT CIM (optical); many CMOS coupled-oscillator papers 2019–2026; FPGA digital annealers | PARTIAL | Not the concept. Candidate residual: open-silicon OIM with search-configurable coupling, reproducible for ~500€ |
| 4 | p-bits / probabilistic computing | Camsari & Datta p-bits; MTJ-based demos incl. factorization; CMOS p-bit papers | PARTIAL | Not the concept. Candidate residual: open-PDK all-standard-cell p-bit patch + published noise characterization |
| 5 | Analog SAT / continuous-time solvers | Ercsey-Ravasz & Toroczkai dynamics; CMOS AC-SAT implementations | PARTIAL | Check what silicon exists; possibly open-silicon first |
| 6 | Race logic / temporal computing | Madhavan et al.; superconducting race logic | PARTIAL | Concept taken; only designed-delay silicon angle |
| 7 | FPGA coupling side channels | Ramesh et al. long-wire crosstalk; Giechaskiel et al.; shared-supply attacks | PARTIAL | Existence is settled ON FPGA. Residual: designed-geometry channel with shielded controls + extraction-predicted quantitative test |
| 8 | sky130 silicon-vs-model characterization | Documented Liberty issues in skywater-pdk repo; suspected academic/TT characterization chips (Zero-to-ASIC, TinyTapeout RO/PUF projects, e.g. tt_um_ro_puf on ttgf26b) | OPEN | Must sweep TT project index + FOSSi/ORConf talks before claiming anything about block A |
| 9 | Mutation testing on physical silicon / sabotage muxes | Fault-injection test chips (reliability community); scan-based fault insertion; DFT literature | OPEN | Candidate residual: mutation-coverage transfer sim→silicon at the timing edge |
| 10 | PUF/TRNG evolution | Large FPGA PUF literature; evolved PUFs exist? | OPEN | Secondary topic, enumerate only if used |
| 11 | Approximate computing / voltage overscaling with graceful failure | Significance-driven design; Razor; VOS arithmetic | PARTIAL | Concept taken; silicon-in-loop search angle only |
| 12 | Physical reservoir computing in silicon | Large field (memristive, photonic, mechanical); CMOS transient reservoirs? | OPEN | Tapeout-two topic |

## Sweep protocol per row
1. Google Scholar + Semantic Scholar keyword sweeps (list queries used in this file).
2. TinyTapeout project index sweep (all shuttles) for on-shuttle precedents.
3. FOSSi Foundation / ORConf / Latch-Up talk archives.
4. Cite the closest 3 works in the row even when CLOSED-favorable.
5. Write the residual claim in one sentence; that sentence is the only form that may appear in a paper.
