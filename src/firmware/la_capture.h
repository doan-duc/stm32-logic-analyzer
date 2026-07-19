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

/* Magic bytes xác nhận đầu gói tin truyền nhận giữa MCU và PC */
#define LA_FRAME_MAGIC "SLA8"

/* Tần số hoạt động mặc định của CPU là 72 MHz */
#define LA_DEFAULT_CPU_FREQ_HZ 72000000UL

/* Ước tính số chu kỳ CPU tối thiểu cho chế độ ngắt Timer thông thường */
#define LA_ESTIMATED_CAPTURE_CYCLES_TIMER_ISR_SAFE 42UL

/* Ước tính số chu kỳ CPU tối thiểu cho chế độ ngắt Timer tối ưu thanh ghi */
#define LA_ESTIMATED_CAPTURE_CYCLES_TIMER_ISR_DIRECT 28UL

#ifndef LA_ALWAYS_INLINE
#define LA_ALWAYS_INLINE inline __attribute__((always_inline))
#endif

/*
 * Kiểu liệt kê các chế độ lấy mẫu (capture mode):
 * - LA_CAPTURE_MODE_TIMER_ISR_SAFE: Sử dụng ngắt timer an toàn (thông qua HAL/API tiêu chuẩn).
 * - LA_CAPTURE_MODE_TIMER_ISR_DIRECT: Sử dụng ngắt timer ghi thanh ghi trực tiếp để giảm trễ.
 * - LA_CAPTURE_MODE_TIMER_DMA_GPIO_IDR: Sử dụng DMA tự động chuyển dữ liệu từ GPIO vào RAM không qua CPU.
 * - LA_CAPTURE_MODE_EDGE_TIMESTAMP_EXTI: Lấy mẫu lưu timestamp theo sườn tín hiệu sử dụng ngắt ngoài EXTI.
 */
typedef enum {
  LA_CAPTURE_MODE_TIMER_ISR_SAFE = 0,
  LA_CAPTURE_MODE_TIMER_ISR_DIRECT = 1,
  LA_CAPTURE_MODE_TIMER_DMA_GPIO_IDR = 2,
  LA_CAPTURE_MODE_TIMER_DMA_GPIO_IDR_EXPERIMENTAL =
      LA_CAPTURE_MODE_TIMER_DMA_GPIO_IDR,
  LA_CAPTURE_MODE_EDGE_TIMESTAMP_EXTI = 3
} la_capture_mode_t;

/*
 * Các trạng thái trong máy trạng thái capture (capture state machine):
 * - LA_CAPTURE_IDLE: Rảnh rỗi, chờ lệnh.
 * - LA_CAPTURE_ARMED: Đã chuẩn bị bộ đệm sẵn sàng nhận dữ liệu.
 * - LA_CAPTURE_PRETRIGGER: Đang lấy mẫu trước trigger (pre-trigger).
 * - LA_CAPTURE_WAIT_TRIGGER: Đang kiểm tra điều kiện trigger để kích hoạt.
 * - LA_CAPTURE_TRIGGERED: Đã tìm thấy điểm trigger.
 * - LA_CAPTURE_POSTTRIGGER: Đang lấy mẫu sau trigger (post-trigger).
 * - LA_CAPTURE_COMPLETE: Hoàn thành lấy mẫu thành công.
 * - LA_CAPTURE_NO_TRIGGER: Không phát hiện trigger sau khoảng thời gian chờ (timeout).
 * - LA_CAPTURE_OVERFLOW: Lỗi tràn bộ nhớ đệm RAM.
 * - LA_CAPTURE_ERROR: Lỗi hệ thống hoặc cấu hình không hợp lệ.
 */
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

/*
 * Kiểu điều kiện kích hoạt trigger:
 * - LA_TRIGGER_IMMEDIATE: Kích hoạt ngay lập tức (không đợi tín hiệu).
 * - LA_TRIGGER_EDGE: Kích hoạt theo sườn tín hiệu (lên/xuống/bất kỳ).
 * - LA_TRIGGER_PATTERN: Kích hoạt theo mẫu nhị phân trên 8 kênh.
 * - LA_TRIGGER_PULSE_WIDTH: Kích hoạt dựa trên độ rộng xung tín hiệu.
 */
