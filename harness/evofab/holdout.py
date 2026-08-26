"""Holdout discipline.

PLAN.md section 2: dies, voltage and temperature points, input traces, and
fabric regions that were never used during evolution, reserved for
generalization tests.

The reason this is a module and not a convention is that holdout discipline
fails silently. Nothing goes wrong at the moment a search touches a reserved
resource. It goes wrong months later, when a generalization result turns out to
have been measured on something the search had already seen, and by then the
only evidence either way is whatever was written down at the time.

So the reservation is declared once, committed to the repository, and enforced
by a guard that the device sits behind. A search that touches a reserved
resource raises, immediately, with the reservation that forbade it.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Iterable, Sequence


class HoldoutViolation(Exception):
    """A search touched a resource reserved for generalization testing."""


@dataclasses.dataclass(frozen=True)
class Reservation:
    """What is held out, and why.

    `reason` is mandatory and is not decoration. A reservation without a stated
    purpose gets quietly relaxed the first time it is inconvenient.
    """
    dies: frozenset[str] = frozenset()
    supply_mv: frozenset[int] = frozenset()
    temperatures_c: frozenset[int] = frozenset()
    sites: frozenset[int] = frozenset()
    trace_ids: frozenset[str] = frozenset()
    reason: str = ""

    def __post_init__(self):
        if not self.reason:
            raise ValueError("a reservation must state why it exists")

    def to_json(self) -> str:
        return json.dumps({
            "dies": sorted(self.dies),
            "supply_mv": sorted(self.supply_mv),
            "temperatures_c": sorted(self.temperatures_c),
            "sites": sorted(self.sites),
            "trace_ids": sorted(self.trace_ids),
            "reason": self.reason,
        }, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> "Reservation":
        d = json.loads(raw)
        return cls(dies=frozenset(d.get("dies", [])),
                   supply_mv=frozenset(d.get("supply_mv", [])),
                   temperatures_c=frozenset(d.get("temperatures_c", [])),
                   sites=frozenset(d.get("sites", [])),
                   trace_ids=frozenset(d.get("trace_ids", [])),
                   reason=d["reason"])


class Holdout:
    """Enforces a Reservation during search, and releases it for evaluation.

    Release is explicit, one call, and it is recorded. There is no way to touch
    a held-out resource by accident, and every way of doing it on purpose leaves
    a trace in the object that the run record can serialise.
    """

    def __init__(self, reservation: Reservation):
        self.reservation = reservation
        self._released = False
        self._release_reason = ""

    # -------------------------------------------------------------- checking
    def check_die(self, die: str) -> None:
        if not self._released and die in self.reservation.dies:
            raise HoldoutViolation(
                f"die {die!r} is held out ({self.reservation.reason}); "
                f"call release() first if this really is the generalization test")

    def check_conditions(self, supply_mv: int | None = None,
                         temperature_c: int | None = None) -> None:
        if self._released:
            return
        if supply_mv is not None and supply_mv in self.reservation.supply_mv:
            raise HoldoutViolation(
                f"supply {supply_mv} mV is held out ({self.reservation.reason})")
        if (temperature_c is not None
                and temperature_c in self.reservation.temperatures_c):
            raise HoldoutViolation(
                f"{temperature_c} C is held out ({self.reservation.reason})")

    def check_genome(self, genome) -> None:
        """A genome must not configure a held-out site to do anything.

        Held-out sites are required to be inert, which for this fabric means the
        default site word. Anything else counts as the search having used the
        region, even if it never scored well there, because the search still saw
        the result.
        """
        if self._released:
            return
        from .genome import Site
        default = Site()
        for i in sorted(self.reservation.sites):
            if i < genome.n_sites and genome.sites[i] != default:
                raise HoldoutViolation(
                    f"site {i} is held out ({self.reservation.reason}) but the "
                    f"genome configures it as {genome.sites[i].describe()}")

    def check_trace(self, trace_id: str) -> None:
        if not self._released and trace_id in self.reservation.trace_ids:
            raise HoldoutViolation(
                f"trace {trace_id!r} is held out ({self.reservation.reason})")

    # ------------------------------------------------------------- releasing
    def release(self, reason: str) -> None:
        if not reason:
            raise ValueError("releasing a holdout requires a stated reason")
        self._released = True
        self._release_reason = reason

    @property
    def released(self) -> bool:
        return self._released

    def audit(self) -> dict:
        return {"reservation": json.loads(self.reservation.to_json()),
                "released": self._released,
                "release_reason": self._release_reason}


class GuardedDevice:
    """Wraps a Device so that no genome reaches it without passing the holdout.

    The guard is on the device rather than in the search loop on purpose. A
    check inside the search is a check that a second search, or a one-off script
    someone writes at midnight, will not have.
    """

    def __init__(self, device, holdout: Holdout):
        self._device = device
        self._holdout = holdout

    @property
    def device_id(self) -> str:
        return self._device.device_id

    @property
    def firmware_version(self) -> str:
        return self._device.firmware_version

    def evaluate(self, genome):
        self._holdout.check_genome(genome)
        self._holdout.check_die(self._device.device_id)
        return self._device.evaluate(genome)

    def evaluate_many(self, genomes: Sequence):
        for g in genomes:
            self._holdout.check_genome(g)
        self._holdout.check_die(self._device.device_id)
        return self._device.evaluate_many(genomes)

    def close(self) -> None:
        self._device.close()
