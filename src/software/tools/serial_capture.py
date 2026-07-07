from __future__ import annotations

import argparse
import sys
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parents[1]
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from protocol_frame import HEADER_LENGTH


def _read_line(ser, timeout_s: float) -> str:
    old_timeout = ser.timeout
    ser.timeout = timeout_s
    try:
        return ser.readline().decode("ascii", errors="ignore").strip()
    finally:
        ser.timeout = old_timeout


def _send_line(ser, text: str) -> None:
    ser.write(text.encode("ascii") + b"\n")
    ser.flush()


def _read_exact(ser, length: int, timeout_s: float) -> bytes:
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


def capture_frame(port: str, output: str | Path, baud: int, rate: int, timeout_s: float) -> None:
    try:
        import serial
    except ImportError as exc:
        raise SystemExit("pyserial is required for hardware serial capture") from exc

    with serial.Serial(port, baud, timeout=1) as ser:
        ser.reset_input_buffer()
        _send_line(ser, "PING")
        if _read_line(ser, 2.0) != "PONG SLA8":
            raise SystemExit("device did not answer PING")

        _send_line(ser, f"CFG RATE {rate}")
        if not _read_line(ser, 2.0).startswith("OK"):
            raise SystemExit("rate config failed")

        _send_line(ser, "TRIG IMM")
        if not _read_line(ser, 2.0).startswith("OK"):
            raise SystemExit("trigger config failed")

        _send_line(ser, "ARM")
        if not _read_line(ser, 2.0).startswith("OK"):
            raise SystemExit("arm failed")

        deadline_line = ""
        for _ in range(max(1, int(timeout_s * 10))):
            deadline_line = _read_line(ser, 0.1)
            if deadline_line.startswith("EVENT "):
                break
        if not deadline_line.startswith("EVENT "):
            raise SystemExit("capture event timeout")

        _send_line(ser, "DUMP")
        header = _read_exact(ser, HEADER_LENGTH, 2.0)
        if header[:4] != b"SLA8":
            raise SystemExit("DUMP did not start with SLA8")
        total_samples = int.from_bytes(header[16:20], "little")
        payload = _read_exact(ser, total_samples, timeout_s)
        Path(output).write_bytes(header + payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture one SLA8 frame over firmware serial protocol")
    parser.add_argument("port")
    parser.add_argument("output")
    parser.add_argument("--baud", type=int, default=1_000_000)
    parser.add_argument("--rate", type=int, default=100_000)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)
    capture_frame(args.port, args.output, args.baud, args.rate, args.timeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
