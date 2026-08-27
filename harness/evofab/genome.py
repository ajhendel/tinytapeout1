"""Genome encoding, decoding, validation and the scan frame format.

This module is the single definition of the bit layout. The RTL in src/ and the
firmware both have to agree with it, and the tests in harness/tests check that
agreement against the actual Verilog rather than against a second copy of the
same assumption.

Layout, matching src/scan_config.v and src/fabric_site.v.

    frame = [ GLOBAL 48 ][ SITE 0 : 12 ] ... [ SITE N-1 : 12 ][ CRC 8 ]

At the shipped 20 sites that is 296 bits.

shifted MSB first, so site 0 lands in the high bits of the site region. That
detail is easy to get backwards and doing so silently reverses the genome, which
is why it is asserted in the tests and not merely commented.
"""

from __future__ import annotations

import dataclasses
import hashlib
import random
from typing import Iterable, Sequence

GLOBAL_W = 48
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
# This layout is duplicated in src/project.v (all fields) and src/scan_config.v
# (window_exp and trans_exp only). Move a field here and you must move it there
# in the same commit; nothing would fail loudly if you did not, the harness
# would simply address the wrong bits.
G_FB_EN, G_FB_EN_W = 0, 1
G_CALIB_EN, G_CALIB_EN_W = 1, 1
G_CALIB_SEL, G_CALIB_SEL_W = 2, 3
G_CNT_SRC, G_CNT_SRC_W = 5, 2
G_READOUT_SEL, G_READOUT_SEL_W = 7, 5
G_WINDOW_EXP, G_WINDOW_EXP_W = 12, 4
G_TRANS_EXP, G_TRANS_EXP_W = 16, 4
G_TDC_EN, G_TDC_EN_W = 20, 1
G_TDC_SRC, G_TDC_SRC_W = 21, 1
G_TDC_POL, G_TDC_POL_W = 22, 1
G_CHAR_SEL, G_CHAR_SEL_W = 23, 5
G_CHAR_DRIVE, G_CHAR_DRIVE_W = 28, 2
G_TDC_TAP, G_TDC_TAP_W = 30, 5
G_TDC_FREERUN, G_TDC_FREERUN_W = 35, 1

# What the frequency counter watches.
CNT_SRC = {"calib": 0, "fabric": 1, "tdc_ring": 2}

# Readout selector codes, matching the case statement in src/project.v.
READOUT = {
    "freq0": 0, "freq1": 1, "freq2": 2,
    "trans0": 3, "trans1": 4, "trans2": 5,
    "status": 6, "n_sites": 7,
    "tdc0": 8, "tdc1": 9, "tdc2": 10, "tdc3": 11,
    "tdc_taps": 12, "twin_mask": 13, "char_count": 14, "alive": 15,
    # The coarse half of a TDC reading. 0xFF means SATURATED: discard the
    # measurement, never scale it. A wrapped count reads as a fast path.
    "tdc_wraps": 16,
    "tdc_tap_echo": 17, "char_sel_echo": 18, "global_w": 19,
}
TDC_WRAPS_SATURATED = 0xFF
TDC_TAPS = 32


def tdc_decode(taps: int, wraps: int, n_taps: int = TDC_TAPS) -> int:
    """Turn a raw TDC capture into a delay in units of one line stage.

    The delay line is a RING, so the tap register is not a thermometer code that
    grows monotonically. The ring parks with every tap high; the launch edge
    walks a 1 to 0 transition down it, then a 0 to 1 transition, alternating.
    So during traversal T the taps below the edge carry the NEW value and the
    ones above carry the old, and which is which flips with the parity of T.

    Population count alone is therefore the wrong decode, and it is wrong in a
    way that looks plausible: it DECREASES as the path gets longer on odd
    traversals. That is what the first run of the depth-series test reported,
    a perfectly ordered series running backwards.

    wraps counts full ring periods, which is two traversals, so it fixes T only
    to within one. The parity comes from the lowest tap, which is the first to
    change and therefore always carries the new value once the edge has moved
    at all.
    """
    full = (1 << n_taps) - 1
    if taps == full:
        # Nothing has moved yet: the arrival beat the first tap. Only reachable
        # for a path shorter than one buffer, which on silicon means something
        # is wrong, so it is not silently folded into the general case.
        return wraps * 2 * n_taps
    ones = bin(taps).count("1")
    if taps & 1:
        traversal = 2 * wraps + 1      # low taps are 1: an odd traversal
        pos = ones
    else:
        traversal = 2 * wraps          # low taps are 0: an even traversal
        pos = n_taps - ones
    return traversal * n_taps + pos


