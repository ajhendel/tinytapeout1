# FUNCTIONS — what this fabric can compute or solve, and why anyone would care

**NONE OF TIER A IS ON TAPEOUT ONE. READ THIS BEFORE QUOTING ANYTHING BELOW.**

This file is the program's map of what an evolvable electrical-realization fabric could be aimed at. It is not a description of the chip being submitted. Tapeout one carries 20 serial configurable sites and the instruments needed to measure them, and no analog patch: no coupled-oscillator optimizer, no p-bit array, no analog constraint relaxation. Two separate things put them off it. The area went to the instruments instead, which is recorded in docs/AREA_GATE.md, and the coupled-oscillator optimization framing was withdrawn on prior art, which is recorded in docs/PRIOR_ART.md row 3. The single feedback edge this chip does have is a feedback edge. It is not a small coupled-oscillator optimizer and must not be written about as one: there is no controllable coupling, no phase readout, no locking guarantee and no independent enable per oscillator.

What tapeout one is actually for is in docs/EXPERIMENT_MATRIX.md, which is the committed list of studies, and it is a measurement program rather than any of the tiers below.

Scale honesty next. At the sizes this program can reach, everything below is toy-instance scale. The value is scientific (does the physics actually compute), methodological (open, reproducible, pre-registered), and platform (the same fabric runs new experiments for years). Nothing here competes with a GPU on throughput. Applications listed are what the *class* of machine is for, demonstrated at small scale.

## Tier A — physics-as-computer. NOT ON TAPEOUT ONE; see the banner above.

### 1. Coupled-oscillator optimization
The field calls these Ising machines. This project does not claim one, at any scale, on any tapeout so far; docs/PRIOR_ART.md row 3 is closed against a large existing literature and against WobblyBits on the previous sky shuttle.
Ring oscillators with configurable coupling strengths settle into minimum-energy phase patterns. Map a graph's edges onto couplings; the settled phases read out a MAX-CUT of the graph. The annealing is performed by physics, not simulated.
- Functions: MAX-CUT, graph partitioning, small QUBO instances (many NP-hard problems reduce to QUBO).
- Applications of the class: scheduling, placement/partitioning in EDA itself, portfolio selection, interference-aware channel assignment. This is an active field with a large prior literature, enumerated in docs/PRIOR_ART.md row 3, and we have no claim in it.
- FPGA status: digital emulation only (that is just a slow annealer with PRNGs). Real phase dynamics need real analog coupling strength.

### 2. Probabilistic bits (p-bits) and sampling
A deliberately marginal bistable element with tunable bias is a hardware random variable driven by true thermal noise. Networks of p-bits do Gibbs/Boltzmann sampling and invertible logic (run a logic circuit backwards, e.g. factor a small integer by clamping the output).
- Functions: sampling from programmable distributions, small satisfiability/factoring demos via invertible logic, stochastic simulated annealing.
- Applications of the class: Bayesian inference primitives, energy-based generative models, Monte Carlo acceleration, hardware security (true randomness).
- FPGA status: emulated with PRNGs; the physical object (true-noise bistable) does not exist there.

### 3. Analog constraint relaxation
Continuous-time dynamical systems whose trajectories flow toward satisfying assignments of Boolean formulas (the analog SAT literature). A small network of integrating nodes wired to a formula relaxes to a solution; physical noise helps escape traps.
- Functions: tiny SAT/CSP instances.
- Applications of the class: verification kernels, constraint solving; scientifically, the interesting question is whether real noise beats simulated noise on escape statistics.
- FPGA status: no continuous trajectories exist on an FPGA.

