#include "la_buffer.h"

void la_ring_buffer_init(la_ring_buffer_t *ring, uint8_t *storage,
                         uint32_t capacity) {
  if (ring == 0) {
    return;
  }
  ring->data = storage;
  ring->capacity = capacity;
  ring->count = 0U;
  ring->head = 0U;
}

bool la_ring_buffer_push(la_ring_buffer_t *ring, uint8_t sample) {
  if (ring == 0 || ring->data == 0 || ring->capacity == 0U) {
    return false;
  }
  // Tang co dieu kien de tranh modulo neu helper nay duoc dung trong ISR.
  ring->data[ring->head] = sample;
  ring->head++;
  if (ring->head >= ring->capacity) {
    ring->head = 0U;
  }
  if (ring->count < ring->capacity) {
    ring->count++;
  }
  return true;
}

uint32_t la_ring_buffer_copy_chronological(const la_ring_buffer_t *ring,
                                           uint8_t *out,
                                           uint32_t out_capacity) {
  if (ring == 0 || out == 0 || ring->data == 0 || ring->capacity == 0U) {
    return 0U;
  }
  const uint32_t count =
      (ring->count < out_capacity) ? ring->count : out_capacity;
  uint32_t src = ring->head + ring->capacity - count;
  if (src >= ring->capacity) {
    src -= ring->capacity;
  }
  uint32_t i;
  for (i = 0U; i < count; i++) {
    out[i] = ring->data[src];
    src++;
    if (src >= ring->capacity) {
      src = 0U;
    }
  }
  return count;
}
