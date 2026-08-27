# SPDX-FileCopyrightText: 2026 Andrew Hendel
# SPDX-License-Identifier: Apache-2.0
#
# Tests for tt_um_ajhendel_evofab.
#
# Discipline note, inherited from the standing rules of this program. These
# tests are written to verify REACH, not only output. Several of them sabotage
# the path and check that the observable moves, because a path that runs is not
# a path that is gated, and an expected value that is just our own tally proves
# nothing. Where a test asserts a value that the design itself computed, that is
# stated in the test.

import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Timer

# Gate-level runs simulate the extracted netlist against the PDK cell models.
# Two tests are skipped there, and the reason is worth stating precisely because
# it is the project's own thesis showing up in its own test suite.
#
# The sky130 FUNCTIONAL cell models are combinational and carry no delay. A ring
# oscillator built from them is therefore a ZERO-DELAY combinational loop, and an
# event simulator cannot advance time through one at all. Measured: seven tests
# completed in 1.3 seconds, then the first test to enable a calibration ring
# froze simulation time at 38,547 ns and ran until GitHub killed the job at its
# six hour limit with vvp still spinning.
#
# This is a fact about event simulators, not about the chip. The rings are real
# oscillators in silicon and the RTL suite exercises them through a behavioural
# model. It is also, precisely, an instance of the bar in PLAN.md: the thing the
# calibration strip measures is unsettleable by simulation alone, which is why
# the strip is on the die.
#
# The related point, for whoever tries to relax this rather than skip it: even if
# the loop could be advanced, unit delay makes every cell take the same time
# regardless of drive variant, so a gate-level run could not tell the inv_1,
# inv_2 and inv_4 rings apart. That difference is a silicon measurement and is
# listed in predictions/ as one.
GATE_LEVEL = os.environ.get("GATES") == "yes"

# Taken from the environment, which test/Makefile exports, with the same default
# as the `define in src/project.v. The gate-level run cannot be told a site
# count, it simulates whatever was built, so these three defaults have to agree
# and test_readout_selector_reaches_every_slot is what proves they do.
N_SITES = int(os.environ.get("N_SITES", "24"))
GLOBAL_W = 32
PAYLOAD_W = GLOBAL_W + 12 * N_SITES
CHAIN_W = PAYLOAD_W + 8

# Global config field positions inside the 32-bit global word. This layout is
# also in src/project.v, src/scan_config.v and harness/evofab/genome.py. Four
# copies is three too many, and the reason it is not centralised is that this
# file has to be able to disagree with the harness for the disagreement to mean
# anything. Move a field and you move it in all four.
G_FB_EN = 0
G_CALIB_EN = 1
G_CALIB_SEL = 2  # 3 bits
G_CNT_SRC = 5
G_READOUT_SEL = 6  # 4 bits
G_WINDOW_EXP = 10  # 4 bits
G_TRANS_EXP = 14  # 4 bits
G_TDC_EN = 18
G_TDC_SRC = 19
G_TDC_POL = 20
G_CHAR_SEL = 21  # 4 bits
G_CHAR_DRIVE = 25  # 2 bits

# Readout selector codes, matching the case statement in src/project.v.
RO_FREQ0, RO_STATUS, RO_NSITES = 0, 6, 7
RO_TDC0, RO_TDC1, RO_TDC2, RO_TDC3 = 8, 9, 10, 11
RO_TDC_TAPS, RO_TWIN_MASK, RO_CHAR_COUNT, RO_ALIVE = 12, 13, 14, 15

# Bit positions inside the status byte, readout slot 6. The packing in
# src/project.v is {0, tdc_valid, tdc_done, tripped, meas_busy, crc_ok, n[1:0]},
# and getting these off by one is a mistake that reads TRIPPED as an arrival
# flag and passes, because both are usually zero.
ST_NSITES, ST_CRC_OK, ST_BUSY = 0, 2, 3
ST_TRIPPED, ST_TDC_DONE, ST_TDC_VALID = 4, 5, 6

