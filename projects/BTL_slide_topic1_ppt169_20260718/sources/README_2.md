# Firmware STM32 P5

Day la firmware duy nhat cua Logic Analyzer STM32F103C8. Ban P3A1 cu da duoc
loai khoi cay source sau khi P4A4 vuot qua kiem thu HIL; lich su cu van con trong Git.

## Build

```powershell
python -m platformio run -e c8_serial
```

Nap qua UART bootloader:

```powershell
python -m platformio run -e c8_serial --target upload --upload-port COM12
```

## Thay doi da lam

- B1: `TIM2_IRQHandler` va hot path ISR dat trong `.RamFunc`; cac ham lay mau nhanh duoc ep inline.
- B2/B3: build voi `-O2`, `-flto`, `-ffunction-sections`, `-fdata-sections`, `-Wl,--gc-sections`.
- B4: timer IRQ priority 0, DMA IRQ priority 1, UART IRQ priority 2; khong tat SysTick.
- C1: chi build `main.cpp`, `la_board.c`, `la_capture.c`, `la_protocol.c`, `la_benchmark.c`.
- A2: buffer chon theo RAM board, mac dinh F103C8 la 13888 mau de giu hon 4 KiB runtime reserve ca khi goi `STATUS`; co the override bang `-DLA_CAPTURE_BUFFER_SAMPLES=...`.
- A1a: them DMA one-shot cho `TRIG IMM` bang `TIM2_UP -> DMA1 Channel2`, du lieu vao buffer `uint8_t`.
- P4: timer clock lay tu PCLK1/APB runtime (generic F103 hien chay 64 MHz, khong hardcode 72 MHz).
- P4: DMA doc GPIO IDR theo word va cat byte thap vao buffer; them `ISR_OVERRUNS`, `END INFO`, `END STATUS`.
- P4: DMA la mode mac dinh cho immediate; edge/pattern van fallback ISR.
- P4A3: HIL Gray-code xac nhan DMA 1 MS/s va ISR 400 kS/s; firmware chan rate vuot tran engine.
- P4A4: parser command chi nhan so u32 decimal/hex hop le toan chuoi, chan overflow/hau to rac va pattern ngoai 8 bit.

## Che do capture

Mac dinh:

```text
CFG MODE DMA
TRIG IMM
```

Chuyen sang ISR khi can benchmark thu cong:

```text
CFG MODE ISR
ARM
```

DMA hien chi ho tro `TRIG IMM`. Edge, pattern, pre-trigger va cac trigger khac
fallback bang ISR. Ket qua HIL xac nhan DMA toi 5.818181 MS/s va ISR toi 400 kS/s;
firmware tu choi cau hinh vuot tran cua engine thuc te.

## Lenh tu bao cao

- `INFO`: in firmware version, buffer, RAM estimate, mode DMA/ISR.
- `STATUS`: in state, sample count, trigger index, overflow, dropped, engine dang dung, `STACK_FREE_EST`.
- `BENCH`: in timing estimate va so chu ky ISR neu build bat DWT benchmark.

## Da verify

- `c8_serial`: build va nap qua FT232/COM12 OK.
- Host/native test: xem `tests/` va lenh trong README goc.
- `.RamFunc` nam trong RAM, `TIM2_IRQHandler` o `.RamFunc`.
- `DMA1_Channel2_IRQHandler` la symbol manh, khong roi ve `Default_Handler`.

## HIL tren STM32F103C8 + Arduino Uno

Ngay 2026-07-10, oracle Gray-code 8 bit 10 kstep/s duoc noi D2..D9 -> PA0..PA7:

- RED P3A1: frame ghi 100000 S/s nhung oracle do 88919 S/s (-11.08%); nguyen nhan generic board chay TIM2 64 MHz trong khi code hardcode 72 MHz.
- GREEN DMA: 9/9 frame tai 100k, 500k, 1M khong sai sequence/checksum, khong glitch, overflow, dropped hay DMA error; sai so oracle <= 0.09%.
- ISR sweep: 100k..400k sach; 450k co khoang 1275 `ISR_OVERRUNS`/frame; 500k chi con khoang 437k hieu dung; 750k..1M bao hoa quanh 444k.
- P4A3: DMA 100k/500k/1M va ISR 100k/250k/400k PASS; MODE ISR tu choi 450k bang `ERR BAD_RATE`; `STACK_FREE_EST=4208` byte.
- P4A4 sau BOOT0=0/reset: DMA 100k/500k/1M va ISR 400k PASS; sai so oracle toi da 0.04%, parser tu choi rate co hau to rac va pattern ngoai 8 bit.

Raw frame co the luu lai bang `src/software/tools/hardware_self_test.py --output-dir ...`.

## Gioi han da xac nhan

- DMA + `TRIG IMM`: toi da 5.818181 MS/s (10/10 frame Gray PASS, sai so <= 0.05%).
- 6.4 MS/s bi chan vi HIL do chi 6.23 MS/s (sai so khoang 2.6%); 8 MS/s
  va cao hon bao hoa quanh 6.30 MS/s.
- ISR va trigger edge/pattern: toi da 400 kS/s.
- Chay `STATUS` sau capture de kiem tra `STACK_FREE_EST`, `DMA_ERRORS` va
  `ISR_OVERRUNS` neu thay doi firmware.
