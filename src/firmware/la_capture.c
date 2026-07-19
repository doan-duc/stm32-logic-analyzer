#include "la_capture.h"

/*
 * Đặt lại trạng thái capture về các giá trị ban đầu mặc định.
 * status: Con trỏ tới cấu trúc trạng thái của phiên capture.
 */
static void la_status_reset(la_capture_status_t *status) {
  status->state = LA_CAPTURE_IDLE;             // Chuyển trạng thái về IDLE (Rảnh rỗi)
  status->write_index = 0U;                     // Chỉ số ghi trong bộ đệm bằng 0
  status->total_samples = 0U;                   // Tổng số mẫu thu thập được bằng 0
  status->trigger_index = -1;                   // Chưa kích hoạt trigger (chỉ số kích hoạt mặc định = -1)
  status->actual_sample_rate_hz = 0U;           // Tần số lấy mẫu thực tế ban đầu bằng 0
  status->overflow_count = 0U;                  // Số lượng lỗi tràn bộ đệm bằng 0
  status->dropped_samples = 0U;                 // Số lượng mẫu bị bỏ lỡ bằng 0
  status->last_error = LA_ERROR_NONE;           // Chưa ghi nhận lỗi nào
}

/*
 * Khởi tạo context capture với cấu trúc dữ liệu mặc định.
 * ctx: Con trỏ tới context lưu trữ thông tin cấu hình và dữ liệu của phiên capture.
 */
void la_capture_init(la_capture_context_t *ctx) {
  if (ctx == 0) {
    return;
  }

  ctx->buffer = 0;                              // Con trỏ bộ đệm chưa được trỏ tới vùng nhớ nào
  ctx->buffer_capacity = 0U;                    // Dung lượng bộ đệm mặc định bằng 0
  la_status_reset(&ctx->status);                // Đặt lại các trường trong status về mặc định
  ctx->previous_sample = 0U;                    // Giá trị mẫu trước đó bằng 0
  ctx->has_previous_sample = false;             // Chưa có mẫu trước đó (dùng cho phát hiện sườn tín hiệu)
  ctx->absolute_sample_index = 0U;              // Chỉ số mẫu tuyệt đối bằng 0
  ctx->ring_count = 0U;                         // Số lượng mẫu hiện tại trong buffer vòng pre-trigger
  ctx->ring_head = 0U;                          // Vị trí đầu đọc/ghi của buffer vòng pre-trigger
  ctx->posttrigger_count = 0U;                  // Số lượng mẫu thu thập được sau trigger bằng 0
  ctx->finalized = false;                       // Chưa hoàn tất đóng gói dữ liệu sau capture
  ctx->trigger_bit = 0U;                        // Bit tương ứng chân trigger bằng 0
  ctx->trigger_mask = 0U;                       // Mặt nạ lọc chân trigger bằng 0
  ctx->trigger_value_masked = 0U;               // Giá trị so khớp trigger sau lọc mặt nạ bằng 0
}

/*
 * Xác thực các tham số cấu hình capture đầu vào để đảm bảo tính hợp lệ trước khi thực hiện đo.
 * config: Cấu hình lấy mẫu.
 * trigger: Cấu hình điều kiện trigger.
 * buffer_capacity: Dung lượng bộ nhớ đệm (RAM) thực tế được cấp phát.
 * Trả về mã lỗi la_error_t.
 */
la_error_t la_capture_validate_config(const la_config_t *config,
                                      const la_trigger_t *trigger,
                                      uint32_t buffer_capacity) {
  if (config == 0 || trigger == 0) {
    return LA_ERROR_NULL;                       // Lỗi con trỏ rỗng
  }
  if (config->sample_rate_hz == 0U) {
    return LA_ERROR_BAD_RATE;                   // Tần số lấy mẫu bằng 0 là không hợp lệ
  }
  if (config->channel_count != LA_CHANNEL_COUNT) {
    return LA_ERROR_BAD_CHANNEL_COUNT;          // Số lượng kênh đo không khớp thiết kế bo mạch (8 kênh)
  }
  if (config->max_samples == 0U) {
    return LA_ERROR_BAD_SAMPLE_COUNT;           // Số mẫu capture tối đa phải lớn hơn 0
  }
  if (buffer_capacity < config->max_samples) {
    return LA_ERROR_BUFFER_TOO_SMALL;           // Dung lượng RAM cấp phát nhỏ hơn số mẫu tối đa yêu cầu
  }
  if (config->pretrigger_samples >= config->max_samples) {
    return LA_ERROR_BAD_SAMPLE_COUNT;           // Mẫu lưu trước trigger phải nhỏ hơn tổng số mẫu tối đa
  }
  if ((config->pretrigger_samples + config->posttrigger_samples + 1U) >
      config->max_samples) {
    return LA_ERROR_BAD_SAMPLE_COUNT;           // Tổng số mẫu yêu cầu vượt quá dung lượng tối đa cấu hình
  }
  if ((trigger->type == LA_TRIGGER_EDGE ||
       trigger->type == LA_TRIGGER_PULSE_WIDTH) &&
      trigger->channel >= LA_CHANNEL_COUNT) {
    return LA_ERROR_BAD_TRIGGER;                 // Chân kích hoạt trigger vượt quá số kênh đo thực tế
  }
  return LA_ERROR_NONE;                         // Không phát hiện lỗi cấu hình
}

