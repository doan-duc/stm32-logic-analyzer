#include "la_board.h"

#if defined(__GNUC__)
#define LA_WEAK __attribute__((weak))
#else
#define LA_WEAK
#endif

LA_WEAK void la_board_init(void) {}

LA_WEAK void la_board_gpio_init_8ch(void) {}

bool la_board_calculate_timer_plan(uint32_t timer_clock_hz,
                                   uint32_t requested_sample_rate_hz,
                                   la_board_timer_plan_t *plan_out) {
  if (timer_clock_hz == 0U || requested_sample_rate_hz == 0U ||
      requested_sample_rate_hz > LA_MAX_SAMPLE_RATE_HZ_TARGET ||
      plan_out == 0) {
    return false;
  }

  const uint64_t rounded_ticks =
      ((uint64_t)timer_clock_hz + (requested_sample_rate_hz / 2U)) /
      requested_sample_rate_hz;
  if (rounded_ticks == 0U) {
    return false;
  }

  uint64_t prescaler_factor =
      (rounded_ticks + LA_TIMER_MAX_ARR) / (LA_TIMER_MAX_ARR + 1ULL);
  if (prescaler_factor == 0U) {
    prescaler_factor = 1U;
  }
  if (prescaler_factor > LA_TIMER_MAX_PRESCALER) {
    return false;
  }

  uint64_t autoreload_ticks = rounded_ticks / prescaler_factor;
  if (autoreload_ticks == 0U) {
    autoreload_ticks = 1U;
  }
  if (autoreload_ticks > (LA_TIMER_MAX_ARR + 1ULL)) {
    autoreload_ticks = LA_TIMER_MAX_ARR + 1ULL;
  }

  const uint64_t divider = prescaler_factor * autoreload_ticks;
  const uint32_t actual_sample_rate_hz =
      (uint32_t)((uint64_t)timer_clock_hz / divider);
  if (actual_sample_rate_hz == 0U) {
    return false;
  }

  const int64_t rate_difference =
      (int64_t)actual_sample_rate_hz - (int64_t)requested_sample_rate_hz;
  const la_board_timer_plan_t plan = {
      timer_clock_hz,
      requested_sample_rate_hz,
      actual_sample_rate_hz,
      (uint32_t)(prescaler_factor - 1ULL),
      (uint32_t)(autoreload_ticks - 1ULL),
      (int32_t)((rate_difference * 1000000LL) /
                (int64_t)requested_sample_rate_hz),
  };
  *plan_out = plan;
  return true;
}

bool la_board_sample_rate_supported(uint32_t sample_rate_hz,
                                    bool using_dma_engine) {
  const uint32_t verified_limit = using_dma_engine
                                      ? LA_MAX_SAMPLE_RATE_HZ_TARGET
                                      : LA_MAX_ISR_SAMPLE_RATE_HZ_VERIFIED;
  return sample_rate_hz > 0U && sample_rate_hz <= verified_limit;
}

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
