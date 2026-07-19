#ifndef LA_BOARD_H
#define LA_BOARD_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/*
 * Đảm bảo tương thích khi biên dịch bằng trình biên dịch C++ (gcc-g++).
 * extern "C" giúp giữ nguyên tên hàm (name mangling) để mã C++ gọi được mã C.
 */
#ifdef __cplusplus
extern "C" {
#endif

/*
 * Tần số lấy mẫu mục tiêu tối đa (Hz).
 * Ví dụ: 72 MHz (tần số MCU) / 11 chu kỳ = khoảng 6.545 MS/s.
 * Đây là giới hạn DMA tối đa đã được kiểm chứng bằng phần cứng (HIL - Hardware In the Loop) khi sử dụng thạch anh ngoài HSE.
 */
#ifndef LA_MAX_SAMPLE_RATE_HZ_TARGET
#define LA_MAX_SAMPLE_RATE_HZ_TARGET 6545454UL
#endif

/*
 * Tần số lấy mẫu tối đa đã kiểm chứng đối với cơ chế ngắt phần cứng (ISR) truyền thống (400 kHz).
 * Do ngắt tốn chi phí đẩy/kéo thanh ghi nên tần số lấy mẫu ngắt không thể quá cao.
 */
#ifndef LA_MAX_ISR_SAMPLE_RATE_HZ_VERIFIED
#define LA_MAX_ISR_SAMPLE_RATE_HZ_VERIFIED 400000UL
#endif

/*
 * Tần số lấy mẫu tối đa đã kiểm chứng đối với cơ chế DMA (6.545 MS/s).
 */
#ifndef LA_MAX_DMA_SAMPLE_RATE_HZ_VERIFIED
#define LA_MAX_DMA_SAMPLE_RATE_HZ_VERIFIED 6545454UL
#endif

/*
 * Giá trị chia tần tối đa của Timer STM32 (thường dùng bộ chia 16-bit nên là 65536).
 */
#ifndef LA_TIMER_MAX_PRESCALER
#define LA_TIMER_MAX_PRESCALER 65536UL
#endif

/*
 * Giá trị nạp lại tự động tối đa (ARR) của Timer STM32 (ARR là thanh ghi 16-bit nên tối đa 65535).
 */
#ifndef LA_TIMER_MAX_ARR
#define LA_TIMER_MAX_ARR 65535UL
#endif

/*
 * Cấu trúc dữ liệu chứa kế hoạch cấu hình Timer:
 * - timer_clock_hz: Tần số nguồn xung nhịp của Timer (Hz).
 * - requested_sample_rate_hz: Tần số lấy mẫu do người dùng yêu cầu (Hz).
 * - actual_sample_rate_hz: Tần số lấy mẫu thực tế mà Timer có thể tạo ra (Hz).
 * - prescaler: Giá trị nạp vào thanh ghi bộ chia (PSC).
 * - autoreload: Giá trị nạp vào thanh ghi tự động nạp lại (ARR).
 * - error_ppm: Sai số giữa thực tế và yêu cầu tính theo phần triệu (PPM).
 */
typedef struct {
  uint32_t timer_clock_hz;
  uint32_t requested_sample_rate_hz;
  uint32_t actual_sample_rate_hz;
  uint32_t prescaler;
  uint32_t autoreload;
  int32_t error_ppm;
} la_board_timer_plan_t;

/*
 * Hàm tính toán hệ số chia tần và giá trị nạp lại tự động của Timer.
 */
bool la_board_calculate_timer_plan(uint32_t timer_clock_hz,
                                   uint32_t requested_sample_rate_hz,
                                   la_board_timer_plan_t *plan_out);

/*
 * Hàm kiểm tra xem một tần số lấy mẫu có được phần cứng hỗ trợ hay không.
 */
bool la_board_sample_rate_supported(uint32_t sample_rate_hz,
                                    bool using_dma_engine);

/*
 * Khởi tạo chung cho bo mạch (Clock, ngoại vi...).
 */
void la_board_init(void);

/*
 * Khởi tạo 8 chân GPIO làm đầu vào đo tín hiệu logic.
 */
void la_board_gpio_init_8ch(void);

/*
 * Khởi tạo Timer dựa trên tần số lấy mẫu được truyền vào.
 */
bool la_board_timer_init(uint32_t sample_rate_hz,
                         la_board_timer_plan_t *plan_out);

/*
 * Bắt đầu chạy Timer phát xung/ngắt lấy mẫu.
 */
void la_board_timer_start(void);

/*
 * Dừng Timer lấy mẫu.
 */
void la_board_timer_stop(void);

/*
 * Khởi tạo cổng UART hoặc USB CDC tùy cấu hình để truyền thông.
 */
void la_board_uart_or_usb_init(void);

/*
 * Gửi mảng dữ liệu đo (chặn luồng - blocking) sau khi hoàn tất phiên capture.
 */
void la_board_write_bytes_blocking_after_capture(const uint8_t *data,
                                                 size_t len);

/*
 * Đọc nhanh trạng thái 8 kênh GPIO hiện tại.
 */
uint8_t la_board_read_gpio_snapshot_8ch(void);

#ifdef __cplusplus
}
#endif

#endif
