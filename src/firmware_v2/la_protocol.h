#ifndef LA_PROTOCOL_H
#define LA_PROTOCOL_H

#include "la_capture.h"

#ifdef __cplusplus
extern "C" {
#endif

#define LA_FRAME_VERSION 2U
#define LA_FRAME_HEADER_LENGTH 48U
#define LA_PAYLOAD_FORMAT_BITPACKED_U8 1U

#define LA_FRAME_FLAG_OVERFLOW 0x00000001UL
#define LA_FRAME_FLAG_NO_TRIGGER 0x00000002UL
#define LA_FRAME_FLAG_ERROR 0x00000004UL

typedef struct {
  uint8_t magic[4];
  uint8_t version;
  uint16_t header_length;
  uint8_t channel_count;
  uint32_t sample_rate_hz;
  uint32_t actual_sample_rate_hz;
  uint32_t total_samples;
  int32_t trigger_index;
  uint32_t flags;
  uint8_t payload_format;
  uint8_t reserved[3];
  uint32_t overflow_count;
  uint32_t dropped_samples;
  uint32_t header_checksum;
  uint32_t payload_checksum;
} la_frame_header_t;

typedef struct {
  uint32_t encoded_length;
  uint32_t header_checksum;
  uint32_t payload_checksum;
} la_frame_result_t;

uint32_t la_checksum32(const uint8_t *data, uint32_t length);
la_error_t la_build_frame_header(const la_capture_context_t *ctx,
                                 uint8_t *header_out,
                                 uint32_t header_capacity,
                                 la_frame_result_t *result);
la_error_t la_encode_frame(const la_capture_context_t *ctx,
                           uint8_t *out,
                           uint32_t out_capacity,
                           la_frame_result_t *result);

#ifdef __cplusplus
}
#endif

#endif