/*
 * Chuẩn bị (Arm) hệ thống lấy mẫu trước khi bắt đầu capture.
 * ctx: Context lưu phiên capture.
 * sample_buffer: Địa chỉ vùng đệm RAM chứa mẫu dữ liệu thu thập.
 * buffer_capacity: Kích thước vùng đệm.
 * config: Cấu hình lấy mẫu.
 * trigger: Cấu hình trigger.
 * Trả về mã lỗi la_error_t.
 */
la_error_t la_capture_arm(la_capture_context_t *ctx,
                           uint8_t *sample_buffer,
                           uint32_t buffer_capacity,
                           const la_config_t *config,
                           const la_trigger_t *trigger) {
  if (ctx == 0 || sample_buffer == 0 || config == 0 || trigger == 0) {
    return LA_ERROR_NULL;
  }

  /* Xác thực cấu hình trước khi lưu vào context */
  la_error_t err = la_capture_validate_config(config, trigger, buffer_capacity);
  if (err != LA_ERROR_NONE) {
    ctx->status.last_error = err;
    ctx->status.state = LA_CAPTURE_ERROR;
    return err;
  }

  /* Gán các con trỏ và sao chép cấu hình vào context */
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

  /*
   * Tính toán sẵn (Precompute) các mặt nạ và bit dịch cho việc kích hoạt trigger.
   * Việc tính toán trước này giúp giảm thiểu số lệnh thực thi trong hàm ngắt lấy mẫu (ISR hot-path),
   * giúp nâng cao tần số lấy mẫu tối đa của thiết bị.
   */
  ctx->trigger_bit = (trigger->channel < LA_CHANNEL_COUNT)
                         ? (uint8_t)(1U << trigger->channel)
                         : 0U;
  ctx->trigger_mask = trigger->mask;
  ctx->trigger_value_masked = (uint8_t)(trigger->value & trigger->mask);

  /*
   * Nếu điều kiện trigger là LA_TRIGGER_IMMEDIATE (kích hoạt ngay lập tức),
   * ta chuyển thẳng sang trạng thái TRIGGERED. Ngược lại, chuyển sang WAIT_TRIGGER (đợi trigger).
   */
  ctx->status.state = (trigger->type == LA_TRIGGER_IMMEDIATE)
                           ? LA_CAPTURE_TRIGGERED
                           : LA_CAPTURE_WAIT_TRIGGER;
  return LA_ERROR_NONE;
}

/*
 * Kiểm tra xem trạng thái capture hiện tại có phải là trạng thái kết thúc (Terminal State) hay không.
 * Các trạng thái kết thúc bao gồm: COMPLETE, OVERFLOW, ERROR...
 */
bool la_capture_is_terminal_state(la_capture_state_t state) {
  return la_capture_state_is_terminal_fast(state);
}

/*
 * Hàm xử lý mẫu đo nhanh (fast-path) gọi từ ISR ngắt Timer.
 * Hàm này đọc trạng thái GPIO từ cổng 8 kênh rồi nạp mẫu này vào máy trạng thái capture.
 */
void la_capture_isr_fastpath(la_capture_context_t *ctx) {
  if (ctx == 0 || ctx->buffer == 0) {
    return;
  }
  la_capture_isr_fastpath_sample(ctx, la_board_read_gpio_snapshot_8ch());
}

/*
 * Hàm phụ trợ xoay mảng trái tại chỗ (in-place array rotation).
 * Dùng để sắp xếp lại buffer vòng pre-trigger mà không cần sử dụng bộ nhớ đệm phụ.
 * data: Mảng dữ liệu cần xoay.
 * length: Kích thước mảng.
 * amount: Số phần tử cần xoay.
 */
