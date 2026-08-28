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
# gcfg[21] is RETIRED. It held a one bit tdc_src; the field grew to two and was
# moved whole rather than split across the word. Nothing reads it.
G_TDC_POL, G_TDC_POL_W = 22, 1
G_CHAR_SEL, G_CHAR_SEL_W = 23, 5
G_CHAR_DRIVE, G_CHAR_DRIVE_W = 28, 2
G_TDC_TAP, G_TDC_TAP_W = 30, 5
G_TDC_FREERUN, G_TDC_FREERUN_W = 35, 1
G_TDC_SRC, G_TDC_SRC_W = 36, 2

# What stops the TDC. The first two are measurements. The last two are
# stimulus: their phase relative to the launch edge is uniform, which is what
# code density calibration needs and what neither of the first two provides.
# See the stop source note in src/project.v.
TDC_STOP_SRC = {"char": 0, "fabric": 1, "calib": 2, "external": 3}

# What the frequency counter watches.
CNT_SRC = {"calib": 0, "fabric": 1, "tdc_ring": 2}

# Readout selector codes, matching the case statement in src/project.v.
READOUT = {
    "freq0": 0, "freq1": 1, "freq2": 2,
    "trans0": 3, "trans1": 4, "trans2": 5,
    "status": 6, "n_sites": 7,
    "tdc0": 8, "tdc1": 9, "tdc2": 10, "tdc3": 11,
    "tdc_taps": 12, "twin_mask": 13, "char_count": 14, "alive": 15,
    # The coarse half of a TDC reading, GRAY CODED on the wire. The saturation
    # value there is 0x80, which is gray(0xFF), and NOT 0xFF: a host working
    # from this table and discarding 0xFF would be throwing away coarse count
    # 85, a perfectly good reading, and keeping the saturated one.
    "tdc_gray": 16,
    "tdc_tap_echo": 17, "char_sel_echo": 18, "global_w": 19,
    "instr_version": 20, "tdc_cfg_echo": 21, "site_w": 22,
}

# The coarse count is GRAY coded on the wire; see the long note in src/tdc.v.
# 0x80 is the Gray code of 0xFF, which is the saturation value.
TDC_GRAY_SATURATED = 0x80
TDC_WRAPS_SATURATED = 0xFF
TDC_TAPS = 32
INSTR_VERSION = 2

# How close to the coarse counter's own clock edge a reading may fall before the
# Gray capture stops being trustworthy on its own, in taps. The Gray code
# confines an ambiguous capture to ADJACENT counts, so one tap either side of
# the boundary is where the fine code has to be consulted to decide which.
TDC_BOUNDARY_GUARD = 1

# How many runs of equal bits a fine code may contain before it stops looking
# like a delay line reading at all. A clean code is two runs. Bubbles are
# expected and are the calibration, but they are LOCAL: a handful of extra runs
# near the boundary, not a scattered pattern. Six is generous; a code with more
# runs than this is a sampling fault, not a bin width.
TDC_MAX_RUNS = 6


class TdcStatus:
    """What a raw capture turned out to be. Not every capture is a delay.

    A decoder that always returns a number is a decoder that reports the
    converter's failures as measurements, and on this chip two of those failures
    (a saturated coarse count, a capture taken at the counter's own carry) look
    exactly like ordinary fast readings.
    """

    VALID = "VALID"
    BOUNDARY_AMBIGUOUS = "BOUNDARY_AMBIGUOUS"
    THERMOMETER_INVALID = "THERMOMETER_INVALID"
    COARSE_SATURATED = "COARSE_SATURATED"
    NO_ARRIVAL = "NO_ARRIVAL"


def gray_to_bin(g: int, width: int = 8) -> int:
    """Undo the Gray coding the coarse counter leaves the chip in.

    The chip does not do this. A converter in metal is an opinion that cannot be
    revised once the die exists, and the raw Gray value is the diagnostic: a
    capture that lands mid transition returns one of two ADJACENT codes, and
    which two it was is visible here and gone after conversion.
    """
    b = g & ((1 << width) - 1)
    shift = 1
    while shift < width:
        b ^= b >> shift
        shift <<= 1
    return b & ((1 << width) - 1)


def bin_to_gray(b: int, width: int = 8) -> int:
    m = (1 << width) - 1
    return ((b & m) ^ ((b & m) >> 1)) & m


