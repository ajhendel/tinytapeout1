## How it works

This chip is an instrument. It exists to find out how far the open sky130
models are from the silicon they describe, on circuits chosen by a search
running against the physical die. The full plan is in PLAN.md in this
repository and the measurement discipline is in docs/MEASUREMENT_PROTOCOL.md.
There are five blocks.

**The fabric.** A column of 24 configurable sites. What makes a site unusual is
that its configuration selects the *electrical* realization of a gate, not only
its truth table. Twelve bits per site choose the function, which of the four
prefabricated drive variants of the standard cell drives the output node, how
much load hangs on that node, what state the load ladder on its output node is in,
whether a fault is inserted at its output, and where its A input comes from. Nothing here resizes a transistor; the variants are library
cells whose internal sizing differs. An FPGA bitstream cannot reach any of these
electrical choices, which is the reason this is an ASIC.

Order matters inside a site. The function bank feeds an 8-to-1 mux, the mux
feeds the sabotage mux, and only then do four tri-state inverters of drive 1, 2,
4 and 8 drive the site output node directly, decoded one-hot so contention is
structurally impossible. Putting the drive select last is the point: if the
variants were muxed instead, the mux output would drive the load and the drive
selection would be electrically invisible. The output is therefore the inversion
of the selected pre-stage function.

Each variant's input is gated by its own enable, so the three unselected
variants do not switch. Four sites, 1, 3, 5 and 7, are deliberately built
WITHOUT that gating, as controls, so the cost of isolation is something this
chip measures rather than something its documentation asserts.

The load ladder hangs tri-state inverters of drive 1, 2 and 4 on the site output
node with their inputs permanently connected. **Enabling one does not connect a
capacitor and this field is not four steps of added load.** The transistor
netlist says why: an einvn's input devices have their drains on the output and
their sources on internal nodes that the enable devices tie to the rails, so
part of the input capacitance is present in every state and part of it faces a
floating node when disabled. The effect on the node is real, partial and bias
dependent. Liberty has one capacitance number per pin and cannot express it at
all, so the Liberty-layer prediction for this field is exactly zero, which makes
it the sharpest model-discrimination test on the chip rather than a weak knob.
Two of the fixed characterization paths carry the same ladder with its enables
tied high and low so the mechanism can be measured on its own.

One combinational feedback edge runs from the column output back to the head of
the column behind a global enable, so the fabric can be configured to oscillate.
It is a feedback edge and nothing more: there is no controllable coupling and no
phase readout, so it is not an Ising machine of any size.

**The calibration strip.** Eight fixed ring oscillators. Three differ only in
drive variant, one carries a fixed load on every stage, one is short and
compact, one is built from the fabric's own output stage, and two more are
byte-for-byte copies of the first. Those three identical rings are the useful
part: their spread is the within-die variation floor, so any effect smaller than
it is not a result, and their difference is a placement effect because nothing
else about them differs. Nothing in this block is configurable, because a
configurable reference is not a reference. A ring is a joint process, voltage,
temperature and activity monitor, not a thermometer.

**The fixed characterization paths.** Twenty non-oscillating paths carrying one
transition each: inverters at four drive variants loaded and unloaded, the same
inverter at four depths, NAND chains, a mux chain, and two matched pairs: replicas of the site output
stage differing only in whether the drive inputs are isolated, and inverter
chains carrying the load ladder differing only in whether its enables are tied
high or low. Each pair makes one construction choice a measurement instead of
an argument. They are the middle rung of the inference chain. Without them, a
disagreement between the models and an evolved circuit could be the models, the
extraction, the cost of configurability or the search, and there would be no way
to tell which.

**The time-to-digital converter.** A 32-stage delay line, closed into a gated
ring and sampled by the arrival edge of the path under test, reporting a raw tap
pattern and a count of ring wraps. The ring is what gives it range: a bare line
spans 3.8 nanoseconds and one fabric site takes 3.5 of them, so a linear line
could not have measured the fabric at all. The ring runs only between launch and
arrival, never for the rest of the window, so the instrument is not oscillating
beside whatever else is being measured. A stop tap selects which site's output
stops it, so the per-site delay comes out as a slope over the sweep rather than
as one unusable total for the whole column. A ring oscillator
averages over millions of transitions and heats itself while it runs; a
combinational path delay is one transition and needed its own instrument. The
code is raw on purpose: bubbles in it are the map of which bins are wide, and
that map is the calibration. The four-point depth series is what turns tap
counts into times, on the die, after fabrication.

**The infrastructure.** A scan chain carries the whole genome. The frame is
`[global 32][site 0 .. site 23][crc 8]`, 328 bits, shifted MSB first, and a load
only reaches the live configuration registers if the CRC-8 matches and ARM is
high, so a corrupt frame cannot reach the fabric at all. A measurement window of
2^(4+window_exp) clocks bounds every trial. A frequency counter clocked by the
selected oscillator counts its edges over that window. A separate activity
monitor in the system clock domain trips, stickily, if the selected node exceeds
2^(4+trans_exp) transitions inside the window, and a trip forces the fabric
inert. The fabric cannot gate its own kill path; the only fabric signal reaching
the safety logic arrives through a synchronizer and can only cause a trip, never
clear one.

## How to test

1. Hold ARM (ui[3]) high.
2. Raise SCAN_EN (ui[0]) and shift the frame in on SCAN_IN (ui[1]), MSB first,
   one bit per clock. The frame is 32 + 12*24 + 8 = 328 bits. Watch it come back
   out on SCAN_OUT (uo[0]) exactly that many clocks later.
3. Lower SCAN_EN, check CRC_OK (uo[1]) is high, then pulse LOAD (ui[2]).
4. INERT (uo[7]) falls, MEAS_BUSY (uo[4]) rises and the window runs. When it
   falls, the selected readout byte is on uio[7:0]. The readout selector is a
   global config field with sixteen slots: three bytes of frequency count, three
   of transition count, a status byte, the site count, four bytes of TDC taps,
   the tap count, the un-isolated site mask, the path count, and a fixed 0xA5
   pattern that proves the multiplexer is alive.
5. Drive FAB_A (ui[4]) and FAB_B (ui[5]) and watch FAB_OUT (uo[2]) for the logic
   behavior. OBS_SEL (ui[6]) puts the calibration oscillator on OBS_OUT (uo[3])
   for a scope; with OBS_SEL low it carries the characterization path output
   when the TDC is enabled, and the fabric feedback node otherwise.
6. For a delay measurement, set tdc_en and a characterization path, run one
   trial reading the status byte to confirm an arrival was seen, then run three
   more trials with tdc_en clear to read the remaining tap bytes. A trial with
   the TDC off cannot disturb the capture it is reading.

The cocotb suite in test/ covers all of this, including the reach tests that
sabotage a path and require the observable to move.

## External hardware

None required for bring-up beyond the Tiny Tapeout demo board. A frequency
counter or oscilloscope on OBS_OUT is useful.

Two things want better instruments. The bench anchoring of on-chip timing, which
the plan requires so the calibration is never circular against Liberty-predicted
delays, needs a counter or scope with better resolution than the on-chip
measurement. And the supply sweep needs a bench supply for the whole board,
because Tiny Tapeout's rails are shared infrastructure and this project cannot
run at a different core voltage from the rest of the chip.
