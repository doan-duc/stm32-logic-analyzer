from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

CHANNEL_COUNT = 8
FRAME_MAGIC = b"SLA8"
PAYLOAD_FORMAT_BITPACKED_U8 = 1


@dataclass
class DecodeEvent:
    timestamp_us: float
    protocol: str
    event_type: str
    channels: tuple[int, ...] = field(default_factory=tuple)
    value: Any = None
    raw_bits: list[int] | None = None
    warning: str | None = None
    error: str | None = None


def require_channel(channel: int) -> None:
    if not 0 <= channel < CHANNEL_COUNT:
        raise ValueError(f"channel must be 0..7, got {channel}")


def sample_bit(sample: int, channel: int) -> int:
    require_channel(channel)
    return (int(sample) >> channel) & 0x01


def channel_bits(samples: Sequence[int] | bytes | bytearray, channel: int) -> list[int]:
    require_channel(channel)
    return [sample_bit(sample, channel) for sample in samples]


def pack_channels(rows: Iterable[Sequence[int]]) -> bytes:
    out = bytearray()
    for row in rows:
        if len(row) != CHANNEL_COUNT:
            raise ValueError("each row must contain exactly 8 channel values")
        value = 0
        for ch, bit in enumerate(row):
            if bit:
                value |= 1 << ch
        out.append(value)
    return bytes(out)


def timestamp_us(sample_index: int, sample_rate_hz: int) -> float:
    if sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be > 0")
    return sample_index * 1_000_000.0 / sample_rate_hz