def _fine(taps: int, n_taps: int):
    """(parity, position) of the launch edge inside the ring, from the fine code.

    The delay line is a RING, so the tap register is not a thermometer code that
    grows monotonically. The ring parks with every tap high; the launch edge
    walks a 1 to 0 transition down it, then a 0 to 1 transition, alternating. So
    during traversal T the taps below the edge carry the NEW value and the ones
    above carry the old, and which is which flips with the parity of T.

    Population count alone is therefore the wrong decode, and it is wrong in a
    way that looks plausible: it DECREASES as the path gets longer on odd
    traversals. That is what the first run of the depth series test reported, a
    perfectly ordered series running backwards.
    """
    if taps == (1 << n_taps) - 1:
        # Every tap high. Either the ring is still parked and the arrival beat
        # the first buffer, or a rising traversal has just completed. Those two
        # are one ring period apart and the fine code cannot separate them,
        # which is why this lands in the boundary case below rather than being
        # quietly folded into the general one.
        return 0, 0
    ones = bin(taps).count("1")
    if taps & 1:
        return 1, ones                 # low taps are 1: an odd traversal
    return 0, n_taps - ones            # low taps are 0: an even traversal


def tdc_runs(taps: int, n_taps: int = TDC_TAPS) -> int:
    """How many runs of equal bits the fine code contains. Clean is 1 or 2."""
    runs = 1
    for i in range(1, n_taps):
        if ((taps >> i) & 1) != ((taps >> (i - 1)) & 1):
            runs += 1
    return runs


def tdc_decode(taps: int, coarse_gray: int, n_taps: int = TDC_TAPS) -> int:
    """Delay in units of one line stage, from a raw capture.

    coarse_gray is the GRAY coded coarse count as the chip reports it at
    readout_sel 16, NOT a binary wrap count. The two agree for 0 and 1 and
    disagree from 2 upward, which is exactly the shape of mistake that passes a
    short test and corrupts a long measurement, so the argument is named for
    what it is.

    This returns a number for every input. Use tdc_reading() where the answer
    matters; it is the one that can say the capture was not a measurement.
    """
    parity, pos = _fine(taps, n_taps)
    return (2 * gray_to_bin(coarse_gray) + parity) * n_taps + pos


@dataclasses.dataclass(frozen=True)
class TdcReading:
    """A decoded capture, and what kind of capture it turned out to be.

    A decoder that always returns a number reports the converter's failures as
    measurements. Two of this converter's failures look exactly like ordinary
    fast readings: a saturated coarse count, and a capture taken while the
    coarse counter was changing. Neither is a delay and neither is detectable
    downstream, so they are named here.
    """

    status: str
    delay_taps: int | None
    candidates: tuple
    taps_raw: int
    gray: int
    coarse: int
    parity: int
    position: int
    bubbles: int
    runs: int

    @property
    def ok(self) -> bool:
        return self.status == TdcStatus.VALID


def tdc_reading(taps: int, coarse_gray: int, done: bool = True,
                n_taps: int = TDC_TAPS,
                guard: int = TDC_BOUNDARY_GUARD) -> TdcReading:
    """Decode one capture and classify it. See TdcStatus for the outcomes.

    The order of the checks is the order in which the failures mask each other.
    A trial that never saw an arrival has a stale tap register from the previous
    one, so `done` is asked first. A saturated coarse count makes the fine code
    meaningless, so it is asked before the fine code is interpreted.

    BOUNDARY_AMBIGUOUS is the case the Gray coding exists to make detectable.
    The coarse counter lives in the ring's domain and is captured by the arrival
    edge; a capture taken while it is changing returns one of two ADJACENT
    counts. The fine code says which side of the counter's own clock edge the
    arrival fell on, but not which of the two values the capture took, so both
    are returned. They differ by a whole ring period, which is 2 * n_taps taps,
    so this must NOT be averaged away. Repeat the trial.
    """
    coarse = gray_to_bin(coarse_gray)
    bubbles = tdc_bubbles(taps, n_taps)
    runs = tdc_runs(taps, n_taps)
    parity, pos = _fine(taps, n_taps)

    def mk(status, delay=None, candidates=()):
        return TdcReading(status=status, delay_taps=delay,
                          candidates=tuple(candidates), taps_raw=taps,
                          gray=coarse_gray, coarse=coarse, parity=parity,
                          position=pos, bubbles=bubbles, runs=runs)

    if not done:
        return mk(TdcStatus.NO_ARRIVAL)
    if coarse_gray == TDC_GRAY_SATURATED:
        return mk(TdcStatus.COARSE_SATURATED)
    if runs > TDC_MAX_RUNS:
        return mk(TdcStatus.THERMOMETER_INVALID)

    def delay(c):
        return (2 * c + parity) * n_taps + pos

    # The coarse counter ticks at the end of every RISING traversal, so the
    # boundary sits between (parity 1, position n_taps) and (parity 0,
    # position 0). Those are the two places a capture can straddle a carry.
    alt = None
    if parity == 1 and pos >= n_taps - guard and coarse >= 1:
        alt = coarse - 1
    elif parity == 0 and pos <= guard and coarse < TDC_WRAPS_SATURATED - 1:
        # The ceiling matches the floor above. Without it, a capture at coarse
        # 0xFE would be offered 0xFF as its alternative candidate, and 0xFF is
        # the saturation code rather than a count, so one of the two candidates
        # would not be a delay at all.
        alt = coarse + 1
    if alt is not None:
        return mk(TdcStatus.BOUNDARY_AMBIGUOUS,
                  candidates=sorted((delay(coarse), delay(alt))))
    return mk(TdcStatus.VALID, delay=delay(coarse))


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