# Characterization path codes, matching the table in src/char_paths.v.
CH_INV1_D8, CH_INV1_D2, CH_INV1_D4, CH_INV1_D16 = 0, 8, 9, 10
CH_DRIVE_ISOLATED, CH_DRIVE_SHARED = 14, 15

# Sites built without drive-variant input isolation, from ISO_TWIN_MASK in
# src/project.v.
ISO_TWIN_MASK = 0xAA

# Site config field positions inside each 12-bit site word.
S_FUNC = 0  # 3 bits
S_DRIVE = 3  # 2 bits
S_LOAD = 5  # 2 bits
S_SAB = 7  # 3 bits
S_ROUTE = 10  # 2 bits

# Site function codes, named by what appears at the site OUTPUT, which is the
# inversion of the pre-stage function. See the table in src/fabric_site.v.
FUNC_AND, FUNC_OR, FUNC_XNOR, FUNC_XOR = 0, 1, 2, 3
FUNC_NOTA, FUNC_NOTB, FUNC_NAND, FUNC_NOR = 4, 5, 6, 7

# Sabotage codes.
SAB_NONE, SAB_STUCK0, SAB_STUCK1, SAB_BYPASS_A = 0, 1, 2, 3
SAB_BYPASS_B, SAB_INVERT = 4, 5

# Route codes for the site A input.
ROUTE_PREV, ROUTE_PI, ROUTE_FB, ROUTE_ONE = 0, 1, 2, 3


def crc8(payload_bits):
    """CRC-8, poly 0x07, init 0x00, MSB first. Mirrors src/scan_config.v.

    payload_bits is an int of width PAYLOAD_W. This is an independent
    reimplementation of the same specified algorithm, not a copy of the RTL,
    which is the only way the CRC test means anything.
    """
    crc = 0
    for i in range(PAYLOAD_W - 1, -1, -1):
        bit = (payload_bits >> i) & 1
        top = (crc >> 7) & 1
        crc = ((crc << 1) & 0xFF) ^ (0x07 if (top ^ bit) else 0x00)
    return crc


def site_word(func=0, drive=0, load=0, sab=SAB_NONE, route=ROUTE_PREV):
    return ((func & 7) << S_FUNC) | ((drive & 3) << S_DRIVE) | \
           ((load & 3) << S_LOAD) | ((sab & 7) << S_SAB) | \
           ((route & 3) << S_ROUTE)


def global_word(fb_en=0, calib_en=0, calib_sel=0, cnt_src=0,
                readout_sel=0, window_exp=2, trans_exp=15,
                tdc_en=0, tdc_src=0, tdc_pol=0, char_sel=0, char_drive=0):
    """window is 2^(4+window_exp) clocks, trip limit is 2^(4+trans_exp) edges."""
    return (fb_en << G_FB_EN) | (calib_en << G_CALIB_EN) | \
           ((calib_sel & 7) << G_CALIB_SEL) | (cnt_src << G_CNT_SRC) | \
           ((readout_sel & 15) << G_READOUT_SEL) | \
           ((window_exp & 15) << G_WINDOW_EXP) | ((trans_exp & 15) << G_TRANS_EXP) | \
           (tdc_en << G_TDC_EN) | (tdc_src << G_TDC_SRC) | (tdc_pol << G_TDC_POL) | \
           ((char_sel & 15) << G_CHAR_SEL) | ((char_drive & 3) << G_CHAR_DRIVE)


def build_frame(gword, site_words, corrupt_crc=False):
    """Assemble the scan frame. Chain order is [global][site0..siteN-1][crc]."""
    payload = gword
    for w in site_words:
        payload = (payload << 12) | (w & 0xFFF)
    crc = crc8(payload)
    if corrupt_crc:
        crc ^= 0xFF
    return (payload << 8) | crc


# The driven state of ui_in is tracked here in Python and never read back from
# the simulator. cocotb applies a write at the end of the current time step, so
# reading a signal you just wrote, without awaiting first, returns the OLD value
# and silently drops the write. That bug cost a debugging round; do not
# reintroduce it by reading dut.ui_in.value.
UI_BITS = {"scan_en": 0, "scan_in": 1, "load": 2, "arm": 3,
           "fab_a": 4, "fab_b": 5, "obs_sel": 6, "cnt_hold": 7}
