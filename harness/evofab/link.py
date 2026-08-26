"""Host to firmware link framing. See docs/LINK_PROTOCOL.md for the spec.

Two protocols live in this project and conflating them would be expensive.

  The SCAN frame goes down the chip's scan chain and is defined in genome.py.
  The LINK frame goes over the wire and carries scan frames.

The link CRC protects the wire. The scan CRC protects the chip, is checked by
the chip in hardware, and gates the load. This module never recomputes a scan
CRC. A firmware or host that recomputed it would destroy the property that a
corrupt frame cannot reach the fabric, which is the property the whole safety
argument rests on.
"""

from __future__ import annotations

import dataclasses
import struct
from typing import Iterable, Sequence

SYNC = b"\xE7\xFA"
VERSION = 1
MAX_PAYLOAD = 4096

# Message types
HELLO = 0x01
HELLO_ACK = 0x81
RUN_BATCH = 0x02
BATCH_RESULT = 0x82
SET_PARAM = 0x03
ABORT = 0x04
FAULT = 0x84

RESULT_STRUCT = struct.Struct("<IiIII B 3x")   # 24 bytes, see docs/LINK_PROTOCOL.md

FLAG_CRC_OK = 0x01
FLAG_TRIPPED = 0x02
FLAG_INERT = 0x04
FLAG_WINDOW_EXPIRED = 0x08


def crc16_ccitt_false(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
    return crc


class FrameError(Exception):
    pass


def encode(msg_type: int, payload: bytes = b"") -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise FrameError(f"payload {len(payload)} exceeds {MAX_PAYLOAD}")
    head = struct.pack("<BBH", VERSION, msg_type, len(payload))
    return SYNC + head + payload + struct.pack("<H", crc16_ccitt_false(head + payload))


def decode_stream(buf: bytearray) -> list[tuple[int, bytes]]:
    """Pull every complete frame out of buf, consuming what it uses.

    Resynchronisation is by scanning for SYNC and validating with the CRC, which
    is what makes a reset at either end recoverable without a handshake. Three
    rules make it actually work and the first was put here by a failing test.

    1. A frame whose CRC does not match causes a skip of the SYNC only, two
       bytes, and NOT of the length that the bad header claimed. Trusting a
       length field that just failed its own checksum is how a truncated frame
       followed by a good one swallows the good one, so the good one is never
       seen and the host retries forever.

    2. A frame whose CRC does not match is dropped, never repaired and never
       partially delivered. A partial batch that looks complete is how a search
       ends up scoring genomes it never ran.

    3. SYNC is not escaped and a payload may legitimately contain it, which is
       why reframing is driven by the CRC rather than by hunting for SYNC inside
       a payload. The cost is that a garbage header claiming a large length
       makes the decoder wait for up to MAX_PAYLOAD more bytes before it can
       reject it. That is bounded, and the host's batch timeout covers it.
    """
    out: list[tuple[int, bytes]] = []
    search = 0
    while True:
        i = buf.find(SYNC, search)
        if i < 0:
            del buf[:max(0, len(buf) - 1)]   # a trailing byte may be half a SYNC
            return out
        if len(buf) - i < 6:
            del buf[:i]
            return out
        ver, msg_type, length = struct.unpack("<BBH", buf[i + 2:i + 6])
        if ver != VERSION or length > MAX_PAYLOAD:
            search = i + 2
            continue
        total = 6 + length + 2
        if len(buf) - i < total:
            del buf[:i]
            return out
        body = bytes(buf[i + 2:i + 6 + length])
        got, = struct.unpack("<H", buf[i + 6 + length:i + total])
        if got != crc16_ccitt_false(body):
            search = i + 2
            continue
        out.append((msg_type, body[4:]))
        del buf[:i + total]
        search = 0


def encode_run_batch(frames_bits: Sequence[Sequence[int]]) -> bytes:
    """Pack scan frames. Each is a bit list, MSB first, as the chain wants it.

    The bit count is sent explicitly because a scan chain is not a whole number
    of bytes and the firmware must shift exactly as many bits as the chip
    expects. Padding to a byte and letting the firmware guess is how a genome
    gets rotated.
    """
    parts = [struct.pack("<H", len(frames_bits))]
    for bits in frames_bits:
        nbits = len(bits)
        blob = bytearray((nbits + 7) // 8)
        for i, b in enumerate(bits):
            if b:
                blob[i >> 3] |= 0x80 >> (i & 7)
        parts.append(struct.pack("<H", nbits))
        parts.append(bytes(blob))
    return b"".join(parts)


def decode_run_batch(payload: bytes) -> list[list[int]]:
    count, = struct.unpack("<H", payload[:2])
    off = 2
    frames = []
    for _ in range(count):
        nbits, = struct.unpack("<H", payload[off:off + 2])
        off += 2
        nbytes = (nbits + 7) // 8
        blob = payload[off:off + nbytes]
        off += nbytes
        frames.append([(blob[i >> 3] >> (7 - (i & 7))) & 1 for i in range(nbits)])
    return frames


@dataclasses.dataclass(frozen=True)
class ResultRecord:
    trial_index: int
    fitness_num: int
    freq_count: int
    trans_count: int
    temp_proxy: int
    flags: int

    @property
    def crc_ok(self) -> bool:
        return bool(self.flags & FLAG_CRC_OK)

    @property
    def tripped(self) -> bool:
        return bool(self.flags & FLAG_TRIPPED)

    def pack(self) -> bytes:
        return RESULT_STRUCT.pack(self.trial_index, self.fitness_num,
                                  self.freq_count, self.trans_count,
                                  self.temp_proxy, self.flags)

    @classmethod
    def unpack(cls, raw: bytes) -> "ResultRecord":
        return cls(*RESULT_STRUCT.unpack(raw))


def encode_batch_result(records: Sequence[ResultRecord]) -> bytes:
    return struct.pack("<H", len(records)) + b"".join(r.pack() for r in records)


def decode_batch_result(payload: bytes) -> list[ResultRecord]:
    count, = struct.unpack("<H", payload[:2])
    size = RESULT_STRUCT.size
    if len(payload) != 2 + count * size:
        raise FrameError(
            f"batch result claims {count} records but carries "
            f"{(len(payload) - 2) / size:.2f}; refusing a partial batch")
    return [ResultRecord.unpack(payload[2 + i * size:2 + (i + 1) * size])
            for i in range(count)]
