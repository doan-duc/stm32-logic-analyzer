# Missing Information Checklist

Generated: 2026-07-07

## Thông Tin Hành Chính

- [ ] MSSV, lớp học phần, nhóm và tên giảng viên.
- [ ] Danh sách thành viên và phân công nếu làm theo nhóm.

## Phần Cứng

- [ ] Ảnh board STM32 thực tế.
- [ ] Sơ đồ nối dây CH0..CH7, UART và nguồn.
- [ ] Sơ đồ mạch bảo vệ đầu vào, BOM và dải điện áp an toàn.
- [ ] Ảnh hoặc sơ đồ nối Arduino UNO dùng làm nguồn tín hiệu kiểm thử.

## Thực Nghiệm

- [ ] Log `INFO`, `STATUS`, `BENCH`.
- [ ] File capture `.sla8` hoặc dữ liệu mẫu.
- [ ] Ảnh waveform trên phần mềm PC.
- [ ] Ảnh bảng decode UART và I2C.
- [ ] Số đo sample rate tại 1 kHz, 100 kHz và 1 MHz.
- [ ] Số đo jitter/skew giữa các kênh.
- [ ] Kết quả kiểm thử trigger immediate/edge/pattern.
- [ ] Video demo nếu cần bảo vệ.

## Nội Dung Nên Hoàn Thiện

- [ ] Bổ sung khảo sát một số logic analyzer thông dụng nếu giảng viên yêu cầu.
- [ ] Bổ sung decoder SPI hoặc ghi rõ giới hạn hiện tại là UART/I2C.
- [ ] Thêm kiểm thử tự động cho protocol frame và decoder.
