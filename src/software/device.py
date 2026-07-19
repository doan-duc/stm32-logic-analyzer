from __future__ import annotations

import time

import serial
import serial.tools.list_ports

from protocol_frame import (
    HEADER_LENGTH,
    FrameError,
    decode_frame,
    decode_frame_header,
)

# Số lượng mẫu tối đa an toàn trong một gói tin để tránh tràn RAM máy tính (PC)
MAX_SAFE_FRAME_SAMPLES = 1_000_000


class LogicAnalyzerDevice:
    """
    Trình điều khiển (Driver) trên PC phục vụ giao tiếp với thiết bị Logic Analyzer chạy firmware SLA8.
    Hỗ trợ chế độ offline-capture (thu thập dữ liệu vào RAM của MCU rồi truyền hàng loạt về PC).
    """

    def __init__(self, port=None, baudrate=1_000_000):
        self.port = port                                # Cổng COM nối với thiết bị (ví dụ "COM3" trên Windows hoặc "/dev/ttyUSB0")
        self.baudrate = baudrate                        # Tốc độ truyền nhận cổng nối tiếp (Mặc định 1,000,000 bps)
        self.serial = None                              # Đối tượng kết nối Serial (PySerial)
        self.device_info = None                         # Lưu thông tin cấu hình đọc được từ thiết bị
        self.last_error = None                          # Lưu thông báo lỗi gần nhất
        self.current_sample_rate_hz = 100_000           # Tần số lấy mẫu hiện tại của thiết bị (Hz)
        self.trigger_enabled = False                    # Trạng thái bật/tắt trigger
        self.current_capture_mode = None                # Chế độ lấy mẫu hiện thời (ISR hoặc DMA)

    @staticmethod
    def list_ports():
        """
        Trả về danh sách tên các cổng COM/Serial đang khả dụng trên máy tính.
        """
        return [detail["device"] for detail in LogicAnalyzerDevice.list_port_details()]

    @staticmethod
    def list_port_details():
        """
        Trả về thông tin chi tiết của tất cả các cổng Serial đang kết nối trên PC
        (gồm: tên cổng, mô tả thiết bị, VID, PID, mã Serial Number).
        """
        return [
            {
                "device": port.device,
                "description": port.description or "Serial port",
                "vid": port.vid,
                "pid": port.pid,
                "serial_number": port.serial_number,
            }
            for port in serial.tools.list_ports.comports()
        ]

    def connect(self):
        """
        Thiết lập kết nối với thiết bị Logic Analyzer thông qua cổng Serial.
        Thực hiện chuỗi thủ tục bắt tay (handshake): STOP -> PING -> INFO.
        Trả về True nếu kết nối và bắt tay thành công, ngược lại trả về False.
        """
        try:
            # Khởi tạo kết nối với timeout mặc định là 1 giây
            self.serial = serial.Serial(self.port, self.baudrate, timeout=1)
            time.sleep(0.1)  # Đợi ổn định cổng vật lý sau khi mở
            self.serial.reset_input_buffer()  # Dọn sạch các byte nhiễu trong bộ đệm nhận
            
            # Gửi lệnh STOP đề phòng thiết bị đang chạy dở phiên capture cũ
            self._send_line("STOP")
            stop_deadline = time.monotonic() + 0.3
            while time.monotonic() < stop_deadline:
                self._read_line(0.05)  # Đọc bỏ các phản hồi thừa

            self.serial.reset_input_buffer()
            # Gửi lệnh PING để kiểm tra thiết bị có phản hồi không
            self._send_line("PING")
            ping_deadline = time.monotonic() + 2.0
            response = ""
            while time.monotonic() < ping_deadline:
                response = self._read_line(0.1)
                if response == "PONG SLA8":
                    break
            
            if response != "PONG SLA8":
                self.last_error = response or "Device did not answer PING"
                self.disconnect()
                return False

            # Đọc thông tin cấu hình phần cứng thiết bị bằng lệnh INFO
            self.device_info = self._read_info()
            if self.device_info:
                self.current_capture_mode = self.device_info.get("capture_mode")
            return self.device_info is not None
        except Exception:
            if self.serial:
                self.serial.close()
                self.serial = None
            raise

    def disconnect(self):
        """
        Ngắt kết nối cổng Serial và đóng phiên làm việc với thiết bị.
        Gửi lệnh dừng STOP trước khi ngắt.
        """
        if self.serial:
            try:
                self._send_line("STOP")
            except Exception:
                pass
            self.serial.close()
            self.serial = None

    def _send_line(self, text):
        """
        Gửi một chuỗi lệnh ASCII kết thúc bằng ký tự xuống dòng '\\n' về phía MCU.
        """
        self.serial.write(text.encode("ascii") + b"\n")
        self.serial.flush()  # Đảm bảo dữ liệu đã được đẩy ra khỏi buffer của OS

    def _read_line(self, timeout_s):
        """
        Đọc một dòng phản hồi dạng văn bản (ASCII) từ thiết bị, kết thúc bằng dấu xuống dòng.
        """
        old_timeout = self.serial.timeout
        self.serial.timeout = timeout_s
        try:
            return self.serial.readline().decode("ascii", errors="ignore").strip()
        finally:
            self.serial.timeout = old_timeout

    def _read_exact(self, length, timeout_s):
        """
        Đọc chính xác một số lượng byte 'length' dữ liệu nhị phân từ thiết bị.
        Thường dùng để đọc gói tin Header và Payload nhị phân của mẫu đo.
        """
        old_timeout = self.serial.timeout
        self.serial.timeout = timeout_s
        try:
            data = bytearray()
            while len(data) < length:
                chunk = self.serial.read(length - len(data))
                if not chunk:
                    raise TimeoutError("serial read timeout")
                data.extend(chunk)
            return bytes(data)
        finally:
            self.serial.timeout = old_timeout

    def _read_info(self):
        """
        Gửi lệnh INFO và phân tích các dòng phản hồi trả về từ thiết bị để lấy cấu hình phần cứng.
        """
        self.serial.reset_input_buffer()
        self._send_line("INFO")
        deadline = time.time() + 2.0
        idle_reads = 0
        saw_legacy_tail = False
        info = {
            "type": "info",
            "device_name": "SLA8",
            "version": "unknown",
            "channels": 8,
            "buffer_size": 0,
            "max_rate": 0,
            "capture_mode": None,
        }

        while time.time() < deadline:
            line = self._read_line(0.1)
            if not line:
                idle_reads += 1
                if saw_legacy_tail and idle_reads >= 2:
                    break
                continue
            idle_reads = 0
            if line.startswith("INFO "):
                info["version"] = line.split(" ", 1)[1]
            elif line.startswith("CHANNELS "):
                info["channels"] = int(line.split(" ", 1)[1])
            elif line.startswith("BUFFER "):
                info["buffer_size"] = int(line.split(" ", 1)[1])
            elif line.startswith("MAX_TARGET_RATE "):
                info["max_rate"] = int(line.split(" ", 1)[1])
            elif line.startswith("CAPTURE_MODE "):
                mode_name = line.split(" ", 1)[1]
                info["capture_mode"] = "DMA" if "DMA" in mode_name else "ISR"
            elif line.startswith("HARDWARE_MAX_RATE "):
                # Nhận diện dòng đuôi của giao thức cũ để kết thúc sớm
                saw_legacy_tail = True
            elif line == "END INFO":
                break

        return info if info["buffer_size"] else None

    def _expect_ok(self, command, timeout_s=2.0):
        """
        Gửi một lệnh cấu hình và kiểm tra xem phản hồi có bắt đầu bằng chữ "OK" hay không.
        """
        if not self.serial:
            return False
        self.serial.reset_input_buffer()
        self._send_line(command)
        response = self._read_line(timeout_s)
        if response.startswith("OK"):
            return True
        self.last_error = response or "No response"
        return False

    def set_sample_rate(self, sample_rate_hz):
        """
        Gửi lệnh cấu hình tần số lấy mẫu (Hz) tới thiết bị.
        """
        sample_rate_hz = int(sample_rate_hz)
        ok = self._expect_ok(f"CFG RATE {sample_rate_hz}")
        if ok:
            self.current_sample_rate_hz = sample_rate_hz
        return ok

    def set_trigger(self, enabled):
        """
        Bật hoặc tắt chức năng trigger.
        - enabled = True: Mặc định cấu hình kích hoạt khi có sườn xuống (Falling Edge) trên kênh 0.
        - enabled = False: Thiết lập trigger tức thời (Immediate) - đo ngay lập tức khi gõ lệnh.
        """
        command = "TRIG FALL 0" if enabled else "TRIG IMM"
        ok = self._expect_ok(command)
        if ok:
            self.trigger_enabled = bool(enabled)
        return ok

    def set_capture_mode(self, mode):
        """
        Gửi lệnh cấu hình cơ chế lấy mẫu: "ISR" (ngắt trực tiếp) hoặc "DMA" (tự động phần cứng).
        """
        normalized = str(mode).strip().upper()
        if normalized not in {"ISR", "DMA"}:
            raise ValueError("capture mode must be ISR or DMA")
        ok = self._expect_ok(f"CFG MODE {normalized}")
        if ok:
            self.current_capture_mode = normalized
        return ok

    def read_status(self, timeout_s=1.0):
        """
        Gửi lệnh STATUS để cập nhật thông tin chi tiết về hoạt động hiện tại của thiết bị nhúng.
        Trả về một dictionary chứa các thông số trạng thái.
        """
        if not self.serial:
            return None
        self.serial.reset_input_buffer()
        self._send_line("STATUS")
        deadline = time.monotonic() + timeout_s
        status = {}
        idle_reads = 0
        while time.monotonic() < deadline:
            line = self._read_line(0.1)
            if not line:
                idle_reads += 1
                if status and idle_reads >= 2:
                    break
                continue
            idle_reads = 0
            if line == "END STATUS":
                break
            key, separator, value = line.partition(" ")
            if not separator:
                continue
            if key == "STATUS":
                status["state"] = value
                continue
            try:
                status[key.lower()] = int(value, 0)
            except ValueError:
                status[key.lower()] = value
        return status or None

    def _capture_timeout_s(self):
        """
        Tính toán khoảng thời gian chờ timeout động của một lệnh capture
        phụ thuộc vào kích thước bộ đệm RAM của MCU và tần số lấy mẫu.
        """
        buffer_size = 8192
        if self.device_info:
            buffer_size = int(self.device_info.get("buffer_size") or buffer_size)
            
        # Nếu có trigger, firmware sẽ đợi tối đa 8 bộ đệm để tìm trigger trước khi báo timeout.
        # Immediate capture chỉ cần khoảng thời gian tương ứng 1 bộ đệm là thu thập đủ.
        capture_buffers = 9 if self.trigger_enabled else 1
        capture_s = capture_buffers * buffer_size / max(1, self.current_sample_rate_hz)
        return max(3.0, capture_s + 2.0)

    def capture(self, timeout=None):
        """
        Thực hiện một chu kỳ đo tín hiệu (Capture):
        1. Gửi lệnh ARM bắt đầu đo và kiểm tra xác nhận ARMED từ MCU.
        2. Chờ nhận phản hồi EVENT (ví dụ: EVENT COMPLETE hoặc EVENT OVERFLOW) báo hiệu đo xong.
        3. Gửi lệnh DUMP để yêu cầu truyền dữ liệu.
        4. Đọc nhị phân gói tin Header (48 byte) và giải mã để xác định kích thước gói tin mẫu đo.
        5. Đọc nhị phân toàn bộ gói dữ liệu mẫu đo (Payload).
        6. Giải mã cấu trúc gói tin và trả về kết quả dưới dạng dictionary dữ liệu hoàn chỉnh.
        """
        if not self.serial:
            return None

        try:
            self.last_error = None
            if timeout is None:
                timeout = self._capture_timeout_s()
            self.serial.reset_input_buffer()
            
            # 1. Khởi động Arm capture
            self._send_line("ARM")
            arm_response = self._read_line(2.0)
            if not arm_response.startswith("OK"):
                self.last_error = arm_response or "ARM did not respond"
                return None

            # 2. Đợi nhận sự kiện kết thúc EVENT từ thiết bị
            event = ""
            deadline = time.time() + timeout
            while time.time() < deadline:
                event = self._read_line(0.1)
                if event.startswith("EVENT "):
                    break
            
            if not event.startswith("EVENT "):
                self.last_error = "Capture event timeout"
                self._send_line("STOP")
                self._read_line(0.5)
                return None
                
            if event == "EVENT NO_TRIGGER":
                return {"type": "trigger_timeout"}
                
            terminal_state = event.removeprefix("EVENT ")
            if terminal_state not in {"COMPLETE", "OVERFLOW"}:
                self.last_error = f"Firmware capture ended in {terminal_state}"
                return None

            # 3. Yêu cầu tải dữ liệu (DUMP)
            self._send_line("DUMP")
            
            # 4. Đọc 48 byte Header đầu tiên
            header = self._read_exact(HEADER_LENGTH, 2.0)
            configured_limit = MAX_SAFE_FRAME_SAMPLES
            if self.device_info:
                configured_limit = int(
                    self.device_info.get("buffer_size") or configured_limit
                )
            
            # Giải mã header
            frame_header = decode_frame_header(
                header,
                max_samples=min(configured_limit, MAX_SAFE_FRAME_SAMPLES),
            )
            total_samples = frame_header.total_samples
            
            # 5. Đọc tiếp chính xác số byte mẫu đo tương ứng
            payload = self._read_exact(total_samples, timeout)
            raw_frame = header + payload
            
            # 6. Giải mã toàn bộ gói tin
            frame = decode_frame(raw_frame)
            sample_period_ns = 1_000_000_000.0 / frame.actual_sample_rate_hz

            return {
                "type": "capture",
                "samples": frame.samples,
                "sample_period_ns": sample_period_ns,
                "sample_count": len(frame.samples),
                "requested_sample_rate_hz": frame.sample_rate_hz,
                "sample_rate_hz": frame.actual_sample_rate_hz,
                "trigger_index": frame.trigger_index,
                "overflow_count": frame.overflow_count,
                "dropped_samples": frame.dropped_samples,
                "flags": frame.flags,
                "raw_frame": raw_frame,
            }
        except (TimeoutError, FrameError, serial.SerialException) as exc:
            self.last_error = str(exc)
            return None

    def start_stream(self):
        """
        Chế độ truyền luồng liên tục (streaming).
        Firmware hiện tại chỉ hỗ trợ chế độ offline capture (nhận khối) nên báo không hỗ trợ.
        """
        self.last_error = "Firmware hien tai chi ho tro offline capture"
        return False

    def stop_stream(self, drain=True):
        return []