_ui = {"v": 0}


def set_ui(dut, **kw):
    v = _ui["v"]
    for k, val in kw.items():
        if val:
            v |= 1 << UI_BITS[k]
        else:
            v &= ~(1 << UI_BITS[k])
    _ui["v"] = v
    dut.ui_in.value = v


CLK_PERIOD_NS = 10
# Where in the clock period the testbench drives inputs and samples outputs.
# Not 1 ns. At RTL an output assignment is instantaneous, so sampling just after
# the edge works; in the gate-level netlist the path from a flip-flop to an
# output pin runs through real cells and takes real time, and sampling 1 ns after
# the edge read the PREVIOUS value. That showed up as the scan chain appearing to
# be one bit long, which is exactly the failure the scan test exists to catch, so
# it was a testbench bug wearing the costume of a design bug.
#
# Mid-period is right for both. Outputs have settled by then, and an input driven
# at mid-period still has half a clock of setup before the next edge.
SETTLE_NS = CLK_PERIOD_NS // 2 + 1


async def tick(dut, n=1):
    """Advance n clock edges, then move to mid-period.

    Everything drives and samples at mid-period. See SETTLE_NS.
    """
    await ClockCycles(dut.clk, n)
    await Timer(SETTLE_NS, unit="ns")


async def shift_frame(dut, frame):
    """Shift CHAIN_W bits in, MSB first."""
    set_ui(dut, scan_en=1)
    for i in range(CHAIN_W - 1, -1, -1):
        set_ui(dut, scan_in=(frame >> i) & 1)
        await tick(dut)
    set_ui(dut, scan_en=0, scan_in=0)


async def load_config(dut, frame, arm=True):
    set_ui(dut, arm=arm)
    await shift_frame(dut, frame)
    await tick(dut, 2)
    set_ui(dut, load=1)
    await tick(dut, 2)
    set_ui(dut, load=0)
    await tick(dut, 2)


def uo(dut):
    return dut.uo_out.value.to_unsigned()


async def start(dut):
    clock = Clock(dut.clk, CLK_PERIOD_NS, unit="ns")
    cocotb.start_soon(clock.start())
    _ui["v"] = 0
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await tick(dut, 2)


@cocotb.test()
async def test_reset_is_inert(dut):
    """Default-inert. Out of reset, before any load, the fabric is held off."""
    await start(dut)
    assert uo(dut) & 0x80, "INERT must be high before a load"
    assert not (uo(dut) & 0x20), "TRIPPED must be clear at reset"


@cocotb.test()
async def test_scan_chain_shifts_through(dut):
    """Bits shifted in reappear at SCAN_OUT exactly CHAIN_W clocks later.

    This is a reach test for the chain length. If the chain were one bit long or
    short, every genome would silently rotate and every downstream test would
    still pass on plausible-looking wrong data.
    """
    await start(dut)
    pattern = [1, 0, 1, 1, 0, 0, 0, 1, 1, 1, 0, 1]
    seen = []
    set_ui(dut, scan_en=1)
    for i in range(CHAIN_W + len(pattern)):
        bit = pattern[i] if i < len(pattern) else 0
        set_ui(dut, scan_in=bit)
        await tick(dut)
        seen.append(uo(dut) & 1)
    set_ui(dut, scan_en=0, scan_in=0)
    got = seen[CHAIN_W - 1:CHAIN_W - 1 + len(pattern)]
    assert got == pattern, f"chain length wrong: sent {pattern}, got back {got}"


