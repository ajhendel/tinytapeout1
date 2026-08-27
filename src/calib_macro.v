// Fixed calibration strip. Block A of PLAN.md section 3.
//
// This block claims nothing. docs/PRIOR_ART.md row 8 is CLOSED with four
// precedents on Tiny Tapeout alone, including drive-variant ring oscillators on
// IHP (Lazar, TTIHP26a) and PVT ring-oscillator arrays on sky130
// (Sivasubramani, TTSKY26a). It exists so that measurements from the fabric
// mean something, and so that Liberty, extracted and SPICE predictions have a
// clean object to be wrong about.
//
// WHAT A RING OSCILLATOR IS AND IS NOT
//
// It is a joint monitor of process, voltage, temperature and its own switching
// activity, read out as one number. It is not a thermometer and this strip
// must never be described as one. Nothing here can separate a die that got
// warmer from a supply that sagged, and running the ring is itself one of the
// things that makes the die warmer. What the strip gives is a COVARIATE that
// travels with the fabric measurement, taken on the same die at the same time,
// so that a fabric result can be conditioned on it. It is not a correction
// oracle and no measurement is ever divided by it.
//
// A single transition, which is what a combinational path actually does, is
// measured by src/tdc.v against src/char_paths.v instead. The two instruments
// answer different questions and the chip carries both on purpose.
//
// THE EIGHT RINGS, AND WHAT EACH ONE IS FOR
//
//   sel  ring                                     what varies
//   ---  ---------------------------------------  --------------------------
//    0   inv_1 x30 + NAND2, unloaded              drive series reference
//    1   inv_2 x30 + NAND2, unloaded              drive variant
//    2   inv_4 x30 + NAND2, unloaded              drive variant
//    3   inv_1 x30 + NAND2, inv_1 sink per stage  fixed load at fixed drive
//    4   inv_1 x10 + NAND2, unloaded              geometry: a compact ring
//    5   drive_node x6 + NAND2                    the fabric's own output stage
//    6   inv_1 x30 + NAND2, unloaded              IDENTICAL to ring 0
//    7   inv_1 x30 + NAND2, unloaded              IDENTICAL to ring 0
//
// Rings 0, 6 and 7 are the same circuit three times. That is the point of them.
//
//   - Their SPREAD is the within-die, same-design variation floor. Any spatial
//     or fabric effect smaller than that spread is not a result.
//   - Their DIFFERENCE is a placement effect and nothing else, because nothing
//     else differs.
//
// We cannot force where the flow puts them. Tiny Tapeout's LibreLane
// configuration gives no standard-cell placement regions, so "near the fabric"
// and "far from the fabric" are not things this file can assert. So they are
// not asserted. tools/check_placement.py reads the placed DEF after the build
// and reports where the three actually landed and how far apart they are, and
// that measured separation is what any spatial statement is quoted against. If
// the flow clusters all three together, the spatial experiment did not happen
// and the report says so rather than the paper saying otherwise.
//
// Ring 5 is a ring made of the site output stage from src/drive_node.v, so the
// strip contains a reference built from the fabric's own structure and not only
// from plain inverters. It runs at a fixed drive variant on purpose: rings 0
// through 2 already vary drive, and a configurable calibration reference is
// not a reference.
//
// Nothing here is configurable except which ring runs. Only the selected ring
// runs; running several at once would couple them through the supply, which is
// a real effect we intend to study on purpose elsewhere and refuse to accept
// as a confound here.
//
// Enable gating uses the NAND2-in-the-ring recipe that is known to survive the
// Tiny Tapeout sky130 flow. tt04's "Multi stage path for delay measurements"
// recorded the failure mode we are avoiding, that the flow will collapse an
// unprotected inverter chain into buffers and refuse the loop, which is why
// every cell here is a keep/dont_touch wrapper from cells.v.

// Explicit timescale. Without one, a module picks up whatever default the
// compiler applies, and a delay written as 5 can land on a completely different
// time base than the testbench driving it. That silently stopped the simulation
// model of the calibration rings from oscillating at all in one harness while
// working in another.
`timescale 1ns / 1ps
`default_nettype none

