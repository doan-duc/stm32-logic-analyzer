# STM32 Logic Analyzer 8 kênh (SLA8)

Logic Analyzer lấy mẫu đồng thời PA0..PA7 vào một byte, capture theo timer/DMA
trên STM32F103C8 và gửi frame nhị phân `SLA8` về ứng dụng Python qua USART1.

```text
src/firmware/      firmware STM32 P5 đang dùng
src/software/      driver, decoder và GUI PyQt5
tools/arduino_signal_generator/  bộ phát chuẩn để self-test
tests/              unit test Python và native C
```

`platformio.ini` chỉ còn một môi trường `c8_serial` cho STM32F103C8 nạp qua
FT232. Bản firmware cũ đã được loại khỏi cây source; khi cần đối chiếu vẫn có
thể xem lại trong lịch sử Git.

## Cổng đang nhận diện trên máy này

- `COM12`: FT232 (`VID:PID 0403:6001`) nối STM32.
- `COM18`: CH340 (`VID:PID 1A86:7523`) của Arduino Uno clone.

Không chọn các cổng Bluetooth chỉ vì chúng cũng có tên `COMx`.

## Nối dây và an toàn điện

FT232 phải dùng mức logic **3,3 V**:

```text
FT232 TX  -> STM32 PA10 (USART1 RX)
FT232 RX  -> STM32 PA9  (USART1 TX)
FT232 GND -> STM32 GND
```

Arduino generator dùng output open-drain: Arduino chỉ kéo LOW, còn STM32 kéo lên
3,3 V. Không đổi sketch thành output HIGH 5 V trực tiếp vào STM32.

```text
Arduino D2 -> STM32 PA0 / CH0
Arduino D3 -> STM32 PA1 / CH1
Arduino D4 -> STM32 PA2 / CH2
Arduino D5 -> STM32 PA3 / CH3
Arduino D6 -> STM32 PA4 / CH4
Arduino D7 -> STM32 PA5 / CH5
Arduino D8 -> STM32 PA6 / CH6
Arduino D9 -> STM32 PA7 / CH7
Arduino GND -> STM32 GND
```

Nếu dây dài hoặc cạnh lên chậm, dùng pull-up ngoài khoảng 4,7–10 kΩ lên **3,3 V**.
Không cấp nguồn song song từ FT232 nếu STM32 đã được cấp bởi nguồn khác.

## Build và nạp Arduino generator

Generator mặc định phát cả hai giao thức trong một superframe 40 ms: UART trên
D2/CH0 trước, sau đó I2C trên D3-D4/CH1-CH2. Hai burst được xếp nối tiếp để
timing từng giao thức ổn định nhưng vẫn xuất hiện trong cùng một capture.
Timer1 đồng thời phát năm sóng vuông open-drain độc lập trên các kênh còn lại:

| Arduino | LA | Tín hiệu trong `MODE BOTH` |
|---|---|---:|
| D5 | CH3 | 2 kHz |
| D6 | CH4 | 1 kHz |
| D7 | CH5 | 500 Hz |
| D8 | CH6 | 250 Hz |
| D9 | CH7 | 125 Hz |

```powershell
python -m platformio run --project-dir tools\arduino_signal_generator -e uno
python -m platformio run --project-dir tools\arduino_signal_generator -e uno `
  --target upload --upload-port COM18
```

Arduino nhận lệnh USB serial `MODE BOTH`, `MODE GRAY`, `MODE UART`, `MODE I2C`,
`STATUS` và `PING` ở 115200 baud. `MODE BOTH` dùng UART 2400 baud/I2C khoảng
20 kHz; `MODE UART` riêng chạy khoảng 57,04 kbaud và `MODE I2C` riêng chạy
SCL khoảng 98,61 kHz. Payload vẫn là UART `55 A5 4F 4B` và I2C địa chỉ
`0x50 W`, dữ liệu `A5 5A`. Hardware self-test tự chuyển generator sang
`MODE GRAY`.

## Build và nạp STM32 qua FT232

Baud bootloader là 115200; baud chạy firmware là 1.000.000. Đây là hai giai
đoạn khác nhau.

```powershell
python -m platformio run -e c8_serial
```

Trình tự nạp ROM bootloader:

1. Đóng GUI/serial monitor đang giữ `COM12`.
2. Giữ `BOOT1/PB2 = 0`, chuyển `BOOT0 = 1`, rồi nhấn RESET hoặc cấp nguồn lại.
3. Chạy:

   ```powershell
   python -m platformio run -e c8_serial `
     --target upload --upload-port COM12
   ```

4. Chuyển `BOOT0 = 0`, nhấn RESET để chạy firmware.

