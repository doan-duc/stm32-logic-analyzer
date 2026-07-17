import pyqtgraph as pg
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QScrollBar
from PyQt5.QtCore import Qt, pyqtSignal
import numpy as np
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import colors from styles
try:
    from .styles import CHANNEL_COLORS, COLORS
except ImportError:
    # Fallback colors if styles not available
    CHANNEL_COLORS = [
        '#ff5252', '#ffb142', '#2ccce4', '#33d9b2',
        '#706fd3', '#f78fb3', '#82ccdd', '#b33939'
    ]
    COLORS = {'bg_dark': '#181818', 'bg_tertiary': '#2d2d2d', 'text_primary': '#d4d4d4', 'accent_secondary': '#0098ff'}

try:
    from .edge_measurement import (
        detect_all_edge_series,
        format_edge_tooltip,
        select_nearest_edge,
    )
except ImportError:
    from gui.edge_measurement import (
        detect_all_edge_series,
        format_edge_tooltip,
        select_nearest_edge,
    )

# Enable OpenGL for hardware acceleration
pg.setConfigOptions(useOpenGL=True, enableExperimental=True, antialias=True)

class TimeZoomViewBox(pg.ViewBox):
    """Rectangle zoom that changes only the time axis."""

    def showAxRect(self, rect, **kwargs):
        normalized = rect.normalized()
        if normalized.width() <= 0:
            return

        self.setXRange(normalized.left(), normalized.right(), padding=0)
        self.sigRangeChangedManually.emit(self.state['mouseEnabled'])


