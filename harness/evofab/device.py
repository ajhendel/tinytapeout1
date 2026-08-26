"""Device interface and implementations.

The interface is deliberately narrow. One configuration goes in, one Trial comes
out. There is no method that takes an input vector, because the moment such a
method exists the host is in the inner loop and docs/THROUGHPUT.md's 10x to 100x
collapse is one refactor away.

Every device is responsible for doing stimulus generation, scoring and
accumulation on its own side of whatever link it has. A device that cannot do
that is not a device this harness can drive at speed, and should say so by
raising rather than by being slow.
"""

from __future__ import annotations

import abc
import dataclasses
import time
from typing import Sequence

from .genome import Genome, Site, FUNCTIONS, SABOTAGE, ROUTES


@dataclasses.dataclass(frozen=True)
class Trial:
    """One evaluation. Everything needed to reproduce or re-analyse it later.

    The covariate fields are not optional bookkeeping. The standing lesson from
    a machine that drifted 1.7x in twenty minutes is that a comparison whose
    arms were taken in different thermal windows is fiction, so the covariates
    that let a later analysis detect that must be recorded per trial, not per
    run.
    """
    config_hash: str
    fitness: float
    components: dict[str, float]
    device_id: str
    firmware_version: str
    trial_index: int
    wall_time_s: float
    temperature_proxy: float | None = None   # on-chip RO count, PVT covariate
    supply_mv: int | None = None
    tripped: bool = False
    crc_ok: bool = True
    notes: str = ""


class Device(abc.ABC):
    """A thing that can score a genome."""

    device_id: str = "unknown"
    firmware_version: str = "unknown"

    @abc.abstractmethod
    def evaluate(self, genome: Genome) -> Trial:
        """Load the genome, run one bounded trial, return the score."""

    def evaluate_many(self, genomes: Sequence[Genome]) -> list[Trial]:
        """Default is sequential. A real device should override this to keep
        the link busy, which is where the throughput actually lives."""
        return [self.evaluate(g) for g in genomes]

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# --------------------------------------------------------------------------
# Reference model
# --------------------------------------------------------------------------

def site_output(site: Site, a_prev: int, a_pi: int, a_fb: int, b: int) -> int:
    """Pure Python model of one fabric site, mirroring src/fabric_site.v.

    Written from the spec rather than transcribed from the RTL, so that the
    cocotb test that compares the two is comparing two derivations and not one
    derivation against a copy of itself.
    """
    a = [a_prev, a_pi, a_fb, 1][site.route]

    pre = [
        1 - (a & b),        # NAND2
        1 - (a | b),        # NOR2
        a ^ b,              # XOR2
        1 - (a ^ b),        # XNOR2
        a,                  # A
        b,                  # B
        a & b,              # AND2
        a | b,              # OR2
    ][site.func]

    mode = SABOTAGE[site.sab]
    if mode == "STUCK0":
        pre = 0
    elif mode == "STUCK1":
        pre = 1
    elif mode == "BYPASS_A":
        pre = a
    elif mode == "BYPASS_B":
        pre = b
    elif mode == "INVERT":
        pre = 1 - pre

    # The output stage inverts. This is why the FUNCTIONS names are the
    # inversions of the pre-stage function names.
    return 1 - pre


def column_output(genome: Genome, a_pi: int, b: int, fb: int = 0) -> int:
    node = a_pi
    for site in genome.sites:
        node = site_output(site, a_prev=node, a_pi=a_pi, a_fb=fb, b=b)
    return node


class SimDevice(Device):
    """Scores a genome against the Python model. No hardware, no timing.

    Useful for developing the search and the operators. Useless for anything
    electrical, which is the entire reason the chip exists, so nothing measured
    here may ever be reported as a fabric result. It exists to make the search
    itself debuggable.
    """

    device_id = "sim"
    firmware_version = "model-1"

    def __init__(self, target: str = "AND", n_sites: int = 8):
        self.target = target
        self.n_sites = n_sites
        self._n = 0

    def _truth(self, a: int, b: int) -> int:
        return {
            "AND": a & b, "OR": a | b, "XOR": a ^ b, "XNOR": 1 - (a ^ b),
            "NAND": 1 - (a & b), "NOR": 1 - (a | b),
        }[self.target]

    def evaluate(self, genome: Genome) -> Trial:
        genome.validate()
        t0 = time.perf_counter()
        correct = 0
        for a in (0, 1):
            for b in (0, 1):
                if column_output(genome, a, b) == self._truth(a, b):
                    correct += 1
        self._n += 1
        # A secondary term that rewards using fewer of the strong drive
        # variants, so the search has something electrical to trade against
        # correctness even in the model. On hardware this term is replaced by a
        # measured quantity; here it is a stand-in and is labelled as one.
        drive_cost = sum(s.drive for s in genome.sites) / (3 * genome.n_sites)
        return Trial(
            config_hash=genome.config_hash(),
            fitness=correct / 4.0 - 0.05 * drive_cost,
            components={"correct": correct / 4.0, "drive_cost_proxy": drive_cost},
            device_id=self.device_id,
            firmware_version=self.firmware_version,
            trial_index=self._n,
            wall_time_s=time.perf_counter() - t0,
            notes="model only, no electrical meaning",
        )


