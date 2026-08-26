# LINK_PROTOCOL — host to firmware framing

WP3 item 1 asks for the scan protocol frame format. There are two protocols and
conflating them is the mistake this document exists to prevent.

**The scan frame** is what goes down the chip's scan chain. It is defined in
src/scan_config.v and harness/evofab/genome.py and it is
`[global 16][site 0..N-1 : 12 each][crc 8]`, shifted MSB first.

**The link frame** is what goes over the wire between the host and the
firmware, whether that firmware is an RP2040 driving the fabricated chip, an
MCU next to the iCE40 pilot, or a stub. It carries scan frames but it is not
one.

## The constraint that shapes it

docs/THROUGHPUT.md: stimulus generation, scoring and the inner loop live in
firmware, and a host round trip per input vector collapses throughput by 10x to
100x. So the link carries genomes down and scores up, and never an input vector
in either direction. If a future revision needs to send a stimulus pattern, it
sends the whole pattern once as configuration, not per trial.

The second constraint is that a batch is the unit. One request carries a whole
generation, because the host must never be in a position where it can go one
trial at a time without noticing.

## Framing

Byte oriented, little endian, designed to be trivially implementable in C on an
RP2040 and equally trivial to resynchronise after a reset at either end.

    SYNC   2 bytes   0xE7 0xFA   fixed, never appears as a length prefix
    VER    1 byte    protocol version, currently 1
    TYPE   1 byte    see below
    LEN    2 bytes   payload length in bytes, max 4096
    PAYLOAD LEN bytes
    CRC    2 bytes   CRC-16/CCITT-FALSE over VER, TYPE, LEN and PAYLOAD

The link CRC is separate from the scan chain's CRC-8 and neither substitutes for
the other. The link CRC protects the wire. The scan CRC protects the chip, is
checked by the chip, and gates the load in hardware. A host that computes the
scan CRC for the firmware would defeat the property that a corrupt frame cannot
reach the fabric, so the firmware forwards the scan frame's CRC byte exactly as
the host built it and never recomputes it.

## Message types

| TYPE | name | direction | payload |
|---|---|---|---|
| 0x01 | HELLO | host to device | none |
| 0x81 | HELLO_ACK | device to host | firmware version string, device id, n_sites, clock Hz |
| 0x02 | RUN_BATCH | host to device | count (2 bytes) then that many scan frames, each length-prefixed |
| 0x82 | BATCH_RESULT | device to host | count (2 bytes) then that many result records |
| 0x03 | SET_PARAM | host to device | key (1 byte), value (4 bytes) |
| 0x04 | ABORT | host to device | none, drives the external kill and clears arm |
| 0x84 | FAULT | device to host | reason code, trial index, whatever state is safe to report |

A result record is fixed width so the firmware can emit it without allocation.

    trial_index      4 bytes
    fitness_num      4 bytes    integer numerator, the host divides
    freq_count       4 bytes
    trans_count      4 bytes
    temp_proxy       4 bytes    on-chip ring monitor count, the PVT covariate
    flags            1 byte     bit0 crc_ok, bit1 tripped, bit2 inert, bit3 window_expired
    reserved         3 bytes

Fitness crosses the wire as an integer numerator, not a float. The firmware has
no business choosing a floating point representation, and an integer count is
exactly reproducible when the same trial is re-analysed later.

`temp_proxy` is not optional and is not a nicety. The standing lesson is that a
comparison whose arms were taken in different thermal windows is fiction, so the
covariate that lets a later analysis detect that is recorded per trial, by the
device, not inferred by the host from a clock.

## Failure behavior

- A bad link CRC is dropped silently and the host times out and retries the
  whole batch. Partial batches are never accepted, because a partial batch that
  looks complete is how a search ends up scoring genomes it never ran.
- Resynchronisation after a reset at either end is automatic, and it is driven
  by the CRC, not by hunting for SYNC inside a payload. SYNC is not escaped and
  a payload may legitimately contain it, so a decoder that abandoned a frame on
  an embedded SYNC would corrupt legitimate traffic. When a frame fails its CRC
  the decoder skips that SYNC and nothing else. It specifically does not skip
  the length the bad header claimed, because trusting a length field that just
  failed its own checksum is how a truncated frame swallows the good frame that
  follows it. The cost is bounded: a garbage header can make the decoder wait
  for at most MAX_PAYLOAD more bytes, which the host's batch timeout covers.
- ABORT is honoured at any point, including mid-batch, and the device replies
  with FAULT rather than BATCH_RESULT so the host cannot mistake an aborted
  batch for a completed one.
- The device never retries a trial on its own. A retry that the host does not
  know about is an unrecorded repeat, and the noise floor study depends on
  knowing exactly how many times each configuration was measured.

## Status

Specified here, implemented in harness/evofab/link.py, and exercised against a
loopback stub. The firmware side is written when there is a board to write it
for. The point of specifying it now is that the RTL must expose what this
protocol needs, and the RTL is what gets frozen in WP4.
