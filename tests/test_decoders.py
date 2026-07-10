from __future__ import annotations

import sys
import unittest
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parents[1] / "src" / "software"
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from decoders import decode_i2c, decode_spi, decode_uart  # noqa: E402


def uart_frame(value: int, samples_per_bit: int = 10) -> bytes:
    bits = [1, 1, 0]
    bits.extend((value >> bit) & 1 for bit in range(8))
    bits.append(1)
    return bytes(bit for bit in bits for _ in range(samples_per_bit))


def spi_frame(
    mosi: int,
    miso: int,
    samples_per_half: int = 3,
    *,
    sck_channel: int = 0,
    mosi_channel: int = 1,
    miso_channel: int = 2,
    cs_channel: int = 3,
) -> bytes:
    # CPOL=0, CPHA=0
    samples = []

    def append_state(sck: int, mosi_bit: int, miso_bit: int, cs_bit: int):
        value = ((sck << sck_channel) | (mosi_bit << mosi_channel) |
                 (miso_bit << miso_channel) | (cs_bit << cs_channel))
        samples.append(value & 0xFF)

    append_state(0, 1, 1, 1)
    append_state(0, 1, 1, 0)

    for mask in (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01):
        mosi_bit = 1 if (mosi & mask) else 0
        miso_bit = 1 if (miso & mask) else 0
        for _ in range(samples_per_half):
            append_state(0, mosi_bit, miso_bit, 0)
        for _ in range(samples_per_half):
            append_state(1, mosi_bit, miso_bit, 0)
        for _ in range(samples_per_half):
            append_state(0, mosi_bit, miso_bit, 0)

    append_state(0, 1, 1, 1)
    return bytes(samples)


class UartBoundaryTests(unittest.TestCase):
    def test_complete_frame_at_end_of_capture_is_decoded(self):
        samples = uart_frame(0x55)

        events = decode_uart(samples, 100_000, rx_channel=0, baudrate=10_000)

        byte_events = [event for event in events if event.event == "BYTE"]
        self.assertEqual([event.value for event in byte_events], ["0x55 'U'"])


class I2cEdgeQualificationTests(unittest.TestCase):
    def test_sda_and_scl_changing_in_same_sample_is_not_start(self):
        # CH0=SCL, CH1=SDA: (SCL=0,SDA=1) -> (SCL=1,SDA=0).
        samples = bytes([0b10, 0b01])

        events = decode_i2c(samples, 100_000, scl_channel=0, sda_channel=1)

        self.assertEqual(events, [])

    def test_stop_without_an_active_frame_is_ignored(self):
        # SCL remains high while SDA rises, but no START preceded it.
        samples = bytes([0b01, 0b11])

        events = decode_i2c(samples, 100_000, scl_channel=0, sda_channel=1)

        self.assertEqual(events, [])


class SpiDecodeTests(unittest.TestCase):
    def test_decodes_full_duplex_spi_byte(self):
        samples = spi_frame(0x55, 0xA5)
        events = decode_spi(samples, 100_000, 0, 1, 2, 3)
        byte_events = [event for event in events if event.event == "BYTE"]
        self.assertEqual(byte_events[0].value, "MOSI=0x55 MISO=0xA5")

    def test_rejects_undersampled_spi_instead_of_emitting_corrupt_byte(self):
        samples = spi_frame(0x55, 0xA5, samples_per_half=1)

        events = decode_spi(samples, 100_000, 0, 1, 2, 3)

        byte_events = [event for event in events if event.event == "BYTE"]
        warnings = [event for event in events if event.event == "WARN"]
        self.assertEqual(byte_events, [])
        self.assertEqual(warnings[0].value, "UNDERSAMPLED")

    def test_discards_buffered_bytes_when_frame_ends_incomplete(self):
        complete_byte = spi_frame(0x55, 0xA5, samples_per_half=3)
        # Add one trailing clock bit before deasserting CS.
        samples = complete_byte[:-1] + bytes([0] * 3 + [1] * 3 + [0] * 3 + [8])

        events = decode_spi(samples, 100_000, 0, 1, 2, 3)

        byte_events = [event for event in events if event.event == "BYTE"]
        warnings = [event for event in events if event.event == "WARN"]
        self.assertEqual(byte_events, [])
        self.assertEqual(warnings[-1].value, "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
