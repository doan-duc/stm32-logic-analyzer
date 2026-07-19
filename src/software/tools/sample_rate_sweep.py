from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

# Thêm thư mục gốc phần mềm vào sys.path để import các module khác
SOFTWARE_DIR = Path(__file__).resolve().parents[1]
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from device import LogicAnalyzerDevice
from sample_rate_benchmark import CaptureResult, best_stable_rate, timer_exact_rates
from signal_verifier import analyze_gray_capture
from tools.hardware_self_test import (
    _generator_command,
    _requested_rate_failures,
    _status_failures,
)


def _failed_repeats(rate: int, repeats: int, reason: str) -> list[CaptureResult]:
    """Tạo nhanh danh sách các kết quả thất bại (FAIL) cho tất cả lượt chạy lặp lại."""
    return [
        CaptureResult(rate, 0, repeat, False, (reason,))
        for repeat in range(1, repeats + 1)
    ]


def run_sweep(args: argparse.Namespace) -> tuple[list[CaptureResult], dict]:
    """
    Thực hiện quét (sweep) qua các tần số lấy mẫu để kiểm tra giới hạn ổn định.
    """
    try:
        import serial
    except ImportError as exc:
        raise SystemExit("pyserial is required for hardware benchmark") from exc

    # Xác định danh sách tần số lấy mẫu cần quét.
    # Nếu không khai báo cụ thể bằng '--rates', tự động tính toán dãy tần số dựa trên hệ số chia của Timer.
    rates = tuple(args.rates) if args.rates else timer_exact_rates(
        args.timer_clock,
        args.minimum_rate,
        args.maximum_rate,
    )
    results: list[CaptureResult] = []
    device = LogicAnalyzerDevice(args.la_port, args.la_baud)

    # Kết nối cổng nạp/phát tín hiệu mẫu Gray của Arduino Uno/Nano
    with serial.Serial(args.generator_port, args.generator_baud, timeout=0.2) as generator:
        time.sleep(args.generator_reset_wait)
        
        # Đồng bộ và bắt tay cấu hình bộ generator
        _generator_command(generator, "PING", "PONG SLA8-GEN", 2.0)
        _generator_command(generator, "MODE GRAY", "OK MODE GRAY", 2.0)
        _generator_command(
            generator,
            f"GRAY RATE {args.gray_rate}",
            f"OK GRAY RATE {args.gray_rate}",
            2.0,
        )

        # Kết nối tới Logic Analyzer cần đánh giá hiệu năng
        if not device.connect():
            raise RuntimeError(device.last_error or "logic analyzer did not connect")
        try:
            # Mặc định sử dụng cơ chế DMA để quét kiểm tra giới hạn tối đa
            if not device.set_trigger(False) or not device.set_capture_mode("DMA"):
                raise RuntimeError(device.last_error or "failed to configure DMA capture")

            for rate in rates:
                # Thiết lập tần số lấy mẫu hiện tại cần test
                if not device.set_sample_rate(rate):
                    reason = device.last_error or "firmware rejected rate"
                    results.extend(_failed_repeats(rate, args.captures, reason))
                    print(f"REJECT rate={rate}: {reason}")
                    continue

                for repeat in range(1, args.captures + 1):
                    # Thực hiện đo đạc
                    frame = device.capture()
                    if not frame:
                        reason = device.last_error or "no capture frame"
                        result = CaptureResult(rate, 0, repeat, False, (reason,))
                        results.append(result)
                        print(f"FAIL rate={rate} repeat={repeat}: {reason}")
                        continue

                    # Xác minh chất lượng dạng sóng thu được qua verifier
                    report = analyze_gray_capture(
                        frame["samples"],
                        sample_rate_hz=frame["sample_rate_hz"],
                        step_rate_hz=args.gray_rate,
                        rate_tolerance=args.rate_tolerance,
                        minimum_states=args.minimum_states,
                    )
                    status = device.read_status() or {}
                    failures = list(report.failures)
                    failures.extend(_status_failures(status, "DMA"))
                    failures.extend(
                        _requested_rate_failures(
                            rate,
                            frame["sample_rate_hz"],
                            args.rate_tolerance,
                        )
                    )
                    
                    # Kiểm tra các siêu dữ liệu và cờ lỗi của gói tin
                    if frame["requested_sample_rate_hz"] != rate:
                        failures.append("frame requested-rate metadata mismatch")
                    if frame["flags"] != 0:
                        failures.append(f"frame flags={frame['flags']}")
                    if frame["overflow_count"] != 0:
                        failures.append(f"overflow={frame['overflow_count']}")
                    if frame["dropped_samples"] != 0:
                        failures.append(f"dropped={frame['dropped_samples']}")

                    # Tạo bản ghi kết quả cho lượt chạy này
                    result = CaptureResult(
                        rate,
                        frame["sample_rate_hz"],
                        repeat,
                        not failures,
                        tuple(failures),
                    )
                    results.append(result)
                    verdict = "PASS" if result.passed else "FAIL"
                    print(
                        f"{verdict} requested={rate} actual={result.actual_rate_hz} "
                        f"repeat={repeat} states={report.stable_states} "
                        f"measured={report.measured_sample_rate_hz:.0f}Hz "
                        f"error={report.rate_error_fraction * 100:.2f}%"
                    )
                    for failure in failures:
                        print(f"  - {failure}")
        finally:
            device.disconnect()

    # Siêu dữ liệu báo cáo
    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "la_port": args.la_port,
        "generator_port": args.generator_port,
        "firmware": (device.device_info or {}).get("version", "unknown"),
        "firmware_max_rate_hz": (device.device_info or {}).get("max_rate", 0),
        "timer_clock_hz": args.timer_clock,
        "gray_rate_hz": args.gray_rate,
        "required_repeats": args.captures,
        "rates_hz": rates,
    }
    return results, metadata