@cocotb.test()
async def test_crc_gates_the_load(dut):
    """A frame with a bad CRC must not reach the fabric.

    Sabotage form: the same frame is loaded twice, once intact and once with the
    CRC inverted. CRC_OK must move and the corrupt frame must leave the design
    inert.
    """
    await start(dut)
    words = [site_word(func=FUNC_AND, drive=0, route=ROUTE_PI)
             for _ in range(N_SITES)]
    good = build_frame(global_word(window_exp=0), words)
    bad = build_frame(global_word(window_exp=0), words, corrupt_crc=True)

    await load_config(dut, bad)
    assert not (uo(dut) & 0x02), "CRC_OK high on a corrupt frame"
    assert uo(dut) & 0x80, "corrupt frame must leave INERT set"

    await load_config(dut, good)
    assert uo(dut) & 0x02, "CRC_OK low on a good frame"
    assert not (uo(dut) & 0x80), "good frame must clear INERT"


@cocotb.test()
async def test_arm_is_required_and_removable(dut):
    """ARM low blocks the load, and dropping ARM after a load forces inert."""
    await start(dut)
    words = [site_word(func=FUNC_AND, route=ROUTE_PI) for _ in range(N_SITES)]
    frame = build_frame(global_word(), words)

    await load_config(dut, frame, arm=False)
    assert uo(dut) & 0x80, "load without ARM must stay inert"

    await load_config(dut, frame, arm=True)
    assert not (uo(dut) & 0x80)

    set_ui(dut, arm=0)
    await tick(dut, 2)
    assert uo(dut) & 0x80, "dropping ARM must force inert"


@cocotb.test()
async def test_function_select_changes_the_truth_table(dut):
    """Sweep the function field on a one-deep path and check the truth table.

    Every site is set to route=PI so the column is N independent copies of the
    same gate on the same inputs, and FAB_OUT is the last one. For an even
    number of sites in series the identity chains cancel, so this test reads the
    LAST site only, which is what FAB_OUT is wired to. The expected values are
    Boolean algebra, not a tally taken from the design.
    """
    await start(dut)

    def expect(func, a, b):
        return {FUNC_AND: a & b, FUNC_OR: a | b, FUNC_XNOR: 1 - (a ^ b),
                FUNC_XOR: a ^ b, FUNC_NOTA: 1 - a, FUNC_NOTB: 1 - b,
                FUNC_NAND: 1 - (a & b), FUNC_NOR: 1 - (a | b)}[func]

    for func in range(8):
        # Only the last site matters for FAB_OUT; give every site route=PI so
        # each one sees the primary inputs directly.
        words = [site_word(func=func, route=ROUTE_PI) for _ in range(N_SITES)]
        frame = build_frame(global_word(), words)
        await load_config(dut, frame)
        for a in (0, 1):
            for b in (0, 1):
                set_ui(dut, fab_a=a, fab_b=b)
                await tick(dut, 3)
                got = (uo(dut) >> 2) & 1
                want = expect(func, a, b)
                assert got == want, (
                    f"func {func} a={a} b={b}: got {got} want {want}")


@cocotb.test()
async def test_sabotage_modes_change_the_output(dut):
    """Each sabotage mode must actually alter the last site's output.

    This is the mutation mechanism that docs/PRIOR_ART.md row 9 rests on. If a
    sabotage code were decoded to a no-op the fabric would look healthy and
    every mutation experiment would silently measure nothing.
    """
    await start(dut)

    async def out_for(sab, a, b):
        words = [site_word(func=FUNC_AND, route=ROUTE_PI) for _ in range(N_SITES)]
        words[-1] = site_word(func=FUNC_AND, route=ROUTE_PI, sab=sab)
        await load_config(dut, build_frame(global_word(), words))
        set_ui(dut, fab_a=a, fab_b=b)
        await tick(dut, 3)
        return (uo(dut) >> 2) & 1

    # Baseline is AND, so a=1 b=1 gives 1 and a=1 b=0 gives 0.
    assert await out_for(SAB_NONE, 1, 1) == 1
    assert await out_for(SAB_NONE, 1, 0) == 0

    # stuck-at faults are applied at the pre-stage node, which the output stage
    # inverts. stuck-0 therefore forces the site output high, stuck-1 low.
    assert await out_for(SAB_STUCK0, 1, 1) == 1
    assert await out_for(SAB_STUCK0, 1, 0) == 1, "stuck-0 must override the gate"
    assert await out_for(SAB_STUCK1, 1, 1) == 0, "stuck-1 must override the gate"
    assert await out_for(SAB_STUCK1, 0, 0) == 0

    # bypass-A ignores B, bypass-B ignores A. Output is the inverted bypassed input.
    assert await out_for(SAB_BYPASS_A, 1, 0) == 0
    assert await out_for(SAB_BYPASS_A, 0, 1) == 1
    assert await out_for(SAB_BYPASS_B, 1, 0) == 1
    assert await out_for(SAB_BYPASS_B, 0, 1) == 0

    # invert flips the healthy result.
    assert await out_for(SAB_INVERT, 1, 1) == 0
    assert await out_for(SAB_INVERT, 1, 0) == 1


