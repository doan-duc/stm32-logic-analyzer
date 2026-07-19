from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QComboBox, 
                             QLabel, QStatusBar, QFrame, QSplitter, QSlider,
                             QCheckBox, QTableWidget, QTableWidgetItem)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QFont
from .waveform_view import WaveformView
from .styles import get_main_stylesheet, get_status_indicator_html, COLORS
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from device import LogicAnalyzerDevice
from capture import Capture
from decoders import decode_i2c, decode_spi, decode_uart

DEFAULT_CAPTURE_BUFFER_SAMPLES = 8192
RATE_OPTIONS = [
    (1_000, "1 kHz"),
    (10_000, "10 kHz"),
    (50_000, "50 kHz"),
    (100_000, "100 kHz"),
    (500_000, "500 kHz"),
    (1_000_000, "1 MHz"),
    (2_000_000, "2 MHz"),
    (3_000_000, "3 MHz"),
    (4_000_000, "4 MHz"),
    (6_000_000, "6 MHz"),
    (6_545_454, "6.55 MHz (max)"),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.device = None
        self.current_capture = None
        self.full_capture = None
        self.live_mode = False
        self.capture_mode = "offline"
        self.realtime_busy = False
        self.capture_count = 0
        self.live_buffer_max_samples = 204800
        self.live_render_samples = 8192
        self.capture_buffer_samples = DEFAULT_CAPTURE_BUFFER_SAMPLES
        self.stream_dropped_frames = 0
        self.stream_corrupt_frames = 0
        
        # Live capture timer
        self.live_timer = QTimer()
        self.live_timer.timeout.connect(self.read_live_stream)
        self.live_interval_ms = 33
        
        # Professional Title
        self.setWindowTitle("STM32 Logic Analyzer Pro")
        self.setGeometry(100, 100, 1400, 900)
        
        # Apply modern stylesheet
        self.setStyleSheet(get_main_stylesheet())
        
        self.setup_ui()
    
    def setup_ui(self):
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Toolbar container with background
        toolbar_container = QWidget()
        toolbar_container.setObjectName("toolbar")
        toolbar_layout = QVBoxLayout(toolbar_container)
        toolbar_layout.setContentsMargins(16, 12, 16, 12)
        toolbar_layout.setSpacing(12)
        
        # ROW 1: Connection and Capture Controls
        row1 = QHBoxLayout()
        row1.setSpacing(16)
        
        # Connection Section
        conn_label = QLabel("CONNECTION")
        conn_label.setObjectName("sectionLabel")
        row1.addWidget(conn_label)
        
        row1.addWidget(QLabel("Port:"))
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(120)
        self.port_combo.setToolTip("Select serial port")
        self.refresh_ports()
        row1.addWidget(self.port_combo)
        
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip("Clear captures and refresh the workspace")
        self.refresh_btn.clicked.connect(self.refresh_workspace)
        row1.addWidget(self.refresh_btn)
        
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setObjectName("connectBtn")
        self.connect_btn.setToolTip("Connect to device")
        self.connect_btn.setMinimumWidth(100)
        self.connect_btn.clicked.connect(self.toggle_connection)
        self.connect_btn.setProperty("connected", False)
        row1.addWidget(self.connect_btn)
        
        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setFrameShadow(QFrame.Sunken)
        row1.addWidget(sep1)
        
        # Capture Section
        cap_label = QLabel("CAPTURE")
        cap_label.setObjectName("sectionLabel")
        row1.addWidget(cap_label)
        
        row1.addWidget(QLabel("Sample Rate:"))
        self.rate_combo = QComboBox()
        self.rate_combo.setMinimumWidth(160)
        self.rate_combo.addItems(self.rate_window_labels())
        self.rate_combo.setCurrentIndex(3)
        self.update_rate_tooltip()
        self.rate_combo.currentIndexChanged.connect(self.on_rate_changed)
        row1.addWidget(self.rate_combo)
        
        self.capture_btn = QPushButton("Capture")
        self.capture_btn.setObjectName("captureBtn")
        self.capture_btn.setToolTip("Start single capture")
        self.capture_btn.clicked.connect(self.do_capture)
        self.capture_btn.setEnabled(False)
        row1.addWidget(self.capture_btn)

        self.trigger_checkbox = QCheckBox("Trigger PA0 falling")
        self.trigger_checkbox.setChecked(False)
        self.trigger_checkbox.setToolTip(
            "Single capture only: wait for a UART start edge on PA0"
        )
        self.trigger_checkbox.toggled.connect(self.on_trigger_changed)
        self.trigger_checkbox.setEnabled(False)
        row1.addWidget(self.trigger_checkbox)
        
        row1.addStretch()
        
        # Sample rate display
        self.sample_rate_label = QLabel("Rate: --")
        self.sample_rate_label.setStyleSheet(f"color: {COLORS['accent_secondary']}; font-weight: bold;")
        row1.addWidget(self.sample_rate_label)
        
        toolbar_layout.addLayout(row1)
        
        # ROW 2: Mode Controls
        row2 = QHBoxLayout()
        row2.setSpacing(16)
        
        mode_label = QLabel("MODE")
        mode_label.setObjectName("sectionLabel")
        row2.addWidget(mode_label)

        self.offline_mode_btn = QPushButton("Offline")
        self.offline_mode_btn.setObjectName("modeBtn")
        self.offline_mode_btn.setCheckable(True)
        self.offline_mode_btn.setChecked(True)
        self.offline_mode_btn.setToolTip("Single offline capture")
        self.offline_mode_btn.clicked.connect(lambda: self.set_capture_mode("offline"))
        row2.addWidget(self.offline_mode_btn)

        self.realtime_mode_btn = QPushButton("Realtime")
        self.realtime_mode_btn.setObjectName("modeBtn")
        self.realtime_mode_btn.setCheckable(True)
        self.realtime_mode_btn.setToolTip("Repeated capture display")
        self.realtime_mode_btn.clicked.connect(lambda: self.set_capture_mode("realtime"))
        row2.addWidget(self.realtime_mode_btn)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setFrameShadow(QFrame.Sunken)
        row2.addWidget(sep2)

        live_label = QLabel("REALTIME")
        live_label.setObjectName("sectionLabel")
        row2.addWidget(live_label)
        
        self.live_btn = QPushButton("Start Realtime")
        self.live_btn.setCheckable(True)
        self.live_btn.setToolTip("Start repeated captures")
        self.live_btn.setMinimumWidth(130)
        self.live_btn.clicked.connect(self.toggle_live_mode)
        self.live_btn.setEnabled(False)
        row2.addWidget(self.live_btn)
        
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setCheckable(True)
        self.pause_btn.setToolTip("Pause/Resume live update")
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.pause_btn.setEnabled(False)
        row2.addWidget(self.pause_btn)

        self.follow_btn = QPushButton("Follow Live")
        self.follow_btn.setObjectName("followBtn")
        self.follow_btn.setCheckable(True)
        self.follow_btn.setChecked(True)
        self.follow_btn.setToolTip("Keep the view pinned to the newest live samples")
        self.follow_btn.clicked.connect(self.toggle_follow_live)
        self.follow_btn.setEnabled(False)
        row2.addWidget(self.follow_btn)
        
        row2.addWidget(QLabel("Interval:"))
        
        self.interval_slider = QSlider(Qt.Horizontal)
        self.interval_slider.setMinimum(16)
        self.interval_slider.setMaximum(1000)
        self.interval_slider.setValue(33)
        self.interval_slider.setMaximumWidth(200)
        self.interval_slider.setToolTip("Live display refresh interval (16ms - 1s)")
        self.interval_slider.valueChanged.connect(self.update_live_interval)
        row2.addWidget(self.interval_slider)
        
        self.interval_label = QLabel("33ms")
        self.interval_label.setStyleSheet(f"color: {COLORS['accent_secondary']}; font-weight: bold;")
        self.interval_label.setMinimumWidth(60)
        row2.addWidget(self.interval_label)
        
        row2.addStretch()
        
        toolbar_layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(16)

        decode_label = QLabel("DECODE")
        decode_label.setObjectName("sectionLabel")
        row3.addWidget(decode_label)

        row3.addWidget(QLabel("Protocol:"))
        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems(["UART", "I2C", "SPI"])
        self.protocol_combo.currentIndexChanged.connect(self.on_decode_protocol_changed)
        row3.addWidget(self.protocol_combo)

        self.decode_ch_a_label = QLabel("RX/SCL:")
        self.decode_ch_a_combo = QComboBox()
        self.decode_ch_a_combo.addItems([f"CH{i}" for i in range(8)])
        self.decode_ch_a_combo.setCurrentIndex(0)
        row3.addWidget(self.decode_ch_a_label)
        row3.addWidget(self.decode_ch_a_combo)

        self.decode_ch_b_label = QLabel("SDA:")
        self.decode_ch_b_combo = QComboBox()
        self.decode_ch_b_combo.addItems([f"CH{i}" for i in range(8)])
        self.decode_ch_b_combo.setCurrentIndex(2)
        row3.addWidget(self.decode_ch_b_label)
        row3.addWidget(self.decode_ch_b_combo)

        self.decode_ch_c_label = QLabel("MISO:")
        self.decode_ch_c_combo = QComboBox()
        self.decode_ch_c_combo.addItems([f"CH{i}" for i in range(8)])
        self.decode_ch_c_combo.setCurrentIndex(2)
        row3.addWidget(self.decode_ch_c_label)
        row3.addWidget(self.decode_ch_c_combo)

        self.decode_ch_d_label = QLabel("CS:")
        self.decode_ch_d_combo = QComboBox()
        self.decode_ch_d_combo.addItems([f"CH{i}" for i in range(8)])
        self.decode_ch_d_combo.setCurrentIndex(3)
        row3.addWidget(self.decode_ch_d_label)
        row3.addWidget(self.decode_ch_d_combo)

        row3.addWidget(QLabel("Baud:"))
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["2400", "4800", "9600", "38400", "57600", "115200"])
        self.baud_combo.setCurrentText("2400")
        row3.addWidget(self.baud_combo)

        self.decode_btn = QPushButton("Decode")
        self.decode_btn.setToolTip("Decode current captured waveform")
        self.decode_btn.clicked.connect(self.decode_current_capture)
        self.decode_btn.setEnabled(False)
        row3.addWidget(self.decode_btn)

        row3.addStretch()
        toolbar_layout.addLayout(row3)
        
        layout.addWidget(toolbar_container)
        
        # Status Indicator below toolbar
        self.status_indicator = QLabel()
        self.status_indicator.setTextFormat(Qt.RichText)
        self.status_indicator.setContentsMargins(16, 8, 16, 8)
        self.update_status_indicator("disconnected", "Disconnected")
        layout.addWidget(self.status_indicator)
        
        self.content_splitter = QSplitter(Qt.Vertical)
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.setHandleWidth(8)

        self.waveform_view = WaveformView()
        self.waveform_view.auto_scroll_changed.connect(self.on_auto_scroll_changed)
        self.waveform_view.set_region_zoom_available(True)
        self.content_splitter.addWidget(self.waveform_view)

        self.decode_table = QTableWidget(0, 5)
        self.decode_table.setHorizontalHeaderLabels(
            ["Time (us)", "Protocol", "Event", "Value", "Note"]
        )
        self.decode_table.setMinimumHeight(90)
        self.content_splitter.addWidget(self.decode_table)
        self.content_splitter.setStretchFactor(0, 5)
        self.content_splitter.setStretchFactor(1, 1)
        self.content_splitter.setSizes([680, 180])
        layout.addWidget(self.content_splitter, 1)
        self.on_decode_protocol_changed()
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def update_status_indicator(self, status, text):
        """Update the status indicator with colored dot"""
        html = get_status_indicator_html(status, text)
        self.status_indicator.setText(html)
    
    def refresh_ports(self, preferred_port=None):
        selected_port = (
            preferred_port
            or self.port_combo.currentData()
            or self.port_combo.currentText()
        )
        self.port_combo.clear()
        ports = LogicAnalyzerDevice.list_port_details()
        if ports:
            for port in ports:
                usb_id = ""
                if port["vid"] is not None and port["pid"] is not None:
                    usb_id = f" [{port['vid']:04X}:{port['pid']:04X}]"
                label = f"{port['device']} — {port['description']}{usb_id}"
                self.port_combo.addItem(label, port["device"])
            selected_index = self.port_combo.findData(selected_port)
            if selected_index >= 0:
                self.port_combo.setCurrentIndex(selected_index)
        else:
            self.port_combo.addItem("No ports found", None)

    def refresh_workspace(self):
        """Return the capture workspace to a clean initial state."""
        selected_port = (
            self.device.port
            if self.device and self.device.serial
            else (self.port_combo.currentData() or self.port_combo.currentText())
        )

        if self.live_mode:
            self.live_btn.setChecked(False)
            self.toggle_live_mode()

        self.current_capture = None
        self.full_capture = None
        self.decode_table.setRowCount(0)
        self.capture_count = 0
        self.stream_dropped_frames = 0
        self.stream_corrupt_frames = 0

        self.pause_btn.setChecked(False)
        self.pause_btn.setText("Pause")
        self.follow_btn.setChecked(True)
        self.set_capture_mode("offline")
        self.waveform_view.reset_view()
        self.refresh_ports(selected_port)

        if self.device and self.device.serial:
            self.update_status_indicator("connected", "Connected")
            self.status_bar.showMessage("Workspace refreshed")
        else:
            self.capture_buffer_samples = DEFAULT_CAPTURE_BUFFER_SAMPLES
            self.refresh_rate_window_labels()
            self.update_status_indicator("disconnected", "Disconnected")
            self.sample_rate_label.setText("Rate: --")
            self.status_bar.showMessage("Workspace refreshed; select a port")
    
    def toggle_connection(self):
        if self.device and self.device.serial:
            # Disconnect
            if self.live_mode:
                self.live_btn.setChecked(False)
                self.toggle_live_mode()
            self.device.disconnect()
            self.device = None
            self.connect_btn.setText("Connect")
            self.connect_btn.setProperty("connected", False)
            self.connect_btn.setStyle(self.connect_btn.style())  # Refresh style
            self.capture_btn.setEnabled(False)
            self.capture_buffer_samples = DEFAULT_CAPTURE_BUFFER_SAMPLES
            self.refresh_rate_window_labels()
            self.update_status_indicator("disconnected", "Disconnected")
            self.status_bar.showMessage("Disconnected from device")
            self.sample_rate_label.setText("Rate: --")
            self.live_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)
            self.follow_btn.setEnabled(False)
            self.trigger_checkbox.setEnabled(False)
            self.offline_mode_btn.setEnabled(True)
            self.realtime_mode_btn.setEnabled(True)
        else:
            # Connect
            port = self.port_combo.currentData()
            if not port:
                self.status_bar.showMessage("No serial ports available")
                return
            
            try:
                self.device = LogicAnalyzerDevice(port)
                if self.device.connect():
                    self.connect_btn.setText("Disconnect")
                    self.connect_btn.setProperty("connected", True)
                    self.connect_btn.setStyle(self.connect_btn.style())  # Refresh style
                    info = self.device.device_info
                    self.capture_buffer_samples = int(
                        info.get("buffer_size") or DEFAULT_CAPTURE_BUFFER_SAMPLES
                    )
                    self.refresh_rate_window_labels()
                    self.apply_mode_controls()
                    self.on_rate_changed(self.rate_combo.currentIndex())
                    self.on_trigger_changed(self.trigger_checkbox.isChecked())
                    self.update_status_indicator("connected", "Connected")
                    self.status_bar.showMessage(
                        f"Connected to {info['device_name']} {info['version']} on {port}"
                    )
                else:
                    self.update_status_indicator("error", "Connection Failed")
                    self.status_bar.showMessage(f"Failed to connect to {port}")
                    self.device = None
            except PermissionError:
                self.update_status_indicator("error", "Port In Use")
                self.status_bar.showMessage(
                    f"{port} is in use by another program. Close other applications and try again."
                )
                self.device = None
            except Exception as e:
                self.update_status_indicator("error", "Connection Error")
                error_msg = str(e)
                if "PermissionError" in error_msg or "Access is denied" in error_msg:
                    self.status_bar.showMessage(
                        f"{port} is in use. Close other serial programs."
                    )
                elif "FileNotFoundError" in error_msg or "could not open port" in error_msg:
                    self.status_bar.showMessage(f"{port} not found. Check device connection.")
                else:
                    self.status_bar.showMessage(f"Error: {error_msg}")
                self.device = None
    
    def do_capture(self):
        if not self.device:
            return
        
        # Don't disable button in live mode
        if not self.live_mode:
            self.update_status_indicator("capturing", "Capturing...")
            self.status_bar.showMessage("Capturing data...")
            self.capture_btn.setEnabled(False)
        
        # Capture (blocking for now)
        frame = self.device.capture()
        
        if frame and frame['type'] == 'trigger_timeout':
            self.update_status_indicator("warning", "Waiting for PA0 signal")
            self.status_bar.showMessage(
                "Trigger armed: send UART data from HC-05 to PA0"
            )
        elif frame and frame['type'] == 'capture':
            new_capture = Capture(
                frame['samples'],
                frame['sample_period_ns']
            )
            
            if self.live_mode:
                # Live Buffer Management
                if self.full_capture is None:
                    # First frame of live capture
                    self.full_capture = new_capture
                    self.current_capture = self.full_capture
                else:
                    # Append to existing buffer
                    self.full_capture.append_samples(frame['samples'])
                    overflow = self.full_capture.sample_count - self.live_buffer_max_samples
                    if overflow > 0:
                        self.full_capture.trim_start(overflow)
                    self.current_capture = self.full_capture

                # Update display
                self.waveform_view.display_capture(
                    self.current_capture,
                    is_rolling_update=True,
                    visible_sample_limit=self.live_render_samples,
                )
                
                rate = new_capture.get_sample_rate_mhz()
                self.sample_rate_label.setText(f"Rate: {rate:.2f} MHz")
                self.status_bar.showMessage(
                    f"Live: {self.current_capture.sample_count} samples buffered"
                )
                self.update_status_indicator("capturing", "Live Capture")
            else:
                # New capture (single shot)
                self.current_capture = new_capture
                self.capture_count += 1
                self.decode_btn.setEnabled(True)
                
                # Display
                self.waveform_view.display_capture(new_capture)
                
                rate = new_capture.get_sample_rate_mhz()
                self.sample_rate_label.setText(f"Rate: {rate:.2f} MHz")
                
                self.update_status_indicator("connected", "Connected")
                self.status_bar.showMessage(
                    f"Captured {new_capture.sample_count} samples @ {rate:.2f} MHz"
                )
        else:
            self.update_status_indicator("error", "Capture Failed")
            self.status_bar.showMessage("Capture failed")
            if self.live_mode:
                self.toggle_live_mode()  # Stop live mode on error
        
        if not self.live_mode:
            self.capture_btn.setEnabled(True)
            self.decode_btn.setEnabled(self.current_capture is not None)

    def read_live_stream(self):
        """Realtime mode dung offline frame lap lai, khong doi firmware stream."""
        if not self.device or not self.live_mode:
            return

        if self.realtime_busy:
            return

        self.realtime_busy = True
        try:
            frame = self.device.capture()
            if frame and frame.get('type') == 'capture':
                self.append_stream_frames([frame], update_display=True)
            elif frame and frame.get('type') == 'trigger_timeout':
                self.status_bar.showMessage("Realtime waiting for trigger")
            else:
                self.update_status_indicator("error", "Realtime Failed")
                self.status_bar.showMessage(
                    f"Realtime capture failed: {self.device.last_error or 'unknown error'}"
                )
                self.live_btn.setChecked(False)
                self.toggle_live_mode()
        finally:
            self.realtime_busy = False

    def append_stream_frames(self, frames, update_display):
        """Append validated stream frames to history without losing boundaries."""
        if not frames:
            return

        for frame in frames:
            self.stream_dropped_frames += frame.get('dropped_frames', 0)
            self.stream_corrupt_frames = frame.get(
                'corrupt_frames',
                self.stream_corrupt_frames,
            )

        combined_samples = b''.join(frame['samples'] for frame in frames)
        if self.full_capture is None:
            self.full_capture = Capture(
                combined_samples,
                frames[0]['sample_period_ns']
            )
        else:
            self.full_capture.append_samples(combined_samples)

        overflow = self.full_capture.sample_count - self.live_buffer_max_samples
        if overflow > 0:
            self.full_capture.trim_start(overflow)

        self.current_capture = self.full_capture
        self.decode_btn.setEnabled(True)
        if update_display:
            self.waveform_view.display_capture(
                self.current_capture,
                is_rolling_update=True,
                visible_sample_limit=self.live_render_samples,
            )

        rate = frames[-1]['sample_rate_hz'] / 1_000_000
        self.sample_rate_label.setText(f"Rate: {rate:.2f} MHz")
        dropped_text = (
            f" | dropped: {self.stream_dropped_frames}"
            if self.stream_dropped_frames else ""
        )
        corrupt_text = (
            f" | recovered: {self.stream_corrupt_frames}"
            if self.stream_corrupt_frames else ""
        )
        self.status_bar.showMessage(
            f"Realtime: {self.current_capture.sample_count} samples"
            f"{dropped_text}{corrupt_text}"
        )
        self.update_status_indicator("capturing", "Realtime")
    
    def toggle_live_mode(self):
        """Toggle realtime repeated offline capture mode."""
        self.live_mode = self.live_btn.isChecked()
        
        if self.live_mode:
            if not self.device:
                self.live_btn.setChecked(False)
                self.live_mode = False
                return

            self.capture_count = 0
            self.current_capture = None
            self.full_capture = None
            self.stream_dropped_frames = 0
            self.stream_corrupt_frames = 0
            self.realtime_busy = False
            self.device.set_trigger(False)

            self.live_btn.setText("Stop Realtime")
            self.live_btn.setStyleSheet(f"background-color: {COLORS['error']}; border: 1px solid {COLORS['error']}; color: white;")
            self.capture_btn.setEnabled(False)
            self.pause_btn.setEnabled(True)
            self.pause_btn.setChecked(False)
            self.pause_btn.setText("Pause")
            self.follow_btn.setEnabled(True)
            self.follow_btn.setChecked(True)
            self.trigger_checkbox.setEnabled(False)
            self.rate_combo.setEnabled(False)
            self.offline_mode_btn.setEnabled(False)
            self.realtime_mode_btn.setEnabled(False)
            self.waveform_view.set_region_zoom_available(False)
            self.waveform_view.set_history_navigation_enabled(False)
            self.waveform_view.begin_live_capture()
            
            self.update_status_indicator("capturing", "Realtime")
            self.status_bar.showMessage(
                f"Realtime started (refresh: {self.live_interval_ms}ms)"
            )
            
            self.live_timer.start(self.live_interval_ms)
            self.read_live_stream()
        else:
            self.live_timer.stop()
            self.live_btn.setText("Start Realtime")
            self.live_btn.setStyleSheet("")
            self.pause_btn.setEnabled(False)
            self.pause_btn.setChecked(False)
            self.follow_btn.setEnabled(False)
            self.rate_combo.setEnabled(True)
            self.offline_mode_btn.setEnabled(True)
            self.realtime_mode_btn.setEnabled(True)
            self.waveform_view.set_region_zoom_available(True)
            self.waveform_view.set_history_navigation_enabled(True)

            if self.current_capture:
                self.waveform_view.display_capture(self.current_capture)
            
            self.apply_mode_controls()
            self.update_status_indicator("connected", "Connected")
            self.status_bar.showMessage("Realtime stopped")

    def toggle_pause(self):
        """Pause/Resume live capture"""
        is_paused = self.pause_btn.isChecked()
        
        if is_paused:
            self.live_timer.stop()
            self.pause_btn.setText("Resume")
            self.update_status_indicator("warning", "Paused")
            self.waveform_view.set_region_zoom_available(True)
            self.waveform_view.set_history_navigation_enabled(True)
            if self.current_capture:
                self.waveform_view.display_capture(self.current_capture)
        else:
            self.live_timer.start(self.live_interval_ms)
            self.pause_btn.setText("Pause")
            self.update_status_indicator("capturing", "Realtime")
            self.waveform_view.set_region_zoom_available(False)
            self.waveform_view.set_history_navigation_enabled(False)
            self.waveform_view.begin_live_capture()
            if self.follow_btn.isChecked():
                self.waveform_view.set_auto_scroll(True)

    def toggle_follow_live(self, enabled):
        """Pin/unpin the plot from the newest live samples."""
        self.waveform_view.set_auto_scroll(enabled)
        if enabled:
            self.waveform_view.scroll_to_latest()

    def on_auto_scroll_changed(self, enabled):
        """Keep the follow control in sync with plot interactions."""
        self.follow_btn.blockSignals(True)
        self.follow_btn.setChecked(enabled)
        self.follow_btn.blockSignals(False)
    
    def update_live_interval(self, value):
        """Update realtime capture interval"""
        self.live_interval_ms = value
        self.interval_label.setText(f"{value}ms")
        
        # Update timer if running
        if self.live_mode:
            self.live_timer.setInterval(value)
            self.status_bar.showMessage(f"Realtime interval: {value}ms")

    def format_capture_window(self, sample_rate_hz):
        window_ms = self.capture_buffer_samples * 1000.0 / sample_rate_hz
        if window_ms >= 1000.0:
            seconds = window_ms / 1000.0
            return f"{seconds:.2f}s" if seconds < 2.0 else f"{seconds:.1f}s"
        if window_ms >= 100.0:
            return f"{window_ms:.1f}ms"
        return f"{window_ms:.2f}ms" if window_ms < 10.0 else f"{window_ms:.1f}ms"

    def rate_window_labels(self):
        return [
            f"{label} ({self.format_capture_window(rate)} window)"
            for rate, label in RATE_OPTIONS
        ]

    def update_rate_tooltip(self):
        self.rate_combo.setToolTip(
            f"Sample rate (time window for {self.capture_buffer_samples} samples)"
        )

    def refresh_rate_window_labels(self):
        current_rate = RATE_OPTIONS[self.rate_combo.currentIndex()][0]
        self.rate_combo.blockSignals(True)
        self.rate_combo.clear()
        self.rate_combo.addItems(self.rate_window_labels())
        for index, (rate, _label) in enumerate(RATE_OPTIONS):
            if rate == current_rate:
                self.rate_combo.setCurrentIndex(index)
                break
        self.rate_combo.blockSignals(False)
        self.update_rate_tooltip()

    def set_capture_mode(self, mode):
        """Chon Offline hoac Realtime tren UI."""
        if mode not in ("offline", "realtime"):
            return
        if self.live_mode and mode != self.capture_mode:
            self.live_btn.setChecked(False)
            self.toggle_live_mode()

        self.capture_mode = mode
        self.offline_mode_btn.blockSignals(True)
        self.realtime_mode_btn.blockSignals(True)
        self.offline_mode_btn.setChecked(mode == "offline")
        self.realtime_mode_btn.setChecked(mode == "realtime")
        self.offline_mode_btn.blockSignals(False)
        self.realtime_mode_btn.blockSignals(False)
        self.apply_mode_controls()

    def apply_mode_controls(self):
        connected = bool(self.device and self.device.serial)
        offline = self.capture_mode == "offline"
        self.capture_btn.setEnabled(connected and offline and not self.live_mode)
        self.live_btn.setEnabled(connected and not offline and not self.live_mode)
        self.trigger_checkbox.setEnabled(connected and offline and not self.live_mode)
        self.decode_btn.setEnabled(self.current_capture is not None)
        if not offline and self.device:
            self.trigger_checkbox.setChecked(False)
            self.device.set_trigger(False)
        if connected:
            text = "Offline mode" if offline else "Realtime mode"
            self.status_bar.showMessage(text)

    def on_decode_protocol_changed(self):
        protocol = self.protocol_combo.currentText()
        is_uart = protocol == "UART"
        is_i2c = protocol == "I2C"
        is_spi = protocol == "SPI"
        self.decode_ch_b_combo.setEnabled(not is_uart)
        self.decode_ch_c_combo.setEnabled(is_spi)
        self.decode_ch_d_combo.setEnabled(is_spi)
        self.baud_combo.setEnabled(is_uart)
        if is_uart:
            self.decode_ch_a_combo.setCurrentIndex(0)
            self.decode_ch_a_label.setText("RX:")
            self.decode_ch_a_combo.setToolTip("UART RX channel")
            self.decode_ch_b_label.setText("Unused:")
            self.decode_ch_b_combo.setToolTip("Unused for UART")
            self.decode_ch_c_label.setText("Unused:")
            self.decode_ch_c_combo.setToolTip("Unused for UART")
            self.decode_ch_d_label.setText("Unused:")
            self.decode_ch_d_combo.setToolTip("Unused for UART")
            self.decode_ch_c_combo.setEnabled(False)
            self.decode_ch_d_combo.setEnabled(False)
        else:
            self.decode_ch_b_combo.setEnabled(is_i2c or is_spi)
            if is_i2c:
                self.decode_ch_a_combo.setCurrentIndex(1)
                self.decode_ch_b_combo.setCurrentIndex(2)
                self.decode_ch_a_label.setText("SCL:")
                self.decode_ch_a_combo.setToolTip("I2C SCL channel")
                self.decode_ch_b_label.setText("SDA:")
                self.decode_ch_b_combo.setToolTip("I2C SDA channel")
                self.decode_ch_c_combo.setCurrentIndex(0)
                self.decode_ch_c_combo.setEnabled(False)
                self.decode_ch_c_label.setText("Unused:")
                self.decode_ch_c_combo.setToolTip("Unused for I2C")
                self.decode_ch_d_combo.setCurrentIndex(0)
                self.decode_ch_d_combo.setEnabled(False)
                self.decode_ch_d_label.setText("Unused:")
                self.decode_ch_d_combo.setToolTip("Unused for I2C")
            else:  # SPI
                self.decode_ch_a_combo.setCurrentIndex(3)
                self.decode_ch_b_combo.setCurrentIndex(4)
                self.decode_ch_c_combo.setCurrentIndex(5)
                self.decode_ch_d_combo.setCurrentIndex(6)
                self.decode_ch_a_label.setText("SCK:")
                self.decode_ch_a_combo.setToolTip("SPI SCK channel")
                self.decode_ch_b_label.setText("MOSI:")
                self.decode_ch_b_combo.setToolTip("SPI MOSI channel")
                self.decode_ch_c_label.setText("MISO:")
                self.decode_ch_c_combo.setToolTip("SPI MISO channel")
                self.decode_ch_d_label.setText("CS:")
                self.decode_ch_d_combo.setToolTip("SPI CS channel")

    def decode_current_capture(self):
        if not self.current_capture:
            self.status_bar.showMessage("No capture to decode")
            return

        samples = self.current_capture.samples
        sample_rate_hz = int(1_000_000_000 / self.current_capture.sample_period_ns)
        protocol = self.protocol_combo.currentText()
        ch_a = self.decode_ch_a_combo.currentIndex()
        ch_b = self.decode_ch_b_combo.currentIndex()

        if protocol == "UART":
            baudrate = int(self.baud_combo.currentText())
            events = decode_uart(samples, sample_rate_hz, ch_a, baudrate)
        elif protocol == "I2C":
            events = decode_i2c(samples, sample_rate_hz, ch_a, ch_b)
        else:
            events = decode_spi(
                samples,
                sample_rate_hz,
                sck_channel=ch_a,
                mosi_channel=ch_b,
                miso_channel=self.decode_ch_c_combo.currentIndex(),
                cs_channel=self.decode_ch_d_combo.currentIndex(),
            )

        self.decode_table.setRowCount(len(events))
        for row, event in enumerate(events):
            values = [
                f"{event.time_us:.2f}",
                event.protocol,
                event.event,
                event.value,
                event.note,
            ]
            for col, value in enumerate(values):
                self.decode_table.setItem(row, col, QTableWidgetItem(value))
        self.decode_table.resizeColumnsToContents()
        self.status_bar.showMessage(f"Decoded {len(events)} {protocol} events")

    def on_rate_changed(self, index):
        """Handle sample rate change"""
        if not self.device:
            return

        if 0 <= index < len(RATE_OPTIONS):
            sample_rate_hz, rate_name = RATE_OPTIONS[index]
            success = self.device.set_sample_rate(sample_rate_hz)
            if success:
                self.status_bar.showMessage(f"Sample rate set to {rate_name}")
            else:
                self.status_bar.showMessage(f"Failed to set sample rate to {rate_name}")

    def on_trigger_changed(self, enabled):
        """Configure capture to wait for the UART start edge on PA0."""
        if not self.device:
            return

        success = self.device.set_trigger(enabled)
        if success:
            state = "PA0 falling edge" if enabled else "off"
            self.status_bar.showMessage(f"Trigger set to {state}")
        else:
            self.status_bar.showMessage("Failed to configure trigger")
            self.trigger_checkbox.blockSignals(True)
            self.trigger_checkbox.setChecked(not enabled)
            self.trigger_checkbox.blockSignals(False)

    def closeEvent(self, event):
        """Stop acquisition before releasing the serial port."""
        self.live_timer.stop()
        if self.device:
            self.device.disconnect()
            self.device = None
        event.accept()
