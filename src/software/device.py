from __future__ import annotations

import time

import serial
import serial.tools.list_ports

from protocol_frame import HEADER_LENGTH, FrameError, decode_frame


class LogicAnalyzerDevice:
    """Driver PC cho firmware SLA8 offline-capture."""

    def __init__(self, port=None, baudrate=1_000_000):
        self.port = port
        self.baudrate = baudrate
        self.serial = None
        self.device_info = None
        self.last_error = None
        self.current_sample_rate_hz = 100_000

    @staticmethod
    def list_ports():
        return [port.device for port in serial.tools.list_ports.comports()]

    def connect(self):
        try:
            self.serial = serial.Serial(self.port, self.baudrate, timeout=1)
            time.sleep(0.1)
            self.serial.reset_input_buffer()
            self._send_line("STOP")
            self._read_line(0.2)

            self._send_line("PING")
            if self._read_line(2.0) != "PONG SLA8":
                self.disconnect()
                return False

            self.device_info = self._read_info()
            return self.device_info is not None
        except Exception:
            if self.serial:
                self.serial.close()
                self.serial = None
            raise

    def disconnect(self):
        if self.serial:
            try:
                self._send_line("STOP")
            except Exception:
                pass
            self.serial.close()
            self.serial = None

    def _send_line(self, text):
        self.serial.write(text.encode("ascii") + b"\n")
        self.serial.flush()

    def _read_line(self, timeout_s):
        old_timeout = self.serial.timeout
        self.serial.timeout = timeout_s
        try:
            return self.serial.readline().decode("ascii", errors="ignore").strip()
        finally:
            self.serial.timeout = old_timeout

    def _read_exact(self, length, timeout_s):
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
        self.serial.reset_input_buffer()
        self._send_line("INFO")
        deadline = time.time() + 2.0
        info = {
            "type": "info",
            "device_name": "SLA8",
            "version": "unknown",
            "channels": 8,
            "buffer_size": 0,
            "max_rate": 0,
        }

        while time.time() < deadline:
            line = self._read_line(0.1)
            if not line:
                continue
            if line.startswith("INFO "):
                info["version"] = line.split(" ", 1)[1]
            elif line.startswith("CHANNELS "):
                info["channels"] = int(line.split(" ", 1)[1])
            elif line.startswith("BUFFER "):
                info["buffer_size"] = int(line.split(" ", 1)[1])
            elif line.startswith("MAX_TARGET_RATE "):
                info["max_rate"] = int(line.split(" ", 1)[1])
            elif line.startswith("HARDWARE_MAX_RATE "):
                break

        return info if info["buffer_size"] else None

    def _expect_ok(self, command, timeout_s=2.0):
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
        sample_rate_hz = int(sample_rate_hz)
        ok = self._expect_ok(f"CFG RATE {sample_rate_hz}")
        if ok:
            self.current_sample_rate_hz = sample_rate_hz
        return ok

    def set_trigger(self, enabled):
        command = "TRIG FALL 0" if enabled else "TRIG IMM"
        return self._expect_ok(command)

    def _capture_timeout_s(self):
        buffer_size = 8192
        if self.device_info:
            buffer_size = int(self.device_info.get("buffer_size") or buffer_size)
        capture_s = buffer_size / max(1, self.current_sample_rate_hz)
        return max(3.0, capture_s + 2.0)

    def capture(self, timeout=None):
        if not self.serial:
            return None

        try:
            if timeout is None:
                timeout = self._capture_timeout_s()
            self.serial.reset_input_buffer()
            self._send_line("ARM")
            if not self._read_line(2.0).startswith("OK"):
                return None

            event = ""
            deadline = time.time() + timeout
            while time.time() < deadline:
                event = self._read_line(0.1)
                if event.startswith("EVENT "):
                    break
            if not event.startswith("EVENT "):
                self.last_error = "Capture event timeout"
                return None
            if event == "EVENT NO_TRIGGER":
                return {"type": "trigger_timeout"}

            self._send_line("DUMP")
            header = self._read_exact(HEADER_LENGTH, 2.0)
            total_samples = int.from_bytes(header[16:20], "little")
            payload = self._read_exact(total_samples, timeout)
            frame = decode_frame(header + payload)
            sample_period_ns = int(1_000_000_000 / frame.actual_sample_rate_hz)

            return {
                "type": "capture",
                "samples": frame.samples,
                "sample_period_ns": sample_period_ns,
                "sample_count": len(frame.samples),
                "sample_rate_hz": frame.actual_sample_rate_hz,
                "trigger_index": frame.trigger_index,
                "overflow_count": frame.overflow_count,
                "dropped_samples": frame.dropped_samples,
            }
        except (TimeoutError, FrameError, serial.SerialException) as exc:
            self.last_error = str(exc)
            return None

    def start_stream(self):
        self.last_error = "Firmware hien tai chi ho tro offline capture"
        return False

    def stop_stream(self, drain=True):
        return []
