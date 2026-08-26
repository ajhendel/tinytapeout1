# BITSTREAM_EVOLUTION_EVAL — WP3 item 8

Evaluated 2026-08-26 against github.com/evolvablehardware/BitstreamEvolution at
its 2026-05-28 state. The published description is Loyd et al., "Bitstream
Evolution: an Open-Source FPGA Intrinsic Evolvable Hardware Toolkit", IEEE
Access 2025, DOI 10.1109/ACCESS.2025.3631393. It is cited in docs/PRIOR_ART.md
row 1 and it is the reason that row is CLOSED against a first-modern-intrinsic
claim.

The instruction for this item was to check it for reuse before building anything
it already provides. This is a verdict, not a review.

## What it is

Python, GPL-3.0, roughly 13 MB of repo. It evolves Lattice iCE40 bitstreams
directly, which IceStorm made possible, and it targets the replication of
Thompson's tone discriminator plus pulse-oscillation experiments.

Architecture, in its own terms.
- `Circuit/` with `IntrinsicCircuit`, `SimHardwareCircuit` and
  `FullySimCircuit`, so the same experiment can run on hardware, on a hardware
  simulator, or fully in software. That three-mode split is a good idea and we
  arrived at the same one independently (`SimDevice`, `IcarusDevice`,
  `SerialDevice`).
- `FitnessFunction` as a class with `get_measurements` and `calculate_fitness`
  separated, subclassed as `PulseCountFitnessFunction`,
  `ToneDiscriminatorFitnessFunction` and `VarMaxFitnessFunction`.
- `Microcontroller.py`, a serial link to an Arduino that does the physical
  measurement and reports over serial.
- `CircuitPopulation.py` for the GA, and an `.ini` configuration file that
  defines an entire experiment.

## Verdict

**Adapt two things. Do not adopt the core. Do not link against it.**

### Do not adopt the core, for three independent reasons

**1. The genome is not the same kind of object.** Theirs is an FPGA bitstream,
addressed by bit position in a reverse-engineered format. Ours is a 12-bit
per-site scan word with named fields and a CRC, defined in
harness/evofab/genome.py. Their `Circuit` abstraction is built around compiling
and flashing a bitstream; there is nothing in it that a scan-chain genome would
use.

**2. The throughput is two orders of magnitude below what we need, and that is
inherent rather than a defect.** `IntrinsicCircuit.__run` compiles the
bitstream, invokes the programmer, and then sleeps one second, per individual.
So the ceiling is about one evaluation per second. docs/THROUGHPUT.md budgets 60
to 300 trials per second and a 100,000 evaluation search in minutes; at their
rate the same search is over a day.

This is not a criticism of their design. Reflashing an FPGA costs about a
second, so bitstream evolution is a 1 Hz activity and their toolkit is honest
about it. Scan-chain evolution is a sub-millisecond activity. The gap is the
difference between the two substrates, and it is worth stating plainly because
it is one of the few concrete advantages our approach has that is not about
electrical realization at all.

**3. Fitness is computed on the host.** The Arduino measures and reports, the
host scores. For pulse counting that is defensible, because the counting happens
on the microcontroller. But it is the architecture docs/THROUGHPUT.md names as
the trap, and adopting it would put the trap inside our harness by default. Our
`Device` interface has no method that takes an input vector precisely so this
cannot happen by accident.

### Licence, which Andrew has to decide

BitstreamEvolution is **GPL-3.0**. This repository is Apache-2.0, inherited from
the Tiny Tapeout template. Deriving our harness from their code makes our
harness GPL-3.0.

That is not automatically bad. Everything here is public by intention and Tiny
Tapeout requires open source at submission anyway. But it is a decision with
consequences and it is not one to make by copying a file. Recommendation is to
keep the harness Apache-2.0 and treat BitstreamEvolution as a separate tool we
run, not a library we import. If we later want their tone discriminator as a
control arm, run their toolkit unmodified in its own checkout and compare
results, which is cleaner science as well as cleaner licensing.

### What to adapt

**Their hardware setup guide.** evolvablehardware.org/setup.html plus PiSetup.md
document a working iCE40 plus Arduino measurement rig. Following a rig that is
known to work is worth more than any code.

**Their experiment-as-config-file idea.** A single `.ini` that fixes the GA
parameters, the fitness function, the stopping conditions and the hardware means
an experiment is a committed artifact rather than a set of command line
arguments someone typed. That fits the pre-registration discipline in PLAN.md
exactly and we should copy the idea, in our own file format, in WP4.

**Their tone discriminator as a control arm, run unmodified.** PLAN.md already
wants an FPGA control arm. Running theirs, rather than our reimplementation of
theirs, makes the comparison mean something, because a difference then cannot be
our bug.

### What not to bother with

Their live plotting, their workspace formatter, and their multi-FPGA transfer
support. We have different observables and a different link.

## Consequence for the plan

None of PLAN.md changes. WP3 item 8 is closed with this verdict. WP3 item 1's
firmware and host split stays as designed, and this evaluation strengthens the
reason for it rather than weakening it.
