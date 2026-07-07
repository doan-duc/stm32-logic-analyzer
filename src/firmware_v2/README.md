# Firmware v2

Firmware v2 duoc copy tu `src/firmware/` de toi uu capture tren STM32F103C8 ma khong sua firmware goc.

## Build

```powershell
python -m platformio run -e c8_v2_serial
python -m platformio run -e c8_v2_stlink
```

Nap qua UART bootloader:

```powershell
python -m platformio run -e c8_v2_serial --target upload --upload-port COM12
```

Nap qua ST-Link:

```powershell
python -m platformio run -e c8_v2_stlink --target upload
```

## Thay doi da lam

- B1: `TIM2_IRQHandler` va hot path ISR dat trong `.RamFunc`; cac ham lay mau nhanh duoc ep inline.
- B2/B3: v2 build voi `-O2`, `-flto`, `-ffunction-sections`, `-fdata-sections`, `-Wl,--gc-sections`.
- B4: timer IRQ priority 0, DMA IRQ priority 1, UART IRQ priority 2; khong tat SysTick.
- C1: v2 chi build `main.cpp`, `la_board.c`, `la_capture.c`, `la_protocol.c`, `la_benchmark.c`.
- A2: buffer chon theo RAM board, mac dinh F103C8 la 14080 mau; co the override bang `-DLA_CAPTURE_BUFFER_SAMPLES=...`.
- A1a: them DMA one-shot cho `TRIG IMM` bang `TIM2_UP -> DMA1 Channel2`, du lieu vao buffer `uint8_t`.

## Che do capture

Mac dinh:

```text
CFG MODE ISR
```

Bat DMA one-shot:

```text
CFG MODE DMA
TRIG IMM
ARM
```

DMA hien chi ho tro `TRIG IMM`. Edge, pattern, pre-trigger va cac trigger khac van fallback bang ISR de giu dung du lieu.

## Lenh tu bao cao

- `INFO`: in firmware version, buffer, RAM estimate, mode DMA/ISR.
- `STATUS`: in state, sample count, trigger index, overflow, dropped, engine dang dung, `STACK_FREE_EST`.
- `BENCH`: in timing estimate va so chu ky ISR neu build bat DWT benchmark.

## Da verify bang build

- `c8_v2_serial`, `c8_v2_stlink`: build OK.
- Env cu `genericSTM32F103C8_release`, `genericSTM32F103C8_serial`,
  `genericSTM32F103C8_stlink`, `genericSTM32F103C8_debug`: build OK.
- Env cu `bluepill_f103c6_serial`, `bluepill_f103c6_stlink`: build OK,
  nhung RAM rat sat nen can do stack tren board.
- Env cu `nucleo_f401re`, `blackpill_f401cc`, `blackpill_f411ce`: build OK.
- Host test: repo hien khong co test suite de chay.
- `.RamFunc` nam trong RAM, `TIM2_IRQHandler` o `.RamFunc`.
- `DMA1_Channel2_IRQHandler` la symbol manh, khong roi ve `Default_Handler`.
- Dead code `la_buffer.c`, `la_trigger.c`, `la_uart_tx.c` khong vao object build v2.

## Can do tren board

- Do jitter ISR va DMA bang tin hieu ngoai/on-board.
- Do max sample rate DMA that, khong suy dien tu build.
- Chay `STATUS` sau capture de xem `STACK_FREE_EST` va `DMA_ERRORS`.
- Test frame `DUMP` voi `CFG MODE DMA`, `TRIG IMM`, nhieu sample rate khac nhau.
- Test lai ISR edge/pattern de xac nhan fallback khong bi lech.
