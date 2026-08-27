# Makefile
# See https://docs.cocotb.org/en/stable/quickstart.html for more info

# defaults
SIM ?= icarus
FST ?= -fst
TOPLEVEL_LANG ?= verilog
SRC_DIR = $(PWD)/../src
PROJECT_SOURCES = cells.v drive_node.v fabric_site.v calib_macro.v char_paths.v tdc.v scan_config.v freq_counter.v project.v

# Site count under test. The default MUST match the `define default in
# src/project.v, because the gate-level run has no way to be told: it simulates
# whatever netlist the flow built. test/test.py reads the same environment
# variable with the same default, and asserts the count the chip reports back
# through readout_sel 7, so a drift between the three fails a test instead of
# silently rotating every genome.
N_SITES ?= 24
export N_SITES

ifneq ($(GATES),yes)

# RTL simulation.
# SIM swaps the hand-instantiated sky130 cells for behavioral equivalents and
# breaks the deliberate combinational loop with a register, because an event
# simulator cannot settle either one. The real cells and the real loop are
# exercised by the gate-level run below, after the GDS build.
SIM_BUILD				= sim_build/rtl
COMPILE_ARGS    += -DSIM
COMPILE_ARGS    += -DN_SITES=$(N_SITES)
VERILOG_SOURCES += $(addprefix $(SRC_DIR)/,$(PROJECT_SOURCES))

else

# Gate level simulation.
SIM_BUILD				= sim_build/gl
COMPILE_ARGS    += -DGL_TEST
COMPILE_ARGS    += -DFUNCTIONAL
COMPILE_ARGS    += -DUSE_POWER_PINS
COMPILE_ARGS    += -DSIM
COMPILE_ARGS    += -DUNIT_DELAY=\#1
VERILOG_SOURCES += $(PDK_ROOT)/sky130A/libs.ref/sky130_fd_sc_hd/verilog/primitives.v
VERILOG_SOURCES += $(PDK_ROOT)/sky130A/libs.ref/sky130_fd_sc_hd/verilog/sky130_fd_sc_hd.v

# this gets copied in by the GDS action workflow
VERILOG_SOURCES += $(PWD)/gate_level_netlist.v

endif

COMPILE_ARGS 		+= -I$(SRC_DIR)

VERILOG_SOURCES += $(PWD)/tb.v
TOPLEVEL = tb

COCOTB_TEST_MODULES = test

include $(shell cocotb-config --makefiles)/Makefile.sim
