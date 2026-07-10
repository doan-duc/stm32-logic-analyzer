from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DecodedEvent:
    time_us: float
    protocol: str
    event: str
    value: str
    note: str = ""


def _bit(sample: int, channel: int) -> int:
    return (sample >> channel) & 0x01


def decode_uart(samples: bytes, sample_rate_hz: int, rx_channel: int, baudrate: int):
    events = []
    if sample_rate_hz <= 0 or baudrate <= 0 or not samples:
        return events

    samples_per_bit = sample_rate_hz / baudrate
    if samples_per_bit < 3.0:
        events.append(
            DecodedEvent(
                0.0,
                "UART",
                "WARN",
                "sample rate qua thap",
                f"{sample_rate_hz} Hz / {baudrate} baud",
            )
        )

    i = 0
    # The last sample used below is the stop-bit midpoint at 9.5 bit periods.
    frame_span = round(samples_per_bit * 9.5)
    idle_span = max(1, int(samples_per_bit * 2.0))
    while i + frame_span < len(samples):
        cur_bit = _bit(samples[i], rx_channel)
        start_edge = False
        if i == 0:
            start_edge = cur_bit == 0
        else:
            prev_bit = _bit(samples[i - 1], rx_channel)
            start_edge = prev_bit == 1 and cur_bit == 0

        if start_edge:
            start_index = i
            idle_start = start_index - idle_span
            if idle_start >= 0 and any(
                _bit(sample, rx_channel) == 0
                for sample in samples[idle_start:start_index]
            ):
                i += 1
                continue
            start_mid = round(start_index + 0.5 * samples_per_bit)
            if _bit(samples[start_mid], rx_channel) != 0:
                i += 1
                continue
            events.append(
                DecodedEvent(
                    start_index * 1_000_000.0 / sample_rate_hz,
                    "UART",
                    "START",
                    "0",
                    "line low",
                )
            )
            value = 0
            raw_bits = []
            for bit_index in range(8):
                sample_index = round(start_index + (1.5 + bit_index) * samples_per_bit)
                bit_value = _bit(samples[sample_index], rx_channel)
                raw_bits.append(bit_value)
                value |= bit_value << bit_index

            stop_index = round(start_index + 9.5 * samples_per_bit)
            stop_bit = _bit(samples[stop_index], rx_channel)
            char = chr(value) if 32 <= value <= 126 else "."
            note = "8N1"
            if stop_bit != 1:
                note = "framing error"
            events.append(
                DecodedEvent(
                    start_index * 1_000_000.0 / sample_rate_hz,
                    "UART",
                    "BYTE",
                    f"0x{value:02X} '{char}'",
                    note,
                )
            )
            events.append(
                DecodedEvent(
                    stop_index * 1_000_000.0 / sample_rate_hz,
                    "UART",
                    "STOP",
                    str(stop_bit),
                    "ok" if stop_bit == 1 else "framing error",
                )
            )
            i = stop_index + max(1, int(samples_per_bit * 0.5))
        else:
            i += 1

    return events