typedef enum {
  LA_TRIGGER_IMMEDIATE = 0,
  LA_TRIGGER_EDGE,
  LA_TRIGGER_PATTERN,
  LA_TRIGGER_PULSE_WIDTH
} la_trigger_type_t;

/*
 * Hướng sườn kích hoạt trigger:
 * - LA_TRIGGER_EDGE_RISING: Sườn lên (từ 0 lên 1).
 * - LA_TRIGGER_EDGE_FALLING: Sườn xuống (từ 1 xuống 0).
 * - LA_TRIGGER_EDGE_ANY: Sườn bất kỳ (đảo trạng thái).
 */
typedef enum {
  LA_TRIGGER_EDGE_RISING = 0,
  LA_TRIGGER_EDGE_FALLING,
  LA_TRIGGER_EDGE_ANY
} la_trigger_edge_t;

/*
 * Định nghĩa mã lỗi phản hồi của Logic Analyzer:
 * - LA_ERROR_NONE: Không lỗi.
 * - LA_ERROR_NULL: Truyền con trỏ rỗng.
 * - LA_ERROR_BAD_RATE: Tần số lấy mẫu không hợp lệ hoặc quá cao.
 * - LA_ERROR_BAD_CHANNEL_COUNT: Số lượng kênh không đúng cấu hình bo mạch.
 * - LA_ERROR_BAD_SAMPLE_COUNT: Số mẫu yêu cầu không hợp lệ.
 * - LA_ERROR_BAD_TRIGGER: Thiết lập trigger bị sai.
 * - LA_ERROR_BUFFER_TOO_SMALL: Vùng đệm RAM cấp phát không đủ dung lượng.
 * - LA_ERROR_FRAME_TOO_SMALL: Khung truyền dữ liệu quá nhỏ.
 * - LA_ERROR_DMA: Lỗi cấu hình hoặc chuyển giao dữ liệu bằng DMA.
 */
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

/*
 * Cấu trúc thông tin cấu hình phiên capture gửi từ PC.
 */
typedef struct {
  uint32_t sample_rate_hz;                      // Tần số lấy mẫu yêu cầu (Hz)
  uint8_t channel_count;                        // Số lượng kênh lấy mẫu
  uint32_t max_samples;                         // Số mẫu capture tối đa
  uint32_t pretrigger_samples;                  // Số lượng mẫu trước trigger cần giữ lại
  uint32_t posttrigger_samples;                 // Số lượng mẫu sau trigger cần lưu trữ
  uint8_t input_mask;                           // Mặt nạ lọc các bit đầu vào GPIO
  uint8_t input_mapping[LA_CHANNEL_COUNT];      // Mảng ánh xạ kênh vật lý sang logic
  la_capture_mode_t capture_mode;               // Chế độ capture (ISR, DMA...)
} la_config_t;

/*
 * Cấu trúc phản hồi trạng thái hiện thời của phiên capture.
 */
typedef struct {
  la_capture_state_t state;                     // Trạng thái hiện thời của máy trạng thái capture
  uint32_t write_index;                         // Vị trí ghi mẫu tiếp theo trong bộ đệm
  uint32_t total_samples;                       // Tổng số mẫu đã thu thập được
  int32_t trigger_index;                        // Chỉ số mảng nơi phát hiện trigger
  uint32_t actual_sample_rate_hz;               // Tần số lấy mẫu thực tế của Timer
  uint32_t overflow_count;                      // Đếm số lần phát hiện lỗi tràn bộ đệm
  uint32_t dropped_samples;                     // Đếm số mẫu bị mất khi bộ đệm vòng ghi đè
  la_error_t last_error;                        // Ghi nhận lỗi cuối cùng xảy ra
} la_capture_status_t;

/*
 * Cấu trúc thiết lập điều kiện kích hoạt trigger.
 */
typedef struct {
  la_trigger_type_t type;                       // Loại trigger (cạnh, mẫu bit...)
  uint8_t channel;                              // Kênh chỉ định làm trigger (0-7)
  la_trigger_edge_t edge;                       // Sườn kích hoạt (lên/xuống...)
  uint8_t mask;                                 // Mặt nạ bit áp dụng cho trigger mẫu bit
  uint8_t value;                                // Giá trị bit cần so khớp
  uint32_t timeout_samples;                     // Thời gian chờ trigger tối đa (tính theo số mẫu)
} la_trigger_t;