# The depth series, in stage order. A straight line through these gives the
# per-stage delay AND the fixed offset from the launch gate, the select merge
# and the TDC input. Everything else in CHAR_PATHS is quoted against that
# offset, which makes the slope the single most load bearing number the chip
# produces.
#
# THIS LIST SAID 24 FOR load_0 AND THE RTL BUILDS IT AT 16.
#
# src/char_paths.v:373 is char_inv_chain #(.DRIVE(1), .DEPTH(16), .LOAD(0)) p4,
# and the comment above it says so: twenty-four was the first choice, bought
# nothing but area, and was cut. Fitting delays measured at depths
# [2, 4, 8, 16, 16, 32] against x values [2, 4, 8, 16, 24, 32] pulls the fitted
# slope to about 0.89 of the true one, roughly 11 percent low, AND inflates the
# residual that the same pre-registration predicts will stay under one tap. So
# it could have pre-registered a falsification of its own linearity claim.
#
# Nothing would have failed. The RTL was right, one test was right, and two
# copies of this list were wrong. harness/tests/test_char_paths_match_rtl.py now
# reads the parameters out of the Verilog and fails if they ever disagree again.
DEPTH_SERIES = [(2, "inv1_d2"), (4, "inv1_d4"), (8, "inv1_d8"),
                (16, "inv1_d16"), (32, "inv1_d32")]

# load_0 is the depth 16 point measured a SECOND time under a different name,
# deliberately not deduplicated in the RTL. Two names for one measurement is a
# free repeatability check: they must agree within a tap, and if they do not,
# the disagreement is about the instrument and not about depth.
DEPTH_REPEAT = (16, "inv1_d16", "load_0")

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

        # The calibration ring IS the stop source in code density mode, so the
        # rule below has to except exactly that case and no other. Written as an
        # exception rather than dropped, because the reason the rule exists has
        # not changed: everywhere else, a ring running beside the converter is a
        # supply disturbance of exactly the size the converter resolves.
        if (self.globals.tdc_en and self.globals.calib_en
                and self.globals.tdc_src != TDC_STOP_SRC["calib"]):
            raise UnsafeGenome(
                "tdc_en with calib_en runs a ring oscillator while the TDC "
                "times a single edge; the ring is a supply disturbance of "
                "exactly the size the TDC is trying to resolve. Take the ring "
                "covariate in a separate trial, immediately before or after. "
                "The one exception is tdc_src=calib, where the ring is the "
                "stop source and its own disturbance is part of the stimulus")

        if (self.globals.tdc_en
                and self.globals.tdc_src == TDC_STOP_SRC["calib"]
                and not self.globals.calib_en):
            raise UnsafeGenome(
                "tdc_src=calib takes the stop edge from a calibration ring, "
                "and calib_en=0 leaves that ring parked, so the converter would "
                "wait for an edge that never comes and the trial would report "
                "NO_ARRIVAL for a reason that has nothing to do with the fabric")

        if (self.globals.tdc_en
                and self.globals.tdc_src == TDC_STOP_SRC["fabric"]
                and self.globals.fb_en):
            raise UnsafeGenome(
                "tdc_en with tdc_src=fabric times the fabric column, and fb_en "
                "closes that column into a loop, so the arrival edge the TDC "
                "samples is whichever oscillation happened to be passing. Time "
                "the column open, then close the loop and use the frequency "
                "counter")

        # Code density is a calibration of the CONVERTER, and a fabric that is
        # switching underneath it is a supply disturbance charged to every bin.
        # The rule is here rather than in the protocol because a bin table with
        # a fabric-shaped bias in it is invisible afterwards and is then applied
        # to every measurement the chip ever makes.
        if (self.globals.tdc_en
                and self.globals.tdc_src in (TDC_STOP_SRC["calib"],
                                             TDC_STOP_SRC["external"])
                and self.globals.fb_en):
            raise UnsafeGenome(
                "an asynchronous stop source is used to calibrate the bins, so "
                "nothing else on the die should be oscillating; fb_en closes "
                "the fabric loop underneath the calibration")


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