def decode_i2c(samples: bytes, sample_rate_hz: int, scl_channel: int, sda_channel: int):
    events = []
    if sample_rate_hz <= 0 or not samples:
        return events

    bits = []
    byte_index = 0
    in_frame = False

    def time_us(index):
        return index * 1_000_000.0 / sample_rate_hz

    for i in range(1, len(samples)):
        prev_scl = _bit(samples[i - 1], scl_channel)
        cur_scl = _bit(samples[i], scl_channel)
        prev_sda = _bit(samples[i - 1], sda_channel)
        cur_sda = _bit(samples[i], sda_channel)

        if prev_scl == 1 and cur_scl == 1 and prev_sda == 1 and cur_sda == 0:
            in_frame = True
            bits = []
            byte_index = 0
            events.append(DecodedEvent(time_us(i), "I2C", "START", "", ""))
            continue

        if (
            in_frame
            and prev_scl == 1
            and cur_scl == 1
            and prev_sda == 0
            and cur_sda == 1
        ):
            events.append(DecodedEvent(time_us(i), "I2C", "STOP", "", ""))
            in_frame = False
            bits = []
            continue

        if in_frame and prev_scl == 0 and cur_scl == 1:
            bits.append(cur_sda)
            if len(bits) == 9:
                data_bits = bits[:8]
                ack_bit = bits[8]
                value = 0
                for bit_value in data_bits:
                    value = (value << 1) | bit_value
                ack_text = "ACK" if ack_bit == 0 else "NACK"
                if byte_index == 0:
                    addr = value >> 1
                    rw = "R" if (value & 1) else "W"
                    events.append(
                        DecodedEvent(
                            time_us(i),
                            "I2C",
                            "ADDR",
                            f"0x{addr:02X} {rw}",
                            ack_text,
                        )
                    )
                else:
                    events.append(
                        DecodedEvent(
                            time_us(i),
                            "I2C",
                            "DATA",
                            f"0x{value:02X}",
                            ack_text,
                        )
                    )
                byte_index += 1
                bits = []

    return events


def decode_spi(
    samples: bytes,
    sample_rate_hz: int,
    sck_channel: int,
    mosi_channel: int,
    miso_channel: int,
    cs_channel: int = -1,
):
    events = []
    if sample_rate_hz <= 0 or not samples:
        return events

    def time_us(index):
        return index * 1_000_000.0 / sample_rate_hz

    uses_cs = 0 <= cs_channel < 8
    in_frame = False
    bits_mosi = []
    bits_miso = []
    byte_index = 0

    for i in range(1, len(samples)):
        prev_sck = _bit(samples[i - 1], sck_channel)
        cur_sck = _bit(samples[i], sck_channel)
        prev_cs = _bit(samples[i - 1], cs_channel) if uses_cs else 0
        cur_cs = _bit(samples[i], cs_channel) if uses_cs else 0

        if not in_frame and (not uses_cs or (prev_cs == 1 and cur_cs == 0)):
            if uses_cs:
                in_frame = True
                bits_mosi = []
                bits_miso = []
                byte_index = 0
                events.append(
                    DecodedEvent(
                        time_us(i),
                        "SPI",
                        "CS",
                        "LOW",
                        "frame start",
                    )
                )
            elif prev_sck == 0 and cur_sck == 1:
                in_frame = True
                bits_mosi = []
                bits_miso = []
                byte_index = 0
                events.append(
                    DecodedEvent(
                        time_us(i),
                        "SPI",
                        "FRAME",
                        "START",
                        "no CS",
                    )
                )

        if not in_frame:
            continue

        if uses_cs and prev_cs == 0 and cur_cs == 1:
            if bits_mosi or bits_miso:
                events.append(
                    DecodedEvent(
                        time_us(i),
                        "SPI",
                        "WARN",
                        "INCOMPLETE",
                        "frame ended early",
                    )
                )
            events.append(
                DecodedEvent(
                    time_us(i),
                    "SPI",
                    "CS",
                    "HIGH",
                    "frame end",
                )
            )
            in_frame = False
            bits_mosi = []
            bits_miso = []
            continue

        if prev_sck == 0 and cur_sck == 1:
            bits_mosi.append(_bit(samples[i], mosi_channel))
            bits_miso.append(_bit(samples[i], miso_channel))
            if len(bits_mosi) == 8:
                mosi_value = 0
                miso_value = 0
                for bit in range(8):
                    mosi_value = (mosi_value << 1) | bits_mosi[bit]
                    miso_value = (miso_value << 1) | bits_miso[bit]
                events.append(
                    DecodedEvent(
                        time_us(i),
                        "SPI",
                        "BYTE",
                        f"MOSI=0x{mosi_value:02X} MISO=0x{miso_value:02X}",
                        f"byte {byte_index}",
                    )
                )
                bits_mosi = []
                bits_miso = []
                byte_index += 1

    return events