def main(argv: list[str] | None = None) -> int:
    """
    Hàm khởi chạy chính của tool quét tần số lấy mẫu.
    """
    parser = argparse.ArgumentParser(
        description="Sweep STM32 DMA sample rates against an Arduino Gray-code oracle"
    )
    parser.add_argument("--la-port", default="COM12", help="Cổng COM của Logic Analyzer")
    parser.add_argument("--generator-port", default="COM18", help="Cổng COM của Arduino phát tín hiệu mẫu")
    parser.add_argument("--la-baud", type=int, default=1_000_000, help="Baud rate cổng truyền thông LA")
    parser.add_argument("--generator-baud", type=int, default=115_200, help="Baud rate cổng truyền thông Arduino")
    parser.add_argument("--generator-reset-wait", type=float, default=2.0, help="Thời gian chờ reset Arduino (giây)")
    parser.add_argument("--timer-clock", type=int, default=64_000_000, help="Tần số nguồn xung nhịp của Timer (Hz)")
    parser.add_argument("--minimum-rate", type=int, default=1_000_000, help="Tần số lấy mẫu tối thiểu muốn sweep (Hz)")
    parser.add_argument("--maximum-rate", type=int, default=32_000_000, help="Tần số lấy mẫu tối đa muốn sweep (Hz)")
    parser.add_argument("--rates", nargs="+", type=int, help="Danh sách thủ công các tần số muốn sweep")
    parser.add_argument("--captures", type=int, default=5, help="Số lần capture lặp lại cho mỗi tần số để lấy thống kê ổn định")
    parser.add_argument("--gray-rate", type=int, default=100_000, help="Tần số chuyển trạng thái đếm mã Gray (Hz)")
    parser.add_argument("--minimum-states", type=int, default=32, help="Số lượng trạng thái ổn định tối thiểu cần quét qua")
    parser.add_argument("--rate-tolerance", type=float, default=0.03, help="Tỷ lệ sai số tần số tối đa cho phép (3%)")
    parser.add_argument(
        "--ledger",
        default="report/generated/sample_rate_benchmark.json",
        help="Đường dẫn file JSON xuất kết quả thống kê",
    )
    args = parser.parse_args(argv)
    
    if args.captures <= 0 or args.minimum_states <= 0:
        parser.error("captures and minimum-states must be > 0")

    # Chạy quy trình quét tần số
    results, metadata = run_sweep(args)
    # Xác định tần số lấy mẫu cao nhất đạt trạng thái ổn định hoàn toàn
    stable_rate = best_stable_rate(results, args.captures)
    
    # Ghi đè thông tin kết quả vào file JSON cấu hình xuất báo cáo
    ledger = {
        **metadata,
        "best_stable_requested_rate_hz": stable_rate,
        "results": [asdict(result) for result in results],
    }
    ledger_path = Path(args.ledger)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")

    if stable_rate is None:
        print(f"NO STABLE RATE; ledger={ledger_path}")
        return 1
        
    highest_tested = max(result.requested_rate_hz for result in results)
    ceiling_reached = stable_rate < highest_tested
    label = "BEST STABLE" if ceiling_reached else "AT LEAST"
    print(f"{label} {stable_rate} samples/s; ledger={ledger_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
