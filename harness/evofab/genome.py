"""Genome encoding, decoding, validation and the scan frame format.

This module is the single definition of the bit layout. The RTL in src/ and the
firmware both have to agree with it, and the tests in harness/tests check that
agreement against the actual Verilog rather than against a second copy of the
same assumption.

Layout, matching src/scan_config.v and src/fabric_site.v.

    frame = [ GLOBAL 16 ][ SITE 0 : 12 ] ... [ SITE N-1 : 12 ][ CRC 8 ]

shifted MSB first, so site 0 lands in the high bits of the site region. That
detail is easy to get backwards and doing so silently reverses the genome, which
is why it is asserted in the tests and not merely commented.
"""

from __future__ import annotations

import dataclasses
import hashlib
import random
from typing import Iterable, Sequence

GLOBAL_W = 16
SITE_W = 12
CRC_W = 8

# ---------------------------------------------------------------- site fields
S_FUNC, S_FUNC_W = 0, 3
S_DRIVE, S_DRIVE_W = 3, 2
S_LOAD, S_LOAD_W = 5, 2
S_SAB, S_SAB_W = 7, 3
S_ROUTE, S_ROUTE_W = 10, 2

# Function codes named by what appears at the SITE OUTPUT. The output stage
# inverts, so these are the inversions of the pre-stage functions.
FUNCTIONS = ["AND", "OR", "XNOR", "XOR", "NOT_A", "NOT_B", "NAND", "NOR"]

# Sabotage codes. 6 and 7 alias to NONE so an unprogrammed field is inert.
SABOTAGE = ["NONE", "STUCK0", "STUCK1", "BYPASS_A", "BYPASS_B", "INVERT",
            "NONE", "NONE"]

ROUTES = ["PREV", "PI", "FEEDBACK", "ONE"]

# -------------------------------------------------------------- global fields
G_FB_EN, G_FB_EN_W = 0, 1
G_CALIB_EN, G_CALIB_EN_W = 1, 1
G_CALIB_SEL, G_CALIB_SEL_W = 2, 2
G_CNT_SRC, G_CNT_SRC_W = 4, 1
G_READOUT_SEL, G_READOUT_SEL_W = 5, 3
G_WINDOW_EXP, G_WINDOW_EXP_W = 8, 4
G_TRANS_EXP, G_TRANS_EXP_W = 12, 4


def _field(value: int, width: int, name: str) -> int:
    if not 0 <= value < (1 << width):
        raise ValueError(f"{name}={value} does not fit in {width} bits")
    return value


@dataclasses.dataclass(frozen=True)
class Site:
    func: int = 0
    drive: int = 0
    load: int = 0
    sab: int = 0
    route: int = 0

    def encode(self) -> int:
        return (_field(self.func, S_FUNC_W, "func") << S_FUNC
                | _field(self.drive, S_DRIVE_W, "drive") << S_DRIVE
                | _field(self.load, S_LOAD_W, "load") << S_LOAD
                | _field(self.sab, S_SAB_W, "sab") << S_SAB
                | _field(self.route, S_ROUTE_W, "route") << S_ROUTE)

    @classmethod
    def decode(cls, word: int) -> "Site":
        m = lambda pos, w: (word >> pos) & ((1 << w) - 1)  # noqa: E731
        return cls(func=m(S_FUNC, S_FUNC_W), drive=m(S_DRIVE, S_DRIVE_W),
                   load=m(S_LOAD, S_LOAD_W), sab=m(S_SAB, S_SAB_W),
                   route=m(S_ROUTE, S_ROUTE_W))

    def describe(self) -> str:
        return (f"{FUNCTIONS[self.func]} x{[1, 2, 4, 8][self.drive]} "
                f"load{self.load} {SABOTAGE[self.sab]} src={ROUTES[self.route]}")