def tdc_bubbles(taps: int, n_taps: int = TDC_TAPS) -> int:
    """How many bit positions disagree with a clean boundary.

    Not an error measure. Bubbles are the map of which bins are wide and which
    are narrow, and that map IS the calibration; see docs/MEASUREMENT_PROTOCOL.md.
    This counts them so a run can report bin quality rather than assume it.
    """
    bits = [(taps >> i) & 1 for i in range(n_taps)]
    first = bits[0]
    # a clean pattern is a run of `first` followed by a run of its complement
    boundary = n_taps
    for i, b in enumerate(bits):
        if b != first:
            boundary = i
            break
    clean = [first] * boundary + [1 - first] * (n_taps - boundary)
    return sum(1 for a, b in zip(bits, clean) if a != b)

# The eight fixed calibration rings, by calib_sel code. See src/calib_macro.v.
# Rings 0, 6 and 7 are the SAME circuit; their spread is the within-die
# variation floor and their difference is placement and nothing else.
CALIB_RINGS = ["inv1", "inv2", "inv4", "inv1_loaded", "inv1_compact",
               "drive_node", "inv1_twin_a", "inv1_twin_b"]

# The sixteen fixed characterization paths, by char_sel code.
# See the table in src/char_paths.v.
CHAR_PATHS = [
    # Drive series: the DRIVER varies, its load does not. Shaped differently
    # from the load series on purpose; see src/char_paths.v.
    "drive_x1", "drive_x2", "drive_x4", "drive_x8",
    # Load series: the LOAD varies, the driver does not.
    "load_0", "load_1", "load_2", "load_4",
    "inv1_d2", "inv1_d4", "inv1_d8", "inv1_d16",
    "nand1_d8", "nand4_d8", "mux4_d4",
    "drive_isolated_d4", "drive_shared_d4",
    # The ladder mechanism in isolation. These two differ ONLY in whether the
    # load ladder's enables are tied high or low. Liberty predicts their
    # difference to be exactly zero because the format has one capacitance per
    # pin; see src/load_ladder.v.
    "ladder_off_d8", "ladder_on_d8",
    "inv1_d32",
]

# The depth series, in stage order. A straight line through these four gives the
# per-stage delay AND the fixed offset from the launch gate, the select tree and
# the TDC input. Everything else in CHAR_PATHS is quoted against that offset.
DEPTH_SERIES = [(2, "inv1_d2"), (4, "inv1_d4"), (8, "inv1_d8"),
                (16, "inv1_d16"), (24, "load_0"), (32, "inv1_d32")]

# The two series that answer the chip's headline questions, and the reason they
# are shaped differently. A drive series must hold the LOAD fixed while the
# driver varies; a load series must hold the DRIVER fixed while the load varies.
# An earlier version used one structure for both, and extraction measured its
# drive series at 76 ps of spread across an eightfold drive change, NOT
# monotonic, against a converter tap of 121 ps.
DRIVE_SERIES = ["drive_x1", "drive_x2", "drive_x4", "drive_x8"]
LOAD_SERIES = ["load_0", "load_1", "load_2", "load_4"]

# The two matched pairs. Each differs in exactly one construction choice, so the
# difference is that choice and nothing else.
MATCHED_PAIRS = {
    "input_isolation": ("drive_isolated_d4", "drive_shared_d4"),
    "load_ladder": ("ladder_off_d8", "ladder_on_d8"),
}

# Sites built WITHOUT drive-variant input isolation, from ISO_TWIN_MASK in
# src/project.v. Each is paired with its even-indexed isolated neighbour.
UNISOLATED_SITES = (1, 3, 5, 7)


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
                f"ladder{self.load} {SABOTAGE[self.sab]} src={ROUTES[self.route]}")


