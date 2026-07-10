from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1] / "src" / "software" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from hardware_self_test import _requested_rate_failures, _status_failures  # noqa: E402


class StatusGateTests(unittest.TestCase):
    def test_missing_status_is_a_failure(self):
        self.assertTrue(_status_failures(None, "DMA"))

    def test_missing_overrun_diagnostic_is_a_failure(self):
        status = {"engine": "TIMER_DMA_GPIO_IDR", "dma_errors": 0}

        failures = _status_failures(status, "DMA")

        self.assertTrue(any("ISR_OVERRUNS" in failure for failure in failures))

    def test_engine_must_match_requested_mode(self):
        status = {
            "engine": "TIMER_ISR_DIRECT",
            "isr_overruns": 0,
            "dma_errors": 0,
        }

        failures = _status_failures(status, "DMA")

        self.assertTrue(any("engine" in failure.lower() for failure in failures))

    def test_complete_dma_status_passes(self):
        status = {
            "engine": "TIMER_DMA_GPIO_IDR",
            "isr_overruns": 0,
            "dma_errors": 0,
        }

        self.assertEqual(_status_failures(status, "DMA"), [])


class RequestedRateGateTests(unittest.TestCase):
    def test_declared_actual_rate_must_match_requested_rate(self):
        failures = _requested_rate_failures(100_000, 88_889, 0.03)

        self.assertTrue(any("requested" in failure for failure in failures))

    def test_small_timer_divider_error_is_allowed(self):
        self.assertEqual(_requested_rate_failures(750_000, 752_941, 0.01), [])


if __name__ == "__main__":
    unittest.main()