class IcarusDevice(Device):
    """Scores genomes against the real Verilog, in batches, through vvp.

    This is the device that matters before silicon. It exercises the actual scan
    frame format, the actual CRC, the actual site decode and the actual safety
    controller, so a disagreement between harness/evofab/genome.py and src/ shows
    up here rather than in a fabricated chip.

    Batching is not an optimization detail. One vvp invocation runs a whole
    generation, which is the same shape the firmware must have, and it means
    this device cannot accidentally be used in a way the real link could not
    sustain.
    """

    device_id = "icarus"

    def __init__(self, n_sites: int = 8, target: str = "AND",
                 build_dir: str = "build", repo_root: str | None = None):
        import os
        import subprocess

        self.n_sites = n_sites
        self.target = target
        self.root = repo_root or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.build_dir = os.path.join(self.root, build_dir)
        os.makedirs(self.build_dir, exist_ok=True)
        self.vvp = os.path.join(self.build_dir, f"runner_n{n_sites}.vvp")
        self._n = 0

        srcs = sorted(
            os.path.join(self.root, "src", f)
            for f in os.listdir(os.path.join(self.root, "src"))
            if f.endswith(".v"))
        cmd = ["iverilog", "-DSIM", f"-DN_SITES={n_sites}", "-g2012",
               "-o", self.vvp, *srcs,
               os.path.join(self.root, "sim", "trial_runner.v")]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"iverilog failed:\n{r.stderr}")
        self.firmware_version = f"iverilog-n{n_sites}"

    def _truth(self, a: int, b: int) -> int:
        return {
            "AND": a & b, "OR": a | b, "XOR": a ^ b, "XNOR": 1 - (a ^ b),
            "NAND": 1 - (a & b), "NOR": 1 - (a | b),
        }[self.target]

    def evaluate(self, genome: Genome) -> Trial:
        return self.evaluate_many([genome])[0]

    def evaluate_many(self, genomes: Sequence[Genome]) -> list[Trial]:
        import os
        import subprocess

        for g in genomes:
            g.validate()
            if g.n_sites != self.n_sites:
                raise ValueError(
                    f"device built for {self.n_sites} sites, genome has "
                    f"{g.n_sites}; rebuild rather than silently truncating")

        frames_path = os.path.join(self.build_dir, "frames.txt")
        out_path = os.path.join(self.build_dir, "results.txt")
        with open(frames_path, "w") as f:
            for g in genomes:
                f.write(f"{g.frame():x}\n")

        t0 = time.perf_counter()
        r = subprocess.run(
            ["vvp", self.vvp, f"+frames={frames_path}", f"+out={out_path}"],
            capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"vvp failed:\n{r.stdout}\n{r.stderr}")
        elapsed = time.perf_counter() - t0

        rows = [line.split() for line in open(out_path) if line.strip()]
        if len(rows) != len(genomes):
            raise RuntimeError(
                f"runner returned {len(rows)} results for {len(genomes)} "
                f"frames; the batch protocol is out of step")

        trials = []
        per = elapsed / max(1, len(genomes))
        expected = [self._truth(a, b) for a in (0, 1) for b in (0, 1)]
        for g, row in zip(genomes, rows):
            _, crc_ok, inert, tripped, *rest = [int(x) for x in row]
            got, freq = rest[:4], rest[4]
            correct = sum(1 for x, y in zip(got, expected) if x == y)
            self._n += 1
            trials.append(Trial(
                config_hash=g.config_hash(),
                fitness=correct / 4.0,
                components={"correct": correct / 4.0, "freq_byte": float(freq)},
                device_id=self.device_id,
                firmware_version=self.firmware_version,
                trial_index=self._n,
                wall_time_s=per,
                temperature_proxy=float(freq),
                tripped=bool(tripped),
                crc_ok=bool(crc_ok),
                notes="rtl simulation, timing has no electrical meaning"))
        return trials
