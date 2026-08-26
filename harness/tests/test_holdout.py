"""Holdout discipline tests.

Holdout discipline fails silently, so these tests exist to make it fail loudly.
Each one sabotages the discipline in a specific way and requires the guard to
notice.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from evofab.device import SimDevice
from evofab.genome import Genome, Globals, Site, random_genome
from evofab.holdout import (GuardedDevice, Holdout, HoldoutViolation,
                            Reservation)
from evofab.search import SearchConfig, evolve


def res(**kw):
    kw.setdefault("reason", "reserved for the cross-device generalization test")
    return Reservation(**kw)


def test_a_reservation_must_say_why():
    with pytest.raises(ValueError):
        Reservation(dies=frozenset({"die-07"}))


def test_reserved_die_is_refused():
    h = Holdout(res(dies=frozenset({"sim"})))
    dev = GuardedDevice(SimDevice("AND", 8), h)
    with pytest.raises(HoldoutViolation):
        dev.evaluate(random_genome(8, random.Random(0)))


def test_reserved_site_must_stay_inert():
    h = Holdout(res(sites=frozenset({3})))
    dev = GuardedDevice(SimDevice("AND", 8), h)
    sites = [Site() for _ in range(8)]
    dev.evaluate(Genome(globals=Globals(), sites=tuple(sites)))   # all default, fine

    sites[3] = Site(func=2, drive=1)
    with pytest.raises(HoldoutViolation) as e:
        dev.evaluate(Genome(globals=Globals(), sites=tuple(sites)))
    assert "site 3" in str(e.value)


def test_reserved_conditions_are_refused():
    h = Holdout(res(supply_mv=frozenset({1620}), temperatures_c=frozenset({85})))
    h.check_conditions(supply_mv=1800, temperature_c=25)
    with pytest.raises(HoldoutViolation):
        h.check_conditions(supply_mv=1620)
    with pytest.raises(HoldoutViolation):
        h.check_conditions(temperature_c=85)


def test_release_requires_a_reason_and_is_audited():
    h = Holdout(res(dies=frozenset({"sim"})))
    with pytest.raises(ValueError):
        h.release("")
    h.release("running the pre-registered generalization test")
    h.check_die("sim")
    a = h.audit()
    assert a["released"] and a["release_reason"]


def test_a_whole_search_cannot_touch_a_reserved_site():
    """The guard is on the device, so an entire GA run, including every mutation
    and crossover it invents, cannot reach a held-out site by accident.

    Sabotage form: reserve a site, run a real search, and require it to raise.
    Without the guard the search happily configures every site.
    """
    h = Holdout(res(sites=frozenset({5})))
    dev = GuardedDevice(SimDevice("XOR", 8), h)
    with pytest.raises(HoldoutViolation):
        evolve(dev, 8, SearchConfig(population=8, generations=5, seed=1))


def test_reservation_survives_a_json_roundtrip():
    r = res(dies=frozenset({"d1", "d2"}), supply_mv=frozenset({1620, 1980}),
            temperatures_c=frozenset({-40, 85}), sites=frozenset({0, 63}),
            trace_ids=frozenset({"trace-a"}))
    assert Reservation.from_json(r.to_json()) == r
