from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean


@dataclass(frozen=True)
class GrayCaptureReport:
    """
    Báo cáo kết quả xác minh chất lượng tín hiệu thu thập được từ bộ phát mã Gray.
    
    - passed: True nếu tất cả kiểm tra đều đạt yêu cầu, False nếu có lỗi.
    - stable_states: Số lượng trạng thái ổn định đếm được.
    - sequence_errors: Số lỗi tuần tự (bị nhảy cóc hoặc sai thứ tự đếm).
    - short_runs: Số lần xuất hiện nhiễu xung ngắn (glitches).
    - measured_sample_rate_hz: Tần số lấy mẫu đo đạc thực tế (Hz).
    - rate_error_fraction: Tỷ lệ sai lệch tần số lấy mẫu so với lý thuyết.
    - channel_edges: Số sườn chuyển trạng thái ghi nhận được trên mỗi kênh (0-7).
    - failures: Danh sách chi tiết các lỗi kiểm tra phát hiện được.
    """
    passed: bool
    stable_states: int
    sequence_errors: int
    short_runs: int
    measured_sample_rate_hz: float
    rate_error_fraction: float
    channel_edges: tuple[int, ...]
    failures: tuple[str, ...]


def binary_to_gray(value: int) -> int:
    """
    Chuyển đổi số nhị phân 8-bit thông thường sang mã Gray (Reflected Gray Code).
    Quy tắc: lấy giá trị XOR với chính nó dịch phải 1 bit.
    """
    value &= 0xFF
    return value ^ (value >> 1)


def gray_to_binary(gray: int) -> int:
    """
    Chuyển đổi ngược mã Gray 8-bit về số nhị phân thông thường.
    """
    gray &= 0xFF
    value = gray
    shifted = gray >> 1
    while shifted:
        value ^= shifted
        shifted >>= 1
    return value & 0xFF


def _runs(samples: bytes) -> list[tuple[int, int]]:
    """
    Thực hiện mã hóa loạt dài (Run-Length Encoding - RLE) trên luồng mẫu đo.
    Gom các mẫu liên tiếp có cùng giá trị lại và tính toán độ dài xuất hiện của chúng.
    
    Trả về danh sách các tuple dạng (giá trị mẫu, độ dài chuỗi mẫu liên tiếp).
    """
    if not samples:
        return []
    runs: list[tuple[int, int]] = []
    current = samples[0]
    length = 1
    for sample in samples[1:]:
        if sample == current:
            length += 1
        else:
            runs.append((current, length))
            current = sample
            length = 1
    runs.append((current, length))
    return runs