@cocotb.test()
async def test_load_ladder_is_reached(dut):
    """The load ladder observable must move when the ladder field is swept.

    On silicon the ladder's effect is electrical, so nothing about it is visible
    to a logic simulator except this reach witness. Its whole job is to prove
    that the ladder enables are wired to something, before we go looking for a
    delay difference on a die.
    """
    await start(dut)
    set_ui(dut, fab_a=1, fab_b=1)
    seen = set()
    for ladder in range(4):
        words = [site_word(func=FUNC_AND, route=ROUTE_PI, load=ladder)
                 for _ in range(N_SITES)]
        await load_config(dut, build_frame(global_word(), words))
        await tick(dut, 3)
        seen.add((uo(dut) >> 6) & 1)
    assert len(seen) > 1, (
        "LOAD_MON never changed across the ladder sweep, so the ladder enables "
        "are not reaching the ladder elements")


@cocotb.test(skip=GATE_LEVEL)
async def test_calibration_rings_are_distinguishable(dut):
    """All eight calibration rings must run, the six DIFFERENT ones must be
    told apart by their count, and the three IDENTICAL ones must not be.

    Rings 0 through 5 differ in drive variant, in loading, in stage count or in
    what they are built from, so a count that does not separate them means the
    variation is not reaching the ring, which is the whole measurement block A
    exists to make.

    Rings 0, 6 and 7 are the same circuit three times. In simulation they MUST
    agree exactly; there is nothing in a logic simulation that could tell them
    apart, so any difference here would be a wiring or select bug. On silicon
    their spread is the within-die variation floor and their difference is a
    placement effect, which is the only form the spatial experiment takes. See
    the note in src/calib_macro.v and tools/check_placement.py."""
    await start(dut)
    counts = []
    for sel in range(8):
        # window_exp 2 is 64 clocks, 640 ns, which keeps every ring's edge
        # count inside the 8 bits that the readout byte can show. A longer
        # window aliases the counter and the test would compare wrapped values.
        gw = global_word(calib_en=1, calib_sel=sel, cnt_src=0,
                         readout_sel=RO_FREQ0, window_exp=2, trans_exp=15)
        words = [site_word(func=FUNC_AND, route=ROUTE_PI) for _ in range(N_SITES)]
        await load_config(dut, build_frame(gw, words))
        # Wait past the end of the window so the count has been captured.
        await tick(dut, 120)
        counts.append(dut.uio_out.value.to_unsigned())
    dut._log.info(f"calibration ring counts: {counts}")
    assert all(c > 0 for c in counts), (
        f"a ring produced no edges: {counts}; the select is not reaching the "
        "rings or a ring is not oscillating")
    distinct = counts[:6]
    assert len(set(distinct)) == 6, (
        f"rings 0 to 5 are not distinguishable ({distinct}), so either the "
        "select or the property under study is not reaching the rings")
    assert counts[6] == counts[0] and counts[7] == counts[0], (
        f"rings 0, 6 and 7 are the same circuit and disagree in simulation "
        f"({counts[0]}, {counts[6]}, {counts[7]}); that is a wiring bug, not a "
        "physical effect")


