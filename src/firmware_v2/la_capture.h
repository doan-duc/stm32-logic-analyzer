#ifndef LA_CAPTURE_H
#define LA_CAPTURE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#ifndef LA_CHANNEL_COUNT
#define LA_CHANNEL_COUNT 8U
#endif

#define LA_FRAME_MAGIC "SLA8"
#define LA_DEFAULT_CPU_FREQ_HZ 72000000UL
#define LA_ESTIMATED_CAPTURE_CYCLES_TIMER_ISR_SAFE 42UL
#define LA_ESTIMATED_CAPTURE_CYCLES_TIMER_ISR_DIRECT 28UL

#ifndef LA_ALWAYS_INLINE
#define LA_ALWAYS_INLINE inline __attribute__((always_inline))
#endif

typedef enum {
  LA_CAPTURE_MODE_TIMER_ISR_SAFE = 0,
  LA_CAPTURE_MODE_TIMER_ISR_DIRECT = 1,
  LA_CAPTURE_MODE_TIMER_DMA_GPIO_IDR = 2,
  LA_CAPTURE_MODE_TIMER_DMA_GPIO_IDR_EXPERIMENTAL =
      LA_CAPTURE_MODE_TIMER_DMA_GPIO_IDR,
  LA_CAPTURE_MODE_EDGE_TIMESTAMP_EXTI = 3
} la_capture_mode_t;

typedef enum {
  LA_CAPTURE_IDLE = 0,
  LA_CAPTURE_ARMED,
  LA_CAPTURE_PRETRIGGER,
  LA_CAPTURE_WAIT_TRIGGER,
  LA_CAPTURE_TRIGGERED,
  LA_CAPTURE_POSTTRIGGER,
  LA_CAPTURE_COMPLETE,
  LA_CAPTURE_NO_TRIGGER,
  LA_CAPTURE_OVERFLOW,
  LA_CAPTURE_ERROR
} la_capture_state_t;

typedef enum {
  LA_TRIGGER_IMMEDIATE = 0,
  LA_TRIGGER_EDGE,
  LA_TRIGGER_PATTERN,
  LA_TRIGGER_PULSE_WIDTH
} la_trigger_type_t;

typedef enum {
  LA_TRIGGER_EDGE_RISING = 0,
  LA_TRIGGER_EDGE_FALLING,
  LA_TRIGGER_EDGE_ANY
} la_trigger_edge_t;

typedef enum {
  LA_ERROR_NONE = 0,
  LA_ERROR_NULL,
  LA_ERROR_BAD_RATE,
  LA_ERROR_BAD_CHANNEL_COUNT,
  LA_ERROR_BAD_SAMPLE_COUNT,
  LA_ERROR_BAD_TRIGGER,
  LA_ERROR_BUFFER_TOO_SMALL,
  LA_ERROR_FRAME_TOO_SMALL,
  LA_ERROR_DMA
} la_error_t;

typedef struct {
  uint32_t sample_rate_hz;
  uint8_t channel_count;
  uint32_t max_samples;
  uint32_t pretrigger_samples;
  uint32_t posttrigger_samples;
  uint8_t input_mask;
  uint8_t input_mapping[LA_CHANNEL_COUNT];
  la_capture_mode_t capture_mode;
} la_config_t;

typedef struct {
  la_capture_state_t state;
  uint32_t write_index;
  uint32_t total_samples;
  int32_t trigger_index;
  uint32_t actual_sample_rate_hz;
  uint32_t overflow_count;
  uint32_t dropped_samples;
  la_error_t last_error;
} la_capture_status_t;

typedef struct {
  la_trigger_type_t type;
  uint8_t channel;
  la_trigger_edge_t edge;
  uint8_t mask;
  uint8_t value;
  uint32_t timeout_samples;
} la_trigger_t;

typedef struct {
  uint32_t cycles_per_sample;
  uint32_t estimated_capture_cycles;
  int32_t estimated_margin_cycles;
  bool warning_tight_budget;
} la_timing_budget_t;

typedef struct {
  uint8_t *buffer;
  uint32_t buffer_capacity;
  la_config_t config;
  la_trigger_t trigger;
  la_capture_status_t status;
  uint8_t previous_sample;
  bool has_previous_sample;
  uint32_t absolute_sample_index;
  uint32_t ring_count;
  uint32_t ring_head;
  uint32_t posttrigger_count;
  bool finalized;
  uint8_t trigger_bit;
  uint8_t trigger_mask;
  uint8_t trigger_value_masked;
} la_capture_context_t;

void la_capture_init(la_capture_context_t *ctx);
la_error_t la_capture_validate_config(const la_config_t *config,
                                      const la_trigger_t *trigger,
                                      uint32_t buffer_capacity);
la_error_t la_capture_arm(la_capture_context_t *ctx,
                          uint8_t *sample_buffer,
                          uint32_t buffer_capacity,
                          const la_config_t *config,
                          const la_trigger_t *trigger);
void la_capture_isr_fastpath(la_capture_context_t *ctx);
static LA_ALWAYS_INLINE bool
la_capture_state_is_terminal_fast(la_capture_state_t state) {
  return state == LA_CAPTURE_COMPLETE || state == LA_CAPTURE_NO_TRIGGER ||
         state == LA_CAPTURE_OVERFLOW || state == LA_CAPTURE_ERROR;
}

