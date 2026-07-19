import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont
from gui.main_window import MainWindow

def main():
    # Khởi tạo đối tượng ứng dụng QApplication quản lý luồng điều khiển và thiết lập giao diện người dùng
    app = QApplication(sys.argv)
    
    # Thiết lập phông chữ (Font) mặc định cho toàn bộ ứng dụng là Segoe UI cỡ 10
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    # Tạo và hiển thị cửa sổ giao diện chính MainWindow
    window = MainWindow()
    window.show()
    
    # Bắt đầu vòng lặp sự kiện của ứng dụng (Event Loop) và thoát chương trình khi đóng cửa sổ
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