@cocotb.test()
async def test_readout_selector_reaches_every_slot(dut):
    """The readout multiplexer must actually decode all sixteen slots.

    Four of the slots carry constants the design knows and the test knows
    independently: the site count, the tap count, the un-isolated twin mask and
    a fixed pattern. A readout mux that had lost its high select bit would
    return plausible counter bytes for everything and nothing else would
    notice."""
    await start(dut)
    words = [site_word(func=FUNC_AND, route=ROUTE_PI) for _ in range(N_SITES)]

    async def read(sel):
        gw = global_word(readout_sel=sel, window_exp=0, trans_exp=15)
        await load_config(dut, build_frame(gw, words))
        await tick(dut, 40)
        return dut.uio_out.value.to_unsigned()

    assert await read(RO_NSITES) == N_SITES
    assert await read(RO_TDC_TAPS) == 32, "tap count slot"
    assert await read(RO_TWIN_MASK) == ISO_TWIN_MASK, (
        "the chip and this test disagree about which sites are the un-isolated "
        "controls; every isolation result would be attributed to the wrong site")
    assert await read(RO_CHAR_COUNT) == 16, "characterization path count slot"
    assert await read(RO_ALIVE) == 0xA5, "default slot pattern"


async def tdc_measure(dut, char_sel, char_drive=0, tdc_src=0, tdc_pol=0):
    """Run one TDC trial and return (taps_int, done, valid).

    Thirty-two taps do not fit in an eight bit port, so the measuring trial is
    followed by three read-only trials with the TDC disabled. That works only
    because src/tdc.v transfers a capture into the readout register solely when
    an arrival edge actually occurred; read the note there before changing this.
    char_sel and tdc_pol are held fixed across all four, so the path output
    stays static and cannot manufacture an arrival edge of its own.
    """
    words = [site_word(func=FUNC_AND, route=ROUTE_PI) for _ in range(N_SITES)]

    async def trial(readout_sel, tdc_en):
        gw = global_word(readout_sel=readout_sel, window_exp=2, trans_exp=15,
                         tdc_en=tdc_en, tdc_src=tdc_src, tdc_pol=tdc_pol,
                         char_sel=char_sel, char_drive=char_drive)
        await load_config(dut, build_frame(gw, words))
        await tick(dut, 120)
        return dut.uio_out.value.to_unsigned()

    # The status byte has to be read on the MEASURING trial. tdc_done reports
    # the last trial and nothing else, so reading it after the read-only trials
    # reports that a read-only trial measured nothing, which is true and
    # useless. This ordering is the host protocol, not a testbench convenience.
    status = await trial(RO_STATUS, 1)
    done = (status >> ST_TDC_DONE) & 1
    valid = (status >> ST_TDC_VALID) & 1

    b0 = await trial(RO_TDC0, 0)
    b1 = await trial(RO_TDC1, 0)
    b2 = await trial(RO_TDC2, 0)
    b3 = await trial(RO_TDC3, 0)
    return b0 | (b1 << 8) | (b2 << 16) | (b3 << 24), done, valid


@cocotb.test(skip=GATE_LEVEL)
async def test_tdc_orders_the_depth_series(dut):
    """Longer fixed paths must reach further down the delay line.

    This is the calibration backbone from src/char_paths.v: the same cell at
    depths 2, 4, 8 and 16. The absolute numbers here are an artefact of the SIM
    delays in src/cells.v and mean nothing. The ORDER is not an artefact. A
    delay line whose taps were captured in the wrong order, or a select that
    did not reach the paths, would break it, and both are mistakes that a
    fabricated chip could not be talked out of.

    Skipped at gate level for the same reason the ring tests are: the sky130
    FUNCTIONAL models carry no delay, so every path would capture identically.
    """
    await start(dut)
    seen = []
    for depth, sel in ((2, CH_INV1_D2), (4, CH_INV1_D4),
                       (8, CH_INV1_D8), (16, CH_INV1_D16)):
        taps, done, valid = await tdc_measure(dut, sel)
        count = bin(taps).count("1")
        dut._log.info(f"depth {depth:>2}: {count} taps, code {taps:#010x}")
        assert done, f"depth {depth} produced no arrival edge at the TDC"
        assert valid, f"depth {depth} left the tap register invalid"
        seen.append((depth, count))
    counts = [c for _, c in seen]
    assert counts == sorted(counts) and len(set(counts)) == 4, (
        f"the depth series is not ordered: {seen}. Either the taps are captured "
        "in the wrong order or the path select is not reaching the paths")


