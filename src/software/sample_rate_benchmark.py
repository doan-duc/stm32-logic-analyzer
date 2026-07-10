from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable


_BENCHMARK_TIMER_DIVIDERS = (64, 32, 16, 10, 8, 7, 6, 5, 4, 3, 2, 1)


@dataclass(frozen=True)
class CaptureResult:
    requested_rate_hz: int
    actual_rate_hz: int
    repeat: int
    passed: bool
    failures: tuple[str, ...]


def timer_exact_rates(
    timer_clock_hz: int,
    minimum_hz: int,
    maximum_hz: int,
) -> tuple[int, ...]:
    """Return a compact sweep ladder aligned to integer timer dividers."""
    if timer_clock_hz <= 0 or minimum_hz <= 0 or maximum_hz < minimum_hz:
        raise ValueError("timer clock and rate range must be positive and ordered")

    rates = {
        round(timer_clock_hz / divider)
        for divider in _BENCHMARK_TIMER_DIVIDERS
        if minimum_hz <= round(timer_clock_hz / divider) <= maximum_hz
    }
    return tuple(sorted(rates))


def best_stable_rate(
    results: Iterable[CaptureResult],
    required_repeats: int,
) -> int | None:
    """Return the highest requested rate whose required repeats all pass."""
    if required_repeats <= 0:
        raise ValueError("required_repeats must be > 0")

    grouped: dict[int, list[CaptureResult]] = defaultdict(list)
    for result in results:
        grouped[result.requested_rate_hz].append(result)

    stable_rates = [
        rate
        for rate, captures in grouped.items()
        if len(captures) >= required_repeats
        and all(capture.passed for capture in captures)
    ]
    return max(stable_rates, default=None)
