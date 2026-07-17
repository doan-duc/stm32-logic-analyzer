"""Compact digital-edge measurement helpers for the waveform GUI."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from html import escape
from math import isfinite
from numbers import Real
from operator import index as integer_index
from typing import Literal

import numpy as np


EdgeKind = Literal["rising", "falling"]


@dataclass(frozen=True, slots=True)
class EdgeMeasurement:
    """An immutable transition and the timing measurements available at it."""

    channel: int
    kind: EdgeKind
    sample_index: int
    timestamp_ns: Real
    interval_label: str | None = None
    delta_ns: Real | None = None
    period_ns: Real | None = None
    frequency_hz: float | None = None


class EdgeSeries(Sequence[EdgeMeasurement]):
    """Compact transition arrays that materialize records only on access."""

    __slots__ = ("_channel", "_polarities", "_sample_indices", "_sample_period_ns")

    def __init__(
        self,
        *,
        channel: int,
        sample_period_ns: Real,
        sample_indices: np.ndarray,
        polarities: np.ndarray,
    ) -> None:
        indices = np.asarray(sample_indices, dtype=np.int64).copy()
        rising = np.asarray(polarities, dtype=np.bool_).copy()
        if indices.ndim != 1 or rising.ndim != 1 or len(indices) != len(rising):
            raise ValueError("transition arrays must be one-dimensional and equal length")

        indices.setflags(write=False)
        rising.setflags(write=False)
        self._channel = channel
        self._sample_period_ns = sample_period_ns
        self._sample_indices = indices
        self._polarities = rising

    @property
    def sample_indices(self) -> np.ndarray:
        """Read-only absolute sample indices for every transition."""
        return self._sample_indices

    @property
    def polarities(self) -> np.ndarray:
        """Read-only polarity flags; true means rising and false means falling."""
        return self._polarities

    def __len__(self) -> int:
        return len(self._sample_indices)

    def __getitem__(self, index):
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
        return int(self._sample_indices[position]) * self._sample_period_ns

    def _materialize(self, position: int) -> EdgeMeasurement:
        rising = bool(self._polarities[position])
        kind: EdgeKind = "rising" if rising else "falling"
        sample_index = int(self._sample_indices[position])
        timestamp_ns = self._timestamp_ns(position)

        interval_label = None
        delta_ns = None
        if position > 0:
            interval_label = "LOW" if rising else "HIGH"
            delta_ns = timestamp_ns - self._timestamp_ns(position - 1)

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
        """Binary-search the closest transition without materializing the rest."""
        if not len(self):
            return None

        target_index = float(time_ns) / float(self._sample_period_ns)
        insertion = int(np.searchsorted(self._sample_indices, target_index, side="left"))
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
    mask = 1 << channel
    local_indices = np.flatnonzero((changed & mask) != 0) + 1
    sample_indices = local_indices.astype(np.int64, copy=False) + sample_offset
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
    """Detect one channel into compact transition arrays."""
    _validate_channel(channel)
    _validate_detection(sample_period_ns, sample_offset)
    sample_values = _sample_array(samples)
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
    """Build all eight channel caches from one adjacent-byte change array."""
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
    """Materialize all transitions for callers that need the legacy list API."""
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
    """Return the closest edge inside an inclusive time tolerance."""
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
    numeric = float(value)
    if numeric.is_integer():
        return f"{int(numeric):,} ns"
    return f"{numeric:,.3f}".rstrip("0").rstrip(".") + " ns"


def _adaptive_time(value_ns: Real) -> str:
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
    if value_hz >= 1_000_000:
        return f"{value_hz / 1_000_000:.3f} MHz"
    if value_hz >= 1_000:
        return f"{value_hz / 1_000:.3f} kHz"
    return f"{value_hz:.3f} Hz"


def format_edge_tooltip(edge: EdgeMeasurement, *, pin_name: str) -> str:
    """Build safe HTML for a selected edge and its available measurements."""
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
