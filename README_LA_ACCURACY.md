# Phân tích độ chính xác và giới hạn lấy mẫu của Logic Analyzer

> Tài liệu được tổng hợp từ source, test và artifact hiện có trong repository. Hiện không có board để tạo phép đo HIL mới; các giới hạn vật lý chưa đo được đều được ghi rõ.

## Kết luận chính

Có năm kết luận cần tách bạch:

1. **Không có tần số nào giúp chế độ Realtime hiện tại thu liên tục 100% tín hiệu theo thời gian.** Realtime chỉ là lặp lại chu trình `ARM → capture → DUMP → vẽ`, không phải streaming. Luôn tồn tại khoảng mù trong lúc truyền dữ liệu về PC.

2. Nếu “visual hết” có nghĩa là **mỗi lần cập nhật nhìn thấy ít nhất một superframe hoàn chỉnh của `MODE BOTH`, gồm UART + I2C + SPI**, thì sau khi sửa lỗi bộ phát Arduino:

   $$
   80\,\text{kS/s}\le f_s\le127.339\,\text{kS/s}
   $$

   Trong danh sách tần số hiện có của GUI, **100 kS/s là lựa chọn duy nhất thỏa mãn**.

3. Ở `100 kS/s`, một frame chứa đủ các giao thức, nhưng Realtime chỉ quan sát tối đa khoảng **49,91% thời gian**, thực tế còn thấp hơn. Ở yêu cầu `5 MHz`, tần số thực là `5,142857 MHz`; mỗi frame chỉ dài `2,700 ms` và duty-cycle tối đa chỉ **1,90%**. Nó cho độ phân giải thời gian rất tốt nhưng bỏ qua khoảng **98,1% thời gian thực**.

4. **Xung đột Timer1 aux với SPI trong `MODE BOTH` đã được sửa ở source hiện tại** bằng cách không khởi động auxiliary timer trong mode này. Native regression test và Arduino build đã pass; tuy nhiên vẫn cần HIL mới khi có board trước khi chứng nhận đường tín hiệu vật lý.

5. **6 MHz không phải là trần tối đa của STM32 trong dự án.** Đây là điểm có sai số lượng tử divider bằng 0 theo $72\,\text{MHz}/12$ và đã PASS 3/3 frame HIL lưu trong repo. Trần DMA cao nhất đã bám đúng là $72\,\text{MHz}/11=6.545454\,\text{MS/s}$; bản tổng hợp HIL ghi mức kế tiếp $72\,\text{MHz}/10=7.2\,\text{MS/s}$ đã hụt tốc độ nên không đạt. “Chính xác” ở đây nghĩa là **không phát hiện lỗi trong các phép thử đã lưu**, không phải chứng nhận sai số tuyệt đối bằng thiết bị chuẩn.

---

## 1. Hai loại “tần số” đang bị trộn lẫn

Tần số chọn trên LA là **sample rate**, đơn vị đúng nên là sample/s:

$$
f_s=\text{số lần đọc 8 kênh trong một giây}
$$

Nó không thay đổi tần số Arduino phát.

