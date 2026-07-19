#include "la_board.h"

/*
 * Định nghĩa macro LA_WEAK để đánh dấu các hàm ở chế độ "weak" (yếu).
 * Các hàm weak này có thể bị ghi đè (override) bởi các hàm cùng tên ở các file khác 
 * mà không gây ra lỗi trùng lặp ký hiệu (duplicate symbol) tại thời điểm liên kết (linking).
 */
#if defined(__GNUC__)
#define LA_WEAK __attribute__((weak))
#else
#define LA_WEAK
#endif

/*
 * Hàm khởi tạo chung cho bo mạch (hàm weak, mặc định trống).
 */
LA_WEAK void la_board_init(void) {}

/*
 * Hàm khởi tạo GPIO cho 8 kênh đo logic (hàm weak, mặc định trống).
 */
LA_WEAK void la_board_gpio_init_8ch(void) {}

/*
 * Tính toán cấu hình bộ đếm Timer (Prescaler và Autoreload Value - ARR) để đạt được tần số lấy mẫu mong muốn.
 * timer_clock_hz: Tần số xung nhịp cấp cho Timer (ví dụ 72 MHz hoặc 84 MHz).
 * requested_sample_rate_hz: Tần số lấy mẫu mong muốn (Hz).
 * plan_out: Con trỏ tới cấu trúc lưu kết quả tính toán.
 * Trả về true nếu tính toán thành công và nằm trong giới hạn phần cứng, ngược lại trả về false.
 */
bool la_board_calculate_timer_plan(uint32_t timer_clock_hz,
                                   uint32_t requested_sample_rate_hz,
                                   la_board_timer_plan_t *plan_out) {
  /* Kiểm tra tính hợp lệ của các tham số đầu vào */
  if (timer_clock_hz == 0U || requested_sample_rate_hz == 0U ||
      requested_sample_rate_hz > LA_MAX_SAMPLE_RATE_HZ_TARGET ||
      plan_out == 0) {
    return false;
  }

  /*
   * Tính số tick đồng hồ của Timer cho mỗi chu kỳ lấy mẫu.
   * Sử dụng công thức cộng thêm (requested_sample_rate_hz / 2) để làm tròn số chia tốt nhất.
   */
  const uint64_t rounded_ticks =
      ((uint64_t)timer_clock_hz + (requested_sample_rate_hz / 2U)) /
      requested_sample_rate_hz;
  if (rounded_ticks == 0U) {
    return false;
  }

  /*
   * Tính toán hệ số chia tần (prescaler_factor).
   * Nếu số tick vượt quá giá trị ARR tối đa của Timer (LA_TIMER_MAX_ARR),
   * ta phải chia nhỏ tần số đầu vào bằng Prescaler trước.
   */
  uint64_t prescaler_factor =
      (rounded_ticks + LA_TIMER_MAX_ARR) / (LA_TIMER_MAX_ARR + 1ULL);
  if (prescaler_factor == 0U) {
    prescaler_factor = 1U;
  }
  /* Hệ số chia vượt quá giới hạn tối đa của thanh ghi Prescaler */
  if (prescaler_factor > LA_TIMER_MAX_PRESCALER) {
    return false;
  }

  /*
   * Tính giá trị nạp lại tự động (ARR - Auto-reload Register).
   * ARR = tổng số tick / hệ số chia.
   */
  uint64_t autoreload_ticks = rounded_ticks / prescaler_factor;
  if (autoreload_ticks == 0U) {
    autoreload_ticks = 1U;
  }
  if (autoreload_ticks > (LA_TIMER_MAX_ARR + 1ULL)) {
    autoreload_ticks = LA_TIMER_MAX_ARR + 1ULL;
  }

  /*
   * Tính toán lại tần số lấy mẫu thực tế đạt được dựa trên Prescaler và ARR đã tính.
   * actual_sample_rate_hz = timer_clock_hz / (prescaler * ARR)
   */
  const uint64_t divider = prescaler_factor * autoreload_ticks;
  const uint32_t actual_sample_rate_hz =
      (uint32_t)((uint64_t)timer_clock_hz / divider);
  if (actual_sample_rate_hz == 0U) {
    return false;
  }

  /*
   * Tính độ lệch tần số và sai số theo phần triệu (PPM - Parts Per Million).
   */
  const int64_t rate_difference =
      (int64_t)actual_sample_rate_hz - (int64_t)requested_sample_rate_hz;
  const la_board_timer_plan_t plan = {
      timer_clock_hz,
      requested_sample_rate_hz,
      actual_sample_rate_hz,
      /* Trong STM32, giá trị nạp vào thanh ghi = Hệ số thực tế - 1 */
      (uint32_t)(prescaler_factor - 1ULL),
      (uint32_t)(autoreload_ticks - 1ULL),
      /* Tính sai số PPM */
      (int32_t)((rate_difference * 1000000LL) /
                (int64_t)requested_sample_rate_hz),
  };
  *plan_out = plan;
  return true;
}

/*
 * Kiểm tra xem tần số lấy mẫu yêu cầu có được hỗ trợ bởi phần cứng hay không.
 * using_dma_engine: Có dùng cơ chế DMA không (nếu có, tần số hỗ trợ tối đa sẽ cao hơn).
 */
bool la_board_sample_rate_supported(uint32_t sample_rate_hz,
                                    bool using_dma_engine) {
  /* Lấy giới hạn tần số lớn nhất tùy thuộc chế độ đo DMA hoặc ngắt thường ISR */
  const uint32_t verified_limit = using_dma_engine
                                      ? LA_MAX_SAMPLE_RATE_HZ_TARGET
                                      : LA_MAX_ISR_SAMPLE_RATE_HZ_VERIFIED;
  return sample_rate_hz > 0U && sample_rate_hz <= verified_limit;
}

/*
 * Hàm khởi tạo Timer lấy mẫu (hàm weak, mặc định gán giá trị stub và trả về true).
 */
LA_WEAK bool la_board_timer_init(uint32_t sample_rate_hz,
                                 la_board_timer_plan_t *plan_out) {
  if (plan_out != 0) {
    plan_out->timer_clock_hz = 0U;
    plan_out->requested_sample_rate_hz = sample_rate_hz;
    plan_out->actual_sample_rate_hz = sample_rate_hz;
    plan_out->prescaler = 0U;
    plan_out->autoreload = 0U;
    plan_out->error_ppm = 0;
  }
  return sample_rate_hz != 0U;
}

/*
 * Hàm bắt đầu chạy Timer (hàm weak, mặc định trống).
 */
LA_WEAK void la_board_timer_start(void) {}

/*
 * Hàm dừng chạy Timer (hàm weak, mặc định trống).
 */
LA_WEAK void la_board_timer_stop(void) {}

/*
 * Hàm khởi tạo cổng UART/USB truyền thông (hàm weak, mặc định trống).
 */
LA_WEAK void la_board_uart_or_usb_init(void) {}

/*
 * Hàm gửi dữ liệu capture về máy tính (hàm weak, mặc định chặn luồng/trống).
 */
LA_WEAK void la_board_write_bytes_blocking_after_capture(const uint8_t *data,
                                                         size_t len) {
  (void)data;
  (void)len;
}

/*
 * Hàm đọc trạng thái GPIO 8 kênh (hàm weak).
 * Thường dùng làm stub khi chạy giả lập trên máy tính (host build), firmware thật sẽ override hàm này.
 */
LA_WEAK uint8_t la_board_read_gpio_snapshot_8ch(void) {
  return 0U;
}
