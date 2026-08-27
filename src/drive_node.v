// The drive stage, factored out so that the fabric site and the fixed
// characterization replica in src/char_paths.v are literally the same circuit
// rather than two circuits described by the same paragraph.
//
// WHY THIS FILE EXISTS AT ALL
//
// Four tri-state inverters of drive 1, 2, 4 and 8 drive one node, one-hot
// decoded. There is no output multiplexer. A mux between the selected driver
// and the load would put the mux output on the load and make the drive
// selection electrically invisible except as a constant extra stage, which
// would defeat the entire chip. So the selected variant really is the thing
// driving the node.
//
// That settles the OUTPUT side. It does not settle the INPUT side, and the
// input side was wrong in the first version of this design. All four variants
// shared one input net, so:
//
//   - whatever drives the stage sees the summed input capacitance of all four
//     variants, no matter which one is selected
//   - the three unselected variants switch their input stages on every
//     transition and draw current doing it
//   - the supply disturbance of a site therefore includes the alternatives the
//     genome did not pick
//
// Only the first of those is a timing effect, and it is a CONSTANT offset
// across drive settings, so a difference measurement between two drive
// settings was never corrupted by it. The other two are real and were not
// mitigated. ISOLATE=1 gates each variant's input with its own enable, so an
// unselected variant sees a static input and does not switch.
//
// ISOLATION IS NOT FREE AND IS NOT ASSUMED CORRECT
//
// Isolating costs four AND2 cells per node and one gate delay in the measured
// path, and it makes the upstream load variant-DEPENDENT, because an einvn_8
// presents a larger input than an einvn_1. That is more physically honest and
// it is also more entangled. Neither arrangement is obviously right, so the
// chip carries both: most sites are isolated, a named minority are not, and
// src/char_paths.v carries a matched fixed pair (paths 14 and 15) that differ
// in nothing except this. The isolation cost is then a measurement on the die
// rather than a claim in a comment.
//
// Inert behaviour. den[0] is forced high when the site is inert, and the data
// input is forced low upstream, so exactly one driver is always active and the
// node never floats. A fully tri-stated node on a real die is an undefined
// input to whatever observes it and a crowbar risk in the sinks.

`timescale 1ns / 1ps
`default_nettype none

module drive_node #(
    parameter integer ISOLATE = 1
) (
    input  wire       d,      // data, already gated by live upstream
    input  wire [3:0] den,    // one-hot drive enables
    output wire       z
);

  wire [3:0] a;

  generate
    if (ISOLATE != 0) begin : g_iso
      cell_and2 i0 (.A(d), .B(den[0]), .X(a[0]));
      cell_and2 i1 (.A(d), .B(den[1]), .X(a[1]));
      cell_and2 i2 (.A(d), .B(den[2]), .X(a[2]));
      cell_and2 i3 (.A(d), .B(den[3]), .X(a[3]));
    end else begin : g_shared
      // The deliberately un-isolated control. Keep this branch: it is the
      // comparison arm, not dead code.
      assign a = {4{d}};
    end
  endgenerate

  cell_einvn #(.DRIVE(1)) drv1 (.A(a[0]), .EN(den[0]), .Z(z));
  cell_einvn #(.DRIVE(2)) drv2 (.A(a[1]), .EN(den[1]), .Z(z));
  cell_einvn #(.DRIVE(4)) drv4 (.A(a[2]), .EN(den[2]), .Z(z));
  cell_einvn #(.DRIVE(8)) drv8 (.A(a[3]), .EN(den[3]), .Z(z));

endmodule
