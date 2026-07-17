from __future__ import annotations

import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest import mock


os.environ["QT_QPA_PLATFORM"] = "offscreen"

SOFTWARE_DIR = Path(__file__).resolve().parents[1] / "src" / "software"
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))


def edge_measurement_api():
    """Import lazily so pytest can collect every RED-stage specification."""
    return importlib.import_module("gui.edge_measurement")


def samples_for_channel(channel: int, levels: list[int]) -> bytes:
    return bytes(level << channel for level in levels)


class EdgeDetectionTests(unittest.TestCase):
    def test_detects_rising_and_falling_edges_with_global_capture_coordinates(self):
        api = edge_measurement_api()
        samples = samples_for_channel(2, [0, 0, 1, 1, 0])

        edges = api.detect_edges(
            samples,
            channel=2,
            sample_period_ns=125,
            sample_offset=100,
        )

        self.assertEqual([edge.kind for edge in edges], ["rising", "falling"])
        self.assertEqual([edge.sample_index for edge in edges], [102, 104])
        self.assertEqual([edge.timestamp_ns for edge in edges], [12_750, 13_000])

    def test_empty_and_constant_captures_have_no_transitions(self):
        api = edge_measurement_api()

        self.assertEqual(
            api.detect_edges(b"", channel=0, sample_period_ns=100),
            [],
        )
        self.assertEqual(
            api.detect_edges(
                samples_for_channel(0, [1, 1, 1]),
                channel=0,
                sample_period_ns=100,
            ),
            [],
        )


class EdgeSeriesTests(unittest.TestCase):
    def test_compact_series_materializes_only_the_selected_edge(self):
        api = edge_measurement_api()
        samples = samples_for_channel(0, [0, 1, 1, 0, 0, 1])

        with mock.patch.object(
            api,
            "EdgeMeasurement",
            wraps=api.EdgeMeasurement,
        ) as record_factory:
            series = api.detect_edge_series(
                samples,
                channel=0,
                sample_period_ns=100,
            )

            self.assertNotIsInstance(series, list)
            self.assertEqual(len(series), 3)
            self.assertEqual(record_factory.call_count, 0)

            selected = api.select_nearest_edge(
                series,
                time_ns=305,
                tolerance_ns=10,
            )

            self.assertEqual(record_factory.call_count, 1)

        self.assertIsInstance(selected, api.EdgeMeasurement)
        self.assertEqual(selected.kind, "falling")
        self.assertEqual(selected.sample_index, 3)
        self.assertEqual(selected.timestamp_ns, 300)

    def test_compact_series_supports_indexing_and_iteration_as_edge_records(self):
        api = edge_measurement_api()
        series = api.detect_edge_series(
            samples_for_channel(1, [0, 1, 1, 0, 0, 1]),
            channel=1,
            sample_period_ns=125,
            sample_offset=10,
        )

        self.assertIsInstance(series[0], api.EdgeMeasurement)
        self.assertEqual(series[0].sample_index, 11)
        self.assertEqual(
            [(edge.kind, edge.sample_index) for edge in series],
            [("rising", 11), ("falling", 13), ("rising", 15)],
        )

    def test_compact_series_rejects_non_integral_indices(self):
        api = edge_measurement_api()
        series = api.detect_edge_series(
            samples_for_channel(0, [0, 1, 1, 0, 0, 1]),
            channel=0,
            sample_period_ns=100,
        )

        self.assertEqual(series[0].sample_index, 1)
        self.assertEqual(series[-1].sample_index, 5)
        with self.assertRaises(TypeError):
            series[1.9]
        with self.assertRaises(TypeError):
            series[True]


class NearestEdgeTests(unittest.TestCase):
    def setUp(self):
        self.api = edge_measurement_api()
        self.edges = self.api.detect_edges(
            samples_for_channel(0, [0, 1, 1, 0, 0, 1]),
            channel=0,
            sample_period_ns=100,
        )

    def test_selects_nearest_edge_within_time_tolerance(self):
        selected = self.api.select_nearest_edge(
            self.edges,
            time_ns=285,
            tolerance_ns=20,
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected.kind, "falling")
        self.assertEqual(selected.timestamp_ns, 300)

    def test_returns_none_when_nearest_edge_is_outside_tolerance(self):
        selected = self.api.select_nearest_edge(
            self.edges,
            time_ns=250,
            tolerance_ns=49,
        )

        self.assertIsNone(selected)

    def test_equal_distance_tie_selects_the_earlier_edge(self):
        selected = self.api.select_nearest_edge(
            self.edges,
            time_ns=200,
            tolerance_ns=100,
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected.timestamp_ns, 100)
        self.assertEqual(selected.kind, "rising")

    def test_no_edges_always_returns_none(self):
        selected = self.api.select_nearest_edge(
            [],
            time_ns=100,
            tolerance_ns=100,
        )

        self.assertIsNone(selected)


