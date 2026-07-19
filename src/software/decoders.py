from __future__ import annotations

from dataclasses import dataclass

# Số lượng mẫu tối thiểu cho mỗi chu kỳ Clock của SPI để đảm bảo tính toàn vẹn (tránh méo dạng do thiếu mẫu)
SPI_MIN_SAMPLES_PER_CLOCK = 4


@dataclass
class DecodedEvent:
    """
    Lớp dữ liệu lưu trữ thông tin về một byte hoặc sự kiện đã được giải mã.
    
    - time_us: Mốc thời gian xảy ra sự kiện (micro giây).
    - protocol: Tên giao thức (ví dụ: "UART", "I2C", "SPI").
    - event: Loại sự kiện (ví dụ: "START", "BYTE", "STOP", "WARN").
    - value: Chuỗi biểu diễn giá trị (ví dụ: "0x41 'A'", "MOSI=0x00 MISO=0xFF").
    - note: Chú thích bổ sung (ví dụ: số thứ tự byte, lỗi truyền...).
    """
    time_us: float
    protocol: str
    event: str
    value: str
    note: str = ""


def _bit(sample: int, channel: int) -> int:
    """
    Hàm nội bộ trích xuất bit trạng thái của một kênh đo từ một mẫu dữ liệu thô.
    """
    return (sample >> channel) & 0x01


def decode_uart(samples: bytes, sample_rate_hz: int, rx_channel: int, baudrate: int):
    """
    Giải mã tín hiệu giao tiếp UART (8-N-1: 8 bit dữ liệu, không parity, 1 bit stop).

    samples: Luồng bytes thô từ Logic Analyzer.
    sample_rate_hz: Tần số lấy mẫu (Hz).
    rx_channel: Kênh logic nối với đường truyền RX UART.
    baudrate: Tốc độ Baud Rate của UART (ví dụ 9600, 115200...).
    """
    events = []
    if sample_rate_hz <= 0 or baudrate <= 0 or not samples:
        return events

    # Tính toán số lượng mẫu trung bình ứng với mỗi Bit thời gian (Width of 1 bit in samples)
    samples_per_bit = sample_rate_hz / baudrate
    if samples_per_bit < 3.0:
        # Cảnh báo nếu tần số lấy mẫu quá thấp, không đảm bảo tính chính xác khi giải mã
        events.append(
            DecodedEvent(
                0.0,
                "UART",
                "WARN",
                "sample rate qua thap",
                f"{sample_rate_hz} Hz / {baudrate} baud",
            )
        )

    i = 0
    # Chiều dài của một khung truyền UART (1 start + 8 data + 1 stop) tính theo số mẫu
    frame_span = round(samples_per_bit * 9.5)
    # Khoảng thời gian yêu cầu đường truyền rảnh (idle - mức cao) trước khi nhận dạng Start Bit mới
    idle_span = max(1, int(samples_per_bit * 2.0))
    
    while i + frame_span < len(samples):
        cur_bit = _bit(samples[i], rx_channel)
        start_edge = False
        if i == 0:
            start_edge = cur_bit == 0
        else:
            prev_bit = _bit(samples[i - 1], rx_channel)
            # Phát hiện sườn xuống (từ 1 xuống 0) - dấu hiệu bắt đầu của Start Bit
            start_edge = prev_bit == 1 and cur_bit == 0

        if start_edge:
            start_index = i
            idle_start = start_index - idle_span
            # Kiểm tra xem đường truyền trước đó có thực sự rảnh (luôn bằng 1) không.
            # Nếu có bất kỳ mẫu nào bằng 0 trong khoảng idle, coi như đó là nhiễu và bỏ qua.
            if idle_start >= 0 and any(
                _bit(sample, rx_channel) == 0
                for sample in samples[idle_start:start_index]
            ):
                i += 1
                continue
                
            # Kiểm tra điểm giữa (midpoint) của Start Bit để xác nhận Start Bit hợp lệ
            start_mid = round(start_index + 0.5 * samples_per_bit)
            if _bit(samples[start_mid], rx_channel) != 0:
                i += 1
                continue  # Nếu điểm giữa không phải là 0, bỏ qua vì là nhiễu đột biến
                
            events.append(
                DecodedEvent(
                    start_index * 1_000_000.0 / sample_rate_hz,
                    "UART",
                    "START",
                    "0",
                    "line low",
                )
            )
            
            # Bắt đầu đọc 8 bit dữ liệu tại điểm giữa của mỗi ô Bit (sampling at midpoints)
            value = 0
            raw_bits = []
            for bit_index in range(8):
                # Vị trí mẫu đo tương ứng với bit thứ bit_index (1.5, 2.5 ... 8.5)
                sample_index = round(start_index + (1.5 + bit_index) * samples_per_bit)
                bit_value = _bit(samples[sample_index], rx_channel)
                raw_bits.append(bit_value)
                value |= bit_value << bit_index  # Lắp ráp byte theo thứ tự LSB-first (bit thấp gửi trước)

            # Lấy mẫu tại vị trí giữa của Stop Bit (chỉ số mẫu thứ 9.5)
            stop_index = round(start_index + 9.5 * samples_per_bit)
            stop_bit = _bit(samples[stop_index], rx_channel)
            
            # Chuyển đổi thành ký tự ASCII nếu nằm trong dải hiển thị, ngược lại hiển thị dấu chấm '.'
            char = chr(value) if 32 <= value <= 126 else "."
            note = "8N1"
            if stop_bit != 1:
                note = "framing error"  # Lỗi khung truyền nếu Stop Bit không ở mức cao (1)
                
            events.append(
                DecodedEvent(
                    start_index * 1_000_000.0 / sample_rate_hz,
                    "UART",
                    "BYTE",
                    f"0x{value:02X} '{char}'",
                    note,
                )
            )
            events.append(
                DecodedEvent(
                    stop_index * 1_000_000.0 / sample_rate_hz,
                    "UART",
                    "STOP",
                    str(stop_bit),
                    "ok" if stop_bit == 1 else "framing error",
                )
            )
            # Nhảy qua khung dữ liệu hiện tại và thêm một khoảng đệm nhỏ trước khi tìm Start Bit kế tiếp
            i = stop_index + max(1, int(samples_per_bit * 0.5))
        else:
            i += 1

    return events


