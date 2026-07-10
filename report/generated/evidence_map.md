# Evidence Map - Topic 1

Updated: 2026-07-10

| Report claim | Evidence file | Evidence detail |
|---|---|---|
| Topic 1 is a simple logic analyzer design task. | `report/BTL Hệ thống nhúng và thiết kế giao tiếp nhúng 2025.2.pdf` | Assignment PDF lists Topic 1 as "Thiết kế và xây dựng thiết bị logic analyzer đơn giản". |
| Topic 1 requires at least 2 input channels, at least 1 kHz sampling and waveform display. | `report/BTL Hệ thống nhúng và thiết kế giao tiếp nhúng 2025.2.pdf` | Topic 1 requirement section states minimum channel count, sampling rate and display requirement. |
| Timing analysis, protocol decoding and input protection are expected or encouraged. | `report/BTL Hệ thống nhúng và thiết kế giao tiếp nhúng 2025.2.pdf` | Common requirements mention timing discussion, UART/I2C/SPI decoding and protection circuitry. |
| The implemented system has firmware and PC software parts. | `README.md` | README describes firmware and PC software usage. |
| The firmware samples 8 channels on PA0..PA7. | `README.md`; `src/firmware/board_config.h` | README and macros `LA_CH0_PIN`..`LA_CH7_PIN` identify PA0..PA7 as logic inputs. |
| PC communication uses UART PA9/PA10 at 1,000,000 baud. | `README.md`; `src/firmware/board_config.h` | UART pin and baud macros define PA9/PA10 and 1,000,000 baud. |
| Default sample rate is 100 kHz and verified DMA maximum is 1 MHz. | `src/firmware/board_config.h`; `src/firmware/la_board.h`; `src/firmware/README.md` | The configuration and HIL record define 100 kS/s default, DMA up to 1 MS/s and ISR up to 400 kS/s. |
| The firmware uses TIM2 and calculates actual sampling rate/error ppm. | `src/firmware/main.cpp`; `src/firmware/board_config.h` | `calculateTimerPlan()` and TIM2 configuration macros support this claim. |
| GPIO samples are read from one GPIOA input data register access. | `src/firmware/board_config.h` | `la_board_read_gpio_snapshot_8ch_fast()` reads `LA_INPUT_PORT->IDR`. |
| The SLA8 data frame has a 48-byte header and bit-packed payload. | `src/firmware/la_protocol.h`; `src/software/protocol_frame.py` | Constants and encoder/decoder fields define the protocol frame. |
| Firmware supports immediate, edge and pattern trigger modes. | `src/firmware/main.cpp`; `src/firmware/la_capture.h` | Commands `TRIG IMM`, `TRIG RISE/FALL/ANY` and `TRIG PAT` are implemented. |
| PC GUI supports sample-rate options from 1 kHz to 1 MHz. | `src/software/gui/main_window.py` | `RATE_OPTIONS` includes 1,000 through 1,000,000 samples per second. |
| PC software displays waveforms and decodes UART/I2C. | `src/software/gui/waveform_view.py`; `src/software/decoders.py`; `src/software/gui/main_window.py` | Waveform view and `decode_uart()`, `decode_i2c()` are present. |
| A CLI capture utility is available. | `src/software/tools/serial_capture.py` | The tool sends PING, CFG RATE, TRIG IMM, ARM and DUMP commands. |
| An Arduino UNO based test-signal source is available. | `tools/arduino_signal_generator/src/arduino_signal_generator.ino`; `tools/arduino_signal_generator/include/generator_modes.h` | The sketch provides Gray-code, isolated UART/I2C modes, combined UART-then-I2C traffic and five divided auxiliary clocks on CH3..CH7. |
| DMA and ISR performance were measured end-to-end on hardware. | `src/firmware/README.md`; `src/software/tools/hardware_self_test.py`; `src/software/signal_verifier.py` | Gray-code HIL passed DMA at 100/500/1000 kS/s and ISR at 400 kS/s without sequence, checksum, overflow or overrun errors. |
| Schematic, capture screenshots and board logs were not found. | Repository scan excluding `.git`, `.pio`, `generated` | No hardware schematic, `.sla8` capture, screenshot or demo log file was found. |