@dataclasses.dataclass(frozen=True)
class Globals:
    fb_en: int = 0
    calib_en: int = 0
    calib_sel: int = 0
    cnt_src: int = 0
    readout_sel: int = 0
    window_exp: int = 2
    trans_exp: int = 15

    def encode(self) -> int:
        return (_field(self.fb_en, G_FB_EN_W, "fb_en") << G_FB_EN
                | _field(self.calib_en, G_CALIB_EN_W, "calib_en") << G_CALIB_EN
                | _field(self.calib_sel, G_CALIB_SEL_W, "calib_sel") << G_CALIB_SEL
                | _field(self.cnt_src, G_CNT_SRC_W, "cnt_src") << G_CNT_SRC
                | _field(self.readout_sel, G_READOUT_SEL_W, "readout_sel") << G_READOUT_SEL
                | _field(self.window_exp, G_WINDOW_EXP_W, "window_exp") << G_WINDOW_EXP
                | _field(self.trans_exp, G_TRANS_EXP_W, "trans_exp") << G_TRANS_EXP)

    @classmethod
    def decode(cls, word: int) -> "Globals":
        m = lambda pos, w: (word >> pos) & ((1 << w) - 1)  # noqa: E731
        return cls(fb_en=m(G_FB_EN, G_FB_EN_W),
                   calib_en=m(G_CALIB_EN, G_CALIB_EN_W),
                   calib_sel=m(G_CALIB_SEL, G_CALIB_SEL_W),
                   cnt_src=m(G_CNT_SRC, G_CNT_SRC_W),
                   readout_sel=m(G_READOUT_SEL, G_READOUT_SEL_W),
                   window_exp=m(G_WINDOW_EXP, G_WINDOW_EXP_W),
                   trans_exp=m(G_TRANS_EXP, G_TRANS_EXP_W))


class UnsafeGenome(Exception):
    """Raised by validate() for a configuration that must not reach a device."""


@dataclasses.dataclass(frozen=True)
class Genome:
    globals: Globals
    sites: tuple[Site, ...]

    @property
    def n_sites(self) -> int:
        return len(self.sites)

    @property
    def payload_w(self) -> int:
        return GLOBAL_W + SITE_W * self.n_sites

    @property
    def chain_w(self) -> int:
        return self.payload_w + CRC_W

    # ------------------------------------------------------------------ bits
    def payload(self) -> int:
        word = self.globals.encode()
        for site in self.sites:
            word = (word << SITE_W) | site.encode()
        return word

    def frame(self) -> int:
        p = self.payload()
        return (p << CRC_W) | crc8(p, self.payload_w)

    def bits_msb_first(self) -> list[int]:
        f = self.frame()
        return [(f >> i) & 1 for i in range(self.chain_w - 1, -1, -1)]

    @classmethod
    def from_payload(cls, payload: int, n_sites: int) -> "Genome":
        sites = []
        for s in range(n_sites):
            shift = SITE_W * (n_sites - 1 - s)
            sites.append(Site.decode((payload >> shift) & ((1 << SITE_W) - 1)))
        g = Globals.decode((payload >> (SITE_W * n_sites)) & ((1 << GLOBAL_W) - 1))
        return cls(globals=g, sites=tuple(sites))

    # --------------------------------------------------------------- identity
    def config_hash(self) -> str:
        """Stable identity for a configuration, for the results database.

        Hash the payload with the site count, not the frame. The CRC is derived,
        so including it would add nothing, and hashing the frame would make the
        identity depend on a checksum choice we might later change.
        """
        raw = f"{self.n_sites}:{self.payload():x}".encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    # ------------------------------------------------------------- validation
    def validate(self) -> None:
        """Reject configurations that must never be loaded onto a device.

        This is the host-side genome validator that PLAN.md section 2 requires.
        It runs before every load, on every device, including simulation, so
        that a rule which only bites on hardware is still exercised constantly.

        It cannot be the only line of defence and is not intended to be. The
        hardware safety controller in src/scan_config.v is, because the fabric
        must be safe against a host that is buggy, malicious or absent.
        """
        for i, s in enumerate(self.sites):
            Site.decode(s.encode())  # field width check
            if s.route == ROUTES.index("FEEDBACK") and not self.globals.fb_en:
                raise UnsafeGenome(
                    f"site {i} routes from the feedback edge but fb_en is 0, so "
                    f"the site would read a node held inactive; this is not "
                    f"dangerous but it is always a bug in the encoder")

        if self.globals.fb_en:
            # A closed combinational loop is the one configuration that can
            # oscillate without bound. It is allowed, because it is the point,
            # but only with a bounded window and a trip limit that can actually
            # fire inside that window.
            if self.globals.window_exp > 10:
                raise UnsafeGenome(
                    f"fb_en with window_exp={self.globals.window_exp} asks for a "
                    f"free-running loop for {1 << (4 + self.globals.window_exp)} "
                    f"clocks; cap the window at 10 while the loop is closed")
            if self.globals.trans_exp >= 15:
                raise UnsafeGenome(
                    "fb_en with the transition limit at maximum disables the "
                    "only automatic stop for a runaway loop")

        if self.globals.calib_en and self.globals.cnt_src:
            raise UnsafeGenome(
                "calib_en with cnt_src=1 runs a calibration ring while the "
                "counter watches the fabric; the ring would be a supply "
                "disturbance during a fabric measurement and the trial would "
                "not be comparable to one taken without it")


