from __future__ import annotations

import sys
import unittest
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parents[1] / "src" / "software"
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from protocol_frame import (  # noqa: E402
    HEADER_CHECKSUM_OFFSET,
    HEADER_LENGTH,
    FrameError,
    decode_frame,
    decode_frame_header,
    encode_frame,
)


class FrameHeaderTests(unittest.TestCase):
    def test_valid_header_is_safe_to_size_payload_read(self):
        encoded = encode_frame(bytes(range(32)), 100_000)

        header = decode_frame_header(encoded[:HEADER_LENGTH], max_samples=64)

        self.assertEqual(header.total_samples, 32)
        self.assertEqual(header.actual_sample_rate_hz, 100_000)

    def test_corrupt_header_is_rejected_before_payload_length_is_trusted(self):
        encoded = bytearray(encode_frame(b"\x01\x02", 100_000))
        encoded[16:20] = (0x7FFFFFFF).to_bytes(4, "little")

        with self.assertRaisesRegex(FrameError, "header checksum"):
            decode_frame_header(encoded[:HEADER_LENGTH], max_samples=1_000_000)

    def test_valid_but_oversized_header_is_rejected(self):
        encoded = encode_frame(bytes(range(32)), 100_000)

        with self.assertRaisesRegex(FrameError, "sample count exceeds"):
            decode_frame_header(encoded[:HEADER_LENGTH], max_samples=16)

    def test_payload_corruption_is_rejected(self):
        encoded = bytearray(encode_frame(b"\x55\xAA", 100_000))
        encoded[-1] ^= 0x01

        with self.assertRaisesRegex(FrameError, "payload checksum"):
            decode_frame(encoded)

    def test_header_checksum_field_is_not_in_its_own_checksum(self):
        encoded = encode_frame(b"\x00", 100_000)

        self.assertNotEqual(
            encoded[HEADER_CHECKSUM_OFFSET : HEADER_CHECKSUM_OFFSET + 4],
            b"\x00\x00\x00\x00",
        )


if __name__ == "__main__":
    unittest.main()