def decode_i2c(samples: bytes, sample_rate_hz: int, scl_channel: int, sda_channel: int):
    """
    Giải mã tín hiệu giao tiếp I2C.

    samples: Luồng bytes thô từ Logic Analyzer.
    sample_rate_hz: Tần số lấy mẫu (Hz).
    scl_channel: Kênh logic nối với đường xung nhịp SCL.
    sda_channel: Kênh logic nối với đường dữ liệu SDA.
    """
    events = []
    if sample_rate_hz <= 0 or not samples:
        return events

    bits = []
    byte_index = 0
    in_frame = False

    def time_us(index):
        return index * 1_000_000.0 / sample_rate_hz

    for i in range(1, len(samples)):
        prev_scl = _bit(samples[i - 1], scl_channel)
        cur_scl = _bit(samples[i], scl_channel)
        prev_sda = _bit(samples[i - 1], sda_channel)
        cur_sda = _bit(samples[i], sda_channel)

        # Phát hiện sự kiện START: SCL ở mức HIGH và SDA chuyển từ HIGH sang LOW
        if prev_scl == 1 and cur_scl == 1 and prev_sda == 1 and cur_sda == 0:
            in_frame = True
            bits = []
            byte_index = 0
            events.append(DecodedEvent(time_us(i), "I2C", "START", "", ""))
            continue

        # Phát hiện sự kiện STOP: SCL ở mức HIGH và SDA chuyển từ LOW sang HIGH
        if (
            in_frame
            and prev_scl == 1
            and cur_scl == 1
            and prev_sda == 0
            and cur_sda == 1
        ):
            events.append(DecodedEvent(time_us(i), "I2C", "STOP", "", ""))
            in_frame = False
            bits = []
            continue

        # Lấy mẫu dữ liệu I2C: Đọc SDA tại sườn lên (Rising Edge) của chân SCL
        if in_frame and prev_scl == 0 and cur_scl == 1:
            bits.append(cur_sda)
            if len(bits) == 9:
                # Đủ 9 bits: 8 bit dữ liệu + 1 bit ACK/NACK
                data_bits = bits[:8]
                ack_bit = bits[8]
                value = 0
                for bit_value in data_bits:
                    value = (value << 1) | bit_value  # Lắp ráp byte dữ liệu, bit MSB gửi trước
                ack_text = "ACK" if ack_bit == 0 else "NACK"
                
                if byte_index == 0:
                    # Byte đầu tiên sau START là byte Địa chỉ (7-bit Address + 1-bit R/W)
                    addr = value >> 1
                    rw = "R" if (value & 1) else "W"
                    events.append(
                        DecodedEvent(
                            time_us(i),
                            "I2C",
                            "ADDR",
                            f"0x{addr:02X} {rw}",
                            ack_text,
                        )
                    )
                else:
                    # Các byte tiếp theo là byte Dữ liệu thường
                    events.append(
                        DecodedEvent(
                            time_us(i),
                            "I2C",
                            "DATA",
                            f"0x{value:02X}",
                            ack_text,
                        )
                    )
                byte_index += 1
                bits = []

    return events


