# Kết quả HIL trên STM32F103C8 chạy thạch anh HSE (72 MHz)

Ngày đo: 2026-07-18. Firmware: `SLA8-FW-V2-P5` (đã thêm `SystemClock_Config()` ép HSE).
Board LA: COM12 (FT232). Bộ tạo xung: Arduino UNO CH340 COM18, mode GRAY 8-bit.
Xác nhận nguồn nhịp: lệnh `INFO` báo `TIMER_CLOCK 72000000` → chạy thạch anh HSE (8 MHz × 9).

## 1. Sai số lượng tử tần số lấy mẫu (đo COM12: CFG RATE + STATUS)

| Yêu cầu (Hz) | Thực tế (Hz) | ERROR_PPM | Sai số (%) |
|---:|---:|---:|---:|
| 1.000 | 1.000 | 0 | 0,000 |
| 10.000 | 10.000 | 0 | 0,000 |
| 100.000 | 100.000 | 0 | 0,000 |
| 500.000 | 500.000 | 0 | 0,000 |
| 1.000.000 | 1.000.000 | 0 | 0,000 |
| 2.000.000 | 2.000.000 | 0 | 0,000 |
| 3.000.000 | 3.000.000 | 0 | 0,000 |
| 4.000.000 | 4.000.000 | 0 | 0,000 |
| 5.000.000 | 5.142.857 | 28571 | +2,857 |
| 5.818.182 | 6.000.000 | 31249 | +3,125 |

Các mức là ước số nguyên của 72 MHz đạt 0 ppm. 5 MHz và 5.818 MHz lệch do 72/N không nguyên (lượng tử hoá divider, xác định trước).

## 2. Gray-code oracle HIL (đối chiếu tín hiệu chuẩn từ Arduino)

Tất cả: `sequence_errors=0`, `short_runs=0`, `dropped=0`, `isr_overrun=0`, không overflow/checksum error.

| Chế độ | Tốc độ (S/s) | Số lần | Kết quả | Sai số tần số đo |
|---|---:|---:|---|---|
| DMA | 100.000 | 3 | PASS | 0,00–0,01% |
| DMA | 500.000 | 3 | PASS | 0,00–0,01% |
| DMA | 1.000.000 | 3 | PASS | 0,00–0,01% |
| DMA | 2.000.000 | 3 | PASS | 0,00–0,01% |
| DMA | 4.000.000 | 3 | PASS | 0,01% |
| ISR | 100.000 | 3 | PASS | 0,00–0,01% |
| ISR | 250.000 | 3 | PASS | 0,00–0,01% |
| ISR | 400.000 | 3 | PASS | 0,01% |

Ghi chú:
- Ở Fs cao (≥2 MS/s) cửa sổ buffer ngắn nên cần tăng tốc bước Gray (step 100 kHz) để đủ số trạng thái và để bit cao CH6/CH7 kịp đổi; đây là giới hạn phương pháp đo, không phải lỗi thiết bị.
- Yêu cầu 5.818.182 S/s cho tần số thực 6.000.000 S/s (lượng tử hoá 72 MHz/12); dữ liệu vẫn sạch (sequence_errors=0) nhưng lệch danh định 3,12% so với số yêu cầu.
- Trần đã quan sát: DMA capture sạch tới ~6 MS/s; ISR tới 400 kS/s (khớp giới hạn firmware).

## 2b. Trần tốc độ DMA thật ở 72 MHz (firmware benchmark, mở khoá tới 32 MHz)

Đo bằng `SLA8-FW-V2-RATE-BENCH`, step Gray 100 kHz. Khi chạm trần vật lý, tần số đo được
chững lại dưới mức lập trình (DMA bỏ mẫu đều nên sequence_errors vẫn 0, nhưng rate hiệu dụng bão hoà).

| Rate lập trình (S/s) | Rate đo được (S/s) | Sai lệch | Kết luận |
|---:|---:|---:|---|
| 6.000.000 (72M/12) | ~6.000.000 | ≤0,03% | Sạch |
| 6.545.454 (72M/11) | ~6.545.500 | ≤0,03% | **Sạch — trần bám chính xác cao nhất** |
| 7.200.000 (72M/10) | ~6.647.000 | +7,7% (chững) | Vượt trần |
| 8.000.000 (72M/9) | ~6.785.000 | +15,2% | Bão hoà |
| 9.000.000 | ~6.810.000 | +24,3% | Bão hoà |

Kết luận: ở 72 MHz (HSE), DMA bám chính xác tới **6,545 MS/s (72 MHz/11)**; bão hoà vật lý quanh **~6,8 MS/s**.
So với HSI 64 MHz (bám tới 5,818 MS/s = 64M/11, bão hoà ~6,23 MS/s), việc chuyển sang HSE nâng
trần thêm ~12,5% — đúng tỉ lệ HCLK 72/64. ISR vẫn giữ mức 400 kS/s (giới hạn thời gian ISR, không phụ thuộc clock nhiều).

## 3. Kiểm thử tự động (không cần phần cứng)

- `pytest tests/`: 63 test PASS.
- Native `tests/native/test_timer_plan.c` (biên dịch host): PASS (kiểm tra công thức PSC/ARR ở cả 64 MHz và 72 MHz).

## 4. So sánh trước/sau khi đổi nguồn nhịp

| | HSI (mặc định cũ) | HSE thạch anh (hiện tại) |
|---|---|---|
| Timer clock | 64 MHz | 72 MHz |
| Sai số tuyệt đối đo được | ~0,09% | ≤0,01% |
| Danh định | ±1% | ±20…50 ppm |
