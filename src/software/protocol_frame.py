from __future__ import annotations

from dataclasses import dataclass

try:
    from .common import CHANNEL_COUNT, FRAME_MAGIC, PAYLOAD_FORMAT_BITPACKED_U8
except ImportError:
    from common import CHANNEL_COUNT, FRAME_MAGIC, PAYLOAD_FORMAT_BITPACKED_U8

# Định nghĩa các hằng số giao thức
FRAME_VERSION = 2                    # Phiên bản gói tin
HEADER_LENGTH = 48                   # Chiều dài của Header gói tin (48 byte)
HEADER_CHECKSUM_OFFSET = 40          # Vị trí đặt Checksum Header trong mảng Header (byte thứ 40)
PAYLOAD_CHECKSUM_OFFSET = 44         # Vị trí đặt Checksum Payload trong mảng Header (byte thứ 44)

# Các mặt nạ bit của cờ lỗi trạng thái
FRAME_FLAG_OVERFLOW = 0x00000001
FRAME_FLAG_NO_TRIGGER = 0x00000002
FRAME_FLAG_ERROR = 0x00000004


class FrameError(ValueError):
    """Lớp ngoại lệ (Exception) định nghĩa riêng cho các lỗi liên quan đến cấu trúc khung gói tin (Frame)."""
    pass


@dataclass
class LogicAnalyzerFrame:
    """
    Lớp chứa toàn bộ thông tin của một gói tin Logic Analyzer đã được giải mã đầy đủ (Header + Payload).
    """
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
    """
    Lớp cấu trúc đóng băng (read-only) chỉ lưu thông tin giải mã từ Header 48 byte của gói tin.
    """
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
    """
    Tính toán mã kiểm tra lỗi Checksum 32-bit bằng thuật toán băm FNV-1a.
    Thuật toán này đồng bộ với hàm la_checksum32 ở phía firmware của MCU.
    """
    checksum = 2166136261
    for value in data:
        checksum ^= value
        checksum = (checksum * 16777619) & 0xFFFFFFFF
    return checksum


def _u16(data: bytes, offset: int) -> int:
    """Đọc số nguyên không dấu 16-bit kiểu Little Endian từ mảng byte tại vị trí offset."""
    return int.from_bytes(data[offset : offset + 2], "little", signed=False)


def _u32(data: bytes, offset: int) -> int:
    """Đọc số nguyên không dấu 32-bit kiểu Little Endian từ mảng byte tại vị trí offset."""
    return int.from_bytes(data[offset : offset + 4], "little", signed=False)


def _i32(data: bytes, offset: int) -> int:
    """Đọc số nguyên có dấu 32-bit kiểu Little Endian từ mảng byte tại vị trí offset."""
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
    """
    Mã hóa thông tin và mảng mẫu đo thành một chuỗi bytes gói tin nhị phân chuẩn (Header + Payload).
    Thường dùng để tạo các file lưu trữ hoặc giả lập dữ liệu phần cứng.
    """
    if sample_rate_hz <= 0:
        raise FrameError("sample_rate_hz must be > 0")
    payload = bytes(samples)
    header = bytearray(HEADER_LENGTH)
    
    # Ghi các thông tin vào Header
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
    
    # Tính toán Checksum cho Header và Payload
    header_checksum = checksum32(header[:HEADER_CHECKSUM_OFFSET])
    payload_checksum = checksum32(payload)
    
    # Ghi các mã Checksum vào các byte cuối của Header
    header[HEADER_CHECKSUM_OFFSET:HEADER_CHECKSUM_OFFSET + 4] = header_checksum.to_bytes(4, "little")
    header[PAYLOAD_CHECKSUM_OFFSET:PAYLOAD_CHECKSUM_OFFSET + 4] = payload_checksum.to_bytes(4, "little")
    
    return bytes(header) + payload


def decode_frame_header(
    data: bytes | bytearray | memoryview,
    *,
    max_samples: int | None = None,
) -> LogicAnalyzerFrameHeader:
    """
    Giải mã và xác minh tính toàn vẹn của Header gói tin (48 byte đầu tiên).
    
    max_samples: Giới hạn an toàn tối đa của số mẫu đo được chấp nhận (tránh lỗi cấp phát quá nhiều RAM).
    """
    blob = bytes(data)
    if len(blob) < HEADER_LENGTH:
        raise FrameError("truncated header")
    header = blob[:HEADER_LENGTH]
    
    # Xác thực Magic String "SLA8"
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
    
    # Xác thực Checksum của Header
    if checksum32(header[:HEADER_CHECKSUM_OFFSET]) != expected_header_checksum:
        raise FrameError("header checksum mismatch")
        
    # Xác thực giới hạn số lượng mẫu đo
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
    """
    Giải mã toàn bộ gói tin nhị phân (Header + Payload) thành đối tượng LogicAnalyzerFrame.
    Thực hiện kiểm tra tính toàn vẹn của cả Header và Payload bằng mã Checksum.
    """
    blob = bytes(data)
    # 1. Giải mã Header để lấy thông tin kích thước Payload
    header = decode_frame_header(blob)
    total_samples = header.total_samples
    expected_length = HEADER_LENGTH + total_samples
    
    # 2. Kiểm tra kích thước gói tin thực tế có khớp không
    if len(blob) < expected_length:
        raise FrameError("truncated payload")
    if len(blob) > expected_length:
        raise FrameError("payload length mismatch")
        
    payload = blob[HEADER_LENGTH:expected_length]
    
    # 3. Xác thực Checksum của Payload
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
