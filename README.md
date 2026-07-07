# STM32 Logic Analyzer 8 kenh

Project da tach ro hai phan:

```text
src/
|-- firmware/   # code PlatformIO nap len STM32
`-- software/   # ung dung Python/PyQt5 hien thi waveform
```

Firmware lay mau 8 kenh PA0..PA7 bang timer, moi sample la mot `uint8_t`.
PC giao tiep qua UART PA9/PA10 va nhan frame nhi phan `SLA8` sau khi capture.

## Build va nap firmware

```powershell
cd D:\BTL_HTN
python -m platformio run -e genericSTM32F103C8_serial
python -m platformio run -e genericSTM32F103C8_serial --target upload --upload-port COM12
```

Nap bang USB-TTL can `BOOT0 = 1`, reset de vao bootloader. Nap xong chuyen
`BOOT0 = 0` va reset de chay firmware.

## Chay giao dien

```powershell
cd D:\BTL_HTN
python src\software\main.py
```

Trong app: chon `COM12`, bam `Connect`, chon `Offline` de capture tung frame hoac `Realtime` de app tu capture lap va cap nhat waveform. Chon sample rate roi bam `Capture` hoac `Start Realtime`.

## Test capture bang CLI

```powershell
cd D:\BTL_HTN
python src\software\tools\serial_capture.py COM12 capture.sla8 --baud 1000000 --rate 100000 --timeout 10
```

## Day noi mac dinh

```text
USB-TTL TX -> STM32 PA10
USB-TTL RX -> STM32 PA9
USB-TTL GND -> STM32 GND

CH0..CH7 -> STM32 PA0..PA7
```

Neu dung HC-05 de tao UART test:

```text
HC-05 TXD -> STM32 PA0
HC-05 GND -> STM32 GND
HC-05 VCC -> nguon dung theo module cua ban
```

Chi dua tin hieu logic 3.3 V vao PA0..PA7, khong noi truc tiep 5 V/cao ap vao GPIO.