def analyze_gray_capture(
    samples: bytes | bytearray | memoryview,
    *,
    sample_rate_hz: int,
    step_rate_hz: int = 10_000,
    rate_tolerance: float = 0.03,
    minimum_states: int = 64,
) -> GrayCaptureReport:
    """
    Phân tích gói tin capture mã Gray để đánh giá độ chính xác và tính toàn vẹn của tín hiệu đo.
    
    Bộ sinh mã Gray mẫu (thường chạy trên một bo mạch Arduino phụ trợ) phát ra chu kỳ đếm mã Gray 8-bit.
    Vì mã Gray chỉ thay đổi duy nhất 1 bit giữa 2 trạng thái liên tiếp, ta có thể dùng nó để kiểm tra xem
    thiết bị đo có bị mất mẫu, đọc sai bit hay sai lệch xung nhịp clock hay không.
    
    - samples: Dữ liệu mẫu logic thô thu được.
    - sample_rate_hz: Tần số lấy mẫu cấu hình (Hz).
    - step_rate_hz: Tần số đổi trạng thái đếm của bộ phát mã Gray (mặc định 10 kHz).
    - rate_tolerance: Mức sai lệch tần số tối đa cho phép (mặc định 3%).
    - minimum_states: Số trạng thái tối thiểu cần kiểm tra để kết luận.
    """
    if sample_rate_hz <= 0 or step_rate_hz <= 0:
        raise ValueError("sample_rate_hz and step_rate_hz must be > 0")
    if not 0 <= rate_tolerance < 1:
        raise ValueError("rate_tolerance must be in [0, 1)")

    # Phân tích luồng mẫu đo thành các đoạn giá trị liên tục (runs)
    raw_runs = _runs(bytes(samples))
    # Số mẫu mong muốn cho một bước trạng thái của bộ phát mã Gray
    expected_samples_per_step = sample_rate_hz / step_rate_hz
    # Độ dài ngắn nhất được coi là một trạng thái ổn định (được đặt bằng 30% độ dài dự kiến, tối thiểu 2 mẫu)
    minimum_run = max(2, int(expected_samples_per_step * 0.30))
    
    # Lọc ra các trạng thái ổn định có độ dài đạt yêu cầu
    stable = [(value, length) for value, length in raw_runs if length >= minimum_run]
    
    # Đếm số lượng nhiễu (glitches) - các đoạn ngắn nằm ở giữa mảng dữ liệu không đạt độ dài ổn định
    short_runs = sum(length < minimum_run for _, length in raw_runs[1:-1])

    # Giải mã các trạng thái ổn định từ Gray sang nhị phân
    decoded = [gray_to_binary(value) for value, _ in stable]
    # Lỗi tuần tự xảy ra nếu hai trạng thái liên tiếp chênh lệch khác 1
    sequence_errors = sum(
        ((current - previous) & 0xFF) != 1
        for previous, current in zip(decoded, decoded[1:])
    )

    # Đếm số lượng sườn xung (edges) ghi nhận được trên mỗi kênh (0 đến 7)
    channel_edges = tuple(
        sum(((left ^ right) & (1 << channel)) != 0 for left, right in zip(
            (value for value, _ in stable),
            (value for value, _ in stable[1:]),
        ))
        for channel in range(8)
    )

    # Tính toán tần số lấy mẫu thực tế dựa trên độ rộng trung bình của các trạng thái ổn định.
    # Loại trừ phần tử đầu và cuối để tránh sai lệch do capture bắt đầu/kết thúc lơ lửng giữa chừng.
    timing_lengths = [length for _, length in stable[1:-1]]
    measured_sample_rate_hz = (
        float(fmean(timing_lengths) * step_rate_hz) if timing_lengths else 0.0
    )
    # Tỷ lệ sai lệch tần số
    rate_error_fraction = (
        abs(measured_sample_rate_hz - sample_rate_hz) / sample_rate_hz
        if measured_sample_rate_hz
        else 1.0
    )

    # Tổng hợp các tiêu chí kiểm tra chất lượng
    failures: list[str] = []
    if len(stable) < minimum_states:
        failures.append(
            f"too few stable Gray states ({len(stable)} < {minimum_states})"
        )
    if sequence_errors:
        failures.append(f"Gray sequence has {sequence_errors} skipped/out-of-order steps")
    if short_runs:
        failures.append(f"captured {short_runs} short interior glitch state(s)")
    # Tìm các kênh không có chuyển trạng thái nào
    missing_channels = [str(index) for index, count in enumerate(channel_edges) if count == 0]
    if missing_channels:
        failures.append("no transition observed on channel(s) " + ", ".join(missing_channels))
    # Phát hiện sai lệch tần số quá giới hạn cho phép
    if rate_error_fraction > rate_tolerance:
        failures.append(
            "sample-rate mismatch: metadata "
            f"{sample_rate_hz} Hz, measured {measured_sample_rate_hz:.1f} Hz "
            f"({rate_error_fraction * 100:.2f}%)"
        )

    return GrayCaptureReport(
        passed=not failures,
        stable_states=len(stable),
        sequence_errors=sequence_errors,
        short_runs=short_runs,
        measured_sample_rate_hz=measured_sample_rate_hz,
        rate_error_fraction=rate_error_fraction,
        channel_edges=channel_edges,
        failures=tuple(failures),
    )