static LA_ALWAYS_INLINE bool la_capture_trigger_matches_fast(
    const la_capture_context_t *ctx, uint8_t sample) {
  switch (ctx->trigger.type) {
  case LA_TRIGGER_IMMEDIATE:
    return true;
  case LA_TRIGGER_PATTERN:
    return (uint8_t)(sample & ctx->trigger_mask) == ctx->trigger_value_masked;
  case LA_TRIGGER_EDGE:
    if (!ctx->has_previous_sample) {
      return false;
    } else {
      // Tinh canh bang XOR/AND tren bit da precompute truoc khi arm.
      const uint8_t changed =
          (uint8_t)((sample ^ ctx->previous_sample) & ctx->trigger_bit);
      if (changed == 0U) {
        return false;
      }
      if (ctx->trigger.edge == LA_TRIGGER_EDGE_ANY) {
        return true;
      }
      if (ctx->trigger.edge == LA_TRIGGER_EDGE_RISING) {
        return (changed & sample) != 0U;
      }
      return (changed & ctx->previous_sample) != 0U;
    }
  default:
    return false;
  }
}

static LA_ALWAYS_INLINE void la_capture_store_pretrigger_fast(la_capture_context_t *ctx,
                                                   uint8_t sample) {
  const uint32_t pre = ctx->config.pretrigger_samples;
  if (pre == 0U) {
    return;
  }

  // Tang co dieu kien de tranh phep chia modulo trong ISR.
  ctx->buffer[ctx->ring_head] = sample;
  ctx->ring_head++;
  if (ctx->ring_head >= pre) {
    ctx->ring_head = 0U;
  }
  if (ctx->ring_count < pre) {
    ctx->ring_count++;
  } else {
    ctx->status.dropped_samples++;
  }
}

static LA_ALWAYS_INLINE void la_capture_commit_trigger_sample_fast(
    la_capture_context_t *ctx, uint8_t trigger_sample) {
  const uint32_t pre_capacity = ctx->config.pretrigger_samples;
  const uint32_t pre_count = ctx->ring_count;
  const uint32_t trigger_slot = pre_capacity;

  ctx->status.trigger_index = (int32_t)pre_count;
  ctx->status.total_samples = pre_count;
  ctx->status.write_index = trigger_slot;

  if (trigger_slot < ctx->config.max_samples) {
    // Trigger ghi vao slot co dinh; sap xep ring sau khi capture dung.
    ctx->buffer[trigger_slot] = trigger_sample;
    ctx->status.write_index = trigger_slot + 1U;
    ctx->status.total_samples = pre_count + 1U;
    ctx->status.state = (ctx->config.posttrigger_samples == 0U)
                            ? LA_CAPTURE_COMPLETE
                            : LA_CAPTURE_POSTTRIGGER;
  } else {
    ctx->status.overflow_count++;
    ctx->status.state = LA_CAPTURE_OVERFLOW;
  }
}

static LA_ALWAYS_INLINE void la_capture_store_posttrigger_fast(la_capture_context_t *ctx,
                                                    uint8_t sample) {
  const uint32_t physical_index =
      ctx->config.pretrigger_samples + 1U + ctx->posttrigger_count;
  if (physical_index >= ctx->config.max_samples) {
    ctx->status.overflow_count++;
    ctx->status.state = LA_CAPTURE_OVERFLOW;
    return;
  }

  ctx->buffer[physical_index] = sample;
  ctx->posttrigger_count++;
  ctx->status.write_index = physical_index + 1U;
  ctx->status.total_samples =
      ctx->ring_count + 1U + ctx->posttrigger_count;

  if (ctx->posttrigger_count >= ctx->config.posttrigger_samples ||
      ctx->status.total_samples >= ctx->config.max_samples) {
    ctx->status.state = LA_CAPTURE_COMPLETE;
  }
}

static LA_ALWAYS_INLINE void la_capture_isr_fastpath_sample(la_capture_context_t *ctx,
                                                  uint8_t sample) {
  la_capture_state_t state = ctx->status.state;
  if (state == LA_CAPTURE_IDLE || la_capture_state_is_terminal_fast(state)) {
    return;
  }

  sample = (uint8_t)(sample & ctx->config.input_mask);

  if (state == LA_CAPTURE_TRIGGERED) {
    la_capture_commit_trigger_sample_fast(ctx, sample);
  } else if (state == LA_CAPTURE_POSTTRIGGER) {
    la_capture_store_posttrigger_fast(ctx, sample);
  } else if (la_capture_trigger_matches_fast(ctx, sample)) {
    la_capture_commit_trigger_sample_fast(ctx, sample);
  } else {
    la_capture_store_pretrigger_fast(ctx, sample);
    if (ctx->trigger.timeout_samples > 0U &&
        (ctx->absolute_sample_index + 1U) >= ctx->trigger.timeout_samples) {
      ctx->status.state = LA_CAPTURE_NO_TRIGGER;
    }
  }

  ctx->previous_sample = sample;
  ctx->has_previous_sample = true;
  ctx->absolute_sample_index++;
}

void la_capture_finalize_after_stop(la_capture_context_t *ctx);
bool la_capture_is_terminal_state(la_capture_state_t state);
la_timing_budget_t la_calculate_timing_budget(uint32_t cpu_freq_hz,
                                              uint32_t sample_rate_hz,
                                              uint32_t estimated_cycles);

uint8_t la_board_read_gpio_snapshot_8ch(void);
void la_benchmark_init(void);
void la_benchmark_start_cycles(void);
void la_benchmark_stop_cycles(void);
bool la_benchmark_is_available(void);
uint32_t la_benchmark_get_last_isr_cycles(void);
uint32_t la_benchmark_get_max_isr_cycles(void);
uint32_t la_benchmark_get_min_isr_cycles(void);
uint32_t la_benchmark_get_average_isr_cycles(void);
uint32_t la_benchmark_get_sample_count(void);

#ifdef __cplusplus
}
#endif

#endif