Trong `MODE BOTH`, Arduino đang cố định các tham số tại [generator_modes.h](tools/arduino_signal_generator/include/generator_modes.h#L40):

- UART: $T_b=416\,\mu s$, tương đương

  $$
  b=\frac{1}{416\ \mu s}=2403.846\ \text{baud}
  $$

- I2C: một nửa chu kỳ SCL là $25\,\mu s$, nên

  $$
  f_{\mathrm{SCL}}=\frac{1}{2\times25\ \mu s}=20\,\text{kHz}
  $$

- SPI: nửa chu kỳ SCK cũng là $25\,\mu s$, nên

  $$
  f_{\mathrm{SCK}}=20\,\text{kHz}
  $$

- Một superframe được lập lịch khoảng mỗi $40\,ms$, tức $25$ superframe/s.

Lệnh `GRAY RATE` chỉ thay đổi mode Gray, không thay đổi các tốc độ trên của `MODE BOTH`.

---

## 2. Tần số lấy mẫu thực tế của STM32

Đối với timer STM32:

$$
f_s=
\frac{f_{\mathrm{TIM}}}
{(PSC+1)(ARR+1)}
$$

Đây là công thức timer tiêu chuẩn trong [STM32F1 Reference Manual](https://www.st.com/resource/en/reference_manual/cd00171190.pdf), và được triển khai tại [la_board.c](src/firmware/la_board.c#L31).

STM32F103C8 hỗ trợ tối đa 72 MHz và có 20 KiB SRAM theo [trang sản phẩm chính thức của ST](https://www.st.com/en/microcontrollers-microprocessors/stm32f103c8.html). Source hiện tại ưu tiên cấu hình TIM2 ở 72 MHz.

### Yêu cầu 100 kS/s

$$
D=\frac{72\,000\,000}{100\,000}=720
$$

Do đó:

$$
f_{s,\mathrm{actual}}=\frac{72\,000\,000}{720}
=100\,000\ \text{S/s}
$$

Sai số lượng tử bộ chia so với yêu cầu:

$$
\varepsilon_{\mathrm{divider}}=0
$$

Chu kỳ lấy mẫu:

$$
T_s=\frac1{f_s}=10\,\mu s
$$

### Yêu cầu 5 MHz

$$
D=\operatorname{round}\left(\frac{72\,000\,000}{5\,000\,000}\right)
=\operatorname{round}(14.4)=14
$$

Do đó:

$$
f_{s,\mathrm{actual}}
=\left\lfloor\frac{72\,000\,000}{14}\right\rfloor
=5\,142\,857\ \text{S/s}
$$

Sai lệch so với yêu cầu:

$$
\varepsilon
=\frac{5\,142\,857-5\,000\,000}{5\,000\,000}
=2.85714\%
=28\,571\ \text{ppm}
$$

Chu kỳ lấy mẫu thực:

$$
T_s=\frac1{5\,142\,857}
=0.194444\ \mu s
$$

GUI dùng `actual_sample_rate_hz` trong frame chứ không dùng mù quáng giá trị yêu cầu, xem [device.py](src/software/device.py#L367). Vì vậy trục thời gian được hiệu chỉnh theo `5,142857 MHz`, không bị gắn nhầm thành đúng `5 MHz`.

Nếu board rơi vào nhánh clock dự phòng 64 MHz thì con số sẽ khác. Không có board hiện tại nên không thể xác nhận nhánh clock vật lý; các artifact 5 MHz đã lưu cho thấy trường hợp 72 MHz.

---

## 3. Vì sao dự án đo được 6 MHz, và trần thật sự là bao nhiêu?

### 3.1. Trước hết phải phân biệt bốn đại lượng

Các báo cáo cũ dễ làm người đọc hiểu “đo được 6 MHz” thành “6 MHz là giới hạn tuyệt đối”. Thực ra cần tách bốn đại lượng:

1. $f_{s,\mathrm{req}}$: tần số phần mềm yêu cầu;
2. $f_{s,\mathrm{timer}}$: tần số TIM2 thực sự lập trình được sau khi lượng tử hóa bộ chia nguyên;
3. $\widehat f_s$: tần số hiệu dụng suy ra từ tín hiệu Gray chuẩn đã capture;
4. $f_{s,\mathrm{verified}}$: mức cao nhất mà **mọi lần lặp bắt buộc** đều thỏa các tiêu chí toàn vẹn.

Vì vậy, có hai câu hỏi độc lập:

- **Timer có tạo đúng 6 triệu yêu cầu DMA mỗi giây không?** Có thể trả lời bằng clock và công thức bộ chia.
- **Toàn bộ đường dữ liệu có phục vụ kịp 6 triệu yêu cầu mỗi giây không?** Chỉ công thức không đủ; phải kiểm tra HIL bằng dữ liệu đã biết trước.

### 3.2. Suy ra 6 MHz từ clock 72 MHz

Source cấu hình ưu tiên thạch anh ngoài HSE 8 MHz và PLL nhân 9, do đó:

$$
f_{\mathrm{SYSCLK}}=8\,\text{MHz}\times9=72\,\text{MHz}
$$

APB1 được chia 2 nên $f_{\mathrm{PCLK1}}=36\,\text{MHz}$. Theo quy tắc clock timer của STM32F1, khi prescaler APB khác 1 thì clock timer bằng hai lần clock ngoại vi:

$$
f_{\mathrm{TIM2}}=2f_{\mathrm{PCLK1}}
=2\times36\,\text{MHz}
=72\,\text{MHz}
$$

Đúng quy tắc này được code tại [hàm đọc clock TIM2](src/firmware/main.cpp#L225) và nhánh HSE được cấu hình tại [SystemClock_Config](src/firmware/main.cpp#L1095). Quan trọng hơn, phiên đo HIL ngày 2026-07-18 đã lưu kết quả lệnh `INFO` là `TIMER_CLOCK 72000000`, xem [báo cáo HIL 72 MHz](report/generated/hil_72mhz_summary.md#L1). Đây là bằng chứng cho board ở lần đo đã chạy nhánh HSE, không chỉ là suy đoán từ source.

Tần số update của timer là công thức chuẩn:

$$
f_{s,\mathrm{timer}}
=\frac{f_{\mathrm{TIM2}}}{(PSC+1)(ARR+1)}
=\frac{f_{\mathrm{TIM2}}}{D}
$$

với

$$
D=(PSC+1)(ARR+1)\in\mathbb{N}^{+}
$$

Firmware chọn số tick gần nhất bằng:

$$
D_{\mathrm{round}}
=\left\lfloor
\frac{f_{\mathrm{TIM2}}+f_{s,\mathrm{req}}/2}
{f_{s,\mathrm{req}}}
\right\rfloor
\approx\operatorname{round}\left(
\frac{f_{\mathrm{TIM2}}}{f_{s,\mathrm{req}}}
\right)
$$

rồi phân rã $D$ thành `PSC` và `ARR`, đúng với [thuật toán trong `la_board.c`](src/firmware/la_board.c#L31).

Với yêu cầu 6 MHz:

$$
D=\operatorname{round}\left(\frac{72\,000\,000}{6\,000\,000}\right)=12
$$

Ở vùng tốc độ cao, firmware dùng:

$$
PSC=0,\qquad ARR=11
$$

nên:

$$
f_{s,\mathrm{timer}}
=\frac{72\,000\,000}{(0+1)(11+1)}
=6\,000\,000\ \text{S/s}
$$

Sai số lượng tử bộ chia so với yêu cầu 6 MHz là:

$$
\varepsilon_{\mathrm{divider}}
=\frac{6\,000\,000-6\,000\,000}{6\,000\,000}
\times10^6
=0\ \text{ppm}
$$

Chu kỳ lấy mẫu và cửa sổ một frame là:

$$
T_s=\frac1{6\,000\,000}=166.6667\,\text{ns}
$$

$$
W=\frac{13\,888}{6\,000\,000}
=2.3146667\,\text{ms}
$$

Một chi tiết giải thích đúng lịch sử báo cáo: mức cũ trên clock 64 MHz là 5.818.182 S/s. Khi giữ nguyên **giá trị yêu cầu cũ** nhưng board đã chuyển sang timer 72 MHz, firmware tính:

$$
D=\operatorname{round}\left(
\frac{72\,000\,000}{5\,818\,182}
\right)
=\operatorname{round}(12.375)=12
$$

và vì thế rate thực nhảy thành:

$$
f_{s,\mathrm{timer}}=\frac{72\,000\,000}{12}
=6\,000\,000\ \text{S/s}
$$

Sai lệch so với chính yêu cầu 5.818.182 S/s là:

$$
\varepsilon
=\frac{6\,000\,000-5\,818\,182}{5\,818\,182}
\times100\%
\approx3.125\%
$$

Đây là dòng `5.818.182 → 6.000.000, ERROR_PPM 31249` trong [bảng HIL](report/generated/hil_72mhz_summary.md#L7). Nghĩa là con số 6 MHz ban đầu xuất hiện một phần vì điểm sweep cũ được lượng tử hóa lại dưới clock 72 MHz; nó không chứng minh 6 MHz là trần.

Đây là lý do toán học 6 MHz là một điểm “đẹp”: 72 MHz chia hết cho 6 MHz. Nhưng **phép chia đúng mới chỉ chứng minh timer được lập trình đúng**, chưa chứng minh DMA và bus kịp chuyển đủ dữ liệu.

### 3.3. Vì sao code dùng DMA có thể đạt 6 MHz còn ISR thì không?

Ngân sách chu kỳ CPU cho mỗi mẫu là:

$$
C_{\mathrm{budget}}=\frac{f_{\mathrm{CPU}}}{f_s}
$$

Tại 72 MHz CPU và 6 MS/s:

$$
C_{\mathrm{budget},6M}=\frac{72}{6}=12
\quad\text{chu kỳ/mẫu}
$$

Source ước tính đường ngắt trực tiếp cần ít nhất 28 chu kỳ và đường ngắt an toàn cần 42 chu kỳ, xem [các hằng timing budget](src/firmware/la_capture.h#L21). Nếu CPU phải chạy một ISR cho từng mẫu thì biên chu kỳ là:

$$
M_{\mathrm{direct}}=12-28=-16
$$

$$
M_{\mathrm{safe}}=12-42=-30
$$

Cả hai đều âm. Vì thế không thể giải thích 6 MHz bằng việc “CPU đủ nhanh để xử lý 6 triệu ISR/s”. Code đạt mức này vì đường capture tức thời dùng phần cứng:

```text
TIM2 update
    → DMA request
    → DMA1 Channel 2 đọc một word GPIOA->IDR
    → ghi byte thấp chứa PA0…PA7 vào captureStorage[i]
    → tăng địa chỉ RAM, giảm CNDTR
    → đủ N mẫu mới ngắt báo hoàn tất
```

Cấu hình này có thể đối chiếu trực tiếp tại [startDmaCaptureOneShot](src/firmware/main.cpp#L448): nguồn là `GPIOA->IDR`, đích là buffer, `CNDTR` bằng số mẫu, DMA priority `Very High`, nguồn đọc 32 bit và đích lưu từng byte. Như vậy:

- CPU chỉ cấu hình trước capture và xử lý khi DMA hoàn tất, không phục vụ từng mẫu;
- cả 8 kênh PA0…PA7 được chụp trong cùng một lần đọc cổng;
- mỗi mẫu lưu đúng 1 byte, nên tốc độ payload vào RAM tại 6 MHz là

  $$
  R_{\mathrm{RAM}}=f_s\times1\,\text{byte}
  =6\,\text{MB/s}
  $$

- mỗi DMA request cách nhau 12 chu kỳ timer tại 6 MHz.

DMA không làm bus nhanh vô hạn: mỗi request vẫn phải đọc ngoại vi và ghi RAM. Bởi vậy công thức clock chỉ cho các **ứng viên**; giới hạn cuối cùng phải tìm bằng sweep. Không thể lấy $72\,\text{MHz}$ rồi kết luận STM32 sẽ lưu được 72 MS/s.

### 3.4. Cách thí nghiệm trong dự án tìm giới hạn

Quy trình đã lưu trong repo nằm ở [sample_rate_sweep.py](src/software/tools/sample_rate_sweep.py#L34), [sample_rate_benchmark.py](src/software/sample_rate_benchmark.py#L29) và [signal_verifier.py](src/software/signal_verifier.py#L76). Có thể diễn giải theo bảy bước:

1. Từ $f_{\mathrm{TIM2}}$, sinh các mức ứng viên theo bộ chia nguyên $D$: $72\,\text{MHz}/D$.
2. Ra lệnh Arduino phát bộ đếm Gray 8 bit với tốc độ bước $f_G=100\,\text{kHz}$.
3. Cấu hình STM32 ở `DMA` và trigger `IMMEDIATE`.
4. Capture đủ $N=13\,888$ mẫu nhiều lần tại từng mức ứng viên.
5. Kiểm tra header, checksum, metadata, `flags`, `overflow`, `dropped` và trạng thái DMA/ISR.
6. Phân tích dữ liệu Gray để kiểm tra thứ tự trạng thái, glitch, hoạt động của đủ 8 kênh và ước lượng lại $\widehat f_s$.
7. Chỉ nhận một mức là ổn định khi mọi lần lặp bắt buộc đều PASS; mức ổn định cao nhất trước mức FAIL là trần đã kiểm chứng.

Lưu ý khi tái lập: script sweep hiện vẫn để mặc định legacy `--timer-clock 64000000`, còn danh sách divider tự sinh trong script benchmark không chứa 11 và 12. Vì vậy một lần đo lại trên HSE phải truyền rõ `--timer-clock 72000000` và các rate cần thử qua `--rates`; các mức lớn hơn 6.545.454 S/s còn cần bản firmware benchmark mở khóa. Không được chạy toàn bộ giá trị mặc định rồi coi đó là phép lặp lại phiên HIL 72 MHz.

Tốc độ Gray 100 kHz cũng không được tạo bằng vòng `delay`. Arduino dùng Timer1 CTC với clock danh định 16 MHz, prescaler 8 và tại 100 kHz có:

$$
N_G=\frac{16\,000\,000}{8\times100\,000}=20
$$

$$
OCR1A=N_G-1=19
$$

$$
f_G=\frac{16\,000\,000}{8(OCR1A+1)}
=100\,000\ \text{state/s}
$$

Cách lập kế hoạch timer nằm tại [generator_gray_timer_plan](tools/arduino_signal_generator/include/generator_modes.h#L137) và cấu hình CTC tại [start_gray_timer](tools/arduino_signal_generator/src/arduino_signal_generator.ino#L117). Như vậy $f_G$ có sai số divider bằng 0 so với clock danh định 16 MHz, nhưng độ chính xác vật lý của thạch anh Arduino vẫn chưa được hiệu chuẩn ngoài.

#### Vì sao dùng Gray code?

Mã Gray của số đếm $n$ là:

$$
G(n)=n\oplus(n\gg1)
$$

Hai trạng thái kế tiếp chỉ đổi một bit:

$$
d_H\bigl(G(n),G(n+1)\bigr)=1
$$

Sau khi run-length encode luồng mẫu thành các cặp $(g_i,n_i)$, verifier đổi $g_i$ về số nhị phân $b_i$ và đếm lỗi tuần tự:

$$
E_{\mathrm{seq}}
=\sum_i
\mathbf{1}\left[
(b_i-b_{i-1})\bmod256\ne1
\right]
$$

Nếu lỗi tạo ra bước nhảy, đảo thứ tự hoặc một run ngắn ở giữa frame, các tiêu chí này thường sẽ phát hiện. Tuy nhiên Gray 8 bit không có “mã cấm”; lỗi trùng đúng state kỳ vọng hoặc chỉ đổi độ dài run vẫn có thể lọt, nên đây không phải chứng minh tuyệt đối không lỗi. Mỗi kênh cũng bắt buộc phải có ít nhất một cạnh trong frame.

#### Vì sao ở tốc độ cao phải tăng Gray từ 10 kHz lên 100 kHz?

Số mẫu kỳ vọng trong một trạng thái Gray là:

$$
q=\frac{f_s}{f_G}
$$

Tần số lấy mẫu được ước lượng ngược từ độ dài trung bình các run ổn định, bỏ run đầu và cuối vì chúng có thể bị cắt giữa chừng:

$$
\widehat f_s
=f_G\,\overline{n_i}
$$

Verifier chỉ coi một run là trạng thái ổn định nếu:

$$
n_i\ge n_{\min}
=\max\left(2,\left\lfloor0.30q\right\rfloor\right)
$$

và tính sai lệch tốc độ:

$$
\varepsilon_G
=\frac{\left|\widehat f_s-f_{s,\mathrm{metadata}}\right|}
{f_{s,\mathrm{metadata}}}
$$

Mặc định hiện tại của sweep yêu cầu ít nhất 32 state và $\varepsilon_G\le3\%$; các frame 6 và 6,545454 MHz thực tế tốt hơn ngưỡng này rất nhiều.

Tại 6 MHz và $f_G=100\,\text{kHz}$:

$$
q_{6M}=\frac{6\,000\,000}{100\,000}=60
\quad\text{mẫu/trạng thái}
$$

Tại trần $72/11$ MHz:

$$
q_{\max}
=\frac{72\,000\,000/11}{100\,000}
=65.454545
\quad\text{mẫu/trạng thái}
$$

Số trạng thái có thể quan sát trong một frame xấp xỉ:

$$
S\approx Wf_G=\frac{Nf_G}{f_s}
$$

Do đó:

$$
S_{6M}\approx\frac{13\,888\times100\,000}{6\,000\,000}
=231.47
$$

$$
S_{\max}\approx
\frac{13\,888\times100\,000}{72\,000\,000/11}
=212.18
$$

Log thực tế ghi 232 trạng thái tại 6 MHz và 212–213 trạng thái tại 6,545454 MHz, đúng với dự đoán. Nếu vẫn để Gray 10 kHz tại trần thì:

$$
S_{10k}\approx21.22<32
$$

không đạt ngưỡng tối thiểu 32 trạng thái của sweep và các bit cao có thể chưa kịp đổi. Đây chính là ý trong báo cáo cũ và đoạn hội thoại đã paste: sample rate tăng làm cửa sổ $W=N/f_s$ ngắn đi, nên phải tăng tốc tín hiệu **kiểm chuẩn** để trong frame vẫn có đủ sự kiện đánh giá. Nó không có nghĩa STM32 tự lấy mẫu nhanh hơn nhờ Arduino phát nhanh hơn.

### 3.5. Kết quả đo đã lưu và cách suy ra trần

Log kết quả verifier còn lưu tại [hil_dma_high.log](report/generated/hardware_evidence_20260718/hil_dma_high.log#L7), đồng thời payload gốc còn ở [các frame SLA8](report/generated/hardware_evidence_20260718/dma_high_frames/), cho kết quả:

| Mức timer | Lần đo | $\widehat f_s$ từ Gray | Sai lệch so với metadata | Gray |
|---:|---:|---:|---:|---|
| 6.000.000 S/s | 1 | 6.000.434,8 Hz | +0,00725% | 232 state, 0 sequence error, 0 short run |
| 6.000.000 S/s | 2 | 6.000.434,8 Hz | +0,00725% | 232 state, 0 sequence error, 0 short run |
| 6.000.000 S/s | 3 | 6.000.000,0 Hz | 0,00000% | 232 state, 0 sequence error, 0 short run |
| 6.545.454 S/s | 1 | 6.542.381,0 Hz | −0,04695% | 212 state, 0 sequence error, 0 short run |
| 6.545.454 S/s | 2 | 6.547.142,9 Hz | +0,02580% | 212 state, 0 sequence error, 0 short run |
| 6.545.454 S/s | 3 | 6.544.075,8 Hz | −0,02106% | 213 state, 0 sequence error, 0 short run |

Vì vậy:

- 6 MHz PASS 3/3, sai lệch Gray lớn nhất quan sát được chỉ khoảng $0.00725\%$;
- 6,545454 MHz cũng PASS 3/3, sai lệch tuyệt đối lớn nhất quan sát được khoảng $0.04695\%$;
- mọi dòng trên đều ghi `dropped=0` và `isr_overrun=0`.

Một artifact TC-04 riêng còn ghi tại [metrics.json](report/generated/la_testsuite_20260718/metrics.json#L206): 13.888 mẫu, `flags=0`, `overflow=0`, `dropped=0`, 213 trạng thái, $\widehat f_s=6\,545\,971.6$ Hz, sai lệch $0.0079\%$ và số cạnh CH0…CH7 lần lượt là $[106,53,27,13,7,3,2,1]$. Cả 8 kênh vì thế đều được quan sát có chuyển mức. Đây là một capture khác nhưng vẫn dùng cùng oracle Gray và verifier, nên là bằng chứng lặp lại chứ không phải một chuẩn đo hoàn toàn độc lập.

Các sai lệch rất nhỏ trong bảng còn chịu lượng tử hóa của chính phép ước lượng run-length. Với $M$ run nội bộ được lấy trung bình, thay đổi tổng cộng một mẫu làm kết quả đổi theo bước:

$$
\Delta\widehat f_s=\frac{f_G}{M}
$$

Ví dụ frame 6 MHz có 232 state, sau khi bỏ state đầu/cuối còn $M=230$:

$$
\Delta\widehat f_s
=\frac{100\,000}{230}
=434.78\ \text{Hz}
$$

$$
\frac{434.78}{6\,000\,000}\times100\%
=0.007246\%
$$

Đây đúng bằng độ lệch 434,8 Hz ở hai dòng đầu. Vì vậy phần chênh nhỏ này có thể chỉ là một mẫu phân bổ khác giữa các run, không nên diễn giải thẳng thành clock STM32 đã trôi đúng 434,8 Hz.

Trần theo bộ chia kế tiếp được suy ra như sau:

| $D$ | Rate lập trình | Rate Gray đo được | Kết luận |
|---:|---:|---:|---|
| 12 | $72/12=6.000$ MS/s | $\approx6.000$ MS/s | PASS |
| 11 | $72/11=6.545454$ MS/s | $\approx6.5455$ MS/s | **PASS cao nhất** |
| 10 | $72/10=7.200$ MS/s | $\approx6.647$ MS/s | hụt khoảng 7,7%, FAIL |
| 9 | $72/9=8.000$ MS/s | $\approx6.785$ MS/s | hụt khoảng 15,2%, bão hòa |
| 8 | $72/8=9.000$ MS/s | $\approx6.810$ MS/s | hụt khoảng 24,3%, bão hòa |

Các điểm trên 6,545454 MHz cần firmware benchmark tạm thời mở khóa giới hạn và hiện chỉ được bảo tồn trong [bản tổng hợp HIL](report/generated/hil_72mhz_summary.md#L44); repo không còn một raw ledger riêng cho sweep mở khóa này. Tuy nhiên, kết luận PASS tại 6,545454 MHz có cả log ba lần lặp, các frame gốc và artifact TC-04 riêng nêu trên.

Bản tổng hợp HIL báo cáo rằng khi yêu cầu 7,2 MHz, timer vẫn phát update mỗi 10 tick nhưng tốc độ hiệu dụng suy ra từ Gray chỉ khoảng 6,647 MS/s. Kết quả đó phù hợp với giả thuyết đường DMA/bus đã bão hòa; khi ấy `actual_sample_rate_hz` tính từ timer không còn đại diện cho số mẫu vật lý ghi được mỗi giây. Vì raw ledger của các điểm vượt trần không còn trong repo, đây là **kết luận từ báo cáo tổng hợp**, không có mức truy vết bằng chứng ngang với các frame 6 và 6,545454 MHz.

Hai dòng trong chính báo cáo HIL cũng phản ánh thứ tự thí nghiệm: phần sweep ban đầu chỉ nói “đã quan sát sạch tới khoảng 6 MS/s”, sau đó mục benchmark mở khóa mới nâng kết luận lên 6,545454 MS/s. Hai câu không mâu thuẫn; 6 MHz là mức cao nhất của sweep đầu, còn 6,545454 MHz là trần được tìm thấy ở sweep bổ sung.

Source sản phẩm hiện chặn đúng tại 6.545.454 S/s ở [`la_board.h`](src/firmware/la_board.h#L21) và native test xác nhận nhận mức này nhưng từ chối 6.545.455 S/s tại [`test_timer_plan.c`](tests/native/test_timer_plan.c#L39). Tuy nhiên chuỗi chẩn đoán `HARDWARE_MAX_RATE DMA_5818181_ISR_400000` trong [`main.cpp`](src/firmware/main.cpp#L604) vẫn là giá trị legacy 64 MHz. Khi đọc repo hiện tại, nên lấy giới hạn từ validation thực tế và `la_board.h`, không lấy chuỗi cũ đó làm trần HSE.

Còn một kiểm tra chéo rất mạnh từ dữ liệu 64 MHz cũ. [Ledger refined 64 MHz](report/generated/sample_rate_benchmark_refined.json#L1) ghi:

- $64/11=5.818181$ MS/s PASS 10/10;
- $64/10=6.4$ MS/s FAIL 10/10, chỉ đo được khoảng 6,23 MS/s.

Sau khi clock tăng từ 64 lên 72 MHz, biên sạch vẫn nằm tại $D=11$:

$$
\frac{6.545454}{5.818181}\approx1.125
$$

$$
\frac{72}{64}=1.125
$$

Hai tỉ số trùng nhau. Điều này củng cố rằng giới hạn dịch chuyển theo clock của đường timer/DMA/bus, chứ 6 MHz không phải một con số được chọn tùy ý.

### 3.6. “Giữ được độ chính xác, không bị sai số” chính xác đến mức nào?

Cần tách bốn loại độ chính xác.

#### A. Độ chính xác tần số timer

Nếu clock vật lý là $f_{\mathrm{TIM,true}}=72\,\text{MHz}(1+\delta_{\mathrm{clk}})$ thì tại $D=12$:

$$
f_{s,\mathrm{true}}
=\frac{72\,\text{MHz}(1+\delta_{\mathrm{clk}})}{12}
=6\,\text{MHz}(1+\delta_{\mathrm{clk}})
$$

Vì bộ chia 12 là chính xác, sai số tương đối của sample rate bằng sai số tương đối của nguồn clock:

$$
\frac{\Delta f_s}{f_s}=\delta_{\mathrm{clk}}
$$

Nói `0 ppm` trong bảng timer chỉ có nghĩa là **0 ppm sai số lượng tử bộ chia so với clock danh định 72 MHz**. Repo chưa có phép đo HSE bằng frequency counter chuẩn truy xuất, nên không thể chứng minh clock vật lý tuyệt đối đúng 72.000.000 Hz.

Phép Gray thực chất so sánh hai clock chưa hiệu chuẩn. Đặt sai số tương đối của clock STM32 và Arduino lần lượt là $\delta_S$ và $\delta_G$:

$$
f_{s,\mathrm{true}}=f_{s,\mathrm{nom}}(1+\delta_S)
$$

$$
f_{G,\mathrm{true}}=f_{G,\mathrm{nom}}(1+\delta_G)
$$

Vì số mẫu trung bình mỗi state là $\overline n\approx f_{s,\mathrm{true}}/f_{G,\mathrm{true}}$, verifier thu được:

$$
\widehat f_s
=\overline n\,f_{G,\mathrm{nom}}
\approx f_{s,\mathrm{nom}}
\frac{1+\delta_S}{1+\delta_G}
$$

Do đó, với sai số nhỏ:

$$
\frac{\widehat f_s-f_{s,\mathrm{nom}}}{f_{s,\mathrm{nom}}}
\approx\delta_S-\delta_G
$$

Nói cách khác, kết quả bám trong 0,05% chứng minh tốt rằng **tỉ lệ hai clock và thông lượng capture** nhất quán; nó không tự tách được sai số tuyệt đối của từng thạch anh.

Tại $D=11$, tần số toán học là:

$$
\frac{72\,000\,000}{11}=6\,545\,454.545\ldots\ \text{S/s}
$$

Firmware lưu phần nguyên `6.545.454 S/s`; chênh lệch do cắt phần lẻ chỉ khoảng:

$$
\frac{0.545\ldots}{6\,545\,454.545\ldots}\times10^6
\approx0.0833\ \text{ppm}
$$

#### B. Độ đầy đủ của dữ liệu trong frame

Các artifact chứng minh rằng trong những frame đã lưu:

- DMA hoàn tất đủ 13.888 transfer;
- frame hợp lệ, checksum/integrity hợp lệ;
- không báo overflow, dropped hoặc ISR overrun;
- chuỗi Gray không có state nhảy hoặc đảo thứ tự;
- không có short interior run;
- cả 8 kênh đều có cạnh;
- $\widehat f_s$ bám metadata trong sai lệch quan sát nêu trên.

Đây là nhiều tiêu chí kiểm tra bổ trợ cùng hội tụ, đủ cơ sở nói **“không phát hiện mất/sai mẫu trong các frame HIL đã lưu tại 6 MHz và 6,545454 MHz.”**

Nhưng không được đổi câu đó thành “DMA không bao giờ mất mẫu”. `dropped=0` là trường chẩn đoán firmware; một request phần cứng không được phục vụ chưa chắc tự động tăng bộ đếm này. Gray code cũng có trạng thái dài 60–65 mẫu, nên một số kiểu lỗi hiếm có thể chỉ làm run ngắn đi mà vẫn giữ đúng thứ tự. Phép ước lượng $\widehat f_s$ giúp phát hiện mất đều/bão hòa lớn, còn chứng nhận không lỗi tuyệt đối cần pattern nhanh hơn, phép đo clock ngoài và soak test dài hơn.

#### C. Độ chính xác thời điểm cạnh

Lấy mẫu đều không biết cạnh xảy ra ở đâu giữa hai mẫu. Nếu cạnh thật xuất hiện sau mẫu $k$ và được thấy ở mẫu $k+1$, sai số lượng tử thời gian thỏa:

$$
0\le e_t<T_s
$$

Do đó:

$$
e_{t,\max}<166.667\,\text{ns}
\qquad\text{tại }6\,\text{MS/s}
$$

$$
e_{t,\max}<152.778\,\text{ns}
\qquad\text{tại }6.545454\,\text{MS/s}
$$

Nếu pha cạnh phân bố đều so với lưới mẫu, độ lệch chuẩn lượng tử lý tưởng là:

$$
\sigma_q=\frac{T_s}{\sqrt{12}}
$$

Tuy nhiên sai số thực còn gồm dung sai clock, jitter, ngưỡng vào số, thời gian lên/xuống và dây nối; các thành phần analog này chưa được artifact hiện tại định lượng.

#### D. 6 MS/s không có nghĩa là đo chính xác tín hiệu 6 MHz

Với một tín hiệu tuần hoàn tần số $f_{\mathrm{sig}}$, hệ số oversampling là:

$$
K=\frac{f_s}{f_{\mathrm{sig}}}
$$

Tối thiểu kiểu Nyquist cần $K>2$ cho tín hiệu đã giới hạn băng, còn tín hiệu số vuông chứa nhiều hài và thực tế thường cần $K\ge4$ đến $10$ tùy mục tiêu decode. Vì thế $f_s=6$ MS/s chỉ cho $K=1.2$ với xung 5 MHz: **không thể bảo đảm tái tạo hay decode đúng xung 5 MHz**. Con số 6 MS/s là tốc độ chụp trạng thái logic, không phải băng thông tín hiệu số được bảo đảm bằng 6 MHz.

Ngược lại, với SCL/SCK 20 kHz của `MODE BOTH`:

$$
K=\frac{6\,000\,000}{20\,000}=300
$$

nên độ phân giải cạnh rất dư, nhưng cửa sổ chỉ 2,315 ms và không chứa đủ superframe khoảng 24,332 ms. Đây là đánh đổi đã nêu trong đoạn paste: tăng $f_s$ làm chi tiết theo thời gian tốt hơn nhưng làm mất bối cảnh dài vì $N$ cố định.

### 3.7. Kết luận ngắn cho câu hỏi “tại sao đo được tới 6 MHz?”

Chuỗi suy luận đúng là:

$$
\boxed{
\text{HSE 8 MHz}\times9
\Rightarrow f_{\mathrm{TIM2}}=72\,\text{MHz}
\Rightarrow D=12
\Rightarrow f_s=6\,\text{MS/s}
}
$$

$$
\boxed{
\text{TIM2}\rightarrow\text{DMA}\rightarrow\text{GPIOA IDR}\rightarrow\text{RAM}
\Rightarrow \text{không cần ISR trên từng mẫu}
}
$$

$$
\boxed{
\text{Gray 100 kHz, 3/3 PASS tại 6 MHz}
\Rightarrow \text{6 MHz được kiểm chứng trên các frame đã lưu}
}
$$

Sau đó tiếp tục sweep cho thấy $D=11$ vẫn PASS còn $D=10$ FAIL, nên kết luận đầy đủ là:

$$
\boxed{
f_{s,\mathrm{verified,max}}
=\frac{72\,\text{MHz}}{11}
=6.545454\,\text{MS/s}
}
$$

6 MHz là mức có sai số lượng tử divider 0 ppm và PASS 3/3 trong các frame HIL đã lưu; **6,545454 MS/s mới là trần DMA đã kiểm chứng của trạng thái repo hiện tại**. Không có board ở hiện tại nên tài liệu này chỉ tái lập suy luận từ source và artifact cũ, không tạo thêm bằng chứng HIL mới.

---

## 4. Giới hạn do buffer

Buffer trên F103C8 là:

$$
N=13\,888\ \text{mẫu}
$$

Mỗi mẫu là một byte chứa đồng thời trạng thái PA0…PA7, xem [board_config.h](src/firmware/board_config.h#L48) và [la_protocol.h](src/firmware/la_protocol.h#L13).

Cửa sổ thời gian của một frame:

$$
W=\frac{N}{f_s}
$$

Do đó:

### Tại 100 kS/s

$$
W_{100k}=\frac{13\,888}{100\,000}
=0.13888\,s=138.88\,ms
$$

### Tại yêu cầu 5 MHz

Phải dùng tần số thực:

$$
W_{5M}=\frac{13\,888}{5\,142\,857}
=2.70044\,ms
$$

Không phải $2.78\,ms$.

### Tại tốc độ tối đa 6,545454 MS/s

$$
W_{\max}=\frac{13\,888}{6\,545\,454}
=2.12178\,ms
$$

DMA không lấy vô hạn mẫu rồi bỏ bớt. Nó nạp:

$$
CNDTR=N
$$

rồi dừng khi đủ đúng $N$ mẫu, xem [main.cpp](src/firmware/main.cpp#L431). Những gì xảy ra sau khi DMA dừng **không hề được lấy mẫu**, chứ không phải được lấy rồi chọn bỏ.

---

## 5. Độ dài thực của `MODE BOTH`

### UART

Một byte được phát gồm:

- 1 start bit;
- 8 data bit;
- 1 stop bit;
- 3 bit idle bổ sung.

Vậy một byte chiếm:

$$
13\times416\,\mu s=5.408\,ms
$$

Có bốn byte `55 A5 4F 4B`, xem [arduino_signal_generator.ino](tools/arduino_signal_generator/src/arduino_signal_generator.ino#L164):

$$
L_{\mathrm{UART}}
=4\times13\times416\,\mu s
=21.632\,ms
$$

### I2C

- START: 2 tick;
- ba byte, mỗi byte có 8 bit + 1 ACK/NACK, mỗi clock có 2 tick;
- STOP: 3 tick.

$$
L_{\mathrm{I2C}}
=[2+3(9\times2)+3]\times25\,\mu s
=59\times25\,\mu s
=1.475\,ms
$$

### SPI

- CS setup: 1 half-period;
- 24 clock, mỗi clock có 2 half-period.

$$
L_{\mathrm{SPI}}
=(1+24\times2)\times25\,\mu s
=1.225\,ms
$$

### Tổng superframe

UART, I2C và SPI được phát tuần tự:

$$
L_{\mathrm{Both}}
=21.632+1.475+1.225
=24.332\,ms
$$

Chu kỳ lập lịch:

$$
P=40\,ms
$$

Idle danh nghĩa:

$$
P-L=40-24.332=15.668\,ms
$$

Đây là giá trị danh nghĩa từ source; overhead lệnh AVR và interrupt làm độ dài vật lý lớn hơn một chút.

---

## 6. Công thức lấy mẫu tín hiệu số và độ chính xác cạnh

Định lý Shannon–Nyquist:

$$
f_s>2B
$$

chỉ đảm bảo tái dựng một tín hiệu **band-limited**. Tín hiệu vuông không band-limited vì chứa nhiều harmonic, nên không thể kết luận “SPI 20 kHz chỉ cần lấy mẫu 40 kS/s”. Đây là giới hạn được trình bày trong [công trình gốc của Shannon](https://people.math.harvard.edu/~ctm/home/text/others/shannon/entropy/entropy.pdf). Tài liệu [Logic Analyzer Fundamentals của Tektronix](https://download.tek.com/document/52W-14266-5.pdf) cũng phân biệt rõ timing resolution với băng thông/tần số cơ bản.

Với logic analyzer:

$$
T_s=\frac1{f_s}
$$

Nếu cạnh thật xảy ra tại $t_e$, cạnh được ghi ở mẫu đầu tiên sau nó:

$$
\hat t_e=t_e+e,\qquad 0\le e<T_s
$$

Đối với khoảng thời gian giữa hai cạnh:

$$
\left|\widehat{\Delta t}-\Delta t\right|<T_s
$$

Suy ra sai số lượng tử tương đối:

$$
\varepsilon_q<\frac{T_s}{\Delta t}
$$

### Tại 100 kS/s

$$
T_s=10\,\mu s
$$

- Với một mức SPI/I2C rộng $25\,\mu s$:

  $$
  \varepsilon_q<\frac{10}{25}=40\%
  $$

- Với một chu kỳ SCK $50\,\mu s$:

  $$
  \varepsilon_q<20\%
  $$

- Đo trên 24 chu kỳ SPI, thời gian $1.2\,ms$:

  $$
  \varepsilon_q<\frac{10\,\mu s}{1.2\,ms}=0.833\%
  $$

- Với một bit UART $416\,\mu s$:

  $$
  \varepsilon_q<\frac{10}{416}=2.404\%
  $$

Nghĩa là 100 kS/s đủ tốt để giải mã mẫu hiện tại, nhưng **không phải phép đo pulse-width rất chính xác** đối với các xung 25 µs.

### Tại 5,142857 MS/s

$$
T_s=0.194444\,\mu s
$$

Đối với mức rộng 25 µs:

$$
\varepsilon_q<\frac{0.194444}{25}=0.778\%
$$

Độ chính xác cục bộ cao hơn rất nhiều, nhưng chỉ trên cửa sổ dài 2.700 ms.

### Xác suất phát hiện một pulse

Nếu thời điểm pulse có pha ngẫu nhiên so với sample clock, với pulse rộng $w$:

$$
P(\text{có ít nhất một mẫu trong pulse})
=\min\left(1,\frac{w}{T_s}\right)
$$

Tổng quát, xác suất có ít nhất $r$ mẫu:

$$
P(N_{\text{pulse}}\ge r)
=
\operatorname{clamp}
\left(
\frac{w}{T_s}-(r-1),\,0,\,1
\right)
$$

Tại 100 kS/s, $w=25\,\mu s=2.5T_s$:

- luôn có ít nhất 2 mẫu trong mỗi half-period;
- xác suất có 3 mẫu là 50%.

Decoder SPI của repo yêu cầu ít nhất 4 mẫu trên một chu kỳ SCK tại [decoders.py](src/software/decoders.py#L6):

$$
f_s\ge4f_{\mathrm{SCK}}
=4\times20\,k
=80\,\text{kS/s}
$$

Do đó 50 kS/s không đủ: chỉ có 2,5 mẫu/clock và decoder sẽ đánh dấu `UNDERSAMPLED`.

---

## 7. Điều kiện để chứa trọn một transaction

Giả sử transaction dài $L$, lặp mỗi $P$, và cửa sổ capture dài $W$.

Nếu capture không được trigger và pha bắt đầu là ngẫu nhiên:

$$
P_{\mathrm{full}}
=
\operatorname{clamp}
\left(
\frac{W-L}{P},\,0,\,1
\right)
$$

Giải thích: transaction chỉ nằm trọn trong cửa sổ nếu điểm bắt đầu của nó rơi trong đoạn dài $W-L$.

Để bảo đảm 100% với mọi pha:

$$
W\ge P+L
$$

Với `MODE BOTH`:

$$
P+L=40+24.332=64.332\,ms
$$

### Toàn bộ frame 13.888 mẫu

$$
\frac{13\,888}{f_s}\ge64.332\,ms
$$

Suy ra:

$$
f_s\le
\frac{13\,888}{0.064332}
=215\,880\ \text{S/s}
$$

Kết hợp điều kiện SPI:

$$
\boxed{
80\,000\le f_s\le215\,880\ \text{S/s}
}
$$

Đây là miền cho một frame đầy đủ, không trigger.

### Phần thực sự được vẽ trong Realtime

Realtime chỉ vẽ 8.192 mẫu cuối, dù giữ history tối đa 204.800 mẫu, xem [main_window.py](src/software/gui/main_window.py#L49).

$$
W_{\mathrm{view}}=\frac{8192}{f_s}
$$

Muốn phần đang nhìn thấy bảo đảm có một `MODE BOTH` hoàn chỉnh:

$$
\frac{8192}{f_s}\ge64.332\,ms
$$

$$
f_s\le127\,339\ \text{S/s}
$$

Kết hợp điều kiện decoder SPI:

$$
\boxed{
80\,000\le f_s\le127\,339\ \text{S/s}
}
$$

GUI hiện có 50 k, 100 k rồi nhảy lên 500 k tại [main_window.py](src/software/gui/main_window.py#L20). Vì vậy:

$$
\boxed{\text{100 kS/s là lựa chọn duy nhất trong GUI}}
$$

---

## 8. Tính toán Realtime và lượng dữ liệu bị mất theo thời gian

Realtime gọi lại `device.capture()` cho từng frame tại [main_window.py](src/software/gui/main_window.py#L540). Firmware không hỗ trợ streaming thật; `start_stream()` trả về `False` tại [device.py](src/software/device.py#L386).

Mỗi frame gồm:

$$
N+H=13\,888+48=13\,936\ \text{byte}
$$

Serial LA chạy 1.000.000 baud. Với 8N1, mỗi byte cần:

$$
1\text{ start}+8\text{ data}+1\text{ stop}=10\text{ bit}
$$

Đây là framing UART tiêu chuẩn, xem [datasheet ATmega328P của Microchip](https://ww1.microchip.com/downloads/aemDocuments/documents/MCU08/ProductDocuments/DataSheets/Atmel-7810-Automotive-Microcontrollers-ATmega328P_Datasheet.pdf).

Băng thông payload lý tưởng:

$$
R_{\mathrm{byte}}
=\frac{1\,000\,000}{10}
=100\,000\ \text{byte/s}
$$

Trong nội dung đính kèm trước đó có typo `100.000.000/10`; giá trị đúng là `1.000.000/10`.

Thời gian truyền tối thiểu:

$$
T_{\mathrm{dump}}
\ge
\frac{13\,936}{100\,000}
=139.36\,ms
$$

Một vòng realtime tối thiểu:

$$
T_{\mathrm{cycle}}
\ge W+T_{\mathrm{dump}}+T_{\mathrm{control}}+T_{\mathrm{GUI}}
$$

Bỏ qua control và GUI để lấy cận trên lạc quan:

$$
\eta_{\max}
=
\frac{W}{W+T_{\mathrm{dump}}}
$$

| LA sample rate | Tần số thực | $T_s$ | Frame $W$ | Phần đang vẽ | Duty tối đa | Kết quả đối với Both |
|---:|---:|---:|---:|---:|---:|---|
| 50 kS/s | 50 k | 20 µs | 277.760 ms | 163.840 ms | 66.59% | Đủ thời gian nhưng SPI chỉ 2,5 mẫu/clock, decoder từ chối |
| **100 kS/s** | **100 k** | **10 µs** | **138.880 ms** | **81.920 ms** | **49.91%** | Frame và phần đang vẽ đều bảo đảm có Both hoàn chỉnh |
| 200 kS/s* | 200 k | 5 µs | 69.440 ms | 40.960 ms | 33.26% | Full frame bảo đảm; phần đang vẽ chỉ có xác suất 41,57% |
| 400 kS/s* | 400 k | 2,5 µs | 34.720 ms | 20.480 ms | 19.94% | Không bảo đảm pha ngẫu nhiên; dùng trigger thì được |
| 500 kS/s | 500 k | 2 µs | 27.776 ms | 16.384 ms | 16.62% | Xác suất chứa Both hoàn chỉnh chỉ 8,61% |
| 1 MS/s | 1 M | 1 µs | 13.888 ms | 8.192 ms | 9.06% | Ngắn hơn Both và UART |
| yêu cầu 5 MHz* | 5.142857 M | 0,194 µs | 2.700 ms | 1.593 ms | 1.90% | Không thể chứa Both hoặc UART hoàn chỉnh |
| 6.545454 MS/s | 6.545454 M | 0,153 µs | 2.122 ms | 1.252 ms | 1.50% | Chỉ quan sát một đoạn rất ngắn |

\* 200 k, 400 k và 5 MHz không có sẵn trong dropdown GUI hiện tại.

### Trong một phiên Realtime lý tưởng 5 giây

Tại 100 kS/s:

$$
T_{\mathrm{cycle,min}}
=138.88+139.36=278.24\,ms
$$

Số frame hoàn chỉnh được truyền:

$$
\left\lfloor\frac{5}{0.27824}\right\rfloor=17
$$

Thời gian thực được thu:

$$
17\times138.88\,ms=2.36096\,s
$$

Tỷ lệ trên đúng phiên 5 giây:

$$
\frac{2.36096}{5}=47.219\%
$$

Tại yêu cầu 5 MHz:

$$
T_{\mathrm{cycle,min}}
=2.70044+139.36
=142.06044\,ms
$$

$$
\left\lfloor\frac5{0.14206044}\right\rfloor=35
$$

$$
35\times2.70044\,ms=94.516\,ms
$$

$$
\frac{94.516\,ms}{5\,s}=1.890\%
$$

Đây vẫn là cận lạc quan vì chưa cộng ARM, EVENT, Python và thời gian vẽ.

Một vấn đề biểu diễn nữa: GUI nối frame sau ngay sát mẫu cuối frame trước bằng `last_time + sample_period` tại [capture.py](src/software/capture.py#L54). Khoảng mù 139 ms không xuất hiện trên trục thời gian. Vì vậy waveform realtime trông liên tục nhưng **không phải timeline vật lý liên tục**; decoder còn có thể hiểu nhầm cạnh nằm ở biên hai frame.

---

## 9. Realtime ở 100 kS/s có “visual hết” không?

Có hai câu trả lời:

### Nếu “hết” nghĩa là một ví dụ đầy đủ của từng giao thức

Sau khi sửa generator:

- $W_{\mathrm{view}}=81.92\,ms>64.332\,ms$;
- bảo đảm ít nhất một superframe Both đầy đủ trong phần đang nhìn;
- toàn frame 138.88 ms bảo đảm ít nhất:

  $$
  \left\lfloor
  \frac{138.88-24.332}{40}
  \right\rfloor
  =2
  $$

  superframe hoàn chỉnh;

- UART có khoảng 41,6 mẫu/bit;
- I2C và SPI có 5 mẫu/clock;
- thỏa mức tối thiểu 4 mẫu/clock của decoder SPI.

Vậy **100 kS/s phù hợp nhất để demo/visual/decode đầy đủ một mẫu Both**.

### Nếu “hết” nghĩa là không bỏ mất bất kỳ occurrence nào

Không. Cận trên duty chỉ 49,91%; trong thời gian dump khoảng 139,36 ms, Arduino đã phát thêm khoảng:

$$
\frac{139.36}{40}=3.484
$$

superframe mà LA không quan sát.

`dropped_samples=0` chỉ có nghĩa là không phát hiện mất mẫu **bên trong frame DMA đã thu**, không có nghĩa là không có khoảng mù ngoài frame.

---

## 10. Offline xảy ra như thế nào?

Offline và Realtime dùng cùng một phép capture vật lý. Khác biệt là Offline chỉ thu một lần và hiển thị toàn bộ 13.888 mẫu.

DUMP diễn ra sau khi capture dừng tại [main.cpp](src/firmware/main.cpp#L915), nên thời gian truyền serial không phá hỏng các mẫu đã nằm trong RAM.

### Offline immediate 100 kS/s

$$
W=138.88\,ms>64.332\,ms
$$

Do đó bất kể bắt đầu ở pha nào:

- chứa ít nhất hai Both hoàn chỉnh;
- hiển thị toàn bộ 13.888 mẫu;
- giải mã UART/I2C/SPI được, với giới hạn timing 10 µs.

Đây là lựa chọn an toàn hiện có trong GUI.

### Offline immediate khoảng 200 kS/s

$$
W=69.44\,ms>64.332\,ms
$$

Vẫn bảo đảm một Both hoàn chỉnh, đồng thời:

- $T_s=5\,\mu s$;
- SPI có 10 mẫu/clock;
- timing tốt hơn 100 kS/s.

Về toán học, đây là lựa chọn offline immediate tốt hơn 100 kS/s, nhưng GUI chưa đưa 200 kS/s vào danh sách.

### Offline có trigger ở 400 kS/s

Nếu trigger theo cạnh xuống PA0, tức start bit đầu của UART:

$$
W=\frac{13\,888}{400\,000}=34.72\,ms
$$

Vì capture được căn theo đầu superframe:

$$
W>L_{\mathrm{Both}}=24.332\,ms
$$

nên chứa được toàn bộ Both.

Đây là cấu hình độ phân giải tốt nhất trong kiến trúc trigger hiện tại:

- $T_s=2.5\,\mu s$;
- 20 mẫu trên một clock SPI;
- cửa sổ vẫn dài hơn toàn superframe.

Trigger cạnh/pattern phải dùng ISR và source giới hạn ISR ở 400 kS/s tại [la_board.h](src/firmware/la_board.h#L25) và [main.cpp](src/firmware/main.cpp#L748). Vì vậy không thể dùng trigger 5 MHz trong firmware hiện tại.

### Offline 5 MHz

$$
W=2.700\,ms
$$

Do đó:

- không thể chứa UART dài 21.632 ms;
- không thể chứa Both dài 24.332 ms;
- có thể chứa một I2C dài 1.475 ms hoặc SPI dài 1.225 ms nếu capture rơi đúng vị trí.

Với pha ngẫu nhiên:

$$
P_{\mathrm{I2C,full}}
=\frac{2.70044-1.475}{40}
=3.064\%
$$

$$
P_{\mathrm{SPI,full}}
=\frac{2.70044-1.225}{40}
=3.689\%
$$

Như vậy Offline 5 MHz rất chính xác cho một đoạn ngắn, nhưng gần như không phù hợp để bắt ngẫu nhiên toàn transaction Both.

---

## 11. Giới hạn decoder cho các giao thức nói chung

Không tồn tại một sample rate chung cho “mọi UART/I2C/SPI”; nó phụ thuộc tốc độ bus.

| Decoder hiện tại | Điều kiện |
|---|---|
| UART 8N1 | Source cảnh báo nếu $f_s/b<3$; thực tế nên dùng 8–16 mẫu/bit |
| I2C | Phải thấy START, STOP và cạnh lên SCL; dùng $f_s\ge K/w_{\min}$ theo độ rộng pha nhỏ nhất |
| SPI | $f_s\ge4f_{\mathrm{SCK}}$; chỉ lấy mẫu cạnh lên, gần với CPOL=0/CPHA=0 |

Tại trần 6,545454 MS/s:

- UART theo ngưỡng tối thiểu 3 mẫu/bit:

  $$
  b_{\max,\min}=\frac{6.545454M}{3}
  =2.182\,Mbaud
  $$

  Với 10 mẫu/bit để chắc chắn hơn:

  $$
  b_{\max,\mathrm{robust}}\approx654.5\,kbaud
  $$

- SPI theo rule decoder:

  $$
  f_{\mathrm{SCK,max}}
  =\frac{6.545454M}{4}
  =1.636\,MHz
  $$

Đây là giới hạn thuật toán, không phải cam kết về chất lượng điện, setup/hold hay mọi mode SPI.

---

## 12. Độ chính xác tuyệt đối chưa thể chứng minh

Sai số đo thời gian thực tế có thể mô hình hóa:

$$
|\widehat{\Delta t}-\Delta t|
\lesssim
T_s
+
|\varepsilon_{\mathrm{clock}}|\Delta t
+
J_{\mathrm{generator}}
+
J_{\mathrm{sampling}}
+
J_{\mathrm{threshold}}
$$

Trong đó:

- $T_s$: lượng tử hóa do sample rate;
- $\varepsilon_{\mathrm{clock}}$: sai số thạch anh/clock STM32;
- $J_{\mathrm{generator}}$: jitter do `delayMicroseconds()`, vòng lặp và interrupt Arduino;
- $J_{\mathrm{sampling}}$: jitter timer/DMA và tranh chấp bus;
- $J_{\mathrm{threshold}}$: trễ do sườn tín hiệu đi qua ngưỡng logic.

Bộ phát dùng open-drain. Sườn lên tuân theo gần đúng:

$$
V(t)=V_{DD}\left(1-e^{-t/(R_pC_b)}\right)
$$

Thời điểm STM32 nhìn thấy logic 1:

$$
t_{\mathrm{cross}}
=-R_pC_b
\ln\left(1-\frac{V_{IH}}{V_{DD}}\right)
$$

Hiện không có board nên không biết:

- điện trở pull-up $R_p$;
- điện dung dây/probe $C_b$;
- ngưỡng thực $V_{IH}$;
- sai số oscillator;
- rise/fall time và jitter.

Do đó repo chỉ cho phép kết luận về **độ phân giải danh nghĩa và tính nhất quán tương đối**, chưa cho phép tuyên bố độ chính xác tuyệt đối traceable theo ppm.

Các log HIL cũ ghi DMA không dropped/overrun trong những lần thử tới 6,545454 MS/s tại [hil_dma_high.log](report/generated/hardware_evidence_20260718/hil_dma_high.log#L1). Điều đó chỉ chứng minh những lần đo đã lưu, không chứng minh mọi điều kiện. Hơn nữa, Arduino và STM32 đều chưa được đối chiếu với cùng một nguồn clock chuẩn, nên sai số HIL là sai số tương đối giữa hai thiết bị.

---

## 13. Trạng thái sửa lỗi `MODE BOTH`

Lỗi trước đây xuất phát từ việc `generator_mode_emits_aux(MODE_BOTH)` trả về `true`. Khi đó Timer1 auxiliary chạy ở 4 kHz và `write_aux_open_drain()` ghi cả CH3…CH7, trong khi SPI cũng dùng CH3…CH6 cho SCK/MOSI/MISO/CS. Một SPI frame dài 1.225 ms có thể gặp khoảng:

$$
\frac{1.225\,ms}{250\,\mu s}=4.9
$$

lần ISR, đủ để cắt ngắn SCK, thay đổi MOSI/MISO hoặc kéo CS sai mức.

Source hiện tại đã sửa theo regression test bằng cách tắt auxiliary routing cho mọi mode đang có:

```cpp
static inline bool generator_mode_emits_aux(GeneratorMode mode) {
  // CH3..CH6 are owned by SPI in MODE_BOTH.
  (void)mode;
  return false;
}
```

Xem [generator_modes.h](tools/arduino_signal_generator/include/generator_modes.h#L32). Khi `MODE BOTH` được chọn, `set_mode()` không còn gọi `start_aux_timer()`, do đó:

- CH3–CH6 chỉ do SPI điều khiển;
- UART trên CH0 và I2C trên CH1–CH2 không thay đổi;
- CH7 vẫn là marker được đổi mức một lần ở đầu mỗi SPI frame;
- jitter do Timer1 ISR chen vào quá trình bit-banging cũng được loại bỏ.

Bằng chứng kiểm tra sau sửa:

- native regression test `test_generator_modes`: **PASS**;
- Arduino Uno PlatformIO build: **SUCCESS**;
- tài nguyên Arduino: 362/2048 byte RAM và 4944/32256 byte Flash;
- Python test suite: **70 PASS**;
- chưa có HIL mới vì hiện không có board.

Do đó lỗi logic trong source đã được xử lý, nhưng log HIL cũ vẫn không đủ để chứng nhận phiên bản mới. Khi có board cần đo lại đồng thời UART + I2C + SPI trong `MODE BOTH`.

---

## Khuyến nghị sử dụng

- **Realtime để quan sát một bộ UART + I2C + SPI hoàn chỉnh:** source hiện đã tắt Timer1 aux trong `MODE BOTH`; dùng **100 kS/s** và chạy lại HIL khi có board để chứng nhận tín hiệu vật lý.
- **Offline không trigger, ưu tiên chắc chắn:** 100 kS/s hiện dùng được; nếu bổ sung GUI, **200 kS/s** cho độ phân giải tốt hơn mà vẫn bảo đảm một Both hoàn chỉnh.
- **Offline độ phân giải tốt nhất:** trigger cạnh xuống PA0 ở **400 kS/s**.
- **5 MHz hoặc 6 MHz:** chỉ dùng để zoom một transaction ngắn đã biết vị trí; không dùng để bắt toàn bộ `MODE BOTH`.
- **Muốn realtime thực sự không mất khoảng thời gian:** phải thiết kế lại thành ping-pong DMA/ring streaming và nâng băng thông. Ngay cả streaming giả định, UART 1 Mbaud chỉ chịu tối đa:

  $$
  f_{s,\max}
  =
  \frac{1\,000\,000}{10}
  \frac{13\,888}{13\,888+48}
  =99\,655.6\ \text{S/s}
  $$

  nên 100 kS/s đã vượt nhẹ trần lý tưởng trước cả command và GUI.

Tóm lại: **100 kS/s là điểm cân bằng đúng để nhìn một mẫu đầy đủ; nó không phải thu liên tục. Offline 200/400 kS/s cho kết quả tốt hơn nếu căn cửa sổ. 5 MHz chính xác cục bộ nhưng mất gần như toàn bộ bối cảnh thời gian. Xung đột Timer1 aux với SPI đã được sửa trong source, nhưng vẫn cần HIL mới để chứng nhận trên phần cứng.**
