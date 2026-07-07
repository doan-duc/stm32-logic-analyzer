#include "la_uart_tx.h"

void la_uart_tx_send_frame(la_uart_write_fn_t writer, const uint8_t *frame,
                           uint32_t frame_length) {
  if (writer == 0 || frame == 0 || frame_length == 0U) {
    return;
  }
  // Hàm này chỉ được gọi sau capture; không dùng trong ISR để tránh jitter.
  writer(frame, frame_length);
}
