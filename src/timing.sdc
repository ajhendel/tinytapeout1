# Timing constraints for tt_um_ajhendel_evofab.
#
# WHY THIS FILE EXISTS
#
# The trial place and route reported its worst setup path as ui_in[5] to
# uo_out[6], which is FAB_B entering the fabric, propagating through every site
# in the column, and leaving at the load-ladder observable. Static timing
# analysis is right that this path is long. It is wrong that it is a violation.
#
# The fabric is a deliberately deep, configurable combinational network whose
# propagation delay is the quantity the chip exists to measure. It sits in no
# clocked path. The measurement protocol loads a configuration, sets the inputs,
# and waits for a window of between 16 and 524,288 clocks before reading
# anything. Constraining that network to settle inside one 20 ns clock would be
# constraining the measurand, and the flow would spend its effort inserting
# repair buffers into the very network whose delay we intend to characterize
# against the open-PDK models.
#
# So the fabric's asynchronous ports are declared as such. Everything else, the
# scan chain, the CRC, the safety controller, the window and the counters, is
# ordinary synchronous logic and is timed normally. That is deliberate: the
# safety controller is the part that must be correct at speed, and nothing here
# relaxes it.
#
# WHAT IS SAFE ABOUT THIS
#
# A false path disables hold checking as well as setup, so it is only safe where
# the destination does not need either. Every consumer of a fabric signal is
# asynchronous by construction.
#   uo_out[2] FAB_OUT     goes to a pin, read by a host that has already waited
#   uo_out[3] OBS_OUT     goes to a pin, for a scope or a frequency counter
#   uo_out[6] LOAD_MON    goes to a pin, the ladder reach witness
#   the safety activity monitor takes the fabric through a three-stage
#     synchronizer, which is what makes a metastable sample harmless, and which
#     exists precisely because this signal is asynchronous
#   the frequency counter is CLOCKED by the fabric or ring node, so it is a
#     clock domain crossing and not a data path at all
#
# uo_out[0] SCAN_OUT, uo_out[1] CRC_OK, uo_out[4] MEAS_BUSY, uo_out[5] TRIPPED,
# uo_out[7] INERT and the whole uio readout bus come from registers and stay
# timed. Do not add them here.

current_design tt_um_ajhendel_evofab

###############################################################################
# Clock
###############################################################################
create_clock -name clk -period 20.0000 [get_ports {clk}]
set_clock_transition 0.1500 [get_clocks {clk}]
set_clock_uncertainty 0.2500 clk
set_propagated_clock [get_clocks {clk}]

###############################################################################
# IO delays
###############################################################################
set_input_delay 4.0000 -clock [get_clocks {clk}] -add_delay [get_ports {ena}]
set_input_delay 4.0000 -clock [get_clocks {clk}] -add_delay [get_ports {rst_n}]
for {set i 0} {$i < 8} {incr i} {
    set_input_delay  4.0000 -clock [get_clocks {clk}] -add_delay [get_ports "ui_in\[$i\]"]
    set_input_delay  4.0000 -clock [get_clocks {clk}] -add_delay [get_ports "uio_in\[$i\]"]
    set_output_delay 4.0000 -clock [get_clocks {clk}] -add_delay [get_ports "uo_out\[$i\]"]
    set_output_delay 4.0000 -clock [get_clocks {clk}] -add_delay [get_ports "uio_out\[$i\]"]
    set_output_delay 4.0000 -clock [get_clocks {clk}] -add_delay [get_ports "uio_oe\[$i\]"]
}

###############################################################################
# The fabric, declared asynchronous. See the note at the top of this file.
###############################################################################
# FAB_A and FAB_B are the fabric's data inputs. They are set by the host and
# then left alone for the whole measurement window.
set_false_path -from [get_ports {ui_in[4]}]
set_false_path -from [get_ports {ui_in[5]}]
# OBS_SEL only steers the observation multiplexer that feeds a scope pin.
set_false_path -from [get_ports {ui_in[6]}]
# ena is Tiny Tapeout's project-select line. The mux asserts it when this
# project is selected and it is static for the whole time the project is in use,
# so it is not a signal that has to settle within a clock. It reaches the fabric
# because it gates ARM, which gates inert, which gates every drive enable, and
# that is exactly the safety chain we want it in. After the fabric's own ports
# were declared asynchronous this was the single remaining violator in the whole
# design, at -4.53 ns and only at the slow corner.
#
# rst_n is deliberately NOT here. It looks similar and is not: reset recovery
# and removal are real checks and the safety controller depends on them.
set_false_path -from [get_ports {ena}]
# The three fabric observables, all of which go to pins.
set_false_path -to [get_ports {uo_out[2]}]
set_false_path -to [get_ports {uo_out[3]}]
set_false_path -to [get_ports {uo_out[6]}]

###############################################################################
# Environment
###############################################################################
set_load -pin_load 0.0334 [all_outputs]
set_driving_cell -lib_cell sky130_fd_sc_hd__inv_2 -pin {Y} \
    -input_transition_rise 0.0000 -input_transition_fall 0.0000 [all_inputs]

###############################################################################
# Design rules
###############################################################################
set_max_transition 0.7500 [current_design]
set_max_capacitance 0.2000 [current_design]
set_max_fanout 10.0000 [current_design]
