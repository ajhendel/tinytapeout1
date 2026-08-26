// Fixed calibration macro. Block A of PLAN.md section 3.
//
// This block claims nothing. docs/PRIOR_ART.md row 8 is CLOSED with four
// precedents on Tiny Tapeout alone, including drive-variant ring oscillators on
// IHP (Lazar, TTIHP26a) and PVT ring-oscillator arrays on sky130 (Sivasubramani,
// TTSKY26a). It exists so that measurements from the fabric mean something, and
// so that Liberty, extracted and SPICE predictions have a clean object to be
// wrong about.
//
// Four fixed ring oscillators, all 31 stages (prime, one NAND2 enable gate plus
// 30 inverters), differing only in the property under study.
//
//   RO0  inv_1 chain, no added load     drive variant reference
//   RO1  inv_2 chain, no added load     drive variant reference
//   RO2  inv_4 chain, no added load     drive variant reference
//   RO3  inv_1 chain, one inv_1 sink hung on every stage
//
// RO0 against RO1 against RO2 gives per-stage delay as a function of drive
// variant with everything else held fixed. RO0 against RO3 gives the delay cost
// of a known fixed load on a known drive variant, which is the reference the
// fabric's load ladder is measured against.
//
// Nothing here is configurable on purpose. A configurable calibration reference
// is not a reference.
//
// Enable gating uses the NAND2-in-the-ring recipe that is known to survive the
// Tiny Tapeout sky130 flow. tt04's "Multi stage path for delay measurements"
// recorded the failure mode we are avoiding, that the flow will collapse an
// unprotected inverter chain into buffers and refuse the loop, which is why
// every cell here is a keep/dont_touch wrapper from cells.v.

`default_nettype none

module calib_ro #(
    parameter DRIVE  = 1,
    parameter LOADED = 0,
    parameter STAGES = 30   // inverters; plus the NAND2 makes 31, an odd ring
) (
    input  wire en,
    output wire osc
);

`ifdef SIM
  // An event simulator cannot settle a real combinational ring. In SIM the ring
  // is replaced by a free-running toggle whose half period differs per drive
  // variant, so tests can still tell the four macros apart and the frequency
  // counter can still be exercised. The real ring is what gets fabricated;
  // gate-level simulation after the GDS build exercises it.
  localparam integer HALF_PERIOD =
      (DRIVE == 1) ? (LOADED ? 7 : 5) : (DRIVE == 2) ? 4 : 3;
  reg q;
  initial q = 1'b0;
  always begin
    #(HALF_PERIOD);
    q <= en ? ~q : 1'b0;
  end
  assign osc = q;
`else
  wire [STAGES:0] ring;

  // NAND2 closes the ring and gates it. en low parks the ring at a known level.
  cell_nand2 #(.DRIVE(1)) gate (.A(en), .B(ring[STAGES]), .Y(ring[0]));

  genvar i;
  generate
    for (i = 0; i < STAGES; i = i + 1) begin : stage
      cell_inv #(.DRIVE(DRIVE)) u (.A(ring[i]), .Y(ring[i+1]));
      if (LOADED != 0) begin : loadgen
        wire sink;
        cell_inv #(.DRIVE(1)) ld (.A(ring[i+1]), .Y(sink));
        // The sink output is deliberately unused. keep/dont_touch on the
        // wrapper is what stops it being swept away, and the load it presents
        // is the whole point of this variant.
        wire unused_sink = sink;
      end
    end
  endgenerate

  assign osc = ring[STAGES];
`endif
endmodule


module calib_macro (
    input  wire       en,
    input  wire [1:0] sel,
    output wire       osc_out
);
  wire o0, o1, o2, o3;

  // Only the selected ring runs. Running all four at once would couple them
  // through the supply, which is a real effect we intend to study on purpose in
  // block P, and a confound we refuse to accept in the calibration strip.
  calib_ro #(.DRIVE(1), .LOADED(0)) ro0 (.en(en & (sel == 2'd0)), .osc(o0));
  calib_ro #(.DRIVE(2), .LOADED(0)) ro1 (.en(en & (sel == 2'd1)), .osc(o1));
  calib_ro #(.DRIVE(4), .LOADED(0)) ro2 (.en(en & (sel == 2'd2)), .osc(o2));
  calib_ro #(.DRIVE(1), .LOADED(1)) ro3 (.en(en & (sel == 2'd3)), .osc(o3));

  cell_mux4 sel_mux (.A0(o0), .A1(o1), .A2(o2), .A3(o3),
                     .S0(sel[0]), .S1(sel[1]), .X(osc_out));
endmodule
