// The load ladder, factored out so that the fabric site and the fixed
// characterization replicas in src/char_paths.v are literally the same circuit
// rather than two circuits described by the same paragraph. Same reasoning as
// src/drive_node.v.
//
// WHAT THIS DOES, STATED CORRECTLY. READ THIS BEFORE WRITING ABOUT IT.
//
// Three tri-state inverters and one permanently enabled keeper hang on `node`
// with their A inputs PERMANENTLY CONNECTED. Enabling one does not connect a
// capacitor. It is not four steps of added load and it must never be described
// that way; an earlier version of this design said "0 = switch parasitic only,
// then +1, +2, +4" and that was wrong.
//
// The sky130 einvn transistor netlist says exactly what happens:
//
//     X0 a_204_297#  A  Z  pfet     A-device: DRAIN on Z, SOURCE on an internal node
//     X5 a_286_47#   A  Z  nfet     A-device: DRAIN on Z, SOURCE on an internal node
//     X3 VPWR  TE_B  a_204_297#     the ENABLE devices sit at the rails
//     X2 VGND  te    a_286_47#
//
// So from `node`, looking into an element's A pin:
//
//   - the gate-to-drain capacitance faces Z and is present in BOTH states. It
//     never disconnects. This is the part that makes "selectable capacitance"
//     the wrong description.
//   - the gate-to-source capacitance faces the internal node, which is tied to
//     a rail when enabled and FLOATING when disabled. Roughly the source-side
//     channel capacitance drops out of the disabled state.
//   - enabling also makes the element drive the shared sink, so the sink's
//     transition gets faster, which increases the Miller current back through
//     the gate-to-drain capacitance that was there all along.
//
// The effect on `node` is therefore real, partial, and bias dependent. Both
// states have to be characterized and neither is "unloaded".
//
// THE PART THAT MAKES THIS AN EXPERIMENT RATHER THAN AN EMBARRASSMENT
//
// The RELEASED sky130 Liberty view assigns one capacitance number to this pin
// and does not represent any dependence on TE_B. For einvn_1 it is 0.002382 pF
// in every state. Stated that way on purpose: this is a fact about the view
// this design is compiled against, which is checkable, and not a claim about
// what the Liberty format is capable of in general, which is not what we
// measured. So the Liberty-layer prediction for the entire ladder is EXACTLY ZERO
// delay difference across all four codes.
//
// That is not a gap to apologize for. It is the sharpest model-discrimination
// test on this chip: one model layer says the knob does nothing, extraction and
// transistor-level SPICE say it does something specific, and silicon arbitrates.
// The prediction for this structure must come from SPICE, and the Liberty
// prediction of zero is written down as a prediction, not as an omission.
//
// src/char_paths.v carries two fixed chains that differ ONLY in whether these
// enables are tied high or low, so the mechanism is measured in isolation from
// everything the configurable fabric adds.
//
// The permanently enabled keeper is not decoration. Without it the shared sink
// floats whenever the ladder is off, and a floating gate input on a real die is
// a static current path, not merely an X in simulation. Every element inverts
// the same node, so they can never disagree and the sink can never see
// contention.

`timescale 1ns / 1ps
`default_nettype none

module load_ladder (
    input  wire       node,   // the node whose loading is modulated
    input  wire [2:0] en,     // en[0] the drive-1 element, en[1] drive-2, en[2] drive-4
    output wire       mon     // witnesses that the enables are decoded and reach here
);

  wire sk;
  cell_inv   #(.DRIVE(1))     keep (.A(node), .Y(sk));
  cell_einvn #(.DRIVE(1)) ld1 (.A(node), .EN(en[0]), .Z(sk));
  cell_einvn #(.DRIVE(2)) ld2 (.A(node), .EN(en[1]), .Z(sk));
  cell_einvn #(.DRIVE(4)) ld4 (.A(node), .EN(en[2]), .Z(sk));

  wire sk_buf;
  cell_inv #(.DRIVE(1)) snk (.A(sk), .Y(sk_buf));

  // mon witnesses that the ladder field is decoded and that the decode reaches
  // this instance. It cannot witness that the enables reach the einvn TE_B
  // pins, because on a correct design every element drives the same logic
  // value; that connection is checked structurally on the synthesized netlist
  // by tools/check_netlist.py, and electrically on the die by the difference
  // between the two fixed chains in src/char_paths.v.
  wire m1, m2;
  cell_xor2 mon_a (.A(sk_buf), .B(en[0]), .X(m1));
  cell_xor2 mon_b (.A(m1),     .B(en[1]), .X(m2));
  cell_xor2 mon_c (.A(m2),     .B(en[2]), .X(mon));

endmodule