module calib_ro #(
    parameter integer DRIVE  = 1,
    parameter integer LOADED = 0,
    parameter integer STAGES = 30   // inverters; plus the NAND2 makes it odd
) (
    input  wire en,
    output wire osc
);

`ifdef SIM
  // An event simulator cannot settle a real combinational ring. In SIM the ring
  // is replaced by a free-running toggle whose half period tracks the stage
  // count and the drive variant, so tests can still tell the macros apart and
  // the frequency counter can still be exercised. This is NOT a model and no
  // measurement may be taken from it. The real ring is what gets fabricated;
  // gate-level simulation after the GDS build exercises it.
  localparam integer PER_STAGE =
      (DRIVE == 1) ? (LOADED ? 7 : 5) : (DRIVE == 2) ? 4 : 3;
  localparam integer HALF_PERIOD = (STAGES * PER_STAGE) / 10;
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


// A ring built from the fabric's own output stage rather than from plain
// inverters, so the strip carries a reference made of the structure whose
// behaviour the fabric experiments depend on. STAGES drive_node inversions plus
// the NAND2 must be odd, so STAGES is even.
module calib_ro_drive #(
    parameter integer STAGES = 6
) (
    input  wire en,
    output wire osc
);
`ifdef SIM
  localparam integer HALF_PERIOD = STAGES + 2;
  reg q;
  initial q = 1'b0;
  always begin
    #(HALF_PERIOD);
    q <= en ? ~q : 1'b0;
  end
  assign osc = q;
`else
  // Fixed at drive variant 1. Rings 0 through 2 are where drive varies; a
  // calibration reference that moves is not a reference.
  wire [3:0] den = 4'b0001;

  wire [STAGES:0] ring;
  cell_nand2 #(.DRIVE(1)) gate (.A(en), .B(ring[STAGES]), .Y(ring[0]));

  genvar i;
  generate
    for (i = 0; i < STAGES; i = i + 1) begin : stage
      drive_node #(.ISOLATE(1)) u (.d(ring[i]), .den(den), .z(ring[i+1]));
    end
  endgenerate

  assign osc = ring[STAGES];
`endif
endmodule


module calib_macro (
    input  wire       en,
    input  wire [2:0] sel,
    output wire       osc_out
);
  wire [7:0] o;

  calib_ro #(.DRIVE(1), .LOADED(0), .STAGES(30)) ro0      (.en(en & (sel == 3'd0)), .osc(o[0]));
  calib_ro #(.DRIVE(2), .LOADED(0), .STAGES(30)) ro1      (.en(en & (sel == 3'd1)), .osc(o[1]));
  calib_ro #(.DRIVE(4), .LOADED(0), .STAGES(30)) ro2      (.en(en & (sel == 3'd2)), .osc(o[2]));
  calib_ro #(.DRIVE(1), .LOADED(1), .STAGES(30)) ro3      (.en(en & (sel == 3'd3)), .osc(o[3]));
  calib_ro #(.DRIVE(1), .LOADED(0), .STAGES(10)) ro4      (.en(en & (sel == 3'd4)), .osc(o[4]));
  calib_ro_drive #(.STAGES(6))                   ro5      (.en(en & (sel == 3'd5)), .osc(o[5]));

  // ro_twin_a and ro_twin_b are byte-for-byte the same circuit as ro0. Their
  // spread is the variation floor and their difference is placement. The
  // instance names are load bearing: tools/check_placement.py looks for them.
  calib_ro #(.DRIVE(1), .LOADED(0), .STAGES(30)) ro_twin_a (.en(en & (sel == 3'd6)), .osc(o[6]));
  calib_ro #(.DRIVE(1), .LOADED(0), .STAGES(30)) ro_twin_b (.en(en & (sel == 3'd7)), .osc(o[7]));

  wire lo, hi;
  cell_mux4 sel_lo (.A0(o[0]), .A1(o[1]), .A2(o[2]), .A3(o[3]),
                    .S0(sel[0]), .S1(sel[1]), .X(lo));
  cell_mux4 sel_hi (.A0(o[4]), .A1(o[5]), .A2(o[6]), .A3(o[7]),
                    .S0(sel[0]), .S1(sel[1]), .X(hi));
  cell_mux2 sel_top (.A0(lo), .A1(hi), .S(sel[2]), .X(osc_out));
endmodule