## Self-test định lượng Arduino → STM32 → PC

Sau khi cả hai board chạy firmware mới:

```powershell
python src\software\tools\hardware_self_test.py `
  --la-port COM12 --generator-port COM18 `
  --modes DMA --rates 100000 1000000 4000000 5818182 --captures 3 `
  --step-rate 100000 --minimum-states 32 `
  --output-dir .\captures\self-test
```

Mỗi frame được kiểm magic/version/length/checksum, chuỗi Gray tăng đúng modulo
256, transition trên đủ 8 kênh, sample rate đo từ oracle và cờ overflow/DMA/ISR.
Stress ISR riêng ở tốc độ thấp trước:

```powershell
python src\software\tools\hardware_self_test.py `
  --modes ISR --rates 100000 250000 400000 --captures 3
```

Không coi 1 MS/s ISR là đạt nếu `ISR_OVERRUNS` khác 0, dù buffer vẫn đủ số byte.

Quét tìm trần DMA và lưu toàn bộ verdict vào JSON:

```powershell
python src\software\tools\sample_rate_sweep.py `
  --la-port COM12 --generator-port COM18 --captures 5 `
  --maximum-rate 32000000
```

Kết quả HIL P5: 5.818.181 S/s PASS 10/10 với sai số tối đa 0,05%;
6,4 MS/s FAIL 10/10 vì tốc độ thực chỉ khoảng 6,23 MS/s. Arduino `MODE UART`
phát khoảng 57,04 kbaud và `MODE I2C` phát SCL khoảng 98,61 kHz; cả hai được
decoder xác nhận đúng nội dung 10/10 capture tại 5.818.181 S/s. `MODE BOTH` vẫn
giữ profile chậm 2.400 baud/I²C khoảng 20 kHz để quan sát trên cửa sổ dài.

## Capture CLI và GUI

```powershell
python src\software\tools\serial_capture.py COM12 capture.sla8 `
  --baud 1000000 --rate 100000 --timeout 10

python src\software\main.py
```

Trong GUI chọn FT232/`COM12`. UART generator nằm ở CH0; I2C dùng SCL=CH1 và
SDA=CH2. “Realtime” hiện là các capture offline lặp lại, có khoảng chết lúc DUMP
và ARM; không dùng timeline ghép qua biên frame để đo tần số liên tục.
CLI mặc định chọn DMA; `--mode AUTO` chỉ được giữ để
đọc thiết bị đã nạp firmware cũ không hỗ trợ lệnh `CFG MODE`.

Với `MODE BOTH`, capture một lần ở 100 kS/s: decode UART bằng CH0/2400 trước,
sau đó đổi Protocol sang I2C, chọn CH1/CH2 và bấm Decode lại trên cùng capture.
GUI hiện thay nội dung bảng khi đổi protocol, không hiển thị hai bảng đồng thời.

## Chạy test host

```powershell
python -m unittest discover -s tests -p "test_*.py" -v

$exe = Join-Path $env:TEMP "sla8_test_timer_plan.exe"
gcc -std=c11 -Wall -Wextra -Werror -Isrc\firmware `
  tests\native\test_timer_plan.c src\firmware\la_board.c `
  src\firmware\la_protocol.c -o $exe
& $exe

$generatorExe = Join-Path $env:TEMP "sla8_test_generator_modes.exe"
g++ -std=c++11 -Wall -Wextra -Werror `
  -Itools\arduino_signal_generator\include `
  tests\native\test_generator_modes.cpp -o $generatorExe
& $generatorExe
```

### Bằng chứng TDD/HIL cho `MODE BOTH`

- RED: native test không biên dịch vì chưa có `generator_modes.h`/`MODE_BOTH`.
- GREEN: cùng test biên dịch và chạy thành công sau khi thêm parser, routing và
  chu kỳ 40 ms cho mode kết hợp.
- RED/GREEN auxiliary: test ban đầu thiếu routing 5 kênh, sau đó khóa Timer1
  4 kstep/s và năm bộ chia nhị phân ở đúng tần số danh nghĩa.
- HIL: 5/5 capture DMA tại 100 kS/s tìm thấy ba frame UART đúng và 3–4
  transaction I2C đúng mỗi capture; CH3..CH7 đo đúng 2k/1k/500/250/125 Hz,
  duty xấp xỉ 50%, mọi nửa chu kỳ trong ±2 mẫu và `DMA_ERRORS=0`.
- Chưa có công cụ coverage cho sketch AVR; native test kiểm mode/parser, còn
  build PlatformIO và HIL kiểm đường chạy thực trên Arduino/STM32.
