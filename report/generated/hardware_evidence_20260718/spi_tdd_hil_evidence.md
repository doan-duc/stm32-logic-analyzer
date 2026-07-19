# SPI open-drain TDD/HIL evidence

- RED: native generator test failed because `GENERATOR_SPI_OPEN_DRAIN` was undefined.
- GREEN: SPI output was changed from push-pull to open-drain; the same native test compiled and passed.
- Build/upload: PlatformIO built 5100 bytes of AVR flash and verified the upload on COM18.
- HIL: `spi_probe_500ksps.sla8` contains 13,888 samples at 500 kS/s, flags=0, overflow=0, dropped=0.
- Decode: CS LOW; MOSI/MISO 55/A5, A5/3C, 5A/C3; CS HIGH on CH3–CH6.
- GUI: `gui_05_spi_decode_ch3_ch6.png` was captured from the PyQt application using the HIL frame above.
- Regression: 70 Python tests and the native generator test passed.

No AVR line-coverage tool is configured; the native safety test, PlatformIO build, verified upload, and physical HIL capture cover the changed path.
