## How it works

This is the WP2 trial vehicle for an evolvable electrical-realization fabric. The full plan is in PLAN.md in this repository. There are three blocks.

**The fabric.** A column of configurable sites. What makes a site unusual is that its configuration selects the *electrical* realization of a gate, not only its truth table. Twelve bits per site choose the function, the drive variant of the transistor stack that actually drives the output node, how much load hangs on that node, whether a fault is inserted, and where the site's A input comes from. An FPGA bitstream cannot reach any of the electrical choices, which is the reason this is an ASIC.

Order matters inside a site. The function bank feeds an 8-to-1 mux, the mux feeds the sabotage mux, and only then do four tri-state inverters of drive 1, 2, 4 and 8 drive the site output node directly, decoded one-hot so contention is structurally impossible. Putting the drive select last is the point. If the drive variants were muxed instead, the mux output would drive the load and the drive selection would be electrically invisible. The output is therefore the inversion of the selected pre-stage function.

The load ladder hangs tri-state inverters of drive 1, 2 and 4 on the site output node with their inputs permanently connected. Enabling one does not connect a capacitor, it makes an already connected input switch. So ladder code 0 is reduced loading and never zero loading. A permanently enabled keeper on the shared sink node prevents a floating gate input, which on a die is a static current path rather than merely an X in simulation.

One combinational feedback edge runs from the column output back to the head of the column behind a global enable, so the fabric can be configured to oscillate.

**The calibration strip.** Four fixed 31-stage ring oscillators that differ only in drive variant (inv_1, inv_2, inv_4) and in whether a fixed load hangs on every stage. Nothing about them is configurable, because a configurable reference is not a reference. They are what the fabric's measurements are referred to. This block claims no novelty; docs/PRIOR_ART.md row 8 lists four Tiny Tapeout precedents including Sivasubramani's sky130 PVT ring array and Lazar's IHP drive-variant characterizer.

**The infrastructure.** A scan chain carries the whole genome. The frame is `[global 16][site 0 .. site N-1][crc 8]`, shifted MSB first, and a load only reaches the live configuration registers if the CRC-8 matches and ARM is high, so a corrupt frame cannot reach the fabric at all. A measurement window of 2^(4+window_exp) clocks bounds the trial. A frequency counter clocked by the selected oscillator counts its edges over that window. A separate activity monitor in the system clock domain trips, stickily, if the selected node exceeds 2^(4+trans_exp) transitions inside the window, and a trip forces the fabric inert. The fabric cannot gate its own kill path; the only fabric signal reaching the safety logic arrives through a synchronizer and can only cause a trip, never clear one.

## How to test

1. Hold ARM (ui[3]) high.
2. Raise SCAN_EN (ui[0]) and shift the frame in on SCAN_IN (ui[1]), MSB first, one bit per clock. The frame is 16 + 12*N + 8 bits. Watch it come back out on SCAN_OUT (uo[0]) exactly that many clocks later.
3. Lower SCAN_EN, check CRC_OK (uo[1]) is high, then pulse LOAD (ui[2]).
4. INERT (uo[7]) falls, MEAS_BUSY (uo[4]) rises and the window runs. When it falls, the frequency count is on the readout bus uio[7:0], one byte at a time as selected by the global config field.
5. Drive FAB_A (ui[4]) and FAB_B (ui[5]) and watch FAB_OUT (uo[2]) for the logic behavior. OBS_SEL (ui[6]) puts either the calibration oscillator or the fabric feedback node on OBS_OUT (uo[3]) for a scope.

The cocotb suite in test/ covers all of this, including the reach tests that sabotage a path and require the observable to move.

## External hardware

None required for bring-up beyond the Tiny Tapeout demo board. A frequency counter or oscilloscope on OBS_OUT is useful. The bench-instrument anchoring of on-chip timing, which the plan requires so that the calibration is never circular against Liberty-predicted delays, needs a counter or scope with better resolution than the on-chip measurement.
