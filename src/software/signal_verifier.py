from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean


@dataclass(frozen=True)
class GrayCaptureReport:
    passed: bool
    stable_states: int
    sequence_errors: int
    short_runs: int
    measured_sample_rate_hz: float
    rate_error_fraction: float
    channel_edges: tuple[int, ...]
    failures: tuple[str, ...]


def binary_to_gray(value: int) -> int:
    value &= 0xFF
    return value ^ (value >> 1)


def gray_to_binary(gray: int) -> int:
    gray &= 0xFF
    value = gray
    shifted = gray >> 1
    while shifted:
        value ^= shifted
        shifted >>= 1
    return value & 0xFF


def _runs(samples: bytes) -> list[tuple[int, int]]:
    if not samples:
        return []
    runs: list[tuple[int, int]] = []
    current = samples[0]
    length = 1
    for sample in samples[1:]:
        if sample == current:
            length += 1
        else:
            runs.append((current, length))
            current = sample
            length = 1
    runs.append((current, length))
    return runs


def analyze_gray_capture(
    samples: bytes | bytearray | memoryview,
    *,
    sample_rate_hz: int,
    step_rate_hz: int = 10_000,
    rate_tolerance: float = 0.03,
    minimum_states: int = 64,
) -> GrayCaptureReport:
    """Check sequence, all eight channels, and sample-clock accuracy.

    The Arduino oracle emits an 8-bit reflected Gray counter. Only one channel
    changes per step, so a captured intermediate multi-bit value is never valid.
    """
    if sample_rate_hz <= 0 or step_rate_hz <= 0:
        raise ValueError("sample_rate_hz and step_rate_hz must be > 0")
    if not 0 <= rate_tolerance < 1:
        raise ValueError("rate_tolerance must be in [0, 1)")

    raw_runs = _runs(bytes(samples))
    expected_samples_per_step = sample_rate_hz / step_rate_hz
    minimum_run = max(2, int(expected_samples_per_step * 0.30))
    stable = [(value, length) for value, length in raw_runs if length >= minimum_run]
    # A capture may start/end in the middle of a valid state. Short runs inside
    # the frame are different: with Gray code they indicate a sampled glitch.
    short_runs = sum(length < minimum_run for _, length in raw_runs[1:-1])

    decoded = [gray_to_binary(value) for value, _ in stable]
    sequence_errors = sum(
        ((current - previous) & 0xFF) != 1
        for previous, current in zip(decoded, decoded[1:])
    )

    channel_edges = tuple(
        sum(((left ^ right) & (1 << channel)) != 0 for left, right in zip(
            (value for value, _ in stable),
            (value for value, _ in stable[1:]),
        ))
        for channel in range(8)
    )

    # The first and last runs can be partial because capture is not synchronized
    # to the generator. Excluding them avoids a deterministic boundary bias.
    timing_lengths = [length for _, length in stable[1:-1]]
    measured_sample_rate_hz = (
        float(fmean(timing_lengths) * step_rate_hz) if timing_lengths else 0.0
    )
    rate_error_fraction = (
        abs(measured_sample_rate_hz - sample_rate_hz) / sample_rate_hz
        if measured_sample_rate_hz
        else 1.0
    )

    failures: list[str] = []
    if len(stable) < minimum_states:
        failures.append(
            f"too few stable Gray states ({len(stable)} < {minimum_states})"
        )
    if sequence_errors:
        failures.append(f"Gray sequence has {sequence_errors} skipped/out-of-order steps")
    if short_runs:
        failures.append(f"captured {short_runs} short interior glitch state(s)")
    missing_channels = [str(index) for index, count in enumerate(channel_edges) if count == 0]
    if missing_channels:
        failures.append("no transition observed on channel(s) " + ", ".join(missing_channels))
    if rate_error_fraction > rate_tolerance:
        failures.append(
            "sample-rate mismatch: metadata "
            f"{sample_rate_hz} Hz, measured {measured_sample_rate_hz:.1f} Hz "
            f"({rate_error_fraction * 100:.2f}%)"
        )

    return GrayCaptureReport(
        passed=not failures,
        stable_states=len(stable),
        sequence_errors=sequence_errors,
        short_runs=short_runs,
        measured_sample_rate_hz=measured_sample_rate_hz,
        rate_error_fraction=rate_error_fraction,
        channel_edges=channel_edges,
        failures=tuple(failures),
    )
