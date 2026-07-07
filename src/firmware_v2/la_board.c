#include "la_board.h"

#if defined(__GNUC__)
#define LA_WEAK __attribute__((weak))
#else
#define LA_WEAK
#endif

LA_WEAK void la_board_init(void) {}

LA_WEAK void la_board_gpio_init_8ch(void) {}

LA_WEAK bool la_board_timer_init(uint32_t sample_rate_hz,
                                 la_board_timer_plan_t *plan_out) {
  if (plan_out != 0) {
    plan_out->requested_sample_rate_hz = sample_rate_hz;
    plan_out->actual_sample_rate_hz = sample_rate_hz;
    plan_out->prescaler = 0U;
    plan_out->autoreload = 0U;
    plan_out->error_ppm = 0;
  }
  return sample_rate_hz != 0U;
}

LA_WEAK void la_board_timer_start(void) {}

LA_WEAK void la_board_timer_stop(void) {}

LA_WEAK void la_board_uart_or_usb_init(void) {}

LA_WEAK void la_board_write_bytes_blocking_after_capture(const uint8_t *data,
                                                         size_t len) {
  (void)data;
  (void)len;
}

LA_WEAK uint8_t la_board_read_gpio_snapshot_8ch(void) {
  // Stub dung cho build host; firmware that se override bang doc GPIO IDR.
  return 0U;
}
