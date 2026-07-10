from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SOFTWARE_DIR = Path(__file__).resolve().parents[1] / "src" / "software"
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from device import LogicAnalyzerDevice  # noqa: E402
from protocol_frame import (  # noqa: E402
    HEADER_CHECKSUM_OFFSET,
    HEADER_LENGTH,
    checksum32,
    encode_frame,
)


class FakeSerial:
    def __init__(self, lines: list[bytes], binary: bytes):
        self.timeout = 1.0
        self._lines = list(lines)
        self._binary = bytearray(binary)
        self.read_requests: list[int] = []
        self.commands: list[bytes] = []

    def reset_input_buffer(self):
        pass

    def write(self, data: bytes):
        self.commands.append(data)
        return len(data)

    def flush(self):
        pass

    def readline(self):
        return self._lines.pop(0) if self._lines else b""

    def read(self, length: int):
        self.read_requests.append(length)
        if not self._binary:
            return b""
        chunk = self._binary[:length]
        del self._binary[:length]
        return bytes(chunk)


class DeviceFrameSafetyTests(unittest.TestCase):
    def test_oversized_length_is_rejected_before_payload_read(self):
        frame = bytearray(encode_frame(b"\x00", 100_000))
        header = frame[:HEADER_LENGTH]
        header[16:20] = (1_000).to_bytes(4, "little")
        header[HEADER_CHECKSUM_OFFSET : HEADER_CHECKSUM_OFFSET + 4] = checksum32(
            header[:HEADER_CHECKSUM_OFFSET]
        ).to_bytes(4, "little")

        fake = FakeSerial(
            lines=[b"OK ARMED\n", b"EVENT COMPLETE\n"],
            binary=bytes(header),
        )
        device = LogicAnalyzerDevice("COM_TEST")
        device.serial = fake
        device.device_info = {"buffer_size": 64}

        self.assertIsNone(device.capture(timeout=0.1))
        self.assertEqual(fake.read_requests, [HEADER_LENGTH])
        self.assertIn("sample count exceeds", device.last_error)

    def test_terminal_firmware_error_does_not_attempt_dump(self):
        fake = FakeSerial(
            lines=[b"OK ARMED\n", b"EVENT ERROR\n"],
            binary=b"",
        )
        device = LogicAnalyzerDevice("COM_TEST")
        device.serial = fake

        self.assertIsNone(device.capture(timeout=0.1))
        self.assertEqual(fake.read_requests, [])
        self.assertNotIn(b"DUMP\n", fake.commands)
        self.assertEqual(device.last_error, "Firmware capture ended in ERROR")


class PortDiscoveryTests(unittest.TestCase):
    @patch("device.serial.tools.list_ports.comports")
    def test_port_details_include_usb_identity(self, comports):
        comports.return_value = [
            SimpleNamespace(
                device="COM12",
                description="USB Serial Port",
                vid=0x0403,
                pid=0x6001,
                serial_number="A5069RR4A",
            )
        ]

        details = LogicAnalyzerDevice.list_port_details()

        self.assertEqual(
            details,
            [
                {
                    "device": "COM12",
                    "description": "USB Serial Port",
                    "vid": 0x0403,
                    "pid": 0x6001,
                    "serial_number": "A5069RR4A",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
