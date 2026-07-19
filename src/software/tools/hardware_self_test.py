from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Tự động thêm thư mục cha (software) vào sys.path để import được các module khác
SOFTWARE_DIR = Path(__file__).resolve().parents[1]
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from device import LogicAnalyzerDevice
from signal_verifier import analyze_gray_capture


def _status_failures(status: dict | None, mode: str) -> list[str]:
    """
    Phân tích kết quả trạng thái STATUS từ thiết bị để tìm các lỗi phần cứng.
    Trả về danh sách các chuỗi mô tả lỗi phát hiện được.
    """
    if not status:
        return ["STATUS response missing or unparseable"]

    failures: list[str] = []
    # Kiểm tra xem có lỗi ngắt timer bị quá tải (ISR Overrun) hay không
    if "isr_overruns" not in status:
        failures.append("STATUS is missing ISR_OVERRUNS")
    elif int(status["isr_overruns"]) != 0:
        failures.append(f"ISR_OVERRUNS={status['isr_overruns']}")

    # Kiểm tra xem có lỗi truyền nhận DMA hay không
    if "dma_errors" not in status:
        failures.append("STATUS is missing DMA_ERRORS")
    elif int(status["dma_errors"]) != 0:
        failures.append(f"DMA_ERRORS={status['dma_errors']}")

    # Kiểm tra xem cơ chế capture thực tế của firmware có khớp với chế độ cấu hình yêu cầu
    expected_engine = {
        "DMA": "TIMER_DMA_GPIO_IDR",
        "ISR": "TIMER_ISR_DIRECT",
    }[mode]
    actual_engine = status.get("engine")
    if actual_engine != expected_engine:
        failures.append(
            f"capture engine mismatch: expected {expected_engine}, got {actual_engine!r}"
        )
    return failures


def _requested_rate_failures(
    requested_rate_hz: int,
    actual_rate_hz: int,
    tolerance: float,
) -> list[str]:
    """
    Kiểm tra sai số giữa tần số lấy mẫu thực tế đo được và tần số cấu hình yêu cầu.
    """
    if requested_rate_hz <= 0 or actual_rate_hz <= 0:
        return ["requested and actual sample rates must be positive"]
    error = abs(actual_rate_hz - requested_rate_hz) / requested_rate_hz
    if error > tolerance:
        return [
            f"actual rate {actual_rate_hz} Hz differs from requested "
            f"{requested_rate_hz} Hz by {error * 100:.2f}%"
        ]
    return []


def _generator_command(ser, command: str, expected: str, timeout_s: float) -> None:
    """
    Gửi một lệnh tới bộ phát tín hiệu mẫu (Arduino generator) qua cổng Serial 
    và chờ nhận chuỗi phản hồi xác nhận mong muốn.
    """
    ser.reset_input_buffer()
    ser.write(command.encode("ascii") + b"\n")
    ser.flush()
    deadline = time.monotonic() + timeout_s
    received: list[str] = []
    while time.monotonic() < deadline:
        line = ser.readline().decode("ascii", errors="replace").strip()
        if not line:
            continue
        received.append(line)
        if line == expected:
            return
    transcript = ", ".join(received) if received else "no response"
    raise RuntimeError(f"generator command {command!r} failed: {transcript}")