@cocotb.test(skip=GATE_LEVEL)
async def test_tdc_is_silent_when_disabled(dut):
    """With the TDC off, nothing launches and no arrival is recorded.

    The sabotage half of the test above. Without it, a TDC that captured on
    some unrelated toggling net would pass the depth series by accident."""
    await start(dut)
    words = [site_word(func=FUNC_AND, route=ROUTE_PI) for _ in range(N_SITES)]
    gw = global_word(readout_sel=RO_STATUS, window_exp=2, trans_exp=15,
                     tdc_en=0, char_sel=CH_INV1_D8)
    await load_config(dut, build_frame(gw, words))
    await tick(dut, 120)
    status = dut.uio_out.value.to_unsigned()
    assert not ((status >> ST_TDC_DONE) & 1), (
        "the TDC recorded an arrival with tdc_en low, so it is capturing on "
        "something other than the launched edge")


@cocotb.test(skip=GATE_LEVEL)
async def test_both_drive_replicas_conduct(dut):
    """The isolated and un-isolated drive replicas must both carry an edge.

    Paths 14 and 15 are the matched pair that make the cost of drive-variant
    input isolation a measurement rather than an argument, and they are the only
    place in the design where the un-isolated arrangement appears outside the
    four control sites. If either one failed to conduct, the comparison would
    quietly become a comparison of one thing with nothing.

    This checks conduction and the drive-variant select, and deliberately does
    NOT compare the two counts. Their difference in simulation is an artefact of
    the SIM delays; on silicon it is the result."""
    await start(dut)
    for sel in (CH_DRIVE_ISOLATED, CH_DRIVE_SHARED):
        for drive in range(4):
            taps, done, valid = await tdc_measure(dut, sel, char_drive=drive)
            assert done and valid, (
                f"path {sel} at drive variant {drive} produced no arrival; the "
                "drive one-hot is not reaching the replica")


@cocotb.test()
async def test_calib_disabled_counts_nothing(dut):
    """Sabotage the enable and the counter must stop. Without this the previous
    test could be passing on some unrelated toggling net."""
    await start(dut)
    gw = global_word(calib_en=0, calib_sel=0, cnt_src=0, readout_sel=0,
                     window_exp=2, trans_exp=15)
    words = [site_word(func=FUNC_AND, route=ROUTE_PI) for _ in range(N_SITES)]
    await load_config(dut, build_frame(gw, words))
    await tick(dut, 300)
    assert dut.uio_out.value.to_unsigned() == 0, "counter advanced with calib_en low"


@cocotb.test(skip=GATE_LEVEL)
async def test_safety_trips_on_a_hot_configuration(dut):
    """A configuration that toggles faster than the limit must trip and be
    forced inert, and the trip must be sticky."""
    await start(dut)
    # trans_exp 0 sets the limit at 2^4 transitions inside the window, and
    # window_exp 8 gives a 4096 clock window, so the fastest ring blows through
    # the limit early in the window rather than at the very end of it.
    gw = global_word(calib_en=1, calib_sel=2, cnt_src=0, readout_sel=0,
                     window_exp=8, trans_exp=0)
    words = [site_word(func=FUNC_AND, route=ROUTE_PI) for _ in range(N_SITES)]
    await load_config(dut, build_frame(gw, words))
    await tick(dut, 500)
    assert uo(dut) & 0x20, "safety did not trip on a hot config"
    assert uo(dut) & 0x80, "trip must force inert"

    # Sticky: a fresh good load must not clear it while reset is not asserted.
    quiet = global_word(calib_en=0, window_exp=2, trans_exp=15)
    await load_config(dut, build_frame(quiet, words))
    assert uo(dut) & 0x20, "trip must be sticky until reset"