class WaveformView(QWidget):
    auto_scroll_changed = pyqtSignal(bool)
    EDGE_HOVER_RADIUS_PX = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.num_channels = 8
        self.channel_colors = CHANNEL_COLORS
        
        # Pin mapping reference (CH -> STM32 Pin)
        self.pin_mapping = {
            0: 'PA0', 1: 'PA1', 2: 'PA2', 3: 'PA3',
            4: 'PA4', 5: 'PA5', 6: 'PA6', 7: 'PA7'
        }
        self.zoom_level = 1.0
        self.updating_scrollbar = False
        self.live_view_width = None
        self.auto_scroll = True
        self.history_navigation_enabled = True
        
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Control bar
        controls = QHBoxLayout()
        controls.setContentsMargins(8, 8, 8, 8)
        controls.setSpacing(8)
        
        # Zoom controls
        zoom_label = QLabel("ZOOM")
        zoom_label.setStyleSheet(f"color: {COLORS.get('text_secondary', '#858585')}; font-weight: bold; font-size: 9pt;")
        controls.addWidget(zoom_label)
        
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setMaximumWidth(40)
        zoom_in_btn.clicked.connect(self.zoom_in)
        zoom_in_btn.setToolTip("Zoom in")
        controls.addWidget(zoom_in_btn)
        
        zoom_out_btn = QPushButton("-")
        zoom_out_btn.setMaximumWidth(40)
        zoom_out_btn.clicked.connect(self.zoom_out)
        zoom_out_btn.setToolTip("Zoom out")
        controls.addWidget(zoom_out_btn)
        
        zoom_fit_btn = QPushButton("Fit")
        zoom_fit_btn.setMaximumWidth(60)
        zoom_fit_btn.clicked.connect(self.zoom_fit)
        zoom_fit_btn.setToolTip("Fit to window")
        controls.addWidget(zoom_fit_btn)

        self.region_zoom_btn = QPushButton("Region Zoom")
        self.region_zoom_btn.setObjectName("regionZoomBtn")
        self.region_zoom_btn.setCheckable(True)
        self.region_zoom_btn.setChecked(True)
        self.region_zoom_btn.setToolTip(
            "Drag a rectangle over the waveform to zoom the selected time range"
        )
        self.region_zoom_btn.clicked.connect(self.set_region_zoom_enabled)
        controls.addWidget(self.region_zoom_btn)
        
        controls.addStretch()
        
        layout.addLayout(controls)
        
        # Create plot widget with dark theme
        self.view_box = TimeZoomViewBox()
        self.plot_widget = pg.PlotWidget(viewBox=self.view_box)
        
        # Dark background
        self.plot_widget.setBackground(COLORS['bg_dark'])
        
        # Configure axes
        self.plot_widget.setLabel('bottom', 'Time', units='s', 
                                  color=COLORS['text_primary'])
        self.plot_widget.setLabel('left', 'Channel', 
                                  color=COLORS['text_primary'])
        
        # Style the axes
        axis_pen = pg.mkPen(color=COLORS.get('text_disabled', '#585858'), width=1)
        self.plot_widget.getAxis('bottom').setPen(axis_pen)
        self.plot_widget.getAxis('left').setPen(axis_pen)
        self.plot_widget.getAxis('bottom').setTextPen(COLORS.get('text_secondary', '#858585'))
        self.plot_widget.getAxis('left').setTextPen(COLORS.get('text_secondary', '#858585'))
        
        # Grid styling - subtle and non-intrusive
        self.plot_widget.showGrid(x=True, y=False, alpha=0.1)
        
        # Enable mouse interaction (Horizontal only)
        self.plot_widget.setMouseEnabled(x=True, y=False)
        self.set_region_zoom_enabled(True)
        self.plot_widget.plotItem.setMenuEnabled(False) 
        
        # UI Elements for Measurement (Hover edges)
        self.measure_line1 = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(color=COLORS.get('accent_secondary', '#0098ff'), width=1.5, style=Qt.DashLine))
        self.measure_line2 = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(color=COLORS.get('accent_secondary', '#0098ff'), width=1.5, style=Qt.DashLine))
        self.measure_text = pg.TextItem(
            color=COLORS.get('text_bright', '#ffffff'), 
            fill=pg.mkBrush(pg.colorTuple(pg.mkColor(COLORS.get('bg_tertiary', '#2d2d2d')))[:3] + (200,)), 
            anchor=(0.5, 1.0)
        )
        self.measure_line1.hide()
        self.measure_line2.hide()
        self.measure_text.hide()
        
        self.plot_widget.addItem(self.measure_line1)
        self.plot_widget.addItem(self.measure_line2)
        self.plot_widget.addItem(self.measure_text)
        
        # Pre-calculated rising and falling edges per channel.
        self.edge_cache = [[] for _ in range(self.num_channels)]
        
        # Connect signals
        self.plot_widget.scene().sigMouseClicked.connect(self.on_mouse_clicked)
        self.plot_widget.scene().sigMouseMoved.connect(self.on_mouse_moved)
        self.plot_widget.sigXRangeChanged.connect(self.update_scrollbar_from_plot)
        
        layout.addWidget(self.plot_widget)
        
        # Horizontal Scrollbar
        self.scrollbar = QScrollBar(Qt.Horizontal)
        self.scrollbar.setRange(0, 10000)
        self.scrollbar.setToolTip("Drag to browse captured history")
        self.scrollbar.sliderPressed.connect(self.on_scrollbar_pressed)
        self.scrollbar.valueChanged.connect(self.on_scrollbar_scroll)
        self.scrollbar.setStyleSheet(f"""
            QScrollBar:horizontal {{
                border: none;
                background: {COLORS['bg_tertiary']};
                height: 14px;
                margin: 0px 0px 0px 0px;
            }}
            QScrollBar::handle:horizontal {{
                background: #555;
                min-width: 20px;
                border-radius: 7px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                border: none;
                background: none;
            }}
        """)
        layout.addWidget(self.scrollbar)
        
        self.setLayout(layout)
        
        # Store plot items
        self.channel_plots = []
        self.channel_labels = []
        self.current_capture = None
    
    def on_mouse_clicked(self, event):
        """Stop auto-scroll on user interaction"""
        if not self.auto_scroll:
             return
        self.set_auto_scroll(False)

    def on_mouse_moved(self, pos):
        """Snap the pointer to the closest digital edge on its channel."""
        if not self.current_capture:
            self.hide_measurement()
            return

        view_box = self.plot_widget.getViewBox()
        scene_bounds = view_box.sceneBoundingRect()
        if not scene_bounds.contains(pos) or scene_bounds.width() <= 0:
            self.hide_measurement()
            return

        mouse_point = view_box.mapSceneToView(pos)
        y = mouse_point.y()

        channel = int(self.num_channels - 1 - np.floor(y))
        view_start, view_end = view_box.viewRange()[0]
        tolerance_ns = (
            max(view_end - view_start, 0)
            * 1_000_000_000
            * self.EDGE_HOVER_RADIUS_PX
            / scene_bounds.width()
        )
        self._update_edge_hover(
            channel=channel,
            time_ns=mouse_point.x() * 1_000_000_000,
            tolerance_ns=tolerance_ns,
        )

    def _update_edge_hover(self, *, channel, time_ns, tolerance_ns):
        """Update edge markers without relying on scene-coordinate mapping."""
        if (
            not self.current_capture
            or not isinstance(channel, int)
            or isinstance(channel, bool)
            or not 0 <= channel < self.num_channels
            or channel >= len(self.edge_cache)
        ):
            self.hide_measurement()
            return None

        try:
            edge = select_nearest_edge(
                self.edge_cache[channel],
                time_ns=time_ns,
                tolerance_ns=tolerance_ns,
            )
        except (TypeError, ValueError):
            self.hide_measurement()
            return None

        if edge is None:
            self.hide_measurement()
            return None

        edge_time = edge.timestamp_ns / 1_000_000_000
        self.measure_line1.setPos(edge_time)
        if edge.delta_ns is not None:
            previous_time = (
                edge.timestamp_ns - edge.delta_ns
            ) / 1_000_000_000
            self.measure_line2.setPos(previous_time)
            self.measure_line2.show()
        else:
            self.measure_line2.hide()

        self.measure_text.setHtml(
            format_edge_tooltip(
                edge,
                pin_name=self.pin_mapping.get(channel, "?"),
            )
        )
        y_base = self.num_channels - 1 - channel
        self.measure_text.setPos(edge_time, y_base + 0.8)
        self.measure_line1.show()
        self.measure_text.show()
        return edge

    def hide_measurement(self):
        """Hide the hover measurement UI"""
        self.measure_line1.hide()
        self.measure_line2.hide()
        self.measure_text.hide()

    def set_auto_scroll(self, enabled):
        """Enable/disable auto-scrolling"""
        if self.auto_scroll == enabled:
            return
        self.auto_scroll = enabled
        self.auto_scroll_changed.emit(enabled)

    def set_region_zoom_available(self, available):
        """Enable rectangle zoom only while capture playback is stopped."""
        self.region_zoom_btn.setEnabled(available)
        self.region_zoom_btn.setChecked(available)
        self.set_region_zoom_enabled(available)

    def set_history_navigation_enabled(self, enabled):
        """Allow history scrubbing only when the waveform is not updating."""
        self.history_navigation_enabled = enabled
        self.scrollbar.setToolTip(
            "Drag to browse captured history"
            if enabled
            else "Pause Live to browse captured history"
        )
        self.update_scrollbar_from_plot()

    def set_region_zoom_enabled(self, enabled):
        """Switch left-drag between rectangle zoom and horizontal pan."""
        self.region_zoom_btn.blockSignals(True)
        self.region_zoom_btn.setChecked(enabled)
        self.region_zoom_btn.blockSignals(False)

        mode = pg.ViewBox.RectMode if enabled else pg.ViewBox.PanMode
        self.plot_widget.getViewBox().setMouseMode(mode)

    def begin_live_capture(self):
        """Reset the viewport before starting a new live session."""
        self.live_view_width = None
        self.set_auto_scroll(True)

    def reset_view(self):
        """Clear all waveform data and restore the initial viewport state."""
        self.current_capture = None
        self.live_view_width = None
        self.edge_cache = [[] for _ in range(self.num_channels)]
        self.hide_measurement()

        self.plot_widget.clear()
        self.plot_widget.addItem(self.measure_line1)
        self.plot_widget.addItem(self.measure_line2)
        self.plot_widget.addItem(self.measure_text)
        self.channel_plots = []
        self.channel_labels = []

        self.plot_widget.getAxis('left').setTicks([[]])
        self.plot_widget.setXRange(0, 1, padding=0)
        self.plot_widget.setYRange(-0.5, self.num_channels + 0.5)
        self.plot_widget.plotItem.enableAutoRange(pg.ViewBox.XYAxes)

        self.scrollbar.blockSignals(True)
        self.scrollbar.setRange(0, 0)
        self.scrollbar.setPageStep(0)
        self.scrollbar.setValue(0)
        self.scrollbar.setEnabled(False)
        self.scrollbar.blockSignals(False)

        self.set_auto_scroll(True)
        self.set_region_zoom_available(True)
        self.set_history_navigation_enabled(True)

    def scroll_to_latest(self):
        """Move the viewport to the newest samples."""
        if not self.current_capture or len(self.current_capture.time) == 0:
            return

        current_time = self.current_capture.time[-1]
        view_width = self.live_view_width
        if not view_width:
            view_range = self.plot_widget.getViewBox().viewRange()[0]
            view_width = max(view_range[1] - view_range[0], 1e-9)

        start_time = max(self.current_capture.time[0], current_time - view_width)
        self.plot_widget.setXRange(start_time, current_time, padding=0)
    
    def update_scrollbar_from_plot(self):
        """Update scrollbar position and page size based on plot ViewBox"""
        if self.updating_scrollbar or not self.current_capture:
            return
            
        view_box = self.plot_widget.getViewBox()
        view_range = view_box.viewRange()[0]
        start_time, end_time = view_range

        data_start = self.current_capture.time[0]
        data_end = self.current_capture.time[-1]
        total_time = max(data_end - data_start, 1e-9)
        
        view_width = min(max(end_time - start_time, 0), total_time)
        SCROLL_MAX = 10000

        page_step = int((view_width / total_time) * SCROLL_MAX)
        page_step = max(10, min(SCROLL_MAX, page_step))

        scroll_range = SCROLL_MAX - page_step
        max_start_time = max(total_time - view_width, 0)
        if scroll_range > 0 and max_start_time > 0:
            position = (start_time - data_start) / max_start_time
            value = int(max(0.0, min(1.0, position)) * scroll_range)
        else:
            value = 0
        
        self.scrollbar.blockSignals(True)
        self.scrollbar.setRange(0, scroll_range)
        self.scrollbar.setPageStep(page_step)
        self.scrollbar.setSingleStep(max(1, scroll_range // 100))
        self.scrollbar.setValue(value)
        self.scrollbar.setEnabled(
            self.history_navigation_enabled and scroll_range > 0
        )
        self.scrollbar.blockSignals(False)
        self._position_channel_labels(start_time, end_time)

    def on_scrollbar_pressed(self):
        """Release live-follow as soon as the user grabs the scrollbar."""
        self.set_auto_scroll(False)
        
    def on_scrollbar_scroll(self, value):
        """Update plot X range based on scrollbar value"""
        if not self.current_capture:
            return
            
        self.updating_scrollbar = True
        self.set_auto_scroll(False)
        
        data_start = self.current_capture.time[0]
        data_end = self.current_capture.time[-1]
        total_time = max(data_end - data_start, 1e-9)
        view_box = self.plot_widget.getViewBox()
        current_view_width = view_box.viewRange()[0][1] - view_box.viewRange()[0][0]
        current_view_width = min(max(current_view_width, 0), total_time)
        max_start_time = max(total_time - current_view_width, 0)
        scroll_range = self.scrollbar.maximum() - self.scrollbar.minimum()
        position = (
            (value - self.scrollbar.minimum()) / scroll_range
            if scroll_range > 0
            else 0
        )

        start_time = data_start + position * max_start_time
        end_time = start_time + current_view_width
        
        self.plot_widget.setXRange(start_time, end_time, padding=0)
        self.updating_scrollbar = False

    def zoom_in(self):
        """Zoom in on the waveform"""
        self.set_auto_scroll(False)
        view_box = self.plot_widget.getViewBox()
        view_box.scaleBy((0.5, 1))
    
    def zoom_out(self):
        """Zoom out on the waveform"""
        self.set_auto_scroll(False)
        view_box = self.plot_widget.getViewBox()
        view_box.scaleBy((2, 1))
    
    def zoom_fit(self):
        """Fit waveform to window"""
        self.set_auto_scroll(False)
        self.plot_widget.autoRange()
    
    def display_capture(
        self,
        capture,
        is_rolling_update=False,
        visible_sample_limit=None,
    ):
        """Display a Capture object with enhanced styling and performance"""
        if not capture or len(capture.time) == 0:
            return
        
        self.current_capture = capture

        render_start = 0
        if visible_sample_limit and capture.sample_count > visible_sample_limit:
            render_start = capture.sample_count - visible_sample_limit

        render_time = capture.time[render_start:]
        
        edge_start = max(render_start - 1, 0)
        edge_samples = capture.samples[edge_start:]
        sample_offset = int(round(
            capture.time[edge_start]
            * 1_000_000_000
            / capture.sample_period_ns
        ))
        self.edge_cache = detect_all_edge_series(
            edge_samples,
            sample_period_ns=capture.sample_period_ns,
            sample_offset=sample_offset,
        )
        
        first_display = len(self.channel_plots) == 0

        if not is_rolling_update or first_display:
             self.plot_widget.clear()
             
             # Re-add measurement items after clear
             self.plot_widget.addItem(self.measure_line1)
             self.plot_widget.addItem(self.measure_line2)
             self.plot_widget.addItem(self.measure_text)
             
             self.channel_plots = []
             self.channel_labels = []
             self.plot_widget.plotItem.enableAutoRange(pg.ViewBox.XYAxes)
        
        channel_height = 0.8
        channel_spacing = 1.0
        
        should_scroll = self.auto_scroll and is_rolling_update

        if should_scroll and self.live_view_width is None:
            sample_period = capture.sample_period_ns / 1e9
            live_samples = visible_sample_limit or len(render_time)
            self.live_view_width = max(live_samples * sample_period, sample_period)

        if should_scroll:
            self.plot_widget.plotItem.disableAutoRange(pg.ViewBox.XAxis)

        for ch in range(self.num_channels):
            channel_data = capture.get_channel(ch)[render_start:]

            time_ds, data_ds = self._digital_edge_points(
                render_time,
                channel_data,
            )
            
            time_expanded, data_expanded = self._expand_digital(time_ds, data_ds)
            y_base = (self.num_channels - 1 - ch) * channel_spacing
            data_plot = (data_expanded * channel_height) + y_base
            
            if is_rolling_update and not first_display and ch < len(self.channel_plots):
                self.channel_plots[ch].setData(time_expanded, data_plot)
            else:
                pen = pg.mkPen(color=self.channel_colors[ch], width=1.5)
                plot = self.plot_widget.plot(
                    time_expanded, 
                    data_plot,
                    pen=pen,
                    name=f'CH{ch}',
                    antialias=False, 
                    autoDownsample=False 
                )
                
                if ch >= len(self.channel_plots):
                    self.channel_plots.append(plot)
                else:
                    self.channel_plots[ch] = plot
                
                if ch >= len(self.channel_labels):
                    pin_name = self.pin_mapping.get(ch, '?')
                    label_text = f'''
                    <div style="font-family: monospace; font-weight: bold;">
                        <span style="color: {self.channel_colors[ch]};">CH{ch}</span>
                        <span style="color: {COLORS.get('text_secondary', '#858585')}; font-size: 8pt;">({pin_name})</span>
                    </div>
                    '''
                    text_item = pg.TextItem(html=label_text, anchor=(0, 0.5))
                    text_item.setPos(capture.time[0], y_base + channel_height/2)
                    self.plot_widget.addItem(text_item)
                    self.channel_labels.append(text_item)
                else:
                    self.channel_labels[ch].setPos(capture.time[0], y_base + channel_height/2)

        if not is_rolling_update or first_display:
            self.plot_widget.setYRange(-0.5, self.num_channels * channel_spacing + 0.5)
            y_ticks = [((self.num_channels - 1 - i) * channel_spacing + channel_height/2, f'CH{i}') 
                       for i in range(self.num_channels)]
            self.plot_widget.getAxis('left').setTicks([y_ticks])
            if not is_rolling_update:
                self.plot_widget.autoRange()

        if should_scroll:
            self.scroll_to_latest()
    
        self.update_scrollbar_from_plot()

    @staticmethod
    def _digital_edge_points(time, data):
        """Keep every digital transition while removing redundant samples."""
        if len(data) <= 2:
            return time, data

        transition_idx = np.flatnonzero(data[1:] != data[:-1]) + 1
        indices = np.concatenate((
            np.array([0], dtype=np.int64),
            transition_idx,
            np.array([len(data) - 1], dtype=np.int64),
        ))
        indices = np.unique(indices)
        return time[indices], data[indices]

    def _position_channel_labels(self, start_time, end_time):
        """Keep channel labels visible at the left edge of the viewport."""
        if not self.channel_labels:
            return

        label_x = start_time + max(end_time - start_time, 0) * 0.005
        channel_height = 0.8
        for ch, label in enumerate(self.channel_labels):
            y_base = self.num_channels - 1 - ch
            label.setPos(label_x, y_base + channel_height / 2)

    def _expand_digital(self, time, data):
        """Convert to step waveform by duplicating points using numpy"""
        if len(time) < 2:
            return time, data
        
        time_expanded = np.repeat(time, 2)[1:]
        data_expanded = np.repeat(data, 2)[:-1]
        
        return time_expanded, data_expanded
