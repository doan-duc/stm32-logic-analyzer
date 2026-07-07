#include "la_protocol.h"

static void la_write_u16_le(uint8_t *out, uint16_t value) {
  out[0] = (uint8_t)(value & 0xFFU);
  out[1] = (uint8_t)((value >> 8) & 0xFFU);
}

static void la_write_u32_le(uint8_t *out, uint32_t value) {
  out[0] = (uint8_t)(value & 0xFFU);
  out[1] = (uint8_t)((value >> 8) & 0xFFU);
  out[2] = (uint8_t)((value >> 16) & 0xFFU);
  out[3] = (uint8_t)((value >> 24) & 0xFFU);
}

uint32_t la_checksum32(const uint8_t *data, uint32_t length) {
  uint32_t checksum = 2166136261UL;
  uint32_t i;
  for (i = 0U; i < length; i++) {
    checksum ^= data[i];
    checksum *= 16777619UL;
  }
  return checksum;
}

static uint32_t la_frame_flags_from_status(const la_capture_status_t *status) {
  uint32_t flags = 0U;
  if (status->overflow_count != 0U || status->state == LA_CAPTURE_OVERFLOW) {
    flags |= LA_FRAME_FLAG_OVERFLOW;
  }
  if (status->state == LA_CAPTURE_NO_TRIGGER) {
    flags |= LA_FRAME_FLAG_NO_TRIGGER;
  }
  if (status->state == LA_CAPTURE_ERROR) {
    flags |= LA_FRAME_FLAG_ERROR;
  }
  return flags;
}

la_error_t la_build_frame_header(const la_capture_context_t *ctx,
                                 uint8_t *header_out,
                                 uint32_t header_capacity,
                                 la_frame_result_t *result) {
  if (ctx == 0 || header_out == 0 || result == 0 || ctx->buffer == 0) {
    return LA_ERROR_NULL;
  }
  if (header_capacity < LA_FRAME_HEADER_LENGTH) {
    return LA_ERROR_FRAME_TOO_SMALL;
  }
  if (ctx->config.channel_count != LA_CHANNEL_COUNT ||
      ctx->config.sample_rate_hz == 0U ||
      ctx->status.total_samples > ctx->buffer_capacity) {
    return LA_ERROR_BAD_SAMPLE_COUNT;
  }

  // Header chua metadata mot lan; timestamp tung mau suy ra tu sample_index/Fs.
  header_out[0] = 'S';
  header_out[1] = 'L';
  header_out[2] = 'A';
  header_out[3] = '8';
  header_out[4] = LA_FRAME_VERSION;
  la_write_u16_le(&header_out[5], LA_FRAME_HEADER_LENGTH);
  header_out[7] = LA_CHANNEL_COUNT;
  la_write_u32_le(&header_out[8], ctx->config.sample_rate_hz);
  la_write_u32_le(&header_out[12],
                  ctx->status.actual_sample_rate_hz != 0U
                      ? ctx->status.actual_sample_rate_hz
                      : ctx->config.sample_rate_hz);
  la_write_u32_le(&header_out[16], ctx->status.total_samples);
  la_write_u32_le(&header_out[20], (uint32_t)ctx->status.trigger_index);
  la_write_u32_le(&header_out[24], la_frame_flags_from_status(&ctx->status));
  header_out[28] = LA_PAYLOAD_FORMAT_BITPACKED_U8;
  header_out[29] = 0U;
  header_out[30] = 0U;
  header_out[31] = 0U;
  la_write_u32_le(&header_out[32], ctx->status.overflow_count);
  la_write_u32_le(&header_out[36], ctx->status.dropped_samples);
  la_write_u32_le(&header_out[40], 0U);
  la_write_u32_le(&header_out[44], 0U);

  const uint32_t header_checksum = la_checksum32(header_out, 40U);
  const uint32_t payload_checksum =
      la_checksum32(ctx->buffer, ctx->status.total_samples);
  la_write_u32_le(&header_out[40], header_checksum);
  la_write_u32_le(&header_out[44], payload_checksum);

  result->encoded_length = LA_FRAME_HEADER_LENGTH + ctx->status.total_samples;
  result->header_checksum = header_checksum;
  result->payload_checksum = payload_checksum;
  return LA_ERROR_NONE;
}

la_error_t la_encode_frame(const la_capture_context_t *ctx,
                           uint8_t *out,
                           uint32_t out_capacity,
                           la_frame_result_t *result) {
  if (ctx == 0 || out == 0 || result == 0) {
    return LA_ERROR_NULL;
  }
  const uint32_t payload_len = ctx->status.total_samples;
  const uint32_t total_len = LA_FRAME_HEADER_LENGTH + payload_len;
  if (out_capacity < total_len) {
    return LA_ERROR_FRAME_TOO_SMALL;
  }

  la_error_t err = la_build_frame_header(ctx, out, LA_FRAME_HEADER_LENGTH,
                                         result);
  if (err != LA_ERROR_NONE) {
    return err;
  }

  uint32_t i;
  for (i = 0U; i < payload_len; i++) {
    out[LA_FRAME_HEADER_LENGTH + i] = ctx->buffer[i];
  }
  result->encoded_length = total_len;
  return LA_ERROR_NONE;
}
