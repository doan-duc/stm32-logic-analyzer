from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

# Các hệ số chia tần số (Divider) của Timer dùng để quét tần số lấy mẫu kiểm thử
_BENCHMARK_TIMER_DIVIDERS = (64, 32, 16, 10, 8, 7, 6, 5, 4, 3, 2, 1)


@dataclass(frozen=True)
class CaptureResult:
    """
    Cấu trúc dữ liệu ghi lại kết quả của một lần thử nghiệm capture đo hiệu năng.
    
    - requested_rate_hz: Tần số lấy mẫu yêu cầu (Hz).
    - actual_rate_hz: Tần số lấy mẫu thực tế do Timer sinh ra (Hz).
    - repeat: Số thứ tự lần lặp lại kiểm thử.
    - passed: Trạng thái kiểm thử có vượt qua (True) hay thất bại (False).
    - failures: Danh sách các chuỗi thông báo lỗi thu thập được.
    """
    requested_rate_hz: int
    actual_rate_hz: int
    repeat: int
    passed: bool
    failures: tuple[str, ...]


def timer_exact_rates(
    timer_clock_hz: int,
    minimum_hz: int,
    maximum_hz: int,
) -> tuple[int, ...]:
    """
    Tính toán và trả về danh sách các tần số lấy mẫu chính xác có thể tạo ra
    tương ứng với các hệ số chia của Timer và nằm trong dải tần số chỉ định.
    
    timer_clock_hz: Tần số nguồn của Timer (Hz).
    minimum_hz: Tần số giới hạn dưới (Hz).
    maximum_hz: Tần số giới hạn trên (Hz).
    """
    if timer_clock_hz <= 0 or minimum_hz <= 0 or maximum_hz < minimum_hz:
        raise ValueError("timer clock and rate range must be positive and ordered")

    # Dùng set comprehension để loại bỏ các giá trị trùng lặp sau khi làm tròn
    rates = {
        round(timer_clock_hz / divider)
        for divider in _BENCHMARK_TIMER_DIVIDERS
        if minimum_hz <= round(timer_clock_hz / divider) <= maximum_hz
    }
    return tuple(sorted(rates))  # Trả về tuple đã được sắp xếp tăng dần


def best_stable_rate(
    results: Iterable[CaptureResult],
    required_repeats: int,
) -> int | None:
    """
    Tìm và trả về tần số lấy mẫu yêu cầu cao nhất mà tại đó mọi lần chạy lặp lại đều thành công (Passed).
    Được dùng để xác định giới hạn hoạt động ổn định thực tế của phần cứng.
    
    results: Tập hợp các kết quả kiểm thử.
    required_repeats: Số lần lặp lại tối thiểu yêu cầu cho mỗi tần số để đảm bảo tính tin cậy.
    """
    if required_repeats <= 0:
        raise ValueError("required_repeats must be > 0")

    # Nhóm các kết quả kiểm thử theo tần số lấy mẫu yêu cầu
    grouped: dict[int, list[CaptureResult]] = defaultdict(list)
    for result in results:
        grouped[result.requested_rate_hz].append(result)

    # Lọc ra các tần số có số lần chạy tối thiểu đạt yêu cầu và tất cả các lần chạy đều thành công
    stable_rates = [
        rate
        for rate, captures in grouped.items()
        if len(captures) >= required_repeats
        and all(capture.passed for capture in captures)
    ]
    # Trả về tần số lớn nhất tìm được, hoặc None nếu không có tần số nào đạt yêu cầu
    return max(stable_rates, default=None)
