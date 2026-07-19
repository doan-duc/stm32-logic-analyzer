from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

# Số lượng kênh đo Logic Analyzer mặc định (8 kênh)
CHANNEL_COUNT = 8

# Chuỗi byte ma thuật xác thực khung dữ liệu
FRAME_MAGIC = b"SLA8"

# Định dạng dữ liệu nén: 8 kênh đóng gói trong 1 byte (uint8)
PAYLOAD_FORMAT_BITPACKED_U8 = 1


@dataclass
class DecodeEvent:
    """
    Lớp dữ liệu lưu trữ thông tin về một sự kiện giải mã giao thức (ví dụ: UART, I2C, SPI...).
    
    - timestamp_us: Mốc thời gian xảy ra sự kiện tính bằng micro giây (us).
    - protocol: Tên giao thức được giải mã (ví dụ: "UART", "SPI", "I2C").
    - event_type: Loại sự kiện (ví dụ: "DATA", "START", "STOP", "ERROR").
    - channels: Danh sách các kênh logic liên quan đến sự kiện này.
    - value: Giá trị dữ liệu giải mã được (ví dụ: ký tự, số nguyên, text).
    - raw_bits: Danh sách các bit thô tương ứng thu thập được.
    - warning: Chuỗi cảnh báo nếu có sự bất thường nhẹ.
    - error: Chuỗi thông báo lỗi nếu giải mã thất bại hoặc sai định dạng khung.
    """
    timestamp_us: float
    protocol: str
    event_type: str
    channels: tuple[int, ...] = field(default_factory=tuple)
    value: Any = None
    raw_bits: list[int] | None = None
    warning: str | None = None
    error: str | None = None


def require_channel(channel: int) -> None:
    """
    Kiểm tra tính hợp lệ của số hiệu kênh đo.
    Bắt buộc kênh phải nằm trong khoảng từ 0 đến 7 (CHANNEL_COUNT - 1).
    """
    if not 0 <= channel < CHANNEL_COUNT:
        raise ValueError(f"channel must be 0..7, got {channel}")


def sample_bit(sample: int, channel: int) -> int:
    """
    Trích xuất trạng thái bit (0 hoặc 1) của một kênh đo cụ thể từ một mẫu byte dữ liệu.
    
    sample: Byte dữ liệu thô chứa 8 kênh.
    channel: Số hiệu kênh cần trích xuất (0 đến 7).
    """
    require_channel(channel)
    return (int(sample) >> channel) & 0x01


def channel_bits(samples: Sequence[int] | bytes | bytearray, channel: int) -> list[int]:
    """
    Trích xuất danh sách trạng thái bit của một kênh từ chuỗi/mảng nhiều mẫu dữ liệu thô.
    
    samples: Chuỗi các byte mẫu dữ liệu.
    channel: Số hiệu kênh cần trích xuất (0 đến 7).
    """
    require_channel(channel)
    return [sample_bit(sample, channel) for sample in samples]


def pack_channels(rows: Iterable[Sequence[int]]) -> bytes:
    """
    Đóng gói ngược lại các bit của 8 kênh đo thành một chuỗi bytes dữ liệu thô.
    Mỗi hàng (row) trong rows chứa đúng 8 giá trị bit tương ứng với 8 kênh.
    
    rows: Tập hợp các hàng dữ liệu kênh đo.
    """
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
    """
    Tính toán mốc thời gian (micro giây - us) của một mẫu đo dựa trên chỉ số mẫu và tần số lấy mẫu.
    
    sample_index: Chỉ số của mẫu đo trong mảng dữ liệu.
    sample_rate_hz: Tần số lấy mẫu (Hz).
    """
    if sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be > 0")
    return sample_index * 1_000_000.0 / sample_rate_hz
