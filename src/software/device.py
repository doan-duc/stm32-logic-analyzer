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


MAX_SAFE_FRAME_SAMPLES = 1_000_000


class LogicAnalyzerDevice:
    """Driver PC cho firmware SLA8 offline-capture."""

    def __init__(self, port=None, baudrate=1_000_000):
        self.port = port
        self.baudrate = baudrate
        self.serial = None
        self.device_info = None
        self.last_error = None
        self.current_sample_rate_hz = 100_000
        self.trigger_enabled = False
        self.current_capture_mode = None

    @staticmethod
    def list_ports():
        return [detail["device"] for detail in LogicAnalyzerDevice.list_port_details()]

    @staticmethod
    def list_port_details():
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
        try:
            self.serial = serial.Serial(self.port, self.baudrate, timeout=1)
            time.sleep(0.1)
            self.serial.reset_input_buffer()
            self._send_line("STOP")
            stop_deadline = time.monotonic() + 0.3
            while time.monotonic() < stop_deadline:
                self._read_line(0.05)

            self.serial.reset_input_buffer()
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
                saw_legacy_tail = True
            elif line == "END INFO":
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
        ok = self._expect_ok(command)
        if ok:
            self.trigger_enabled = bool(enabled)
        return ok

    def set_capture_mode(self, mode):
        normalized = str(mode).strip().upper()
        if normalized not in {"ISR", "DMA"}:
            raise ValueError("capture mode must be ISR or DMA")
        ok = self._expect_ok(f"CFG MODE {normalized}")
        if ok:
            self.current_capture_mode = normalized
        return ok

    def read_status(self, timeout_s=1.0):
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
        buffer_size = 8192
        if self.device_info:
            buffer_size = int(self.device_info.get("buffer_size") or buffer_size)
        # Edge/pattern firmware waits up to 8 buffers for a trigger, then still
        # needs the configured post-trigger window. Immediate capture needs one.
        capture_buffers = 9 if self.trigger_enabled else 1
        capture_s = capture_buffers * buffer_size / max(1, self.current_sample_rate_hz)
        return max(3.0, capture_s + 2.0)

    def capture(self, timeout=None):
        if not self.serial:
            return None

        try:
            self.last_error = None
            if timeout is None:
                timeout = self._capture_timeout_s()
            self.serial.reset_input_buffer()
            self._send_line("ARM")
            arm_response = self._read_line(2.0)
            if not arm_response.startswith("OK"):
                self.last_error = arm_response or "ARM did not respond"
                return None

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

            self._send_line("DUMP")
            header = self._read_exact(HEADER_LENGTH, 2.0)
            configured_limit = MAX_SAFE_FRAME_SAMPLES
            if self.device_info:
                configured_limit = int(
                    self.device_info.get("buffer_size") or configured_limit
                )
            frame_header = decode_frame_header(
                header,
                max_samples=min(configured_limit, MAX_SAFE_FRAME_SAMPLES),
            )
            total_samples = frame_header.total_samples
            payload = self._read_exact(total_samples, timeout)
            raw_frame = header + payload
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
        self.last_error = "Firmware hien tai chi ho tro offline capture"
        return False

    def stop_stream(self, drain=True):
        return []
