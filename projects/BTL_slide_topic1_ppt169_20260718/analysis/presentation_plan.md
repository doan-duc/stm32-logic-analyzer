# Kế hoạch trình bày đã xác nhận

Trạng thái: confirmed

1. Bìa — tên đề tài, nhóm sinh viên, giảng viên hướng dẫn.
2. Đặt vấn đề — vì sao cần quan sát đồng thời nhiều tín hiệu số.
3. Mục tiêu và phạm vi — 8 kênh, 1 kHz trở lên, GUI, UART/I2C/SPI.
4. Kiến trúc tổng thể — nguồn tín hiệu, STM32, khung SLA8, phần mềm PC.
5. Thiết kế phần cứng và đấu nối — PA0–PA7, USART1, mức 3,3 V, open-drain.
6. Cơ chế lấy mẫu — DMA cho trigger tức thời, ISR cho trigger có điều kiện.
7. Firmware và khung SLA8 — luồng ARM/CAPTURE/DUMP và metadata/checksum.
8. Phần mềm PC — kết nối, cấu hình, waveform, đo cạnh và decoder.
9. Phương pháp kiểm thử HIL — STM32 COM12, Arduino COM18, oracle Gray, 10 TC.
10. Kết quả tốc độ — DMA 6,545 MS/s; ISR 400 kS/s; từ chối vượt ngưỡng.
11. Kiểm chứng 8 kênh và Nyquist — Gray sạch và ví dụ aliasing 25 kHz.
12. Decode UART/I2C/SPI — kết quả giải mã vật lý từng giao thức.
13. Trigger và xử lý biên — cảnh báo SPI undersampled, trigger FALL CH6.
14. Đối chiếu yêu cầu — các chỉ tiêu chính và 10/10 kịch bản đạt.
15. Hạn chế, hướng phát triển và kết luận.

Nguồn sự thật chính: `content.tex`, `metrics.json`, mã nguồn và ảnh HIL.
Không dùng các kết luận cũ trong `evidence_map.md` về trần 1 MS/s.
Không tuyên bố chế độ Arduino phát đồng thời UART/I2C/SPI đã được kiểm chứng.
