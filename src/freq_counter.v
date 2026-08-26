// Frequency counter for the calibration rings and for the fabric's feedback
// node.
//
// Separate from scan_config.v on purpose. The safety controller is conventional
// synchronous logic in the system clock domain and stays that way. This block is
// deliberately clocked by the thing being measured, which is the only honest way
// to count a ring oscillator, and there is Tiny Tapeout precedent on both sky130
// and IHP (Sivasubramani TTSKY26a, Lazar TTIHP26a).
//
// Two mistakes were made here before this version and both are worth recording,
// because both produce a number that looks perfectly reasonable.
//
//   1. Counting transitions of the ring AFTER a two-stage synchronizer in the
//      system clock domain. That is a fine activity monitor and a useless
//      frequency counter, because a ring near a multiple of the system clock
//      aliases, in the limit to exactly zero counts for a ring at the clock
//      frequency.
//
//   2. Fixing staleness with a clock-domain activity detector, which is the
//      same sampler as mistake 1 wearing a different hat, and which zeroed the
//      count for exactly the ring that aliased.
//
// The arrangement below has no sampler in it. `gate` is held high a few system
// clocks past the end of the window and asynchronously clears the counter
// whenever it is low, so between windows the count is structurally zero and can
// never be a stale reading from a previous trial. `count_en` is the window
// itself. `capture` pulses inside the tail, while the counter is frozen and the
// gate is still high, so the clock domain reads a static value.
//
// `count_en` and `gate` cross into the ring domain without a handshake, which
// costs at most one ring period of uncertainty at each end of the window. That
// is budgeted in docs/THROUGHPUT.md against the resolvable difference, not
// ignored.

// Explicit timescale. Without one, a module picks up whatever default the
// compiler applies, and a delay written as 5 can land on a completely different
// time base than the testbench driving it. That silently stopped the simulation
// model of the calibration rings from oscillating at all in one harness while
// working in another.
`timescale 1ns / 1ps
`default_nettype none

module freq_counter (
    input  wire        clk,        // system clock, for the capture only
    input  wire        rst_n,
    input  wire        osc,        // the oscillator under measurement
    input  wire        gate,       // window, extended past the capture
    input  wire        count_en,   // the window itself
    input  wire        capture,    // one system clock pulse inside the tail
    output reg  [23:0] value
);

  // Asynchronous clear whenever the gate is low. This is what makes a parked
  // ring report zero rather than whatever the last live ring left behind.
  wire cnt_clr_n = rst_n & gate;

  reg [23:0] cnt;
  always @(posedge osc or negedge cnt_clr_n) begin
    if (!cnt_clr_n) cnt <= 24'd0;
    else if (count_en) cnt <= cnt + 24'd1;
  end

  always @(posedge clk) begin
    if (!rst_n)      value <= 24'd0;
    else if (capture) value <= cnt;
  end

endmodule
