"""
Các hàm và lớp phụ trợ đo đạc khoảng thời gian, chu kỳ và tần số của sườn tín hiệu logic (edge) trên giao diện GUI.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from html import escape
from math import isfinite
from numbers import Real
from operator import index as integer_index
from typing import Literal

import numpy as np


# Kiểu định dạng loại sườn: "rising" (sườn lên) hoặc "falling" (sườn xuống)
EdgeKind = Literal["rising", "falling"]


@dataclass(frozen=True, slots=True)
class EdgeMeasurement:
    """
    Đối tượng immutable (không thể thay đổi sau khi tạo) lưu thông tin đo đạc sườn tín hiệu:
    
    - channel: Kênh đo logic (0-7).
    - kind: Loại sườn ("rising" hoặc "falling").
    - sample_index: Chỉ số mẫu tuyệt đối nơi xảy ra sườn.
    - timestamp_ns: Mốc thời gian xảy ra sườn tín hiệu (nano giây).
    - interval_label: Nhãn trạng thái trước sườn (ví dụ sườn lên -> nhãn LOW, sườn xuống -> nhãn HIGH).
    - delta_ns: Độ rộng xung của trạng thái trước đó (nano giây).
    - period_ns: Chu kỳ tín hiệu (khoảng cách tới sườn cùng loại trước đó) (nano giây).
    - frequency_hz: Tần số tính toán được tương ứng (Hz).
    """

    channel: int
    kind: EdgeKind
    sample_index: int
    timestamp_ns: Real
    interval_label: str | None = None
    delta_ns: Real | None = None
    period_ns: Real | None = None
    frequency_hz: float | None = None


class EdgeSeries(Sequence[EdgeMeasurement]):
    """
    Lớp lưu trữ loạt sườn tín hiệu tối ưu hóa bộ nhớ.
    Thay vì tạo sẵn hàng ngàn đối tượng EdgeMeasurement trong RAM, lớp này chỉ lưu các mảng numpy 
    chỉ số mẫu và trạng thái phân cực. Khi người dùng truy cập một sườn (ví dụ qua chỉ số index),
    hàm sẽ tính toán và sinh ra (materialize) đối tượng EdgeMeasurement tương ứng tại thời điểm đó.
    """

    __slots__ = ("_channel", "_polarities", "_sample_indices", "_sample_period_ns")

    def __init__(
        self,
        *,
        channel: int,
        sample_period_ns: Real,
        sample_indices: np.ndarray,
        polarities: np.ndarray,
    ) -> None:
        # Tạo bản sao mảng chỉ số và loại sườn để bảo vệ dữ liệu gốc
        indices = np.asarray(sample_indices, dtype=np.int64).copy()
        rising = np.asarray(polarities, dtype=np.bool_).copy()
        if indices.ndim != 1 or rising.ndim != 1 or len(indices) != len(rising):
            raise ValueError("transition arrays must be one-dimensional and equal length")

        # Thiết lập thuộc tính chỉ đọc (read-only) cho mảng numpy để tránh sửa đổi ngoài ý muốn
        indices.setflags(write=False)
        rising.setflags(write=False)
        self._channel = channel
        self._sample_period_ns = sample_period_ns
        self._sample_indices = indices
        self._polarities = rising

    @property
    def sample_indices(self) -> np.ndarray:
        """Mảng chỉ số mẫu của các sườn chuyển trạng thái (chỉ đọc)."""
        return self._sample_indices

    @property
    def polarities(self) -> np.ndarray:
        """Mảng trạng thái sườn: True nghĩa là sườn lên, False là sườn xuống (chỉ đọc)."""
        return self._polarities

    def __len__(self) -> int:
        return len(self._sample_indices)

    def __getitem__(self, index):
        # Hỗ trợ lấy lát cắt (slice)
        if isinstance(index, slice):
            return tuple(self[position] for position in range(*index.indices(len(self))))

        if isinstance(index, bool):
            raise TypeError("edge indices must be integers or slices, not bool")
        try:
            position = integer_index(index)
        except TypeError:
            raise TypeError("edge indices must be integers or slices") from None
            
        if position < 0:
            position += len(self)
        if not 0 <= position < len(self):
            raise IndexError("edge index out of range")
        return self._materialize(position)

    def __iter__(self) -> Iterator[EdgeMeasurement]:
        for position in range(len(self)):
            yield self._materialize(position)

    def _timestamp_ns(self, position: int) -> Real:
        """Tính mốc thời gian dạng nano giây của sườn tại vị trí position."""
        return int(self._sample_indices[position]) * self._sample_period_ns

    def _materialize(self, position: int) -> EdgeMeasurement:
        """
        Tính toán và sinh ra (instantiate) một đối tượng EdgeMeasurement tại vị trí chỉ định.
        """
        rising = bool(self._polarities[position])
        kind: EdgeKind = "rising" if rising else "falling"
        sample_index = int(self._sample_indices[position])
        timestamp_ns = self._timestamp_ns(position)

        # Tính độ rộng xung của trạng thái trước đó (nếu không phải phần tử đầu tiên)
        interval_label = None
        delta_ns = None
        if position > 0:
            interval_label = "LOW" if rising else "HIGH"
            delta_ns = timestamp_ns - self._timestamp_ns(position - 1)

        # Tính toán chu kỳ và tần số (nếu có tối thiểu 2 sườn trước đó)
        period_ns = None
        frequency_hz = None
        if position > 1:
            period_ns = timestamp_ns - self._timestamp_ns(position - 2)
            frequency_hz = 1_000_000_000 / period_ns

        return EdgeMeasurement(
            channel=self._channel,
            kind=kind,
            sample_index=sample_index,
            timestamp_ns=timestamp_ns,
            interval_label=interval_label,
            delta_ns=delta_ns,
            period_ns=period_ns,
            frequency_hz=frequency_hz,
        )

    def nearest(self, *, time_ns: Real, tolerance_ns: Real) -> EdgeMeasurement | None:
        """
        Tìm kiếm nhị phân (Binary Search) sườn tín hiệu gần nhất với mốc thời gian yêu cầu,
        nhằm tránh khởi tạo toàn bộ mảng gây chậm hiệu năng GUI.
        """
        if not len(self):
            return None

        # Quy đổi thời gian sang chỉ số mẫu đo tương đối
        target_index = float(time_ns) / float(self._sample_period_ns)
        # Sử dụng thuật toán tìm vị trí chèn nhị phân của numpy
        insertion = int(np.searchsorted(self._sample_indices, target_index, side="left"))
        
        # So sánh 2 phần tử lân cận (bên trái và bên phải vị trí tìm được) để tìm sườn gần nhất thực tế
        positions = (insertion - 1, insertion)
        nearest_position = None
        nearest_key = None

        for position in positions:
            if not 0 <= position < len(self):
                continue
            timestamp_ns = self._timestamp_ns(position)
            distance = abs(timestamp_ns - time_ns)
            if distance > tolerance_ns:
                continue
            key = (distance, timestamp_ns)
            if nearest_key is None or key < nearest_key:
                nearest_position = position
                nearest_key = key

        if nearest_position is None:
            return None
        return self._materialize(nearest_position)


def _require_finite_number(value: Real, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")


def _validate_channel(channel: int) -> None:
    if isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel < 8:
        raise ValueError("channel must be an integer from 0 to 7")


def _validate_detection(sample_period_ns: Real, sample_offset: int) -> None:
    _require_finite_number(sample_period_ns, "sample_period_ns")
    if sample_period_ns <= 0:
        raise ValueError("sample_period_ns must be greater than zero")
    if (
        isinstance(sample_offset, bool)
        or not isinstance(sample_offset, int)
        or sample_offset < 0
    ):
        raise ValueError("sample_offset must be a non-negative integer")


def _sample_array(samples: bytes | bytearray | memoryview) -> np.ndarray:
    return np.frombuffer(memoryview(samples).cast("B"), dtype=np.uint8)


def _series_from_changes(
    sample_values: np.ndarray,
    changed: np.ndarray,
    *,
    channel: int,
    sample_period_ns: Real,
    sample_offset: int,
) -> EdgeSeries:
    """
    Hàm dựng đối tượng EdgeSeries từ thông tin các điểm thay đổi mức logic.
    """
    mask = 1 << channel
    # Tìm các chỉ số mẫu đo có sự thay đổi bit trên kênh hiện tại
    local_indices = np.flatnonzero((changed & mask) != 0) + 1
    sample_indices = local_indices.astype(np.int64, copy=False) + sample_offset
    # Xác định mức logic phân cực sau khi đổi trạng thái (True = 1, False = 0)
    polarities = (sample_values[local_indices] & mask) != 0
    return EdgeSeries(
        channel=channel,
        sample_period_ns=sample_period_ns,
        sample_indices=sample_indices,
        polarities=polarities,
    )


def detect_edge_series(
    samples: bytes | bytearray | memoryview,
    *,
    channel: int,
    sample_period_ns: Real,
    sample_offset: int = 0,
) -> EdgeSeries:
    """
    Phát hiện và trích xuất chuỗi sườn tín hiệu (EdgeSeries) của một kênh đơn lẻ.
    """
    _validate_channel(channel)
    _validate_detection(sample_period_ns, sample_offset)
    sample_values = _sample_array(samples)
    # Phép toán XOR sai phân giúp xác định vị trí các điểm đổi trạng thái bit
    changed = np.bitwise_xor(sample_values[1:], sample_values[:-1])
    return _series_from_changes(
        sample_values,
        changed,
        channel=channel,
        sample_period_ns=sample_period_ns,
        sample_offset=sample_offset,
    )


def detect_all_edge_series(
    samples: bytes | bytearray | memoryview,
    *,
    sample_period_ns: Real,
    sample_offset: int = 0,
) -> tuple[EdgeSeries, ...]:
    """
    Phát hiện và trích xuất sườn tín hiệu cho toàn bộ 8 kênh đo cùng lúc bằng cách
    tính toán mảng thay đổi bit chung một lần để tăng tốc tối đa.
    """
    _validate_detection(sample_period_ns, sample_offset)
    sample_values = _sample_array(samples)
    changed = np.bitwise_xor(sample_values[1:], sample_values[:-1])
    return tuple(
        _series_from_changes(
            sample_values,
            changed,
            channel=channel,
            sample_period_ns=sample_period_ns,
            sample_offset=sample_offset,
        )
        for channel in range(8)
    )


def detect_edges(
    samples: bytes | bytearray | memoryview,
    *,
    channel: int,
    sample_period_ns: Real,
    sample_offset: int = 0,
) -> list[EdgeMeasurement]:
    """
    Phát hiện và khởi tạo (materialize) toàn bộ danh sách EdgeMeasurement.
    Dành cho các hàm gọi API cũ yêu cầu kiểu danh sách thông thường.
    """
    return list(
        detect_edge_series(
            samples,
            channel=channel,
            sample_period_ns=sample_period_ns,
            sample_offset=sample_offset,
        )
    )


def select_nearest_edge(
    edges: Iterable[EdgeMeasurement],
    *,
    time_ns: Real,
    tolerance_ns: Real,
) -> EdgeMeasurement | None:
    """
    Lựa chọn sườn tín hiệu gần nhất với mốc thời gian chỉ định nằm trong phạm vi sai số dung sai (tolerance_ns).
    """
    _require_finite_number(time_ns, "time_ns")
    _require_finite_number(tolerance_ns, "tolerance_ns")
    if tolerance_ns < 0:
        raise ValueError("tolerance_ns must be non-negative")
    if isinstance(edges, EdgeSeries):
        return edges.nearest(time_ns=time_ns, tolerance_ns=tolerance_ns)

    nearest = None
    nearest_key = None
    for edge in edges:
        distance = abs(edge.timestamp_ns - time_ns)
        if distance > tolerance_ns:
            continue
        key = (distance, edge.timestamp_ns)
        if nearest_key is None or key < nearest_key:
            nearest = edge
            nearest_key = key
    return nearest


def _raw_nanoseconds(value: Real) -> str:
    """Định dạng số hiển thị nano giây."""
    numeric = float(value)
    if numeric.is_integer():
        return f"{int(numeric):,} ns"
    return f"{numeric:,.3f}".rstrip("0").rstrip(".") + " ns"


def _adaptive_time(value_ns: Real) -> str:
    """Tự động chuyển đổi đơn vị hiển thị thời gian (s, ms, us, ns) cho dễ đọc."""
    numeric = float(value_ns)
    magnitude = abs(numeric)
    if magnitude >= 1_000_000_000:
        return f"{numeric / 1_000_000_000:.3f} s"
    if magnitude >= 1_000_000:
        return f"{numeric / 1_000_000:.3f} ms"
    if magnitude >= 1_000:
        return f"{numeric / 1_000:.3f} us"
    return _raw_nanoseconds(value_ns)


def _adaptive_frequency(value_hz: float) -> str:
    """Tự động chuyển đổi đơn vị hiển thị tần số (MHz, kHz, Hz) cho dễ đọc."""
    if value_hz >= 1_000_000:
        return f"{value_hz / 1_000_000:.3f} MHz"
    if value_hz >= 1_000:
        return f"{value_hz / 1_000:.3f} kHz"
    return f"{value_hz:.3f} Hz"


def format_edge_tooltip(edge: EdgeMeasurement, *, pin_name: str) -> str:
    """
    Xây dựng nội dung chú thích Tooltip định dạng HTML hiển thị khi người dùng di chuột qua sườn tín hiệu.
    Hiển thị thông tin kênh, thời gian, chỉ số mẫu đo, chu kỳ và tần số đo đạc được.
    """
    pin = escape(str(pin_name))
    edge_label = "Rising" if edge.kind == "rising" else "Falling"
    adaptive_timestamp = _adaptive_time(edge.timestamp_ns)
    raw_timestamp = _raw_nanoseconds(edge.timestamp_ns)
    timestamp = adaptive_timestamp
    if adaptive_timestamp != raw_timestamp:
        timestamp = f"{adaptive_timestamp} ({raw_timestamp})"

    lines = [
        f"<b>CH{edge.channel} ({pin}) - {edge_label}</b>",
        f"Time: {timestamp}",
        f"Sample #{edge.sample_index}",
    ]
    if edge.interval_label is not None and edge.delta_ns is not None:
        lines.append(f"{escape(edge.interval_label)}: {_adaptive_time(edge.delta_ns)}")
    if edge.period_ns is not None:
        lines.append(f"Period: {_adaptive_time(edge.period_ns)}")
    if edge.frequency_hz is not None:
        lines.append(f"Frequency: {_adaptive_frequency(edge.frequency_hz)}")

    return "<div style='text-align: center;'>" + "<br>".join(lines) + "</div>"
