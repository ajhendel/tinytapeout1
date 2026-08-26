// Frequency counter for the calibration rings and for the fabric's feedback
// node.
//
// This is a separate module from scan_config.v on purpose. The safety
// controller is conventional synchronous logic in the system clock domain and
// stays that way. This block is deliberately clocked by the thing being
// measured, which is the only way to count a ring oscillator honestly.
//
// The mistake this replaces is worth recording, because it is easy to make
// again. An earlier version counted transitions of the ring AFTER a two-stage
// synchronizer in the system clock domain. That is a perfectly good safety
// activity monitor and a useless frequency counter, because the synchronizer
// samples at the system clock and any ring near a multiple of that clock
// aliases, in the limit to exactly zero counts for a ring at the clock
// frequency. The test caught it as a ring that reported no transitions at all.
//
// Counting a ring oscillator with a counter clocked by the ring is the standard
// approach and there is Tiny Tapeout precedent on both sky130 and IHP
// (Sivasubramani TTSKY26a, Lazar TTIHP26a). The gate signal crosses from the
// system clock domain into the ring domain without a handshake, which costs at
// most one ring period of uncertainty at each end of the window. That is
// budgeted, not ignored; see docs/THROUGHPUT.md on the resolvable difference.

`default_nettype none

module freq_counter (
    input  wire        clk,        // system clock, for the readout capture only
    input  wire        rst_n,
    input  wire        osc,        // the oscillator under measurement
    input  wire        gate,       // high for the duration of the window
    output reg  [23:0] value       // last completed window's count
);

  reg [23:0] cnt;
  reg        gate_q;

  // Ring domain. Cleared at the start of a window, counts while gated.
  always @(posedge osc or negedge rst_n) begin
    if (!rst_n) begin
      cnt    <= 24'd0;
      gate_q <= 1'b0;
    end else begin
      gate_q <= gate;
      if (gate && !gate_q) cnt <= 24'd0;
      else if (gate)       cnt <= cnt + 24'd1;
    end
  end

  // System clock domain. The count is only read after the gate has fallen, so
  // cnt is static by then and a plain register is enough.
  reg gate_s1, gate_s2, gate_s3;
  always @(posedge clk) begin
    if (!rst_n) begin
      gate_s1 <= 1'b0;
      gate_s2 <= 1'b0;
      gate_s3 <= 1'b0;
      value   <= 24'd0;
    end else begin
      gate_s1 <= gate;
      gate_s2 <= gate_s1;
      gate_s3 <= gate_s2;
      if (!gate_s2 && gate_s3) value <= cnt;   // capture on the falling gate
    end
  end

endmodule
