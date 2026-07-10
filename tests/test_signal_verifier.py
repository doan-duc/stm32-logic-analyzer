from __future__ import annotations

import sys
import unittest
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parents[1] / "src" / "software"
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from signal_verifier import analyze_gray_capture, binary_to_gray, gray_to_binary  # noqa: E402


def make_gray_capture(samples_per_step: int, step_count: int = 300) -> bytes:
    payload = bytearray()
    for counter in range(step_count):
        payload.extend([binary_to_gray(counter & 0xFF)] * samples_per_step)
    return bytes(payload)


class GrayCodeTests(unittest.TestCase):
    def test_gray_round_trip(self):
        for value in range(256):
            self.assertEqual(gray_to_binary(binary_to_gray(value)), value)

    def test_known_good_capture_passes_all_channels_and_rate(self):
        report = analyze_gray_capture(
            make_gray_capture(samples_per_step=10),
            sample_rate_hz=100_000,
            step_rate_hz=10_000,
        )

        self.assertTrue(report.passed, report.failures)
        self.assertEqual(report.sequence_errors, 0)
        self.assertAlmostEqual(report.measured_sample_rate_hz, 100_000, delta=1)
        self.assertTrue(all(edges > 0 for edges in report.channel_edges))

    def test_clock_metadata_mismatch_is_detected(self):
        report = analyze_gray_capture(
            make_gray_capture(samples_per_step=9),
            sample_rate_hz=100_000,
            step_rate_hz=10_000,
            rate_tolerance=0.02,
        )

        self.assertFalse(report.passed)
        self.assertAlmostEqual(report.measured_sample_rate_hz, 90_000, delta=1)
        self.assertTrue(any("sample-rate" in failure for failure in report.failures))

    def test_fractional_samples_per_step_uses_long_run_average(self):
        payload = bytearray()
        for counter in range(300):
            run_length = 8 if counter % 9 == 0 else 9
            payload.extend([binary_to_gray(counter)] * run_length)

        report = analyze_gray_capture(
            payload,
            sample_rate_hz=100_000,
            step_rate_hz=10_000,
        )

        self.assertAlmostEqual(report.measured_sample_rate_hz, 88_888.9, delta=5)

    def test_skipped_gray_state_is_detected(self):
        samples = make_gray_capture(samples_per_step=10, step_count=140)
        skipped = samples[:700] + samples[710:]

        report = analyze_gray_capture(
            skipped,
            sample_rate_hz=100_000,
            step_rate_hz=10_000,
        )

        self.assertFalse(report.passed)
        self.assertGreater(report.sequence_errors, 0)

    def test_interior_short_glitch_is_not_silently_discarded(self):
        samples = bytearray(make_gray_capture(samples_per_step=10, step_count=140))
        samples[700:700] = b"\xFF"

        report = analyze_gray_capture(
            samples,
            sample_rate_hz=100_000,
            step_rate_hz=10_000,
        )

        self.assertFalse(report.passed)
        self.assertGreater(report.short_runs, 0)


if __name__ == "__main__":
    unittest.main()
