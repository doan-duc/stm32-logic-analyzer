# STM32 Logic Analyzer

Logic analyzer 8 kenh dung STM32F103C6, DMA va ung dung Python/PyQt5 de
hien thi waveform theo thoi gian thuc.

## Cau truc

```text
src/
|-- firmware/
|   |-- stm32_logic_analyzer/
|   |   `-- stm32_logic_analyzer.ino
|   `-- stm32_loc_analyzer.ino.GENERIC_F103C6TX.bin
|-- software/
|   |-- gui/
|   |-- capture.py
|   |-- device.py
|   `-- main.py
`-- main.cpp
```

## Build firmware

```powershell
platformio run
```

Nap qua FT232:

```powershell
platformio run --target upload
```

## Chay phan mem

Can Python 3 va cac thu vien:

```powershell
pip install pyqt5 pyqtgraph numpy pyserial
python src/software/main.py
```

Ket noi UART voi STM32:

- FT232 TX -> PA10
- FT232 RX -> PA9
- FT232 GND -> STM32 GND

Tin hieu can do duoc noi vao PA0 den PA7. Tat ca cac mach phai dung chung GND.