static void la_rotate_left_u8(uint8_t *data, uint32_t length,
                              uint32_t amount) {
  if (data == 0 || length == 0U) {
    return;
  }
  /* Rút gọn số lượng xoay nếu lượng xoay lớn hơn kích thước mảng */
  while (amount >= length) {
    amount -= length;
  }
  if (amount == 0U) {
    return;
  }

  /* Tìm ước chung lớn nhất (GCD) giữa chiều dài mảng và lượng xoay để thực hiện dịch chuyển tối ưu */
  uint32_t gcd = length;
  uint32_t b = amount;
  while (b != 0U) {
    const uint32_t t = gcd - ((gcd / b) * b);
    gcd = b;
    b = t;
  }

  /* Thuật toán xoay mảng Juggling Algorithm (dựa trên toán học nhóm/ước chung) */
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

/*
 * Hàm hoàn tất và chuẩn hóa bộ đệm dữ liệu sau khi quá trình capture dừng.
 * Do phần pre-trigger hoạt động như bộ đệm vòng (ring buffer) để tối ưu ISR,
 * nên sau khi capture dừng ta phải xoay và sắp xếp lại mảng để đưa dữ liệu về đúng trình tự thời gian:
 * [Pre-trigger Samples sắp xếp theo thứ tự] -> [Trigger Sample] -> [Post-trigger Samples]
 */
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

  /*
   * Nếu bộ đệm vòng pre-trigger đã đầy, thực hiện xoay mảng trái
   * để phần tử đầu tiên (cũ nhất) được đưa về chỉ số 0.
   */
  if (pre_capacity > 0U && pre_count == pre_capacity) {
    la_rotate_left_u8(ctx->buffer, pre_capacity, ctx->ring_head);
  }

  /*
   * Nếu bộ đệm vòng pre-trigger chưa đầy, dịch chuyển các mẫu nằm sau trigger
   * áp sát vào các mẫu pre-trigger để loại bỏ khoảng trống chưa dùng trong RAM.
   */
  if (pre_count < pre_capacity) {
    uint32_t i;
    for (i = 0U; i < payload_after_pre; i++) {
      ctx->buffer[pre_count + i] = ctx->buffer[pre_capacity + i];
    }
  }

  /* Cập nhật chỉ số kích hoạt trigger thực tế và tổng số mẫu thu thập được */
  ctx->status.trigger_index = (int32_t)pre_count;
  ctx->status.total_samples = pre_count + payload_after_pre;
  ctx->status.write_index = ctx->status.total_samples;
  ctx->finalized = true;
}

/*
 * Tính toán và dự đoán ngân sách thời gian (Timing Budget) của CPU.
 * Giúp phát hiện xem CPU có đủ thời gian xử lý mỗi mẫu ở tần số yêu cầu hay không.
 * cpu_freq_hz: Tần số nhân CPU (ví dụ 72 MHz).
 * sample_rate_hz: Tần số lấy mẫu yêu cầu (Hz).
 * estimated_cycles: Ước tính số chu kỳ CPU tiêu tốn cho một lần lấy mẫu (qua ISR hoặc ngắt).
 * Trả về cấu trúc la_timing_budget_t.
 */
la_timing_budget_t la_calculate_timing_budget(uint32_t cpu_freq_hz,
                                              uint32_t sample_rate_hz,
                                              uint32_t estimated_cycles) {
  la_timing_budget_t budget;
  /* Tính tổng số chu kỳ CPU rảnh rỗi giữa mỗi chu kỳ lấy mẫu */
  budget.cycles_per_sample =
      (sample_rate_hz == 0U) ? 0U : (cpu_freq_hz / sample_rate_hz);
  budget.estimated_capture_cycles = estimated_cycles;
  /* Tính khoảng chu kỳ CPU còn dư thừa (margin) */
  budget.estimated_margin_cycles =
      (int32_t)budget.cycles_per_sample - (int32_t)estimated_cycles;
  /*
   * Cảnh báo nếu ngân sách thời gian quá ngặt nghèo (warning_tight_budget):
   * Xảy ra khi số chu kỳ còn dư thừa nhỏ hơn 25% tổng số chu kỳ cần thiết để lấy mẫu.
   */
  budget.warning_tight_budget =
      budget.cycles_per_sample == 0U ||
      budget.estimated_margin_cycles < (int32_t)(estimated_cycles / 4U);
  return budget;
}
