#ifndef LA_UART_TX_H
#define LA_UART_TX_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*la_uart_write_fn_t)(const uint8_t *data, uint32_t length);

void la_uart_tx_send_frame(la_uart_write_fn_t writer, const uint8_t *frame,
                           uint32_t frame_length);

#ifdef __cplusplus
}
#endif

#endif