def run_self_test(args: argparse.Namespace) -> bool:
    """
    Thực hiện quy trình tự kiểm tra lỗi phần cứng (self-test) tự động.
    """
    try:
        import serial
    except ImportError as exc:
        raise SystemExit("pyserial is required for hardware self-test") from exc

    # Tạo thư mục đầu ra nếu được cấu hình
    output_dir = Path(args.output_dir).resolve() if args.output_dir else None
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    # Khởi tạo đối tượng Logic Analyzer đo tín hiệu
    device = LogicAnalyzerDevice(args.la_port, args.la_baud)
    passed = True
    
    # Kết nối với bộ sinh tín hiệu Gray mẫu (Arduino)
    with serial.Serial(args.generator_port, args.generator_baud, timeout=0.2) as generator:
        # Nhấn reset DTR trên Arduino Uno và đợi nạp bootloader ổn định
        time.sleep(args.generator_reset_wait)
        
        # Bắt tay với Arduino generator
        _generator_command(generator, "PING", "PONG SLA8-GEN", 2.0)
        _generator_command(generator, "MODE GRAY", "OK MODE GRAY", 2.0)
        _generator_command(
            generator,
            f"GRAY RATE {args.step_rate}",
            f"OK GRAY RATE {args.step_rate}",
            2.0,
        )

        # Kết nối với Logic Analyzer cần kiểm thử
        if not device.connect():
            raise RuntimeError(device.last_error or "logic analyzer did not connect")
        try:
            if not device.set_trigger(False):
                raise RuntimeError(device.last_error or "failed to select immediate trigger")

            for mode in args.modes:
                if mode == "ISR":
                    # Đề phòng trước đó chạy DMA với tần số rất cao vượt quá khả năng của ngắt ISR,
                    # ta phải hạ tần số xuống thấp trước khi yêu cầu chuyển đổi cơ chế hoạt động.
                    transition_rate = min(args.rates)
                    if not device.set_sample_rate(transition_rate):
                        raise RuntimeError(
                            device.last_error
                            or f"failed to set ISR transition rate {transition_rate} Hz"
                        )
                # Cấu hình chế độ lấy mẫu (ISR hoặc DMA)
                if not device.set_capture_mode(mode):
                    raise RuntimeError(device.last_error or f"failed to select {mode} mode")
                    
                for rate in args.rates:
                    # Thiết lập tần số lấy mẫu kiểm thử
                    if not device.set_sample_rate(rate):
                        raise RuntimeError(device.last_error or f"failed to set {rate} Hz")
                        
                    for capture_index in range(args.captures):
                        # Thực hiện capture tín hiệu thực tế
                        frame = device.capture()
                        if not frame:
                            passed = False
                            print(
                                f"FAIL mode={mode} rate={rate} capture={capture_index + 1}: "
                                f"{device.last_error or 'no frame'}"
                            )
                            continue

                        # Xác minh dữ liệu sóng mã Gray thu thập được bằng verifier
                        report = analyze_gray_capture(
                            frame["samples"],
                            sample_rate_hz=frame["sample_rate_hz"],
                            step_rate_hz=args.step_rate,
                            rate_tolerance=args.rate_tolerance,
                            minimum_states=args.minimum_states,
                        )
                        # Đọc trạng thái STATUS chi tiết từ MCU để đối chiếu thêm
                        status = device.read_status() or {}
                        status_failures = _status_failures(status, mode)
                        request_failures = _requested_rate_failures(
                            rate,
                            frame["sample_rate_hz"],
                            args.rate_tolerance,
                        )
                        if frame["requested_sample_rate_hz"] != rate:
                            request_failures.append(
                                "frame requested-rate metadata mismatch: "
                                f"expected {rate}, got "
                                f"{frame['requested_sample_rate_hz']}"
                            )
                            
                        overrun_count = status.get("isr_overruns", "missing")
                        
                        # Điều kiện vượt qua kiểm thử:
                        # - Verifier không báo lỗi (report.passed).
                        # - Không có cờ lỗi nhị phân trong frame (flags == 0).
                        # - Không bị tràn bộ đệm (overflow_count == 0).
                        # - Không bị mất mẫu dữ liệu (dropped_samples == 0).
                        # - Không phát hiện lỗi trạng thái hoặc sai số tần số vượt ngưỡng.
                        frame_ok = (
                            report.passed
                            and frame["flags"] == 0
                            and frame["overflow_count"] == 0
                            and frame["dropped_samples"] == 0
                            and not status_failures
                            and not request_failures
                        )
                        passed = passed and frame_ok
                        verdict = "PASS" if frame_ok else "FAIL"
                        print(
                            f"{verdict} mode={mode} rate={rate} "
                            f"capture={capture_index + 1} states={report.stable_states} "
                            f"measured={report.measured_sample_rate_hz:.1f}Hz "
                            f"error={report.rate_error_fraction * 100:.2f}% "
                            f"sequence_errors={report.sequence_errors} "
                            f"short_runs={report.short_runs} "
                            f"dropped={frame['dropped_samples']} "
                            f"isr_overrun={overrun_count}"
                        )
                        
                        # In ra chi tiết các lỗi cụ thể nếu kiểm thử thất bại (FAIL)
                        for failure in report.failures:
                            print(f"  - {failure}")
                        for failure in status_failures:
                            print(f"  - {failure}")
                        for failure in request_failures:
                            print(f"  - {failure}")

                        # Xuất file nhị phân thô chứa gói tin (.sla8) để lưu vết phân tích ngoại tuyến
                        if output_dir:
                            filename = (
                                f"{mode.lower()}_{rate}_{capture_index + 1:02d}.sla8"
                            )
                            (output_dir / filename).write_bytes(frame["raw_frame"])
        finally:
            device.disconnect()
    return passed


def main(argv: list[str] | None = None) -> int:
    """
    Hàm khởi động chính xử lý các tham số dòng lệnh đầu vào.
    """
    parser = argparse.ArgumentParser(
        description="Verify SLA8 timing and all channels against the Arduino Gray-code oracle"
    )
    parser.add_argument("--la-port", default="COM12", help="Cổng COM của thiết bị Logic Analyzer")
    parser.add_argument("--generator-port", default="COM18", help="Cổng COM của Arduino phát tín hiệu mẫu")
    parser.add_argument("--la-baud", type=int, default=1_000_000, help="Baud rate kết nối Logic Analyzer")
    parser.add_argument("--generator-baud", type=int, default=115_200, help="Baud rate kết nối Arduino")
    parser.add_argument("--generator-reset-wait", type=float, default=2.0, help="Thời gian chờ reset Arduino (giây)")
    parser.add_argument("--modes", nargs="+", choices=("DMA", "ISR"), default=["DMA"], help="Chế độ đo cần test (DMA hoặc ISR)")
    parser.add_argument(
        "--rates",
        nargs="+",
        type=int,
        default=[100_000, 500_000, 1_000_000],
        help="Danh sách các tần số lấy mẫu cần test (Hz)",
    )
    parser.add_argument("--captures", type=int, default=3, help="Số lần lặp lại capture kiểm thử cho mỗi tần số")
    parser.add_argument("--step-rate", type=int, default=10_000, help="Tần số đổi trạng thái đếm của mã Gray (Hz)")
    parser.add_argument("--minimum-states", type=int, default=64, help="Số trạng thái mã Gray tối thiểu cần quét qua")
    parser.add_argument("--rate-tolerance", type=float, default=0.03, help="Tỷ lệ sai lệch tần số tối đa cho phép")
    parser.add_argument("--output-dir", help="Thư mục xuất lưu trữ file nhị phân raw dạng sóng thu được")
    args = parser.parse_args(argv)
    
    if args.captures <= 0:
        parser.error("--captures must be > 0")
    if args.minimum_states <= 0:
        parser.error("--minimum-states must be > 0")
    return 0 if run_self_test(args) else 1


if __name__ == "__main__":
    raise SystemExit(main())
