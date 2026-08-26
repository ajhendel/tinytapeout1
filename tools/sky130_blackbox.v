// Blackbox stubs for the sky130_fd_sc_hd cells this design hand-instantiates.
//
// Used ONLY by tools/area_sweep.sh and tools/check_netlist.py so that yosys can
// elaborate the design on a machine that has no PDK installed. These stubs are
// never part of the submission; LibreLane reads the real Liberty. Port names are
// taken from github.com/google/skywater-pdk-libs-sky130_fd_sc_hd.

`default_nettype none

(* blackbox *) module sky130_fd_sc_hd__inv_1   (input A, output Y); endmodule
(* blackbox *) module sky130_fd_sc_hd__inv_2   (input A, output Y); endmodule
(* blackbox *) module sky130_fd_sc_hd__inv_4   (input A, output Y); endmodule
(* blackbox *) module sky130_fd_sc_hd__inv_8   (input A, output Y); endmodule

(* blackbox *) module sky130_fd_sc_hd__nand2_1 (input A, input B, output Y); endmodule
(* blackbox *) module sky130_fd_sc_hd__nand2_2 (input A, input B, output Y); endmodule
(* blackbox *) module sky130_fd_sc_hd__nand2_4 (input A, input B, output Y); endmodule
(* blackbox *) module sky130_fd_sc_hd__nor2_1  (input A, input B, output Y); endmodule
(* blackbox *) module sky130_fd_sc_hd__and2_1  (input A, input B, output X); endmodule
(* blackbox *) module sky130_fd_sc_hd__or2_1   (input A, input B, output X); endmodule
(* blackbox *) module sky130_fd_sc_hd__xor2_1  (input A, input B, output X); endmodule
(* blackbox *) module sky130_fd_sc_hd__xnor2_1 (input A, input B, output Y); endmodule

(* blackbox *) module sky130_fd_sc_hd__mux2_1  (input A0, input A1, input S, output X); endmodule
(* blackbox *) module sky130_fd_sc_hd__mux4_1  (input A0, input A1, input A2, input A3,
                                                input S0, input S1, output X); endmodule

(* blackbox *) module sky130_fd_sc_hd__einvn_1 (input A, input TE_B, output Z); endmodule
(* blackbox *) module sky130_fd_sc_hd__einvn_2 (input A, input TE_B, output Z); endmodule
(* blackbox *) module sky130_fd_sc_hd__einvn_4 (input A, input TE_B, output Z); endmodule
(* blackbox *) module sky130_fd_sc_hd__einvn_8 (input A, input TE_B, output Z); endmodule