def decode_spi(
    samples: bytes,
    sample_rate_hz: int,
    sck_channel: int,
    mosi_channel: int,
    miso_channel: int,
    cs_channel: int = -1,
):
    """
    Giải mã tín hiệu giao tiếp SPI (Mặc định CPOL=0, CPHA=0: Lấy mẫu tại sườn lên của SCK).

    samples: Luồng bytes thô từ Logic Analyzer.
    sample_rate_hz: Tần số lấy mẫu (Hz).
    sck_channel: Kênh logic nối với đường xung nhịp SCK.
    mosi_channel: Kênh logic nối với đường dữ liệu MOSI.
    miso_channel: Kênh logic nối với đường dữ liệu MISO.
    cs_channel: Kênh chọn chip CS/SS (Nếu < 0, coi như không dùng chân CS và tự động kích hoạt khung dữ liệu).
    """
    events = []
    if sample_rate_hz <= 0 or not samples:
        return events

    def time_us(index):
        return index * 1_000_000.0 / sample_rate_hz

    # Kiểm tra xem có cấu hình chân CS hợp lệ hay không
    uses_cs = 0 <= cs_channel < 8
    in_frame = False
    bits_mosi = []
    bits_miso = []
    sampling_edges = []
    pending_bytes = []
    byte_index = 0

    def finish_frame(index: int, note: str = "frame end"):
        """
        Hoàn tất một khung truyền SPI: Kiểm tra lỗi đo đạc và đẩy các byte tích lũy vào danh sách sự kiện.
        """
        nonlocal bits_mosi, bits_miso, sampling_edges, pending_bytes

        # Tính toán chu kỳ xung clock SCK ngắn nhất đo được để phát hiện lỗi thiếu mẫu (undersampling)
        shortest_cycle = min(
            (right - left for left, right in zip(sampling_edges, sampling_edges[1:])),
            default=None,
        )
        if shortest_cycle is not None and shortest_cycle < SPI_MIN_SAMPLES_PER_CLOCK:
            events.append(
                DecodedEvent(
                    time_us(index),
                    "SPI",
                    "WARN",
                    "UNDERSAMPLED",
                    (
                        f"shortest SCK cycle is {shortest_cycle} samples; "
                        f"need at least {SPI_MIN_SAMPLES_PER_CLOCK}"
                    ),
                )
            )
        elif bits_mosi or bits_miso:
            # Lỗi nếu khung truyền kết thúc khi chưa nhận đủ số bit cho một byte (bội số của 8)
            events.append(
                DecodedEvent(
                    time_us(index),
                    "SPI",
                    "WARN",
                    "INCOMPLETE",
                    f"frame ended with {len(bits_mosi)} trailing bits",
                )
            )
        else:
            # Nếu khung hợp lệ, đẩy các byte đã lưu tạm vào sự kiện chính
            events.extend(pending_bytes)

        bits_mosi = []
        bits_miso = []
        sampling_edges = []
        pending_bytes = []

    for i in range(1, len(samples)):
        prev_sck = _bit(samples[i - 1], sck_channel)
        cur_sck = _bit(samples[i], sck_channel)
        prev_cs = _bit(samples[i - 1], cs_channel) if uses_cs else 0
        cur_cs = _bit(samples[i], cs_channel) if uses_cs else 0

        # Phát hiện bắt đầu khung truyền SPI
        if not in_frame and (not uses_cs or (prev_cs == 1 and cur_cs == 0)):
            if uses_cs:
                # Bắt đầu khung khi đường CS chuyển từ HIGH xuống LOW
                in_frame = True
                bits_mosi = []
                bits_miso = []
                sampling_edges = []
                pending_bytes = []
                byte_index = 0
                events.append(
                    DecodedEvent(
                        time_us(i),
                        "SPI",
                        "CS",
                        "LOW",
                        "frame start",
                    )
                )
            elif prev_sck == 0 and cur_sck == 1:
                # Nếu không dùng CS, bắt đầu khung khi phát hiện sườn lên SCK đầu tiên
                in_frame = True
                bits_mosi = []
                bits_miso = []
                sampling_edges = []
                pending_bytes = []
                byte_index = 0
                events.append(
                    DecodedEvent(
                        time_us(i),
                        "SPI",
                        "FRAME",
                        "START",
                        "no CS",
                    )
                )

        if not in_frame:
            continue

        # Phát hiện kết thúc khung truyền SPI khi dùng CS (đường CS kéo lên HIGH)
        if uses_cs and prev_cs == 0 and cur_cs == 1:
            finish_frame(i)
            events.append(
                DecodedEvent(
                    time_us(i),
                    "SPI",
                    "CS",
                    "HIGH",
                    "frame end",
                )
            )
            in_frame = False
            continue

        # Lấy mẫu SPI tại sườn lên (Rising Edge) của chân SCK
        if prev_sck == 0 and cur_sck == 1:
            sampling_edges.append(i)
            bits_mosi.append(_bit(samples[i], mosi_channel))
            bits_miso.append(_bit(samples[i], miso_channel))
            
            if len(bits_mosi) == 8:
                # Đã nhận đủ 8 bit, tiến hành dựng byte
                mosi_value = 0
                miso_value = 0
                for bit in range(8):
                    mosi_value = (mosi_value << 1) | bits_mosi[bit]  # MSB-first
                    miso_value = (miso_value << 1) | bits_miso[bit]
                byte_event = DecodedEvent(
                    time_us(i),
                    "SPI",
                    "BYTE",
                    f"MOSI=0x{mosi_value:02X} MISO=0x{miso_value:02X}",
                    f"byte {byte_index}",
                )
                if uses_cs:
                    pending_bytes.append(byte_event)  # Lưu tạm, chỉ hiển thị nếu CS kéo lên HIGH thành công
                else:
                    events.append(byte_event)
                bits_mosi = []
                bits_miso = []
                byte_index += 1

    # Nếu đang đo dở dang mà luồng mẫu kết thúc
    if uses_cs and in_frame and (bits_mosi or pending_bytes):
        finish_frame(len(samples) - 1, "capture ended before CS HIGH")

    return events
