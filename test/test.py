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

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Timer

N_SITES = 8
GLOBAL_W = 16
PAYLOAD_W = GLOBAL_W + 12 * N_SITES
CHAIN_W = PAYLOAD_W + 8

# Global config field positions inside the 16-bit global word.
G_FB_EN = 0
G_CALIB_EN = 1
G_CALIB_SEL = 2  # 2 bits
G_CNT_SRC = 4
G_READOUT_SEL = 5  # 3 bits
G_WINDOW_EXP = 8  # 4 bits
G_TRANS_EXP = 12  # 4 bits

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
                readout_sel=0, window_exp=2, trans_exp=15):
    """window is 2^(4+window_exp) clocks, trip limit is 2^(4+trans_exp) edges."""
    return (fb_en << G_FB_EN) | (calib_en << G_CALIB_EN) | \
           ((calib_sel & 3) << G_CALIB_SEL) | (cnt_src << G_CNT_SRC) | \
           ((readout_sel & 7) << G_READOUT_SEL) | \
           ((window_exp & 15) << G_WINDOW_EXP) | ((trans_exp & 15) << G_TRANS_EXP)


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


async def tick(dut, n=1):
    """One or more clock edges, then settle before anything is sampled."""
    await ClockCycles(dut.clk, n)
    await Timer(1, unit="ns")


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
    clock = Clock(dut.clk, 10, unit="ns")
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


@cocotb.test()
async def test_calibration_rings_are_distinguishable(dut):
    """Every calibration ring must produce a nonzero count, and the four rings
    must be told apart by that count.

    The four rings differ only in drive variant and in whether a fixed load is
    hung on every stage, so a count that does not separate them means the drive
    variant is not reaching the ring, which is the whole measurement block A
    exists to make."""
    await start(dut)
    counts = []
    for sel in range(4):
        # window_exp 2 is 64 clocks, 640 ns, which keeps every ring's edge
        # count inside the 8 bits that the readout byte can show. A longer
        # window aliases the counter and the test would compare wrapped values.
        gw = global_word(calib_en=1, calib_sel=sel, cnt_src=0,
                         readout_sel=0, window_exp=2, trans_exp=15)
        words = [site_word(func=FUNC_AND, route=ROUTE_PI) for _ in range(N_SITES)]
        await load_config(dut, build_frame(gw, words))
        # Wait past the end of the window so the count has been captured.
        await tick(dut, 120)
        counts.append(dut.uio_out.value.to_unsigned())
    dut._log.info(f"calibration ring counts: {counts}")
    assert all(c > 0 for c in counts), f"a ring produced no edges: {counts}"
    assert len(set(counts)) == 4, (
        f"calibration rings are not distinguishable ({counts}), so either the "
        "select or the drive variant is not reaching the rings")


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


@cocotb.test()
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
