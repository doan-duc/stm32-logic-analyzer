import pyqtgraph as pg
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QScrollBar
from PyQt5.QtCore import Qt, pyqtSignal
import numpy as np
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import màu sắc từ tệp styles
try:
    from .styles import CHANNEL_COLORS, COLORS
except ImportError:
    # Màu mặc định dự phòng nếu styles không khả dụng
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

# Kích hoạt OpenGL tăng tốc phần cứng, các tính năng thử nghiệm và làm mịn gai sóng (antialias)
pg.setConfigOptions(useOpenGL=True, enableExperimental=True, antialias=True)

class TimeZoomViewBox(pg.ViewBox):
    """
    Hộp nhìn đồ thị (ViewBox) tùy chỉnh cho phép zoom hình chữ nhật (Region Zoom)
    chỉ thay đổi tỷ lệ trên trục thời gian (trục X) và giữ nguyên trục kênh đo (trục Y).
    """

    def showAxRect(self, rect, **kwargs):
        normalized = rect.normalized()
        if normalized.width() <= 0:
            return

        self.setXRange(normalized.left(), normalized.right(), padding=0)
        # Phát tín hiệu báo đã thay đổi khoảng trục thủ công
        self.sigRangeChangedManually.emit(self.state['mouseEnabled'])


class WaveformView(QWidget):
    """
    Widget hiển thị đồ thị dạng sóng logic 8 kênh.
    Hỗ trợ kéo, zoom, đo đạc sườn xung bằng cách di chuột qua, tự động cuộn (auto-scroll) và thanh cuộn lịch sử.
    """
    auto_scroll_changed = pyqtSignal(bool)           # Tín hiệu phát đi khi chế độ tự động cuộn thay đổi
    EDGE_HOVER_RADIUS_PX = 8                         # Bán kính vùng nhạy cảm di chuột phát hiện sườn xung (pixel)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.num_channels = 8
        self.channel_colors = CHANNEL_COLORS
        
        # Bảng ánh xạ kênh đo logic sang tên chân GPIO tương ứng trên chip STM32F103
        self.pin_mapping = {
            0: 'PA0', 1: 'PA1', 2: 'PA2', 3: 'PA3',
            4: 'PA4', 5: 'PA5', 6: 'PA6', 7: 'PA7'
        }
        self.zoom_level = 1.0
        self.updating_scrollbar = False                  # Cờ chống khóa lặp khi đồng bộ đồ thị và thanh cuộn
        self.live_view_width = None                      # Độ rộng cửa sổ thời gian quan sát được ở chế độ live
        self.auto_scroll = True                          # Tự động cuộn sang phải theo mẫu mới nhất
        self.history_navigation_enabled = True           # Cho phép kéo thanh cuộn duyệt lịch sử sóng
        
        self.setup_ui()
    
    def setup_ui(self):
        """
        Khởi tạo và cấu hình giao diện vẽ đồ thị.
        """
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Thanh điều khiển đồ thị (Zoom, Fit, Region Zoom)
        controls = QHBoxLayout()
        controls.setContentsMargins(8, 8, 8, 8)
        controls.setSpacing(8)
        
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
        
        # Tạo widget vẽ đồ thị sử dụng ViewBox tùy chỉnh
        self.view_box = TimeZoomViewBox()
        self.plot_widget = pg.PlotWidget(viewBox=self.view_box)
        
        # Cấu hình màu nền đồ thị tối (Dark Theme)
        self.plot_widget.setBackground(COLORS['bg_dark'])
        
        # Cấu hình nhãn trục thời gian (Bottom) và trục kênh đo (Left)
        self.plot_widget.setLabel('bottom', 'Time', units='s', 
                                  color=COLORS['text_primary'])
        self.plot_widget.setLabel('left', 'Channel', 
                                  color=COLORS['text_primary'])
        
        # Thiết lập màu viền và màu chữ cho các trục
        axis_pen = pg.mkPen(color=COLORS.get('text_disabled', '#585858'), width=1)
        self.plot_widget.getAxis('bottom').setPen(axis_pen)
        self.plot_widget.getAxis('left').setPen(axis_pen)
        self.plot_widget.getAxis('bottom').setTextPen(COLORS.get('text_secondary', '#858585'))
        self.plot_widget.getAxis('left').setTextPen(COLORS.get('text_secondary', '#858585'))
        
        # Hiển thị đường lưới (Grid) mờ dọc theo trục X
        self.plot_widget.showGrid(x=True, y=False, alpha=0.1)
        
        # Chỉ cho phép kéo chuột (pan/zoom) theo chiều ngang (trục X), khóa chiều dọc (trục Y)
        self.plot_widget.setMouseEnabled(x=True, y=False)
        self.set_region_zoom_enabled(True)
        self.plot_widget.plotItem.setMenuEnabled(False)  # Tắt menu chuột phải mặc định của pyqtgraph
        
        # --- Khởi tạo các phần tử đo đạc nhanh khi di chuột ---
        # measure_line1: Đường thẳng nét đứt đứng màu xanh chỉ điểm sườn đang chọn
        self.measure_line1 = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(color=COLORS.get('accent_secondary', '#0098ff'), width=1.5, style=Qt.DashLine))
        # measure_line2: Đường đứng nét đứt chỉ điểm sườn trước đó (để đo khoảng cách delta)
        self.measure_line2 = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(color=COLORS.get('accent_secondary', '#0098ff'), width=1.5, style=Qt.DashLine))
        # measure_text: Khung hiển thị thông tin đo đạc dạng HTML
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
        
        # Mảng cache lưu các sườn xung của từng kênh để tìm kiếm nhanh
        self.edge_cache = [[] for _ in range(self.num_channels)]
        
        # Kết nối các tín hiệu chuột và tầm nhìn
        self.plot_widget.scene().sigMouseClicked.connect(self.on_mouse_clicked)
        self.plot_widget.scene().sigMouseMoved.connect(self.on_mouse_moved)
        self.plot_widget.sigXRangeChanged.connect(self.update_scrollbar_from_plot)
        
        layout.addWidget(self.plot_widget)
        
        # Thanh cuộn ngang duyệt dữ liệu lịch sử
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
        
        self.channel_plots = []                          # Danh sách đối tượng PlotItem vẽ sóng của mỗi kênh
        self.channel_labels = []                         # Danh sách đối tượng TextItem ghi tên kênh (CH0...)
        self.current_capture = None
    
    def on_mouse_clicked(self, event):
        """Khi người dùng click chuột vào đồ thị, tự động tắt chế độ tự động cuộn (Auto-scroll)."""
        if not self.auto_scroll:
             return
        self.set_auto_scroll(False)

    def on_mouse_moved(self, pos):
        """Xử lý bắt dính (snap) con trỏ chuột vào sườn tín hiệu gần nhất trên kênh đo đang di qua."""
        if not self.current_capture:
            self.hide_measurement()
            return

        view_box = self.plot_widget.getViewBox()
        scene_bounds = view_box.sceneBoundingRect()
        # Chỉ xử lý nếu chuột di chuyển bên trong khu vực vẽ đồ thị
        if not scene_bounds.contains(pos) or scene_bounds.width() <= 0:
            self.hide_measurement()
            return

        # Quy đổi vị trí chuột trong khung vẽ sang tọa độ giá trị thật (Thời gian - Biên độ)
        mouse_point = view_box.mapSceneToView(pos)
        y = mouse_point.y()

        # Xác định kênh đo logic hiện tại đang di chuột qua dựa trên tọa độ Y
        channel = int(self.num_channels - 1 - np.floor(y))
        
        # Tính toán dung sai bắt điểm sườn xung (pixel sang nano giây) dựa trên mức zoom X hiện thời
        view_start, view_end = view_box.viewRange()[0]
        tolerance_ns = (
            max(view_end - view_start, 0)
            * 1_000_000_000
            * self.EDGE_HOVER_RADIUS_PX
            / scene_bounds.width()
        )
        # Tiến hành cập nhật vị trí đường đo và hiển thị thông tin đo đạc sườn xung
        self._update_edge_hover(
            channel=channel,
            time_ns=mouse_point.x() * 1_000_000_000,
            tolerance_ns=tolerance_ns,
        )

    def _update_edge_hover(self, *, channel, time_ns, tolerance_ns):
        """Tìm kiếm sườn xung gần nhất và cập nhật hiển thị dòng/tooltip đo đạc."""
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
            # Gọi hàm tìm kiếm nhị phân sườn xung gần nhất
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

        # Quy đổi thời gian nano giây sang giây phục vụ vẽ
        edge_time = edge.timestamp_ns / 1_000_000_000
        self.measure_line1.setPos(edge_time)
        
        # Nếu sườn xung này có sườn liền trước, vẽ đường đứng thứ hai để hiển thị khoảng đo
        if edge.delta_ns is not None:
            previous_time = (
                edge.timestamp_ns - edge.delta_ns
            ) / 1_000_000_000
            self.measure_line2.setPos(previous_time)
            self.measure_line2.show()
        else:
            self.measure_line2.hide()

        # Cập nhật tooltip đo đạc
        self.measure_text.setHtml(
            format_edge_tooltip(
                edge,
                pin_name=self.pin_mapping.get(channel, "?"),
            )
        )
        # Đặt vị trí tooltip hiển thị phía trên kênh đo
        y_base = self.num_channels - 1 - channel
        self.measure_text.setPos(edge_time, y_base + 0.8)
        self.measure_line1.show()
        self.measure_text.show()
        return edge

    def hide_measurement(self):
        """Ẩn các đường thẳng nét đứt và nhãn thông tin đo đạc."""
        self.measure_line1.hide()
        self.measure_line2.hide()
        self.measure_text.hide()

    def set_auto_scroll(self, enabled):
        """Bật/tắt tự động cuộn đồ thị theo dữ liệu mới nhất."""
        if self.auto_scroll == enabled:
            return
        self.auto_scroll = enabled
        self.auto_scroll_changed.emit(enabled)

    def set_region_zoom_available(self, available):
        """Cho phép/Không cho phép nút chọn Region Zoom hoạt động."""
        self.region_zoom_btn.setEnabled(available)
        self.region_zoom_btn.setChecked(available)
        self.set_region_zoom_enabled(available)

    def set_history_navigation_enabled(self, enabled):
        """Bật/tắt khả năng tương tác với thanh cuộn lịch sử."""
        self.history_navigation_enabled = enabled
        self.scrollbar.setToolTip(
            "Drag to browse captured history"
            if enabled
            else "Pause Live to browse captured history"
        )
        self.update_scrollbar_from_plot()

    def set_region_zoom_enabled(self, enabled):
        """Chuyển đổi thao tác kéo thả chuột trái giữa kéo màn hình (Pan) và khoanh vùng zoom (Region Zoom)."""
        self.region_zoom_btn.blockSignals(True)
        self.region_zoom_btn.setChecked(enabled)
        self.region_zoom_btn.blockSignals(False)

        mode = pg.ViewBox.RectMode if enabled else pg.ViewBox.PanMode
        self.plot_widget.getViewBox().setMouseMode(mode)

    def begin_live_capture(self):
        """Khởi động chuẩn bị cửa sổ vẽ cho phiên đo liên tục mới."""
        self.live_view_width = None
        self.set_auto_scroll(True)

    def reset_view(self):
        """Xóa toàn bộ đồ thị sóng, nhãn, dữ liệu đo đạc và đưa tầm nhìn về mặc định."""
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
        """Cuộn đồ thị trục X về các mẫu dữ liệu mới thu thập được ở cuối hàng."""
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
        """Đồng bộ vị trí và tỷ lệ chiều dài con chạy của thanh cuộn dựa trên tầm nhìn trục X hiện thời của đồ thị."""
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

        # Tính tỷ lệ phần trăm vùng nhìn thấy trên tổng thể để đặt kích thước (PageStep) của con chạy
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
        """Tắt tự động cuộn ngay khi người dùng nhấn/giữ vào thanh cuộn."""
        self.set_auto_scroll(False)
        
    def on_scrollbar_scroll(self, value):
        """Cập nhật lại tầm nhìn trục X của đồ thị khi người dùng kéo thanh cuộn."""
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
        """Phóng to trục X dạng sóng."""
        self.set_auto_scroll(False)
        view_box = self.plot_widget.getViewBox()
        view_box.scaleBy((0.5, 1))
    
    def zoom_out(self):
        """Thu nhỏ trục X dạng sóng."""
        self.set_auto_scroll(False)
        view_box = self.plot_widget.getViewBox()
        view_box.scaleBy((2, 1))
    
    def zoom_fit(self):
        """Tự động điều chỉnh tỷ lệ hiển thị vừa vặn toàn bộ dữ liệu mẫu."""
        self.set_auto_scroll(False)
        self.plot_widget.autoRange()
    
    def display_capture(
        self,
        capture,
        is_rolling_update=False,
        visible_sample_limit=None,
    ):
        """
        Vẽ đồ thị dạng sóng của đối tượng Capture lên màn hình với hiệu năng tối ưu.
        
        - capture: Đối tượng Capture chứa dữ liệu.
        - is_rolling_update: True nếu là cập nhật cuộn realtime (để tái sử dụng nét vẽ cũ, tránh giật lag).
        - visible_sample_limit: Giới hạn số lượng mẫu hiển thị trên màn hình để tối ưu tài nguyên CPU/RAM.
        """
        if not capture or len(capture.time) == 0:
            return
        
        self.current_capture = capture

        # Giới hạn chỉ hiển thị một số lượng mẫu gần nhất nếu chạy chế độ realtime cuộn
        render_start = 0
        if visible_sample_limit and capture.sample_count > visible_sample_limit:
            render_start = capture.sample_count - visible_sample_limit

        render_time = capture.time[render_start:]
        
        # Tính toán và lưu cache sườn xung phục vụ đo đạc nhanh
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

        # Nếu không phải là cập nhật cuộn hoặc vẽ lần đầu tiên, xóa sạch đồ thị cũ để vẽ lại
        if not is_rolling_update or first_display:
             self.plot_widget.clear()
             
             # Nạp lại các đường đo đạc
             self.plot_widget.addItem(self.measure_line1)
             self.plot_widget.addItem(self.measure_line2)
             self.plot_widget.addItem(self.measure_text)
             
             self.channel_plots = []
             self.channel_labels = []
             self.plot_widget.plotItem.enableAutoRange(pg.ViewBox.XYAxes)
        
        channel_height = 0.8
        channel_spacing = 1.0
        
        should_scroll = self.auto_scroll and is_rolling_update

        # Tính toán lại độ rộng cửa sổ nhìn thời gian cho phiên realtime
        if should_scroll and self.live_view_width is None:
            sample_period = capture.sample_period_ns / 1e9
            live_samples = visible_sample_limit or len(render_time)
            self.live_view_width = max(live_samples * sample_period, sample_period)

        if should_scroll:
            self.plot_widget.plotItem.disableAutoRange(pg.ViewBox.XAxis)

        for ch in range(self.num_channels):
            channel_data = capture.get_channel(ch)[render_start:]

            # Rút gọn dữ liệu số: Chỉ giữ lại các điểm chuyển đổi sườn mức logic 0-1,
            # loại bỏ tất cả các điểm giữ nguyên mức ở giữa để vẽ nhanh gấp hàng ngàn lần.
            time_ds, data_ds = self._digital_edge_points(
                render_time,
                channel_data,
            )
            
            # Nhân đôi các tọa độ điểm để biến các sườn xiên chéo thành sườn vuông góc dạng số bậc thang
            time_expanded, data_expanded = self._expand_digital(time_ds, data_ds)
            y_base = (self.num_channels - 1 - ch) * channel_spacing
            data_plot = (data_expanded * channel_height) + y_base
            
            # Nếu là cập nhật cuộn, gọi setData ghi đè dữ liệu vẽ cũ để cải thiện tốc độ vẽ
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
                
                # Tạo và gán chữ nhãn ghi tên kênh đo (ví dụ: CH0 (PA0)) ở vị trí bắt đầu
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

        # Cấu hình nhãn trục Y
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
        """
        Hàm tối ưu hóa: Chỉ giữ lại các mốc thời gian và điểm dữ liệu nơi xảy ra sườn chuyển trạng thái logic.
        Loại bỏ hoàn toàn các mẫu trùng lặp nằm ngang ở giữa giúp đồ thị vẽ cực nhanh và mượt mà.
        """
        if len(data) <= 2:
            return time, data

        # Tìm các chỉ số nơi mẫu hiện tại khác mẫu trước đó
        transition_idx = np.flatnonzero(data[1:] != data[:-1]) + 1
        # Luôn giữ lại điểm đầu tiên và điểm cuối cùng để mảng dữ liệu có điểm biên
        indices = np.concatenate((
            np.array([0], dtype=np.int64),
            transition_idx,
            np.array([len(data) - 1], dtype=np.int64),
        ))
        indices = np.unique(indices)
        return time[indices], data[indices]

    def _position_channel_labels(self, start_time, end_time):
        """Giữ cho các nhãn ghi tên kênh đo (CH0...) luôn bám dọc theo lề trái của màn hình khi người dùng cuộn đồ thị."""
        if not self.channel_labels:
            return

        label_x = start_time + max(end_time - start_time, 0) * 0.005
        channel_height = 0.8
        for ch, label in enumerate(self.channel_labels):
            y_base = self.num_channels - 1 - ch
            label.setPos(label_x, y_base + channel_height / 2)

    def _expand_digital(self, time, data):
        """
        Nhân bản các tọa độ điểm thời gian và dữ liệu bằng numpy 
        để tạo hình bậc thang vuông góc góc cạnh cho xung logic (Step Waveform).
        """
        if len(time) < 2:
            return time, data
        
        time_expanded = np.repeat(time, 2)[1:]
        data_expanded = np.repeat(data, 2)[:-1]
        
        return time_expanded, data_expanded
