#include "la_capture.h"

static void la_status_reset(la_capture_status_t *status) {
  status->state = LA_CAPTURE_IDLE;
  status->write_index = 0U;
  status->total_samples = 0U;
  status->trigger_index = -1;
  status->actual_sample_rate_hz = 0U;
  status->overflow_count = 0U;
  status->dropped_samples = 0U;
  status->last_error = LA_ERROR_NONE;
}

void la_capture_init(la_capture_context_t *ctx) {
  if (ctx == 0) {
    return;
  }

  ctx->buffer = 0;
  ctx->buffer_capacity = 0U;
  la_status_reset(&ctx->status);
  ctx->previous_sample = 0U;
  ctx->has_previous_sample = false;
  ctx->absolute_sample_index = 0U;
  ctx->ring_count = 0U;
  ctx->ring_head = 0U;
  ctx->posttrigger_count = 0U;
  ctx->finalized = false;
  ctx->trigger_bit = 0U;
  ctx->trigger_mask = 0U;
  ctx->trigger_value_masked = 0U;
}

la_error_t la_capture_validate_config(const la_config_t *config,
                                      const la_trigger_t *trigger,
                                      uint32_t buffer_capacity) {
  if (config == 0 || trigger == 0) {
    return LA_ERROR_NULL;
  }
  if (config->sample_rate_hz == 0U) {
    return LA_ERROR_BAD_RATE;
  }
  if (config->channel_count != LA_CHANNEL_COUNT) {
    return LA_ERROR_BAD_CHANNEL_COUNT;
  }
  if (config->max_samples == 0U) {
    return LA_ERROR_BAD_SAMPLE_COUNT;
  }
  if (buffer_capacity < config->max_samples) {
    return LA_ERROR_BUFFER_TOO_SMALL;
  }
  if (config->pretrigger_samples >= config->max_samples) {
    return LA_ERROR_BAD_SAMPLE_COUNT;
  }
  if ((config->pretrigger_samples + config->posttrigger_samples + 1U) >
      config->max_samples) {
    return LA_ERROR_BAD_SAMPLE_COUNT;
  }
  if ((trigger->type == LA_TRIGGER_EDGE ||
       trigger->type == LA_TRIGGER_PULSE_WIDTH) &&
      trigger->channel >= LA_CHANNEL_COUNT) {
    return LA_ERROR_BAD_TRIGGER;
  }
  return LA_ERROR_NONE;
}

la_error_t la_capture_arm(la_capture_context_t *ctx,
                          uint8_t *sample_buffer,
                          uint32_t buffer_capacity,
                          const la_config_t *config,
                          const la_trigger_t *trigger) {
  if (ctx == 0 || sample_buffer == 0 || config == 0 || trigger == 0) {
    return LA_ERROR_NULL;
  }

  la_error_t err = la_capture_validate_config(config, trigger, buffer_capacity);
  if (err != LA_ERROR_NONE) {
    ctx->status.last_error = err;
    ctx->status.state = LA_CAPTURE_ERROR;
    return err;
  }

  ctx->buffer = sample_buffer;
  ctx->buffer_capacity = buffer_capacity;
  ctx->config = *config;
  ctx->trigger = *trigger;
  la_status_reset(&ctx->status);
  ctx->previous_sample = 0U;
  ctx->has_previous_sample = false;
  ctx->absolute_sample_index = 0U;
  ctx->ring_count = 0U;
  ctx->ring_head = 0U;
  ctx->posttrigger_count = 0U;
  ctx->finalized = false;
  ctx->status.actual_sample_rate_hz = config->sample_rate_hz;

  // Precompute truoc khi arm de ISR khong tinh shift/mask lap lai.
  ctx->trigger_bit = (trigger->channel < LA_CHANNEL_COUNT)
                         ? (uint8_t)(1U << trigger->channel)
                         : 0U;
  ctx->trigger_mask = trigger->mask;
  ctx->trigger_value_masked = (uint8_t)(trigger->value & trigger->mask);

  ctx->status.state = (trigger->type == LA_TRIGGER_IMMEDIATE)
                          ? LA_CAPTURE_TRIGGERED
                          : LA_CAPTURE_WAIT_TRIGGER;
  return LA_ERROR_NONE;
}

bool la_capture_is_terminal_state(la_capture_state_t state) {
  return la_capture_state_is_terminal_fast(state);
}

void la_capture_isr_fastpath(la_capture_context_t *ctx) {
  if (ctx == 0 || ctx->buffer == 0) {
    return;
  }
  la_capture_isr_fastpath_sample(ctx, la_board_read_gpio_snapshot_8ch());
}

static void la_rotate_left_u8(uint8_t *data, uint32_t length,
                              uint32_t amount) {
  if (data == 0 || length == 0U) {
    return;
  }
  while (amount >= length) {
    amount -= length;
  }
  if (amount == 0U) {
    return;
  }

  uint32_t gcd = length;
  uint32_t b = amount;
  while (b != 0U) {
    const uint32_t t = gcd - ((gcd / b) * b);
    gcd = b;
    b = t;
  }

  uint32_t start;
  for (start = 0U; start < gcd; start++) {
    uint8_t temp = data[start];
    uint32_t current = start;
    while (true) {
      uint32_t next = current + amount;
      if (next >= length) {
        next -= length;
      }
      if (next == start) {
        break;
      }
      data[current] = data[next];
      current = next;
    }
    data[current] = temp;
  }
}

void la_capture_finalize_after_stop(la_capture_context_t *ctx) {
  if (ctx == 0 || ctx->buffer == 0 || ctx->finalized) {
    return;
  }
  if (ctx->status.state != LA_CAPTURE_COMPLETE &&
      ctx->status.state != LA_CAPTURE_OVERFLOW) {
    ctx->finalized = true;
    return;
  }

  const uint32_t pre_capacity = ctx->config.pretrigger_samples;
  const uint32_t pre_count = ctx->ring_count;
  const uint32_t payload_after_pre = 1U + ctx->posttrigger_count;

  if (pre_capacity > 0U && pre_count == pre_capacity) {
    // Sap xep ring pre-trigger ngoai ISR de hot path khong co vong copy dai.
    la_rotate_left_u8(ctx->buffer, pre_capacity, ctx->ring_head);
  }

  if (pre_count < pre_capacity) {
    uint32_t i;
    for (i = 0U; i < payload_after_pre; i++) {
      ctx->buffer[pre_count + i] = ctx->buffer[pre_capacity + i];
    }
  }

  ctx->status.trigger_index = (int32_t)pre_count;
  ctx->status.total_samples = pre_count + payload_after_pre;
  ctx->status.write_index = ctx->status.total_samples;
  ctx->finalized = true;
}

la_timing_budget_t la_calculate_timing_budget(uint32_t cpu_freq_hz,
                                              uint32_t sample_rate_hz,
                                              uint32_t estimated_cycles) {
  la_timing_budget_t budget;
  budget.cycles_per_sample =
      (sample_rate_hz == 0U) ? 0U : (cpu_freq_hz / sample_rate_hz);
  budget.estimated_capture_cycles = estimated_cycles;
  budget.estimated_margin_cycles =
      (int32_t)budget.cycles_per_sample - (int32_t)estimated_cycles;
  budget.warning_tight_budget =
      budget.cycles_per_sample == 0U ||
      budget.estimated_margin_cycles < (int32_t)(estimated_cycles / 4U);
  return budget;
}