@dataclasses.dataclass(frozen=True)
class Globals:
    fb_en: int = 0
    calib_en: int = 0
    calib_sel: int = 0
    cnt_src: int = 0
    readout_sel: int = 0
    window_exp: int = 2
    trans_exp: int = 15
    tdc_en: int = 0
    tdc_src: int = 0
    tdc_pol: int = 0
    char_sel: int = 0
    char_drive: int = 0
    tdc_tap: int = 0
    tdc_freerun: int = 0

    def encode(self) -> int:
        return (_field(self.fb_en, G_FB_EN_W, "fb_en") << G_FB_EN
                | _field(self.calib_en, G_CALIB_EN_W, "calib_en") << G_CALIB_EN
                | _field(self.calib_sel, G_CALIB_SEL_W, "calib_sel") << G_CALIB_SEL
                | _field(self.cnt_src, G_CNT_SRC_W, "cnt_src") << G_CNT_SRC
                | _field(self.readout_sel, G_READOUT_SEL_W, "readout_sel") << G_READOUT_SEL
                | _field(self.window_exp, G_WINDOW_EXP_W, "window_exp") << G_WINDOW_EXP
                | _field(self.trans_exp, G_TRANS_EXP_W, "trans_exp") << G_TRANS_EXP
                | _field(self.tdc_en, G_TDC_EN_W, "tdc_en") << G_TDC_EN
                | _field(self.tdc_src, G_TDC_SRC_W, "tdc_src") << G_TDC_SRC
                | _field(self.tdc_pol, G_TDC_POL_W, "tdc_pol") << G_TDC_POL
                | _field(self.char_sel, G_CHAR_SEL_W, "char_sel") << G_CHAR_SEL
                | _field(self.char_drive, G_CHAR_DRIVE_W, "char_drive") << G_CHAR_DRIVE
                | _field(self.tdc_tap, G_TDC_TAP_W, "tdc_tap") << G_TDC_TAP
                | _field(self.tdc_freerun, G_TDC_FREERUN_W, "tdc_freerun") << G_TDC_FREERUN)

    @classmethod
    def decode(cls, word: int) -> "Globals":
        m = lambda pos, w: (word >> pos) & ((1 << w) - 1)  # noqa: E731
        return cls(fb_en=m(G_FB_EN, G_FB_EN_W),
                   calib_en=m(G_CALIB_EN, G_CALIB_EN_W),
                   calib_sel=m(G_CALIB_SEL, G_CALIB_SEL_W),
                   cnt_src=m(G_CNT_SRC, G_CNT_SRC_W),
                   readout_sel=m(G_READOUT_SEL, G_READOUT_SEL_W),
                   window_exp=m(G_WINDOW_EXP, G_WINDOW_EXP_W),
                   trans_exp=m(G_TRANS_EXP, G_TRANS_EXP_W),
                   tdc_en=m(G_TDC_EN, G_TDC_EN_W),
                   tdc_src=m(G_TDC_SRC, G_TDC_SRC_W),
                   tdc_pol=m(G_TDC_POL, G_TDC_POL_W),
                   char_sel=m(G_CHAR_SEL, G_CHAR_SEL_W),
                   char_drive=m(G_CHAR_DRIVE, G_CHAR_DRIVE_W),
                   tdc_tap=m(G_TDC_TAP, G_TDC_TAP_W),
                   tdc_freerun=m(G_TDC_FREERUN, G_TDC_FREERUN_W))


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

        # The rules below are about COMPARABILITY, not damage, which is the same
        # category as the one above. They live here rather than in a review
        # checklist because a confound that only shows up in the analysis three
        # months later is indistinguishable from a result.
        if self.globals.tdc_en and self.globals.window_exp < 1:
            raise UnsafeGenome(
                "tdc_en with window_exp=0 gives a 16 clock window, and the "
                "converter spends the first 12 of those settling and arming. "
                "See the note on tdc_wait in src/project.v; use window_exp >= 1")

        if self.globals.tdc_freerun and not self.globals.tdc_en:
            raise UnsafeGenome(
                "tdc_freerun without tdc_en does nothing; the ring is gated by "
                "the launch edge, which only fires when the TDC is enabled")

        if self.globals.tdc_freerun and self.globals.cnt_src != CNT_SRC["tdc_ring"]:
            raise UnsafeGenome(
                "tdc_freerun exists to measure the TDC ring's own period, so "
                "the frequency counter has to be watching the ring. Any other "
                "counter source with the ring free-running is a measurement "
                "taken beside an oscillator nobody is reading")

        if self.globals.tdc_en and self.globals.calib_en:
            raise UnsafeGenome(
                "tdc_en with calib_en runs a ring oscillator while the TDC "
                "times a single edge; the ring is a supply disturbance of "
                "exactly the size the TDC is trying to resolve. Take the ring "
                "covariate in a separate trial, immediately before or after")

        if self.globals.tdc_en and self.globals.tdc_src and self.globals.fb_en:
            raise UnsafeGenome(
                "tdc_en with tdc_src=1 times the fabric column, and fb_en "
                "closes that column into a loop, so the arrival edge the TDC "
                "samples is whichever oscillation happened to be passing. Time "
                "the column open, then close the loop and use the frequency "
                "counter")


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
    """Move one site's LOAD LADDER STATE by one step.

    Not "add a unit of capacitance". The four codes are four states of a fixed
    ladder whose loading on the node differs by a bias-dependent fraction, and
    Liberty predicts no difference between them at all. See src/load_ladder.v.
    """
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
