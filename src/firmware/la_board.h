#ifndef LA_BOARD_H
#define LA_BOARD_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
  uint32_t requested_sample_rate_hz;
  uint32_t actual_sample_rate_hz;
  uint32_t prescaler;
  uint32_t autoreload;
  int32_t error_ppm;
} la_board_timer_plan_t;

void la_board_init(void);
void la_board_gpio_init_8ch(void);
bool la_board_timer_init(uint32_t sample_rate_hz,
                         la_board_timer_plan_t *plan_out);
void la_board_timer_start(void);
void la_board_timer_stop(void);
void la_board_uart_or_usb_init(void);
void la_board_write_bytes_blocking_after_capture(const uint8_t *data,
                                                 size_t len);
uint8_t la_board_read_gpio_snapshot_8ch(void);

#ifdef __cplusplus
}
#endif

#endif
