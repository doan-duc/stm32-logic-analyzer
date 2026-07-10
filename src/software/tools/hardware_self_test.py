from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parents[1]
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from device import LogicAnalyzerDevice
from signal_verifier import analyze_gray_capture


def _status_failures(status: dict | None, mode: str) -> list[str]:
    if not status:
        return ["STATUS response missing or unparseable"]

    failures: list[str] = []
    if "isr_overruns" not in status:
        failures.append("STATUS is missing ISR_OVERRUNS")
    elif int(status["isr_overruns"]) != 0:
        failures.append(f"ISR_OVERRUNS={status['isr_overruns']}")

    if "dma_errors" not in status:
        failures.append("STATUS is missing DMA_ERRORS")
    elif int(status["dma_errors"]) != 0:
        failures.append(f"DMA_ERRORS={status['dma_errors']}")

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
    try:
        import serial
    except ImportError as exc:
        raise SystemExit("pyserial is required for hardware self-test") from exc

    output_dir = Path(args.output_dir).resolve() if args.output_dir else None
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    device = LogicAnalyzerDevice(args.la_port, args.la_baud)
    passed = True
    with serial.Serial(args.generator_port, args.generator_baud, timeout=0.2) as generator:
        # Opening an Uno's USB serial normally resets it through DTR.
        time.sleep(args.generator_reset_wait)
        _generator_command(generator, "PING", "PONG SLA8-GEN", 2.0)
        _generator_command(generator, "MODE GRAY", "OK MODE GRAY", 2.0)
        _generator_command(
            generator,
            f"GRAY RATE {args.step_rate}",
            f"OK GRAY RATE {args.step_rate}",
            2.0,
        )

        if not device.connect():
            raise RuntimeError(device.last_error or "logic analyzer did not connect")
        try:
            if not device.set_trigger(False):
                raise RuntimeError(device.last_error or "failed to select immediate trigger")

            for mode in args.modes:
                if mode == "ISR":
                    # A previous DMA run may have left the device above ISR max.
                    # Lower the rate before asking firmware to switch engines.
                    transition_rate = min(args.rates)
                    if not device.set_sample_rate(transition_rate):
                        raise RuntimeError(
                            device.last_error
                            or f"failed to set ISR transition rate {transition_rate} Hz"
                        )
                if not device.set_capture_mode(mode):
                    raise RuntimeError(device.last_error or f"failed to select {mode} mode")
                for rate in args.rates:
                    if not device.set_sample_rate(rate):
                        raise RuntimeError(device.last_error or f"failed to set {rate} Hz")
                    for capture_index in range(args.captures):
                        frame = device.capture()
                        if not frame:
                            passed = False
                            print(
                                f"FAIL mode={mode} rate={rate} capture={capture_index + 1}: "
                                f"{device.last_error or 'no frame'}"
                            )
                            continue

                        report = analyze_gray_capture(
                            frame["samples"],
                            sample_rate_hz=frame["sample_rate_hz"],
                            step_rate_hz=args.step_rate,
                            rate_tolerance=args.rate_tolerance,
                            minimum_states=args.minimum_states,
                        )
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
                        for failure in report.failures:
                            print(f"  - {failure}")
                        for failure in status_failures:
                            print(f"  - {failure}")
                        for failure in request_failures:
                            print(f"  - {failure}")

                        if output_dir:
                            filename = (
                                f"{mode.lower()}_{rate}_{capture_index + 1:02d}.sla8"
                            )
                            (output_dir / filename).write_bytes(frame["raw_frame"])
        finally:
            device.disconnect()
    return passed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify SLA8 timing and all channels against the Arduino Gray-code oracle"
    )
    parser.add_argument("--la-port", default="COM12")
    parser.add_argument("--generator-port", default="COM18")
    parser.add_argument("--la-baud", type=int, default=1_000_000)
    parser.add_argument("--generator-baud", type=int, default=115_200)
    parser.add_argument("--generator-reset-wait", type=float, default=2.0)
    parser.add_argument("--modes", nargs="+", choices=("DMA", "ISR"), default=["DMA"])
    parser.add_argument(
        "--rates",
        nargs="+",
        type=int,
        default=[100_000, 500_000, 1_000_000],
    )
    parser.add_argument("--captures", type=int, default=3)
    parser.add_argument("--step-rate", type=int, default=10_000)
    parser.add_argument("--minimum-states", type=int, default=64)
    parser.add_argument("--rate-tolerance", type=float, default=0.03)
    parser.add_argument("--output-dir")
    args = parser.parse_args(argv)
    if args.captures <= 0:
        parser.error("--captures must be > 0")
    if args.minimum_states <= 0:
        parser.error("--minimum-states must be > 0")
    return 0 if run_self_test(args) else 1


if __name__ == "__main__":
    raise SystemExit(main())
