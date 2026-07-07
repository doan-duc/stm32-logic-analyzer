#ifndef LA_BUFFER_H
#define LA_BUFFER_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
  uint8_t *data;
  uint32_t capacity;
  uint32_t count;
  uint32_t head;
} la_ring_buffer_t;

void la_ring_buffer_init(la_ring_buffer_t *ring, uint8_t *storage,
                         uint32_t capacity);
bool la_ring_buffer_push(la_ring_buffer_t *ring, uint8_t sample);
uint32_t la_ring_buffer_copy_chronological(const la_ring_buffer_t *ring,
                                           uint8_t *out,
                                           uint32_t out_capacity);

#ifdef __cplusplus
}
#endif

#endif