### 4. Temporal computation
Race logic (first-arrival encodes the answer), pulse-width and frequency classification, arrival-order discrimination, analog-time integration (the RC node as an ODE integrator; the continuous-time SSM connection).
- Functions: shortest-path wavefronts on small DAGs, tone/pulse discrimination without a clock or counter, interval measurement, leaky integration.
- Applications of the class: sensor front-ends (time-of-flight, particle/photon timing), spike-based neuromorphic pipelines, RF envelope detection, event cameras.
- FPGA status: race logic is FPGA-doable (prior art, Madhavan et al.); the beyond-FPGA part is designed delays, analog-time integration, and sub-gate-delay discrimination via our own TDC.

### 5. Entropy and identity
Free-running feedback configurations scored on output entropy (TRNG), or on inter-die uniqueness + intra-die stability (PUF).
- Functions: random bitstreams, per-chip fingerprints.
- Applications of the class: key generation, device authentication, anti-counterfeiting.
- FPGA status: heavily explored on FPGA; ours is only interesting through designed entropy structures and cross-die geometry control. Secondary, not flagship.

### 6. Physical reservoir computing
The fabric's transient dynamics (with feedback edges enabled) as a fixed random dynamical system; only a linear readout is trained.
- Functions: tiny time-series classification (waveform identity, frequency bands).
- Applications of the class: ultra-low-power always-on sensing.
- FPGA status: doable digitally; richer and stranger with marginal physical dynamics, so this is a tapeout-two candidate once tier-3 cells exist.

## Tier B — below-the-abstraction search (the second class)

### 7. Electrical-realization evolution
Hold a truth table fixed and evolve the physical realization of it. **Corrected 2026-08-27: the payload has to be a TWO-input, one-output function, or a serial composition of them.** The fabric is a single column with two Boolean inputs, one output and no per-site state, so a full adder, which needs three inputs and two outputs, cannot be expressed on this chip and was a wrong example in an earlier draft. What fits: any two-input gate, long compositions of them, and delay chains whose truth table is the identity. Three-input payloads are a tapeout-two requirement. Evolve drive strengths, loads, and routes against measured delay and marginal-voltage correctness. Compare with open-PDK model predictions committed before tapeout.
- Applications: this is science about the abstraction gap and about the open PDK's models; the practical beneficiary is the open-silicon toolchain community (better-calibrated models, documented failure modes).

### 8. Fault-tolerance at the physical level
Circuits that keep computing under every single-SITE OUTPUT fault, measured at speed and at voltage corners, not just logically.
- **Named accurately 2026-08-27.** The sabotage field alters what leaves a site: stuck at zero, stuck at one, bypass A, bypass B, invert. It does not disable individual gates inside a site, and it cannot: the function bank is always active and is not individually sabotageable. So the chip supports exhaustive single-site output fault injection, and it does NOT support deleting an arbitrary gate from the circuit. The mechanism is still the right one for the fault-tolerance question; the granularity has to be stated every time it is used.
- Applications of the class: radiation-tolerant and safety-critical design insight; whether logical redundancy is free at the operating edge.

### 9. Graceful degradation under overclock and reduced supply
Arithmetic cells whose timing failures are numerically benign (lose LSBs first, stay monotonic).
- Applications of the class: approximate computing, energy-proportional arithmetic, timing-speculation design.
- **Corrected 2026-08-27, and the correction is a real limit on tapeout one.** Tiny Tapeout's power rails are shared infrastructure and a project cannot run at a different core voltage from the rest of the chip. There is no independent fabric supply, so "drop the supply until this configuration fails" is not an experiment this chip can run. What it can run is a whole-chip supply sweep on the demo board, which takes the scan chain, the safety controller and the counters down with the fabric, and which is usable only because those blocks report their own health. The protocol is in docs/MEASUREMENT_PROTOCOL.md. A per-block supply is now a tapeout-two requirement.
- Overclocking has no such limit. The clock is ours and the fabric's delay is not in a clocked path at all, so the overclock half of this function is unaffected.

## What the physics patch cannot do
No large instances (node count), no claims of beating classical solvers, no cryptographically serious TRNG certification on tapeout one, no energy-per-solution claims (instrumentation limit). Every published number states instance size beside it.
