"""
Bảng mã màu và mã CSS Stylesheet giao diện chuyên nghiệp cho Logic Analyzer GUI (PyQt).
Lấy cảm hứng từ giao diện tối màu (Dark Theme) của VS Code / JetBrains.
"""

# Bảng mã màu chủ đạo của hệ thống
COLORS = {
    # Nhóm màu nền (Backgrounds)
    'bg_primary': '#1e1e1e',                     # Nền chính tối màu
    'bg_secondary': '#252526',                   # Nền Toolbar và các panel phụ
    'bg_tertiary': '#2d2d2d',                    # Nền các khung chọn/nhập liệu
    'bg_header': '#333333',                      # Nền header bảng và nút bấm thường
    'bg_dark': '#181818',                        # Nền siêu tối cho đồ thị sóng

    # Nhóm màu nhấn mạnh (Accents)
    'accent_primary': '#007acc',                 # Màu xanh dương thương hiệu (VS Code)
    'accent_secondary': '#0098ff',               # Màu xanh dương sáng khi hover/active
    'accent_hover': '#005f9e',                   # Màu xanh dương đậm khi nhấn giữ

    # Nhóm màu trạng thái (Status)
    'success': '#4ec9b0',                        # Màu xanh ngọc (Đã kết nối / Thành công)
    'warning': '#cca700',                        # Màu vàng hổ phách (Cảnh báo / Đang chờ)
    'error': '#f14c4c',                          # Màu đỏ (Lỗi / Quá tải / Dừng)
    'info': '#9cdcfe',                           # Màu xanh lam nhạt (Thông tin)

    # Nhóm màu chữ (Text)
    'text_primary': '#d4d4d4',                   # Chữ chính màu xám nhạt dễ chịu cho mắt
    'text_secondary': '#858585',                 # Chữ phụ màu xám đậm hơn
    'text_disabled': '#585858',                  # Chữ bị vô hiệu hóa
    'text_bright': '#ffffff',                    # Chữ màu trắng sáng nổi bật

    # Nhóm đường viền (Borders)
    'border_light': '#3e3e42',
    'border_dark': '#1e1e1e',

    # Nhóm màu riêng biệt cho 8 kênh logic (phân biệt các đường sóng tín hiệu)
    'ch0': '#ff5252',                            # Kênh 0: Đỏ
    'ch1': '#ffb142',                            # Kênh 1: Cam
    'ch2': '#2ccce4',                            # Kênh 2: Xanh dương sáng
    'ch3': '#33d9b2',                            # Kênh 3: Xanh lá cây nhạt
    'ch4': '#706fd3',                            # Kênh 4: Tím
    'ch5': '#f78fb3',                            # Kênh 5: Hồng
    'ch6': '#82ccdd',                            # Kênh 6: Xanh băng giá
    'ch7': '#b33939',                            # Kênh 7: Đỏ sẫm
}

# Mảng lưu màu sắc của 8 kênh logic đo đạc
CHANNEL_COLORS = [COLORS[f'ch{i}'] for i in range(8)]


