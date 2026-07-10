from __future__ import annotations

import sys
import unittest
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parents[1] / "src" / "software"
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from sample_rate_benchmark import (  # noqa: E402
    CaptureResult,
    best_stable_rate,
    timer_exact_rates,
)


class TimerRatePlanTests(unittest.TestCase):
    def test_generates_exact_rates_from_integer_timer_dividers(self):
        self.assertEqual(
            timer_exact_rates(
                timer_clock_hz=64_000_000,
                minimum_hz=1_000_000,
                maximum_hz=12_000_000,
            ),
            (
                1_000_000,
                2_000_000,
                4_000_000,
                6_400_000,
                8_000_000,
                9_142_857,
                10_666_667,
            ),
        )

    def test_rejects_invalid_rate_range(self):
        with self.assertRaises(ValueError):
            timer_exact_rates(64_000_000, 0, 10_000_000)
        with self.assertRaises(ValueError):
            timer_exact_rates(64_000_000, 2_000_000, 1_000_000)


class StableLimitTests(unittest.TestCase):
    def test_requires_every_repeat_to_pass(self):
        results = (
            CaptureResult(1_000_000, 1_000_000, 1, True, ()),
            CaptureResult(1_000_000, 1_000_000, 2, True, ()),
            CaptureResult(8_000_000, 8_000_000, 1, True, ()),
            CaptureResult(8_000_000, 8_000_000, 2, False, ("Gray glitch",)),
        )
        self.assertEqual(best_stable_rate(results, required_repeats=2), 1_000_000)

    def test_returns_none_when_no_rate_has_enough_valid_repeats(self):
        results = (CaptureResult(4_000_000, 4_000_000, 1, True, ()),)
        self.assertIsNone(best_stable_rate(results, required_repeats=2))


if __name__ == "__main__":
    unittest.main()