/*
 * Cấu trúc lưu thông tin ngân sách chu kỳ CPU để kiểm soát tần số lấy mẫu.
 */
typedef struct {
  uint32_t cycles_per_sample;                   // Số chu kỳ CPU có sẵn cho mỗi mẫu
  uint32_t estimated_capture_cycles;            // Dự tính số chu kỳ CPU mà ngắt lấy mẫu chiếm dụng
  int32_t estimated_margin_cycles;              // Số chu kỳ CPU dư thừa còn lại
  bool warning_tight_budget;                    // Cảnh báo nếu CPU bị quá tải ở tần số này
} la_timing_budget_t;

/*
 * Context điều khiển trung tâm chứa toàn bộ thông tin phiên lấy mẫu.
 */
typedef struct {
  uint8_t *buffer;                              // Con trỏ tới vùng đệm lưu trữ mẫu trong RAM
  uint32_t buffer_capacity;                    // Sức chứa tối đa của vùng đệm (byte)
  la_config_t config;                           // Bản sao cấu hình lấy mẫu hiện tại
  la_trigger_t trigger;                         // Bản sao cấu hình trigger hiện tại
  la_capture_status_t status;                   // Trạng thái capture hiện thời
  uint8_t previous_sample;                      // Mẫu thu được ở chu kỳ ngắt trước đó
  bool has_previous_sample;                     // Cờ báo hiệu đã lưu được mẫu trước đó
  uint32_t absolute_sample_index;              // Đếm số mẫu tuyệt đối từ lúc bắt đầu đo
  uint32_t ring_count;                          // Số lượng mẫu hiện đang lưu trong bộ đệm vòng pre-trigger
  uint32_t ring_head;                           // Con trỏ ghi hiện tại của bộ đệm vòng pre-trigger
  uint32_t posttrigger_count;                  // Đếm số mẫu thu được sau khi trigger kích hoạt
  bool finalized;                               // Cờ báo hiệu bộ đệm đã được sắp xếp chuẩn hóa xong
  uint8_t trigger_bit;                          // Bit mặt nạ của kênh trigger (ví dụ kênh 2 -> 0x04)
  uint8_t trigger_mask;                         // Mặt nạ lọc các bit trigger
  uint8_t trigger_value_masked;                 // Giá trị trigger đã lọc qua mặt nạ
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

/*
 * Hàm inline kiểm tra trạng thái capture hiện tại có phải là trạng thái kết thúc (Terminal State) hay không.
 * Việc đặt inline giúp trình biên dịch nhúng trực tiếp code mà không cần gọi hàm, tối ưu tốc độ thực thi trong ISR.
 */
static LA_ALWAYS_INLINE bool
la_capture_state_is_terminal_fast(la_capture_state_t state) {
  return state == LA_CAPTURE_COMPLETE || state == LA_CAPTURE_NO_TRIGGER ||
         state == LA_CAPTURE_OVERFLOW || state == LA_CAPTURE_ERROR;
}

/*
 * Hàm inline kiểm tra xem mẫu dữ liệu logic hiện tại có thỏa mãn điều kiện trigger đã cấu hình hay không.
 * sample: Mẫu dữ liệu logic hiện thời (8-bit biểu diễn trạng thái 8 kênh).
 */
static LA_ALWAYS_INLINE bool la_capture_trigger_matches_fast(
    const la_capture_context_t *ctx, uint8_t sample) {
  switch (ctx->trigger.type) {
  case LA_TRIGGER_IMMEDIATE:
    /* Kích hoạt ngay lập tức mà không cần kiểm tra điều kiện */
    return true;
  case LA_TRIGGER_PATTERN:
    /* So khớp trạng thái bit của mẫu đo sau khi áp dụng mặt nạ lọc kênh */
    return (uint8_t)(sample & ctx->trigger_mask) == ctx->trigger_value_masked;
  case LA_TRIGGER_EDGE:
    if (!ctx->has_previous_sample) {
      /* Cần có mẫu dữ liệu trước đó để so sánh phát hiện sườn tín hiệu thay đổi */
      return false;
    } else {
      /*
       * Phép toán XOR giúp phát hiện các bit có sự thay đổi trạng thái.
       * Sau đó AND với bit đại diện kênh trigger (ctx->trigger_bit) để lọc riêng kênh quan tâm.
       */
      const uint8_t changed =
          (uint8_t)((sample ^ ctx->previous_sample) & ctx->trigger_bit);
      if (changed == 0U) {
        return false;                           // Không có sự thay đổi trạng thái trên kênh trigger
      }
      if (ctx->trigger.edge == LA_TRIGGER_EDGE_ANY) {
        return true;                            // Kích hoạt khi có sườn bất kỳ (lên hoặc xuống)
      }
      if (ctx->trigger.edge == LA_TRIGGER_EDGE_RISING) {
        /* Kích hoạt sườn lên: Trạng thái hiện tại của kênh trigger phải là mức cao (1) */
        return (changed & sample) != 0U;
      }
      /* Kích hoạt sườn xuống: Trạng thái trước đó của kênh trigger phải là mức cao (1) */
      return (changed & ctx->previous_sample) != 0U;
    }
  default:
    return false;
  }
}

/*
 * Hàm inline ghi một mẫu dữ liệu vào bộ đệm vòng pre-trigger.
 * Do trước khi có trigger kích hoạt, ta chỉ cần giữ lại một số lượng mẫu pre-trigger nhất định,
 * các mẫu cũ hơn sẽ bị ghi đè để tiết kiệm RAM.
 */
static LA_ALWAYS_INLINE void la_capture_store_pretrigger_fast(la_capture_context_t *ctx,
                                                   uint8_t sample) {
  const uint32_t pre = ctx->config.pretrigger_samples;
  if (pre == 0U) {
    return;
  }

  /*
   * Ghi mẫu vào bộ đệm vòng tại vị trí ring_head.
   * Tăng ring_head và kiểm tra vượt giới hạn để quay vòng về 0.
   * Cách so sánh điều kiện này tối ưu hơn nhiều so với phép chia lấy dư (%) trong ISR.
   */
  ctx->buffer[ctx->ring_head] = sample;
  ctx->ring_head++;
  if (ctx->ring_head >= pre) {
    ctx->ring_head = 0U;
  }
  if (ctx->ring_count < pre) {
    ctx->ring_count++;                          // Tăng số mẫu hiện có trong bộ đệm vòng
  } else {
    ctx->status.dropped_samples++;              // Bộ đệm đã đầy, ghi đè mẫu cũ nhất và ghi nhận số mẫu bị ghi đè
  }
}

/*
 * Hàm inline xử lý lưu trữ mẫu kích hoạt trigger (Trigger Sample).
 * Mẫu này được lưu ở một vị trí cố định (slot bằng pretrigger_samples) trong bộ đệm.
 */
static LA_ALWAYS_INLINE void la_capture_commit_trigger_sample_fast(
    la_capture_context_t *ctx, uint8_t trigger_sample) {
  const uint32_t pre_capacity = ctx->config.pretrigger_samples;
  const uint32_t pre_count = ctx->ring_count;
  const uint32_t trigger_slot = pre_capacity;   // Vị trí cố định dành cho mẫu trigger

  ctx->status.trigger_index = (int32_t)pre_count;
  ctx->status.total_samples = pre_count;
  ctx->status.write_index = trigger_slot;

  if (trigger_slot < ctx->config.max_samples) {
    /* Ghi mẫu trigger vào vị trí định sẵn, việc xoay/sắp xếp lại pre-trigger buffer sẽ làm sau */
    ctx->buffer[trigger_slot] = trigger_sample;
    ctx->status.write_index = trigger_slot + 1U;
    ctx->status.total_samples = pre_count + 1U;
    /*
     * Nếu không yêu cầu lấy mẫu sau trigger (posttrigger_samples == 0),
     * phiên capture hoàn thành ngay lập tức. Ngược lại chuyển sang post-trigger.
     */
    ctx->status.state = (ctx->config.posttrigger_samples == 0U)
                            ? LA_CAPTURE_COMPLETE
                            : LA_CAPTURE_POSTTRIGGER;
  } else {
    /* Đề phòng trường hợp lỗi tràn bộ đệm */
    ctx->status.overflow_count++;
    ctx->status.state = LA_CAPTURE_OVERFLOW;
  }
}

/*
 * Hàm inline lưu trữ các mẫu dữ liệu thu được sau điểm kích hoạt trigger.
 */
static LA_ALWAYS_INLINE void la_capture_store_posttrigger_fast(la_capture_context_t *ctx,
                                                     uint8_t sample) {
  /* Vị trí vật lý trong mảng: bằng số lượng mẫu pre-trigger + 1 (mẫu trigger) + số mẫu post-trigger hiện tại */
  const uint32_t physical_index =
      ctx->config.pretrigger_samples + 1U + ctx->posttrigger_count;
  if (physical_index >= ctx->config.max_samples) {
    /* Nếu vượt quá sức chứa tối đa của bộ đệm, dừng lấy mẫu và báo lỗi tràn */
    ctx->status.overflow_count++;
    ctx->status.state = LA_CAPTURE_OVERFLOW;
    return;
  }

  ctx->buffer[physical_index] = sample;         // Ghi mẫu vào bộ đệm
  ctx->posttrigger_count++;                     // Tăng số đếm mẫu post-trigger
  ctx->status.write_index = physical_index + 1U;
  ctx->status.total_samples =
      ctx->ring_count + 1U + ctx->posttrigger_count;

  /* Nếu đã thu thập đủ số mẫu post-trigger yêu cầu hoặc chạm mốc giới hạn mảng, kết thúc capture */
  if (ctx->posttrigger_count >= ctx->config.posttrigger_samples ||
      ctx->status.total_samples >= ctx->config.max_samples) {
    ctx->status.state = LA_CAPTURE_COMPLETE;
  }
}

/*
 * Máy trạng thái xử lý mẫu chính trong hàm ngắt lấy mẫu (ISR Hot-path).
 * Hàm này quyết định cách xử lý mẫu đo hiện tại dựa trên trạng thái hoạt động:
 * - Lọc nhiễu qua input_mask.
 * - Ghi nhận trực tiếp nếu ở trạng thái TRIGGERED / POSTTRIGGER.
 * - So khớp điều kiện trigger để kích hoạt.
 * - Ghi vào bộ đệm vòng pre-trigger và tăng bộ đếm thời gian chờ (timeout) nếu chưa trigger.
 */
static LA_ALWAYS_INLINE void la_capture_isr_fastpath_sample(la_capture_context_t *ctx,
                                                   uint8_t sample) {
  la_capture_state_t state = ctx->status.state;
  /* Nếu hệ thống rảnh rỗi hoặc đã kết thúc phiên đo, bỏ qua mẫu này */
  if (state == LA_CAPTURE_IDLE || la_capture_state_is_terminal_fast(state)) {
    return;
  }

  /* Lọc các bit đầu vào không dùng tới bằng mặt nạ cấu hình */
  sample = (uint8_t)(sample & ctx->config.input_mask);

  if (state == LA_CAPTURE_TRIGGERED) {
    /* Đã trigger trước đó, thực hiện lưu mẫu trigger */
    la_capture_commit_trigger_sample_fast(ctx, sample);
  } else if (state == LA_CAPTURE_POSTTRIGGER) {
    /* Đang trong giai đoạn lưu các mẫu sau trigger */
    la_capture_store_posttrigger_fast(ctx, sample);
  } else if (la_capture_trigger_matches_fast(ctx, sample)) {
    /* Chưa trigger, thực hiện so khớp trigger. Nếu khớp, lưu mẫu kích hoạt */
    la_capture_commit_trigger_sample_fast(ctx, sample);
  } else {
    /* Chưa trigger và chưa khớp điều kiện, tiếp tục lưu vào bộ đệm vòng pre-trigger */
    la_capture_store_pretrigger_fast(ctx, sample);
    /* Kiểm tra thời gian chờ trigger tối đa (nếu cấu hình) để dừng khi hết thời gian chờ */
    if (ctx->trigger.timeout_samples > 0U &&
        (ctx->absolute_sample_index + 1U) >= ctx->trigger.timeout_samples) {
      ctx->status.state = LA_CAPTURE_NO_TRIGGER;
    }
  }

  /* Cập nhật thông tin mẫu trước đó để phục vụ lần ngắt tiếp theo */
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