def get_main_stylesheet():
    """
    Trả về chuỗi định dạng CSS QSS (Qt Style Sheet) cho giao diện cửa sổ ứng dụng.
    """
    return f"""
    QMainWindow {{
        background-color: {COLORS['bg_primary']};
        color: {COLORS['text_primary']};
    }}

    QWidget {{
        background-color: {COLORS['bg_primary']};
        color: {COLORS['text_primary']};
        font-family: 'Segoe UI', 'Roboto', Arial, sans-serif;
        font-size: 10pt;
    }}

    QPushButton {{
        background-color: {COLORS['bg_header']};
        color: {COLORS['text_primary']};
        border: 1px solid {COLORS['border_light']};
        border-radius: 4px;
        padding: 6px 14px;
        font-weight: 500;
        min-width: 80px;
    }}

    QPushButton:hover {{
        background-color: {COLORS['border_light']};
        border: 1px solid {COLORS['text_secondary']};
    }}

    QPushButton:pressed {{
        background-color: {COLORS['bg_tertiary']};
        border: 1px solid {COLORS['accent_primary']};
    }}

    QPushButton:disabled {{
        background-color: {COLORS['bg_secondary']};
        color: {COLORS['text_disabled']};
        border: 1px solid {COLORS['bg_tertiary']};
    }}

    /* Phong cách nút bấm Capture (Nổi bật nhất) */
    QPushButton#captureBtn {{
        background-color: {COLORS['accent_primary']};
        border: 1px solid {COLORS['accent_primary']};
        color: white;
        font-weight: bold;
        padding: 8px 20px;
    }}

    QPushButton#captureBtn:hover {{
        background-color: {COLORS['accent_secondary']};
        border: 1px solid {COLORS['accent_secondary']};
    }}

    QPushButton#captureBtn:pressed {{
        background-color: {COLORS['accent_hover']};
        border: 1px solid {COLORS['accent_hover']};
    }}

    QPushButton#captureBtn:disabled {{
        background-color: {COLORS['bg_tertiary']};
        color: {COLORS['text_disabled']};
        border: 1px solid {COLORS['bg_tertiary']};
    }}

    /* Phong cách nút Connect khi đã kết nối */
    QPushButton#connectBtn[connected="true"] {{
        background-color: {COLORS['bg_tertiary']};
        border: 1px solid {COLORS['success']};
        color: {COLORS['success']};
    }}

    /* Phong cách các nút bấm khi được tích chọn (Checked) */
    QPushButton#followBtn:checked {{
        background-color: {COLORS['accent_primary']};
        border: 1px solid {COLORS['accent_secondary']};
        color: {COLORS['text_bright']};
    }}

    QPushButton#modeBtn:checked {{
        background-color: {COLORS['accent_primary']};
        border: 1px solid {COLORS['accent_secondary']};
        color: {COLORS['text_bright']};
        font-weight: bold;
    }}

    QPushButton#regionZoomBtn:checked {{
        background-color: {COLORS['accent_primary']};
        border: 1px solid {COLORS['accent_secondary']};
        color: {COLORS['text_bright']};
    }}

    /* Danh sách chọn (ComboBox) */
    QComboBox {{
        background-color: {COLORS['bg_header']};
        color: {COLORS['text_primary']};
        border: 1px solid {COLORS['border_light']};
        border-radius: 4px;
        padding: 5px 10px;
        min-width: 120px;
    }}

    QComboBox:hover {{
        border: 1px solid {COLORS['text_secondary']};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}

    QComboBox::down-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {COLORS['text_secondary']};
        margin-right: 8px;
    }}

    QComboBox QAbstractItemView {{
        background-color: {COLORS['bg_secondary']};
        color: {COLORS['text_primary']};
        selection-background-color: {COLORS['accent_primary']};
        selection-color: white;
        border: 1px solid {COLORS['border_light']};
        outline: 0px;
    }}

    QLabel {{
        color: {COLORS['text_primary']};
        background: transparent;
        border: none;
    }}

    /* Phong cách nhãn tiêu đề phân mục */
    QLabel#sectionLabel {{
        color: {COLORS['accent_secondary']};
        font-weight: 600;
        font-size: 9pt;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}

    /* Thanh trạng thái dưới cùng */
    QStatusBar {{
        background-color: {COLORS['accent_primary']};
        color: white;
        font-weight: bold;
    }}

    QStatusBar::item {{
        border: none;
    }}

    /* Panel Toolbar */
    QWidget#toolbar {{
        background-color: {COLORS['bg_secondary']};
        border-bottom: 1px solid {COLORS['border_light']};
    }}

    /* Đường chia kẻ khung */
    QFrame[frameShape="4"] {{
        background-color: {COLORS['border_light']};
        max-width: 1px;
        border: none;
    }}

    QFrame[frameShape="5"] {{
        background-color: {COLORS['border_light']};
        max-height: 1px;
        border: none;
    }}

    /* Thanh trượt (Slider) */
    QSlider::groove:horizontal {{
        border: 1px solid {COLORS['bg_tertiary']};
        height: 6px;
        background: {COLORS['bg_tertiary']};
        margin: 2px 0;
        border-radius: 3px;
    }}

    QSlider::handle:horizontal {{
        background: {COLORS['accent_primary']};
        border: 1px solid {COLORS['accent_primary']};
        width: 14px;
        height: 14px;
        margin: -5px 0;
        border-radius: 7px;
    }}

    QSlider::handle:horizontal:hover {{
        background: {COLORS['accent_secondary']};
    }}

    /* Thanh kéo giãn phân chia khung nhìn (Splitter Handle) */
    QSplitter::handle:vertical {{
        background-color: {COLORS['border_light']};
        height: 8px;
        margin: 2px 0;
    }}

    QSplitter::handle:vertical:hover {{
        background-color: {COLORS['accent_primary']};
    }}

    /* Thanh cuộn (ScrollBars) */
    QScrollBar:horizontal {{
        background: {COLORS['bg_primary']};
        height: 10px;
    }}

    QScrollBar::handle:horizontal {{
        background: {COLORS['border_light']};
        min-width: 20px;
        border-radius: 5px;
        margin: 2px;
    }}

    QScrollBar::handle:horizontal:hover {{
        background: {COLORS['text_secondary']};
    }}

    QScrollBar:vertical {{
        background: {COLORS['bg_primary']};
        width: 10px;
    }}

    QScrollBar::handle:vertical {{
        background: {COLORS['border_light']};
        min-height: 20px;
        border-radius: 5px;
        margin: 2px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {COLORS['text_secondary']};
    }}

    QScrollBar::add-line, QScrollBar::sub-line {{
        border: none;
        background: none;
    }}

    /* Khung chú giải khi di chuột qua (ToolTip) */
    QToolTip {{
        background-color: {COLORS['bg_secondary']};
        color: {COLORS['text_primary']};
        border: 1px solid {COLORS['border_light']};
        padding: 4px;
    }}
    """


def get_status_indicator_html(status, text):
    """
    Tạo chuỗi HTML đại diện cho nhãn trạng thái với chấm tròn có màu động.
    
    - status: Trạng thái ('connected', 'disconnected', 'capturing', 'warning', 'error').
    - text: Văn bản đi kèm.
    """
    color_map = {
        'connected': COLORS['success'],
        'disconnected': COLORS['text_disabled'],
        'capturing': COLORS['accent_secondary'],
        'warning': COLORS['warning'],
        'error': COLORS['error'],
    }

    color = color_map.get(status, COLORS['text_secondary'])

    return f"""
    <div style='font-family: Consolas, monospace; font-size: 9pt;'>
        <span style='color: {color};'>&#9679;</span>
        <span style='color: {COLORS["text_primary"]}; margin-left: 4px;'>{text}</span>
    </div>
    """