class EdgeTimingTests(unittest.TestCase):
    def test_edges_expose_level_delta_and_same_kind_period(self):
        api = edge_measurement_api()
        edges = api.detect_edges(
            samples_for_channel(0, [0, 0, 1, 1, 1, 0, 0, 1, 1, 0]),
            channel=0,
            sample_period_ns=100,
            sample_offset=20,
        )

        first_rising, first_falling, second_rising, second_falling = edges
        self.assertEqual(first_falling.interval_label, "HIGH")
        self.assertEqual(first_falling.delta_ns, 300)
        self.assertEqual(second_rising.interval_label, "LOW")
        self.assertEqual(second_rising.delta_ns, 200)
        self.assertEqual(second_rising.period_ns, 500)
        self.assertEqual(second_rising.frequency_hz, 2_000_000)
        self.assertEqual(second_falling.interval_label, "HIGH")
        self.assertEqual(second_falling.delta_ns, 200)
        self.assertEqual(second_falling.period_ns, 400)
        self.assertEqual(second_falling.frequency_hz, 2_500_000)

        selected = api.select_nearest_edge(
            edges,
            time_ns=2_700,
            tolerance_ns=0,
        )
        self.assertEqual(selected, second_rising)
        self.assertEqual(selected.interval_label, "LOW")
        self.assertEqual(selected.delta_ns, 200)
        self.assertEqual(selected.period_ns, 500)
        self.assertEqual(selected.frequency_hz, 2_000_000)

        selected = api.select_nearest_edge(
            edges,
            time_ns=2_900,
            tolerance_ns=0,
        )
        self.assertEqual(selected, second_falling)
        self.assertEqual(selected.interval_label, "HIGH")
        self.assertEqual(selected.delta_ns, 200)
        self.assertEqual(selected.period_ns, 400)
        self.assertEqual(selected.frequency_hz, 2_500_000)

    def test_first_edge_has_no_delta_period_or_frequency(self):
        api = edge_measurement_api()
        first_edge = api.detect_edges(
            samples_for_channel(1, [0, 1, 1]),
            channel=1,
            sample_period_ns=250,
        )[0]

        self.assertIsNone(first_edge.interval_label)
        self.assertIsNone(first_edge.delta_ns)
        self.assertIsNone(first_edge.period_ns)
        self.assertIsNone(first_edge.frequency_hz)


class TooltipFormattingTests(unittest.TestCase):
    def test_tooltip_includes_identity_timestamp_and_available_measurements(self):
        api = edge_measurement_api()
        edge = api.detect_edges(
            samples_for_channel(3, [0, 1, 1, 0, 0, 1]),
            channel=3,
            sample_period_ns=250_000,
            sample_offset=4,
        )[-1]

        tooltip = api.format_edge_tooltip(edge, pin_name="PA3")

        self.assertIn("CH3", tooltip)
        self.assertIn("PA3", tooltip)
        self.assertIn("Rising", tooltip)
        self.assertIn("2.250 ms", tooltip)
        self.assertIn("2,250,000 ns", tooltip)
        self.assertIn("Sample #9", tooltip)
        self.assertIn("LOW: 500.000 us", tooltip)
        self.assertIn("Period: 1.000 ms", tooltip)
        self.assertIn("Frequency: 1.000 kHz", tooltip)

    def test_first_edge_tooltip_omits_unavailable_measurements(self):
        api = edge_measurement_api()
        edge = api.detect_edges(
            samples_for_channel(0, [0, 1]),
            channel=0,
            sample_period_ns=100,
        )[0]

        tooltip = api.format_edge_tooltip(edge, pin_name="PA0")

        self.assertIn("CH0", tooltip)
        self.assertIn("PA0", tooltip)
        self.assertIn("Rising", tooltip)
        self.assertIn("100 ns", tooltip)
        self.assertIn("Sample #1", tooltip)
        self.assertNotIn("HIGH:", tooltip)
        self.assertNotIn("LOW:", tooltip)
        self.assertNotIn("Period:", tooltip)
        self.assertNotIn("Frequency:", tooltip)


class WaveformViewIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication

        from capture import Capture
        from gui.waveform_view import WaveformView

        cls.app = QApplication.instance() or QApplication([])
        cls.Capture = Capture
        cls.WaveformView = WaveformView

    def test_edge_hover_updates_and_resets_headlessly(self):
        widget = self.WaveformView()
        self.addCleanup(widget.close)
        capture = self.Capture(
            samples_for_channel(0, [0, 0, 1, 1, 0, 0]),
            sample_period_ns=100,
        )

        widget.display_capture(capture)
        self.app.processEvents()

        missing_seams = [
            name
            for name in ("edge_cache", "_update_edge_hover")
            if not hasattr(widget, name)
        ]
        self.assertEqual(
            missing_seams,
            [],
            "WaveformView needs a polarity-aware cache and deterministic hover seam",
        )

        cached_edges = widget.edge_cache[0]
        self.assertEqual([edge.kind for edge in cached_edges], ["rising", "falling"])
        self.assertEqual([edge.sample_index for edge in cached_edges], [2, 4])
        self.assertEqual([edge.timestamp_ns for edge in cached_edges], [200, 400])

        widget._update_edge_hover(channel=0, time_ns=405, tolerance_ns=10)
        self.app.processEvents()

        self.assertTrue(widget.measure_line1.isVisible())
        self.assertTrue(widget.measure_text.isVisible())
        tooltip = widget.measure_text.toHtml()
        self.assertIn("CH0", tooltip)
        self.assertIn("PA0", tooltip)
        self.assertIn("Falling", tooltip)
        self.assertIn("400 ns", tooltip)

        widget._update_edge_hover(channel=0, time_ns=900, tolerance_ns=10)
        self.app.processEvents()

        self.assertFalse(widget.measure_line1.isVisible())
        self.assertFalse(widget.measure_line2.isVisible())
        self.assertFalse(widget.measure_text.isVisible())

        widget._update_edge_hover(channel=0, time_ns=200, tolerance_ns=0)
        self.assertTrue(widget.measure_text.isVisible())
        widget.reset_view()
        self.app.processEvents()

        self.assertTrue(all(not edges for edges in widget.edge_cache))
        self.assertFalse(widget.measure_line1.isVisible())
        self.assertFalse(widget.measure_line2.isVisible())
        self.assertFalse(widget.measure_text.isVisible())

    def test_full_display_keeps_early_edges_beyond_compact_cache_window(self):
        widget = self.WaveformView()
        self.addCleanup(widget.close)
        capture = self.Capture(
            b"\x00\x00" + (b"\x01" * 8_203),
            sample_period_ns=100,
        )

        widget.display_capture(capture, visible_sample_limit=None)

        self.assertNotIsInstance(widget.edge_cache[0], list)
        self.assertEqual(
            [(edge.kind, edge.sample_index) for edge in widget.edge_cache[0]],
            [("rising", 2)],
        )
        widget._update_edge_hover(channel=0, time_ns=200, tolerance_ns=0)
        self.assertTrue(widget.measure_line1.isVisible())
        self.assertIn("Rising", widget.measure_text.toHtml())

    def test_rolling_slice_detects_transition_at_first_rendered_sample(self):
        widget = self.WaveformView()
        self.addCleanup(widget.close)
        capture = self.Capture(
            b"\x00\x00" + (b"\x01" * 8_192),
            sample_period_ns=125,
        )

        widget.display_capture(
            capture,
            is_rolling_update=True,
            visible_sample_limit=8_192,
        )

        edge = widget.edge_cache[0][0]
        self.assertEqual(edge.kind, "rising")
        self.assertEqual(edge.sample_index, 2)
        self.assertEqual(edge.timestamp_ns, 250)

    def test_trimmed_capture_preserves_absolute_edge_coordinates(self):
        widget = self.WaveformView()
        self.addCleanup(widget.close)
        capture = self.Capture(
            samples_for_channel(0, [0, 1, 1, 0, 1, 1, 0, 0]),
            sample_period_ns=100,
        )
        capture.trim_start(3)

        widget.display_capture(capture)

        self.assertEqual(
            [edge.sample_index for edge in widget.edge_cache[0]],
            [4, 6],
        )
        self.assertEqual(
            [edge.timestamp_ns for edge in widget.edge_cache[0]],
            [400, 600],
        )

    def test_tooltip_is_anchored_at_selected_edge_not_interval_midpoint(self):
        widget = self.WaveformView()
        self.addCleanup(widget.close)
        capture = self.Capture(
            samples_for_channel(0, [0, 0, 1, 1, 0]),
            sample_period_ns=100,
        )
        widget.display_capture(capture)

        widget._update_edge_hover(channel=0, time_ns=400, tolerance_ns=0)

        self.assertAlmostEqual(widget.measure_line1.value(), 400e-9)
        self.assertAlmostEqual(widget.measure_line2.value(), 200e-9)
        self.assertAlmostEqual(widget.measure_text.pos().x(), 400e-9)

    def test_scene_mouse_mapping_uses_pixel_snap_radius_without_showing_widget(self):
        from PyQt5.QtCore import QPointF

        widget = self.WaveformView()
        self.addCleanup(widget.close)
        widget.resize(800, 400)
        widget.layout().activate()
        capture = self.Capture(
            samples_for_channel(0, [0, 0, 1, 1, 0, 0]),
            sample_period_ns=100,
        )
        widget.display_capture(capture)
        widget.layout().activate()
        self.app.processEvents()

        view_box = widget.plot_widget.getViewBox()
        edge_scene = view_box.mapViewToScene(QPointF(200e-9, 7.4))

        widget.on_mouse_moved(edge_scene)
        self.assertTrue(widget.measure_text.isVisible())

        widget.on_mouse_moved(QPointF(edge_scene.x() + 6, edge_scene.y()))
        self.assertTrue(widget.measure_text.isVisible())

        widget.on_mouse_moved(QPointF(edge_scene.x() + 20, edge_scene.y()))
        self.assertFalse(widget.measure_line1.isVisible())
        self.assertFalse(widget.measure_line2.isVisible())
        self.assertFalse(widget.measure_text.isVisible())


if __name__ == "__main__":
    unittest.main()