# ------------------------------------------------------------------------ crc
def crc8(payload: int, width: int) -> int:
    """CRC-8, poly 0x07, init 0x00, MSB first. Mirrors src/scan_config.v.

    Catches the failure that actually matters here, a frame short or long by a
    bit, which would otherwise rotate the entire genome and produce a wrong but
    entirely plausible configuration.
    """
    crc = 0
    for i in range(width - 1, -1, -1):
        bit = (payload >> i) & 1
        top = (crc >> 7) & 1
        crc = ((crc << 1) & 0xFF) ^ (0x07 if (top ^ bit) else 0x00)
    return crc


# ------------------------------------------------------------------ operators
def random_genome(n_sites: int, rng: random.Random,
                  base_globals: Globals | None = None) -> Genome:
    g = base_globals or Globals()
    sites = tuple(
        Site(func=rng.randrange(8), drive=rng.randrange(4), load=rng.randrange(4),
             sab=0, route=rng.choice([0, 1, 3]))
        for _ in range(n_sites))
    return Genome(globals=g, sites=sites)


# Mutation operators are named and separable so that a study can report which
# operator produced a change. docs/THROUGHPUT.md requires that the expected
# fitness step of an operator exceed the measurement noise floor, so the noise
# floor study has to be able to attribute steps to operators.
def mutate_function(g: Genome, rng: random.Random) -> Genome:
    i = rng.randrange(g.n_sites)
    s = g.sites[i]
    return _replace_site(g, i, dataclasses.replace(s, func=rng.randrange(8)))


def mutate_drive(g: Genome, rng: random.Random) -> Genome:
    """Move one site's drive variant by one step.

    One step, not a random redraw. A redraw from x1 to x8 is a large electrical
    change and would make the operator's effect size uninformative about the
    gradient the search is climbing.
    """
    i = rng.randrange(g.n_sites)
    s = g.sites[i]
    step = rng.choice([-1, 1])
    return _replace_site(g, i,
                         dataclasses.replace(s, drive=max(0, min(3, s.drive + step))))


def mutate_load(g: Genome, rng: random.Random) -> Genome:
    i = rng.randrange(g.n_sites)
    s = g.sites[i]
    step = rng.choice([-1, 1])
    return _replace_site(g, i,
                         dataclasses.replace(s, load=max(0, min(3, s.load + step))))


def mutate_route(g: Genome, rng: random.Random) -> Genome:
    i = rng.randrange(g.n_sites)
    s = g.sites[i]
    choices = [0, 1, 3] if not g.globals.fb_en else [0, 1, 2, 3]
    return _replace_site(g, i, dataclasses.replace(s, route=rng.choice(choices)))


OPERATORS = {
    "function": mutate_function,
    "drive": mutate_drive,
    "load": mutate_load,
    "route": mutate_route,
}


def _replace_site(g: Genome, i: int, site: Site) -> Genome:
    sites = list(g.sites)
    sites[i] = site
    return Genome(globals=g.globals, sites=tuple(sites))


def crossover(a: Genome, b: Genome, rng: random.Random) -> Genome:
    if a.n_sites != b.n_sites:
        raise ValueError("crossover between genomes of different site counts")
    cut = rng.randrange(1, a.n_sites) if a.n_sites > 1 else 1
    return Genome(globals=a.globals, sites=a.sites[:cut] + b.sites[cut:])


def apply_sabotage(g: Genome, site: int, mode: int) -> Genome:
    """Return g with one site's sabotage field set. Used by mutation testing.

    Separate from the mutation operators on purpose. Sabotage is an experimental
    treatment applied to a finished configuration, not a move the search is
    allowed to make, because a search free to insert faults would learn to hide
    behind them.
    """
    return _replace_site(g, site, dataclasses.replace(g.sites[site], sab=mode))
