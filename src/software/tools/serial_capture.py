from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Thêm thư mục phần mềm vào sys.path để import các module khác
SOFTWARE_DIR = Path(__file__).resolve().parents[1]
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from protocol_frame import (
    HEADER_LENGTH,
    FrameError,
    decode_frame,
    decode_frame_header,
)

# Giới hạn số mẫu an toàn tối đa để tránh lỗi cấp phát quá nhiều RAM trên PC
MAX_SAFE_FRAME_SAMPLES = 1_000_000


def _read_line(ser, timeout_s: float) -> str:
    """Đọc một dòng văn bản kết thúc bằng ký tự xuống dòng từ cổng Serial."""
    old_timeout = ser.timeout
    ser.timeout = timeout_s
    try:
        return ser.readline().decode("ascii", errors="ignore").strip()
    finally:
        ser.timeout = old_timeout


def _send_line(ser, text: str) -> None:
    """Gửi một dòng lệnh ASCII kết thúc bằng ký tự xuống dòng '\\n'."""
    ser.write(text.encode("ascii") + b"\n")
    ser.flush()


def _read_exact(ser, length: int, timeout_s: float) -> bytes:
    """Đọc chính xác 'length' byte nhị phân thô từ cổng Serial."""
    old_timeout = ser.timeout
    ser.timeout = timeout_s
    try:
        data = bytearray()
        while len(data) < length:
            chunk = ser.read(length - len(data))
            if not chunk:
                raise TimeoutError("serial read timeout")
            data.extend(chunk)
        return bytes(data)
    finally:
        ser.timeout = old_timeout


def capture_frame(
    port: str,
    output: str | Path,
    baud: int,
    rate: int,
    timeout_s: float,
    mode: str = "DMA",
) -> None:
    """
    Kết nối tới cổng Serial, cấu hình và thu thập đúng một Frame dạng sóng rồi lưu vào file.
    
    - port: Cổng kết nối (ví dụ "COM12").
    - output: Đường dẫn tệp tin lưu kết quả (ví dụ "capture.sla8").
    - baud: Tốc độ Baud Rate truyền thông.
    - rate: Tần số lấy mẫu mong muốn (Hz).
    - timeout_s: Thời gian chờ capture tối đa (giây).
    - mode: Chế độ đo ("DMA", "ISR", hoặc "AUTO").
    """
    try:
        import serial
    except ImportError as exc:
        raise SystemExit("pyserial is required for hardware serial capture") from exc

    with serial.Serial(port, baud, timeout=1) as ser:
        ser.reset_input_buffer()
        # 1. Bắt tay PING-PONG kiểm tra kết nối với MCU
        _send_line(ser, "PING")
        if _read_line(ser, 2.0) != "PONG SLA8":
            raise SystemExit("device did not answer PING")

        # 2. Cấu hình chế độ lấy mẫu (nếu không chọn AUTO)
        if mode != "AUTO":
            _send_line(ser, f"CFG MODE {mode}")
            if not _read_line(ser, 2.0).startswith("OK"):
                raise SystemExit("capture mode config failed")

        # 3. Cấu hình tần số lấy mẫu (Hz)
        _send_line(ser, f"CFG RATE {rate}")
        if not _read_line(ser, 2.0).startswith("OK"):
            raise SystemExit("rate config failed")

        # 4. Thiết lập trigger tức thời (Immediate) để đo ngay khi Arm
        _send_line(ser, "TRIG IMM")
        if not _read_line(ser, 2.0).startswith("OK"):
            raise SystemExit("trigger config failed")

        # 5. Phát lệnh ARM để bắt đầu quá trình capture trên MCU
        _send_line(ser, "ARM")
        if not _read_line(ser, 2.0).startswith("OK"):
            raise SystemExit("arm failed")

        # 6. Đợi MCU hoàn thành lấy mẫu và phát ra sự kiện "EVENT ..."
        deadline_line = ""
        for _ in range(max(1, int(timeout_s * 10))):
            deadline_line = _read_line(ser, 0.1)
            if deadline_line.startswith("EVENT "):
                break
        if not deadline_line.startswith("EVENT "):
            raise SystemExit("capture event timeout")
            
        terminal_state = deadline_line.removeprefix("EVENT ")
        if terminal_state == "NO_TRIGGER":
            raise SystemExit("capture ended without a trigger")
        if terminal_state not in {"COMPLETE", "OVERFLOW"}:
            raise SystemExit(f"firmware capture ended in {terminal_state}")

        # 7. Phát lệnh DUMP để lấy dữ liệu gói tin nhị phân
        _send_line(ser, "DUMP")
        
        # Đọc 48 byte Header trước
        header = _read_exact(ser, HEADER_LENGTH, 2.0)
        try:
            # Giải mã Header để lấy thông tin chiều dài Payload
            frame_header = decode_frame_header(
                header,
                max_samples=MAX_SAFE_FRAME_SAMPLES,
            )
        except FrameError as exc:
            raise SystemExit(f"invalid SLA8 header: {exc}") from exc
            
        total_samples = frame_header.total_samples
        # Đọc chính xác phần còn lại (Payload) của gói tin
        payload = _read_exact(ser, total_samples, timeout_s)
        
        frame_bytes = header + payload
        try:
            # Giải mã xác thực tính toàn vẹn (Checksum) của toàn bộ gói tin
            decode_frame(frame_bytes)
        except FrameError as exc:
            raise SystemExit(f"invalid SLA8 frame: {exc}") from exc
            
        # Ghi toàn bộ chuỗi byte thô của gói tin ra file đầu ra
        Path(output).write_bytes(frame_bytes)


def main(argv: list[str] | None = None) -> int:
    """
    Hàm khởi động chính xử lý các đối số dòng lệnh đầu vào.
    """
    parser = argparse.ArgumentParser(description="Capture one SLA8 frame over firmware serial protocol")
    parser.add_argument("port", help="Cổng COM kết nối thiết bị")
    parser.add_argument("output", help="Đường dẫn file lưu gói tin kết quả")
    parser.add_argument("--baud", type=int, default=1_000_000, help="Tốc độ Baud Rate truyền nối tiếp")
    parser.add_argument("--rate", type=int, default=100_000, help="Tần số lấy mẫu (Hz)")
    parser.add_argument("--timeout", type=float, default=10.0, help="Thời gian chờ tối đa (giây)")
    parser.add_argument("--mode", choices=("DMA", "ISR", "AUTO"), default="DMA", help="Chế độ lấy mẫu phần cứng")
    args = parser.parse_args(argv)
    
    capture_frame(
        args.port,
        args.output,
        args.baud,
        args.rate,
        args.timeout,
        args.mode,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
