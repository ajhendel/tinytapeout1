# harness — the search loop, the genome, and the results database

WP3 items 1 and 2 from HANDOFF.md. This is the software that will drive the FPGA
pilot, the FPGA control arm, and the fabricated chip, through one interface.

## The rule this is built around

docs/THROUGHPUT.md says the fitness loop must live in RP2040 firmware and that a
host round trip per input vector collapses throughput by 10x to 100x. That is a
claim about where code runs, so the code is split accordingly and the split is
enforced by the type system rather than by discipline.

- `evofab/genome.py` encodes and decodes the configuration, and validates it for
  structural safety before anything is allowed to reach a device.
- `evofab/device.py` is the device interface. One trial in, one score out. Every
  implementation of it must do stimulus, scoring and accumulation on the far
  side of the link, never per vector across it.
- `evofab/search.py` is the outer loop. It never sees an input vector.
- `evofab/store.py` is the results database, with the reproducibility metadata
  the design review asked for on every single row.
- `evofab/link.py` is the host to firmware framing, specified in
  docs/LINK_PROTOCOL.md. It never recomputes a scan CRC, because a host or
  firmware that did would destroy the property that a corrupt frame cannot reach
  the fabric.
- `evofab/holdout.py` enforces the holdout discipline from PLAN.md section 2.
  The guard sits on the DEVICE, not inside the search loop, because a check
  inside the search is a check that a second search, or a one-off script someone
  writes at midnight, will not have.

## Devices

- `SimDevice` scores against a Python model of the fabric. No hardware. Used to
  develop mutation operators and to test the search itself.
- `IcarusDevice` scores against the actual Verilog through cocotb, which makes
  the genome encoder and the scan frame format testable against the RTL that
  will be fabricated. This is what catches an off-by-one in the chain before it
  is in silicon.
- `SerialDevice` talks to a real board over a framed serial protocol. The same
  frame format serves the iCE40 pilot, the FPGA control arm and the RP2040
  driving the fabricated chip.

## What is deliberately not here

No fitness function that needs the host in the inner loop. If you find yourself
wanting one, that is the trap docs/THROUGHPUT.md names, and the answer is to
move the scoring into the device.
