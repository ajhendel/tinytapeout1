# FUNCTIONS — what this fabric can compute or solve, and why anyone would care

Scale honesty first. At 8–64 sites everything below is toy-instance scale. The value is scientific (does the physics actually compute), methodological (open, reproducible, pre-registered), and platform (the same fabric runs new experiments for years). Nothing here competes with a GPU on throughput. Applications listed are what the *class* of machine is for, demonstrated at small scale.

## Tier A — physics-as-computer (the flagship class, beyond FPGA by construction)

### 1. Coupled-oscillator optimization (Ising machine)
Ring oscillators with configurable coupling strengths settle into minimum-energy phase patterns. Map a graph's edges onto couplings; the settled phases read out a MAX-CUT of the graph. The annealing is performed by physics, not simulated.
- Functions: MAX-CUT, graph partitioning, small QUBO instances (many NP-hard problems reduce to QUBO).
- Applications of the class: scheduling, placement/partitioning in EDA itself, portfolio selection, interference-aware channel assignment. Active research field (oscillator Ising machines); our angle is configurable coupling searched in-loop on open silicon.
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
Hold a truth table fixed (full adder, majority, popcount cell, the mojolearn rounding/sticky cell as a payload with personal resonance). Evolve drive strengths, loads, and routes against measured delay and marginal-voltage correctness. Compare with open-PDK model predictions committed before tapeout.
- Applications: this is science about the abstraction gap and about the open PDK's models; the practical beneficiary is the open-silicon toolchain community (better-calibrated models, documented failure modes).

### 8. Fault-tolerance at the physical level
Circuits that keep computing under every single-cell sabotage, measured at speed and at voltage corners, not just logically.
- Applications of the class: radiation-tolerant and safety-critical design insight; whether logical redundancy is free at the operating edge.

### 9. Graceful degradation under overclock/undervolt
Arithmetic cells whose timing failures are numerically benign (lose LSBs first, stay monotonic).
- Applications of the class: approximate computing, energy-proportional arithmetic, timing-speculation design.

## What the physics patch cannot do
No large instances (node count), no claims of beating classical solvers, no cryptographically serious TRNG certification on tapeout one, no energy-per-solution claims (instrumentation limit). Every published number states instance size beside it.
