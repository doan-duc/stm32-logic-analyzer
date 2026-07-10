from __future__ import annotations

from dataclasses import dataclass

try:
    from .common import CHANNEL_COUNT, FRAME_MAGIC, PAYLOAD_FORMAT_BITPACKED_U8
except ImportError:
    from common import CHANNEL_COUNT, FRAME_MAGIC, PAYLOAD_FORMAT_BITPACKED_U8

FRAME_VERSION = 2
HEADER_LENGTH = 48
HEADER_CHECKSUM_OFFSET = 40
PAYLOAD_CHECKSUM_OFFSET = 44
FRAME_FLAG_OVERFLOW = 0x00000001
FRAME_FLAG_NO_TRIGGER = 0x00000002
FRAME_FLAG_ERROR = 0x00000004


class FrameError(ValueError):
    pass


@dataclass
class LogicAnalyzerFrame:
    sample_rate_hz: int
    samples: bytes
    trigger_index: int = -1
    actual_sample_rate_hz: int | None = None
    flags: int = 0
    overflow_count: int = 0
    dropped_samples: int = 0
    channel_count: int = CHANNEL_COUNT
    payload_format: int = PAYLOAD_FORMAT_BITPACKED_U8
    header_checksum: int = 0
    payload_checksum: int = 0


@dataclass(frozen=True)
class LogicAnalyzerFrameHeader:
    sample_rate_hz: int
    actual_sample_rate_hz: int
    total_samples: int
    trigger_index: int
    flags: int
    overflow_count: int
    dropped_samples: int
    channel_count: int
    payload_format: int
    header_checksum: int
    payload_checksum: int


def checksum32(data: bytes | bytearray | memoryview) -> int:
    checksum = 2166136261
    for value in data:
        checksum ^= value
        checksum = (checksum * 16777619) & 0xFFFFFFFF
    return checksum


def _u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], "little", signed=False)


def _u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "little", signed=False)


def _i32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "little", signed=True)


def encode_frame(
    samples: bytes | bytearray | list[int],
    sample_rate_hz: int,
    trigger_index: int = -1,
    actual_sample_rate_hz: int | None = None,
    flags: int = 0,
    overflow_count: int = 0,
    dropped_samples: int = 0,
) -> bytes:
    if sample_rate_hz <= 0:
        raise FrameError("sample_rate_hz must be > 0")
    payload = bytes(samples)
    header = bytearray(HEADER_LENGTH)
    header[0:4] = FRAME_MAGIC
    header[4] = FRAME_VERSION
    header[5:7] = HEADER_LENGTH.to_bytes(2, "little")
    header[7] = CHANNEL_COUNT
    header[8:12] = int(sample_rate_hz).to_bytes(4, "little")
    header[12:16] = int(actual_sample_rate_hz or sample_rate_hz).to_bytes(4, "little")
    header[16:20] = len(payload).to_bytes(4, "little")
    header[20:24] = int(trigger_index).to_bytes(4, "little", signed=True)
    header[24:28] = int(flags).to_bytes(4, "little")
    header[28] = PAYLOAD_FORMAT_BITPACKED_U8
    header[32:36] = int(overflow_count).to_bytes(4, "little")
    header[36:40] = int(dropped_samples).to_bytes(4, "little")
    header_checksum = checksum32(header[:HEADER_CHECKSUM_OFFSET])
    payload_checksum = checksum32(payload)
    header[HEADER_CHECKSUM_OFFSET:HEADER_CHECKSUM_OFFSET + 4] = header_checksum.to_bytes(4, "little")
    header[PAYLOAD_CHECKSUM_OFFSET:PAYLOAD_CHECKSUM_OFFSET + 4] = payload_checksum.to_bytes(4, "little")
    return bytes(header) + payload


def decode_frame_header(
    data: bytes | bytearray | memoryview,
    *,
    max_samples: int | None = None,
) -> LogicAnalyzerFrameHeader:
    """Validate a wire header before its payload length is trusted."""
    blob = bytes(data)
    if len(blob) < HEADER_LENGTH:
        raise FrameError("truncated header")
    header = blob[:HEADER_LENGTH]
    if header[:4] != FRAME_MAGIC:
        raise FrameError("wrong magic")
    version = header[4]
    if version != FRAME_VERSION:
        raise FrameError(f"unsupported version {version}")
    header_length = _u16(header, 5)
    if header_length != HEADER_LENGTH:
        raise FrameError("wrong header length")
    channel_count = header[7]
    if channel_count != CHANNEL_COUNT:
        raise FrameError("wrong channel count")
    sample_rate_hz = _u32(header, 8)
    if sample_rate_hz == 0:
        raise FrameError("sample_rate_hz is zero")
    actual_sample_rate_hz = _u32(header, 12)
    if actual_sample_rate_hz == 0:
        raise FrameError("actual_sample_rate_hz is zero")
    total_samples = _u32(header, 16)
    trigger_index = _i32(header, 20)
    flags = _u32(header, 24)
    payload_format = header[28]
    if payload_format != PAYLOAD_FORMAT_BITPACKED_U8:
        raise FrameError("unsupported payload format")
    overflow_count = _u32(header, 32)
    dropped_samples = _u32(header, 36)
    expected_header_checksum = _u32(header, HEADER_CHECKSUM_OFFSET)
    expected_payload_checksum = _u32(header, PAYLOAD_CHECKSUM_OFFSET)
    if checksum32(header[:HEADER_CHECKSUM_OFFSET]) != expected_header_checksum:
        raise FrameError("header checksum mismatch")
    if max_samples is not None:
        if max_samples < 0:
            raise ValueError("max_samples must be >= 0")
        if total_samples > max_samples:
            raise FrameError(
                f"sample count exceeds safe limit ({total_samples} > {max_samples})"
            )
    return LogicAnalyzerFrameHeader(
        sample_rate_hz=sample_rate_hz,
        actual_sample_rate_hz=actual_sample_rate_hz,
        total_samples=total_samples,
        trigger_index=trigger_index,
        flags=flags,
        overflow_count=overflow_count,
        dropped_samples=dropped_samples,
        channel_count=channel_count,
        payload_format=payload_format,
        header_checksum=expected_header_checksum,
        payload_checksum=expected_payload_checksum,
    )


def decode_frame(data: bytes | bytearray | memoryview) -> LogicAnalyzerFrame:
    blob = bytes(data)
    header = decode_frame_header(blob)
    total_samples = header.total_samples
    expected_length = HEADER_LENGTH + total_samples
    if len(blob) < expected_length:
        raise FrameError("truncated payload")
    if len(blob) > expected_length:
        raise FrameError("payload length mismatch")
    payload = blob[HEADER_LENGTH:expected_length]
    if checksum32(payload) != header.payload_checksum:
        raise FrameError("payload checksum mismatch")
    return LogicAnalyzerFrame(
        sample_rate_hz=header.sample_rate_hz,
        samples=payload,
        trigger_index=header.trigger_index,
        actual_sample_rate_hz=header.actual_sample_rate_hz,
        flags=header.flags,
        overflow_count=header.overflow_count,
        dropped_samples=header.dropped_samples,
        channel_count=header.channel_count,
        payload_format=header.payload_format,
        header_checksum=header.header_checksum,
        payload_checksum=header.payload_checksum,
    )
