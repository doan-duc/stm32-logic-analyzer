from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QComboBox, 
                             QLabel, QStatusBar, QFrame, QSplitter, QSlider,
                             QCheckBox)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QFont
from .waveform_view import WaveformView
from .styles import get_main_stylesheet, get_status_indicator_html, COLORS
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from device import LogicAnalyzerDevice
from capture import Capture

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.device = None
        self.current_capture = None
        self.full_capture = None
        self.live_mode = False
        self.capture_count = 0
        self.live_buffer_max_samples = 204800
        self.live_render_samples = 8192
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
        self.rate_combo.addItems([
            "100 Hz (20s window)",
            "1 kHz (2s window)",
            "10 kHz (200ms window)",
            "50 kHz (40ms window)",
            "100 kHz (20ms window)",
            "1 MHz (2ms window)",
            "2 MHz (1ms window)",
            "5 MHz (0.4ms window)",
            "6 MHz (0.3ms window)",
        ])
        self.rate_combo.setCurrentIndex(4)
        self.rate_combo.setToolTip("Sample rate (time window for 2048 samples)")
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
        
        # ROW 2: Live Capture Controls
        row2 = QHBoxLayout()
        row2.setSpacing(16)
        
        # Live mode section
        live_label = QLabel("LIVE MODE")
        live_label.setObjectName("sectionLabel")
        row2.addWidget(live_label)
        
        self.live_btn = QPushButton("Start Live")
        self.live_btn.setCheckable(True)
        self.live_btn.setToolTip("Toggle live capture mode")
        self.live_btn.setMinimumWidth(100)
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
        
        layout.addWidget(toolbar_container)
        
        # Status Indicator below toolbar
        self.status_indicator = QLabel()
        self.status_indicator.setTextFormat(Qt.RichText)
        self.status_indicator.setContentsMargins(16, 8, 16, 8)
        self.update_status_indicator("disconnected", "Disconnected")
        layout.addWidget(self.status_indicator)
        
        # Main content area - Waveform View only
        # No splitter needed anymore as we removed the protocol panel
        self.waveform_view = WaveformView()
        self.waveform_view.auto_scroll_changed.connect(self.on_auto_scroll_changed)
        self.waveform_view.set_region_zoom_available(True)
        layout.addWidget(self.waveform_view, 1) # 1 stretch factor to take remaining space
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def update_status_indicator(self, status, text):
        """Update the status indicator with colored dot"""
        html = get_status_indicator_html(status, text)
        self.status_indicator.setText(html)
    
    def refresh_ports(self, preferred_port=None):
        selected_port = preferred_port or self.port_combo.currentText()
        self.port_combo.clear()
        ports = LogicAnalyzerDevice.list_ports()
        if ports:
            self.port_combo.addItems(ports)
            if selected_port in ports:
                self.port_combo.setCurrentText(selected_port)
        else:
            self.port_combo.addItem("No ports found")

    def refresh_workspace(self):
        """Return the capture workspace to a clean initial state."""
        selected_port = (
            self.device.port
            if self.device and self.device.serial
            else self.port_combo.currentText()
        )

        if self.live_mode:
            self.live_btn.setChecked(False)
            self.toggle_live_mode()

        self.current_capture = None
        self.full_capture = None
        self.capture_count = 0
        self.stream_dropped_frames = 0
        self.stream_corrupt_frames = 0

        self.pause_btn.setChecked(False)
        self.pause_btn.setText("Pause")
        self.follow_btn.setChecked(True)
        self.waveform_view.reset_view()
        self.refresh_ports(selected_port)

        if self.device and self.device.serial:
            self.update_status_indicator("connected", "Connected")
            self.status_bar.showMessage("Workspace refreshed")
        else:
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
            self.update_status_indicator("disconnected", "Disconnected")
            self.status_bar.showMessage("Disconnected from device")
            self.sample_rate_label.setText("Rate: --")
            self.live_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)
            self.follow_btn.setEnabled(False)
            self.trigger_checkbox.setEnabled(False)
        else:
            # Connect
            port = self.port_combo.currentText()
            if port == "No ports found":
                self.status_bar.showMessage("No serial ports available")
                return
            
            try:
                self.device = LogicAnalyzerDevice(port)
                if self.device.connect():
                    self.connect_btn.setText("Disconnect")
                    self.connect_btn.setProperty("connected", True)
                    self.connect_btn.setStyle(self.connect_btn.style())  # Refresh style
                    self.capture_btn.setEnabled(True)
                    self.live_btn.setEnabled(True)
                    self.on_rate_changed(self.rate_combo.currentIndex())
                    self.trigger_checkbox.setEnabled(True)
                    self.on_trigger_changed(self.trigger_checkbox.isChecked())
                    info = self.device.device_info
                    self.update_status_indicator("connected", "Connected")
                    self.status_bar.showMessage(
                        f"Connected to {info['device_name']} v{info['version']} on {port}"
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
                self.waveform_view.display_capture(self.current_capture, is_rolling_update=True)
                
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

    def read_live_stream(self):
        """Drain continuous stream frames without stopping acquisition."""
        if not self.device or not self.live_mode:
            return

        frames = self.device.read_stream_frames()
        if not frames:
            return

        self.append_stream_frames(frames, update_display=True)

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
            f"Live continuous: {self.current_capture.sample_count} samples"
            f"{dropped_text}{corrupt_text}"
        )
        self.update_status_indicator("capturing", "Live Streaming")
    
    def toggle_live_mode(self):
        """Toggle live capture mode"""
        self.live_mode = self.live_btn.isChecked()
        
        if self.live_mode:
            # Start live capture
            self.capture_count = 0
            self.current_capture = None  # Reset buffer
            self.full_capture = None     # Reset full capture buffer
            self.stream_dropped_frames = 0
            self.stream_corrupt_frames = 0

            if not self.device.start_stream():
                self.live_mode = False
                self.live_btn.setChecked(False)
                self.update_status_indicator("error", "Stream Start Failed")
                self.status_bar.showMessage(
                    f"Stream start failed: {self.device.last_error}"
                )
                return

            self.live_btn.setText("Stop Live")
            # Style update for active state
            self.live_btn.setStyleSheet(f"background-color: {COLORS['error']}; border: 1px solid {COLORS['error']}; color: white;")
            self.capture_btn.setEnabled(False)
            self.pause_btn.setEnabled(True)
            self.pause_btn.setChecked(False)
            self.pause_btn.setText("Pause")
            self.follow_btn.setEnabled(True)
            self.follow_btn.setChecked(True)
            self.trigger_checkbox.setEnabled(False)
            self.rate_combo.setEnabled(False)
            self.waveform_view.set_region_zoom_available(False)
            self.waveform_view.set_history_navigation_enabled(False)
            self.waveform_view.begin_live_capture()
            
            self.update_status_indicator("capturing", "Live Streaming")
            self.status_bar.showMessage(
                f"Continuous live started (refresh: {self.live_interval_ms}ms)"
            )
            
            # Start timer
            self.live_timer.start(self.live_interval_ms)
        else:
            # Stop live capture
            self.live_timer.stop()
            if self.device:
                pending_frames = self.device.stop_stream(drain=True)
                self.append_stream_frames(pending_frames, update_display=False)
            self.live_btn.setText("Start Live")
            self.live_btn.setStyleSheet("")
            self.capture_btn.setEnabled(True)
            self.pause_btn.setEnabled(False)
            self.pause_btn.setChecked(False)
            self.follow_btn.setEnabled(False)
            self.trigger_checkbox.setEnabled(True)
            self.rate_combo.setEnabled(True)
            self.waveform_view.set_region_zoom_available(True)
            self.waveform_view.set_history_navigation_enabled(True)

            if self.current_capture:
                self.waveform_view.display_capture(self.current_capture)
            
            self.update_status_indicator("connected", "Connected")
            self.status_bar.showMessage(f"Live capture stopped")

    def toggle_pause(self):
        """Pause/Resume live capture"""
        is_paused = self.pause_btn.isChecked()
        
        if is_paused:
            self.live_timer.stop()
            pending_frames = self.device.stop_stream(drain=True)
            self.append_stream_frames(pending_frames, update_display=False)
            self.pause_btn.setText("Resume")
            self.update_status_indicator("warning", "Paused")
            self.waveform_view.set_region_zoom_available(True)
            self.waveform_view.set_history_navigation_enabled(True)
            if self.current_capture:
                self.waveform_view.display_capture(self.current_capture)
        else:
            if not self.device.start_stream():
                self.pause_btn.setChecked(True)
                self.status_bar.showMessage("Failed to resume continuous stream")
                return
            self.live_timer.start(self.live_interval_ms)
            self.pause_btn.setText("Pause")
            self.update_status_indicator("capturing", "Live Capture")
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
        """Update live capture interval"""
        self.live_interval_ms = value
        self.interval_label.setText(f"{value}ms")
        
        # Update timer if running
        if self.live_mode:
            self.live_timer.setInterval(value)
            self.status_bar.showMessage(f"Live interval: {value}ms")

    def on_rate_changed(self, index):
        """Handle sample rate change"""
        if not self.device:
            return
        
        # Map index to firmware command (slowest to fastest)
        rate_commands = {
            0: ('E', "100 Hz"),
            1: ('D', "1 kHz"),
            2: ('B', "10 kHz"),
            3: ('F', "50 kHz"),
            4: ('A', "100 kHz"),
            5: ('1', "1 MHz"),
            6: ('2', "2 MHz"),
            7: ('5', "5 MHz"),
            8: ('6', "6 MHz"),
        }
        
        if index in rate_commands:
            cmd, rate_name = rate_commands[index]
            success = self.device.set_sample_rate(cmd)
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

    def closeEvent(self, event):
        """Stop acquisition before releasing the serial port."""
        self.live_timer.stop()
        if self.device:
            self.device.disconnect()
            self.device = None
        event.accept()
