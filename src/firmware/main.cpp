#include <Arduino.h>
#include "board_config.h"
#if !LA_USE_DIRECT_TIMER_IRQ
#include <HardwareTimer.h>
#endif
#include <ctype.h>
#include <string.h>

extern "C" {
#include "la_board.h"
#include "la_capture.h"
#include "la_protocol.h"
}

/* Định nghĩa chân LED mặc định là PC13 (đèn LED onboard của bo mạch Blue Pill) */
#ifndef LED_BUILTIN
#define LED_BUILTIN PC13
#endif

/*
 * Kiểm tra xem các macro của DMA1 Channel 2 và các thanh ghi liên quan có tồn tại không
 * để quyết định xem có biên dịch phần mềm hỗ trợ chế độ DMA capture hay không.
 */
#if LA_ENABLE_DMA_CAPTURE && defined(DMA1) && defined(DMA1_Channel2) &&        \
    defined(DMA_CCR_EN) && defined(DMA_CCR_PSIZE_1) && defined(TIM_DIER_UDE)
#define LA_DMA_CAPTURE_COMPILED 1
#else
#define LA_DMA_CAPTURE_COMPILED 0
#endif

/*
 * Thiết lập chế độ lấy mẫu mặc định lúc khởi động:
 * - Nếu có DMA: Sử dụng chế độ lấy mẫu qua DMA (TIM2 kích hoạt DMA đọc trực tiếp GPIO IDR).
 * - Nếu không có DMA: Fallback về chế độ lấy mẫu dùng ngắt Timer trực tiếp (ISR).
 */
#if LA_DMA_CAPTURE_COMPILED
#define LA_DEFAULT_CAPTURE_MODE LA_CAPTURE_MODE_TIMER_DMA_GPIO_IDR
#else
#define LA_DEFAULT_CAPTURE_MODE LA_CAPTURE_MODE_TIMER_ISR_DIRECT
#endif

#if LA_DMA_CAPTURE_COMPILED
#define LA_DMA_CHANNEL DMA1_Channel2                  // Kênh DMA mặc định cho TIM2_UP
#define LA_DMA_IRQN DMA1_Channel2_IRQn                // Ngắt DMA tương ứng
/* Các cờ xóa trạng thái ngắt DMA Channel 2 (Global, Transfer Complete, Half Transfer, Transfer Error) */
#define LA_DMA_CLEAR_FLAGS                                                    \
  (DMA_IFCR_CGIF2 | DMA_IFCR_CTCIF2 | DMA_IFCR_CHTIF2 | DMA_IFCR_CTEIF2)
#endif

/* Khởi tạo cổng truyền thông nối tiếp UART dùng chân cấu hình trong board_config.h */
static HardwareSerial AnalyzerSerial(LA_UART_RX_PIN, LA_UART_TX_PIN);
#if !LA_USE_DIRECT_TIMER_IRQ
static HardwareTimer sampleTimer(LA_TIMER_INSTANCE);
static bool timerInterruptAttached = false;
#endif

/*
 * Bộ nhớ đệm RAM lưu trữ các mẫu logic thu thập được.
 * Đảm bảo căn lề 4 bytes (aligned(4)) để CPU ARM Cortex-M truy xuất nhanh nhất.
 */
static LA_SAMPLE_TYPE captureStorage[LA_CAPTURE_BUFFER_SAMPLES]
    __attribute__((aligned(4)));

/* Bộ nhớ đệm lưu trữ phần Header gói tin trước khi gửi đi */
static uint8_t frameHeaderStorage[LA_FRAME_HEADER_LENGTH]
    __attribute__((aligned(4)));

/* Context trung tâm lưu thông tin trạng thái phiên lấy mẫu */
static la_capture_context_t captureContext;

/* Biến cờ báo hiệu phiên capture đã chạm tới trạng thái kết thúc (COMPLETE, OVERFLOW...) */
static volatile bool terminalStateSeen = false;

/* Lưu trữ chế độ capture engine hiện tại đang chạy (ISR hay DMA) */
static volatile uint8_t activeCaptureEngine = LA_CAPTURE_MODE_TIMER_ISR_DIRECT;

/* Bộ đếm số lần hàm ngắt lấy mẫu (ISR) bị quá tải (không xử lý kịp trước ngắt kế tiếp) */
static volatile uint32_t timerIsrOverrunCount = 0U;

#if LA_DMA_CAPTURE_COMPILED
/* Số lượng mẫu yêu cầu thu thập bằng DMA hiện thời */
static volatile uint32_t activeDmaSampleCount = 0U;
/* Bộ đếm số lượng lỗi xảy ra trong quá trình truyền dữ liệu DMA */
static volatile uint32_t dmaTransferErrors = 0U;
#endif

/* Các ký hiệu phân vùng vùng nhớ linker script để đo dung lượng RAM tĩnh và Heap */
extern "C" char _end;      // Địa chỉ kết thúc của phân vùng RAM tĩnh (BSS/DATA)
extern "C" char _estack;   // Địa chỉ bắt đầu của Stack (đỉnh RAM)

/* Vùng đệm chứa dòng lệnh nhận được từ cổng Serial */
static char commandBuffer[96];
static uint8_t commandLength = 0U;

/* Cấu hình bộ Timer hiện tại */
static la_board_timer_plan_t activeTimerPlan = {
    0U,
    LA_DEFAULT_SAMPLE_RATE_HZ,
    LA_DEFAULT_SAMPLE_RATE_HZ,
    0U,
    0U,
    0,
};

/* Cấu hình phiên lấy mẫu hiện hành */
static la_config_t activeConfig = {
    LA_DEFAULT_SAMPLE_RATE_HZ,
    LA_CHANNEL_COUNT,
    LA_CAPTURE_BUFFER_SAMPLES,
    LA_DEFAULT_PRETRIGGER_SAMPLES,
    LA_DEFAULT_POSTTRIGGER_SAMPLES,
    0xFFU,
    {0, 1, 2, 3, 4, 5, 6, 7},
    LA_DEFAULT_CAPTURE_MODE,
};

/* Cấu hình điều kiện kích hoạt trigger hiện hành */
static la_trigger_t activeTrigger = {
    LA_TRIGGER_IMMEDIATE,
    0U,
    LA_TRIGGER_EDGE_RISING,
    0xFFU,
    0U,
    LA_CAPTURE_BUFFER_SAMPLES,
};

/*
 * Kiểm tra xem hệ thống lấy mẫu hiện tại có đang trong trạng thái capture tích cực hay không.
 */
static bool isCaptureActive(void) {
  const la_capture_state_t state = captureContext.status.state;
  return state == LA_CAPTURE_ARMED || state == LA_CAPTURE_PRETRIGGER ||
         state == LA_CAPTURE_WAIT_TRIGGER || state == LA_CAPTURE_TRIGGERED ||
         state == LA_CAPTURE_POSTTRIGGER;
}

/*
 * Đọc giá trị thanh ghi con trỏ ngăn xếp chính (MSP - Main Stack Pointer) hiện tại của CPU ARM.
 */
static uint32_t readMainStackPointer(void) {
#if defined(__arm__) || defined(__thumb__)
  uint32_t sp;
  __asm volatile("mrs %0, msp" : "=r"(sp));
  return sp;
#else
  return 0U;
#endif
}

/*
 * Ước lượng dung lượng RAM trống tại thời điểm chạy bằng cách lấy giá trị MSP trừ đi heap start (_end).
 * Giúp debug phát hiện nguy cơ tràn RAM.
 */
static uint32_t estimateRuntimeFreeBytes(void) {
  const uintptr_t heapStart = (uintptr_t)&_end;
  const uintptr_t stackPointer = (uintptr_t)readMainStackPointer();
  if (stackPointer <= heapStart) {
    return 0U;
  }
  return (uint32_t)(stackPointer - heapStart);
}

/*
 * Trả về chuỗi mô tả trạng thái máy trạng thái capture.
 */
static const char *captureStateName(la_capture_state_t state) {
  switch (state) {
  case LA_CAPTURE_IDLE:
    return "IDLE";
  case LA_CAPTURE_ARMED:
    return "ARMED";
  case LA_CAPTURE_PRETRIGGER:
    return "PRETRIGGER";
  case LA_CAPTURE_WAIT_TRIGGER:
    return "WAIT_TRIGGER";
  case LA_CAPTURE_TRIGGERED:
    return "TRIGGERED";
  case LA_CAPTURE_POSTTRIGGER:
    return "POSTTRIGGER";
  case LA_CAPTURE_COMPLETE:
    return "COMPLETE";
  case LA_CAPTURE_NO_TRIGGER:
    return "NO_TRIGGER";
  case LA_CAPTURE_OVERFLOW:
    return "OVERFLOW";
  case LA_CAPTURE_ERROR:
    return "ERROR";
  default:
    return "UNKNOWN";
  }
}

/*
 * Trả về chuỗi mô tả chế độ capture.
 */
static const char *captureModeName(la_capture_mode_t mode) {
  switch (mode) {
  case LA_CAPTURE_MODE_TIMER_ISR_SAFE:
    return "TIMER_ISR_SAFE";
  case LA_CAPTURE_MODE_TIMER_ISR_DIRECT:
    return "TIMER_ISR_DIRECT";
  case LA_CAPTURE_MODE_TIMER_DMA_GPIO_IDR:
    return "TIMER_DMA_GPIO_IDR";
  case LA_CAPTURE_MODE_EDGE_TIMESTAMP_EXTI:
    return "EDGE_TIMESTAMP_EXTI";
  default:
    return "UNKNOWN";
  }
}

/*
 * Trả về tên cơ chế thu thập mẫu đang kích hoạt.
 */
static const char *activeEngineName(void) {
  return activeCaptureEngine == LA_CAPTURE_MODE_TIMER_DMA_GPIO_IDR
             ? "TIMER_DMA_GPIO_IDR"
             : "TIMER_ISR_DIRECT";
}

/*
 * Đọc tần số clock chính xác đang cấp cho Timer TIM2 từ HAL RCC.
 * Trên dòng chip STM32, nếu bộ chia tần số của APB1 khác 1 (RCC_HCLK_DIV1), 
 * thì tần số cấp cho Timer APB1 sẽ được nhân đôi.
 */
static uint32_t readTimer2ClockHz(void) {
  RCC_ClkInitTypeDef clockConfig = {};
  uint32_t flashLatency = 0U;
  HAL_RCC_GetClockConfig(&clockConfig, &flashLatency);

  const uint32_t peripheralClockHz = HAL_RCC_GetPCLK1Freq();
  if (peripheralClockHz == 0U) {
    return 0U;
  }

  if (clockConfig.APB1CLKDivider == RCC_HCLK_DIV1) {
    return peripheralClockHz;
  }
  if (peripheralClockHz > (UINT32_MAX / 2U)) {
    return 0U;
  }
  return peripheralClockHz * 2U;
}

/*
 * Khởi tạo cổng UART với tốc độ Baud Rate quy định.
 */
extern "C" void la_board_uart_or_usb_init(void) {
  AnalyzerSerial.begin(LA_UART_BAUD_RATE);
}

/*
 * Khởi tạo 8 chân đo Logic thành cổng Input đầu vào.
 */
extern "C" void la_board_gpio_init_8ch(void) {
  pinMode(LA_CH0_PIN, LA_INPUT_PULL_MODE);
  pinMode(LA_CH1_PIN, LA_INPUT_PULL_MODE);
  pinMode(LA_CH2_PIN, LA_INPUT_PULL_MODE);
  pinMode(LA_CH3_PIN, LA_INPUT_PULL_MODE);
  pinMode(LA_CH4_PIN, LA_INPUT_PULL_MODE);
  pinMode(LA_CH5_PIN, LA_INPUT_PULL_MODE);
  pinMode(LA_CH6_PIN, LA_INPUT_PULL_MODE);
  pinMode(LA_CH7_PIN, LA_INPUT_PULL_MODE);
}

/*
 * Hàm ngắt con Timer (ISR) gọi tại mỗi chu kỳ lấy mẫu.
 * Hàm này được định nghĩa thuộc tính chạy trên RAM (.RamFunc) để đạt độ trễ nhỏ nhất.
 */
static LA_ALWAYS_INLINE LA_RAMFUNC void sampleTimerISR(void) {
#if LA_ENABLE_DWT_BENCHMARK
  la_benchmark_start_cycles();                   // Bắt đầu đo chu kỳ CPU
#endif
  /* Đọc trạng thái 8 chân GPIO đầu vào */
  const uint8_t sample = la_board_read_gpio_snapshot_8ch_fast();
  /* Nạp mẫu vào máy trạng thái */
  la_capture_isr_fastpath_sample(&captureContext, sample);
#if LA_ENABLE_DWT_BENCHMARK
  la_benchmark_stop_cycles();                    // Kết thúc đo chu kỳ CPU
#endif

  /* Nếu máy trạng thái chuyển sang trạng thái kết thúc (đã lấy đủ mẫu...) */
  if (la_capture_state_is_terminal_fast(captureContext.status.state)) {
    /* Tắt Timer lấy mẫu ngay lập tức để ngắt không tiếp tục xảy ra */
#if defined(TIM_CR1_CEN)
    LA_TIMER_INSTANCE->CR1 &= ~TIM_CR1_CEN;     // Tắt Timer qua thanh ghi CR1
#elif !LA_USE_DIRECT_TIMER_IRQ
    sampleTimer.pause();
#endif
    terminalStateSeen = true;                   // Bật cờ báo hiệu kết thúc phiên đo
  }
}

#if LA_USE_DIRECT_TIMER_IRQ
/*
 * Trình phục vụ ngắt phần cứng (IRQHandler) trực tiếp của Timer TIM2.
 */
extern "C" void LA_TIMER_IRQ_HANDLER(void) LA_RAMFUNC;
extern "C" void LA_TIMER_IRQ_HANDLER(void) {
  /* Kiểm tra xem cờ báo ngắt tràn (Update Interrupt Flag - UIF) của Timer có bật không */
  if ((LA_TIMER_INSTANCE->SR & TIM_SR_UIF) != 0U) {
    /* Xóa cờ ngắt sớm nhất có thể để giảm nguy cơ bỏ lỡ ngắt tiếp theo */
    LA_TIMER_INSTANCE->SR = 0U;
    sampleTimerISR();                           // Gọi xử lý lấy mẫu
    
    /*
     * Nếu cờ UIF lại bị bật lên ngay lập tức sau khi xử lý xong hàm lấy mẫu,
     * điều này chứng tỏ tốc độ lấy mẫu quá nhanh so với tốc độ xử lý của CPU (CPU Overrun).
     * Ta tăng biến đếm cảnh báo.
     */
    if ((LA_TIMER_INSTANCE->SR & TIM_SR_UIF) != 0U &&
        timerIsrOverrunCount != UINT32_MAX) {
      timerIsrOverrunCount++;
    }
  }
}
#endif

/*
 * Khởi tạo phần cứng Timer phát nhịp lấy mẫu.
 */
extern "C" bool la_board_timer_init(uint32_t sample_rate_hz,
                                    la_board_timer_plan_t *plan_out) {
  la_board_timer_plan_t plan;
  const uint32_t timerClockHz = readTimer2ClockHz();
  if (!la_board_calculate_timer_plan(timerClockHz, sample_rate_hz, &plan)) {
    return false;
  }

#if LA_USE_DIRECT_TIMER_IRQ
  /* Cấu hình Timer TIM2 thông qua các thanh ghi trực tiếp để tối ưu hóa hiệu năng */
  LA_TIMER_ENABLE_CLOCK();                      // Cấp Clock cho TIM2
  LA_TIMER_INSTANCE->CR1 = 0U;                  // Reset cấu hình điều khiển
  LA_TIMER_INSTANCE->PSC = (uint16_t)plan.prescaler;   // Ghi bộ chia PSC
  LA_TIMER_INSTANCE->ARR = (uint16_t)plan.autoreload;  // Ghi giá trị nạp lại tự động ARR
  LA_TIMER_INSTANCE->CNT = 0U;                  // Reset bộ đếm về 0
  LA_TIMER_INSTANCE->EGR = TIM_EGR_UG;          // Tạo sự kiện update để cập nhật PSC/ARR
  LA_TIMER_INSTANCE->SR = 0U;                   // Xóa cờ ngắt
  LA_TIMER_INSTANCE->DIER = TIM_DIER_UIE;       // Bật ngắt Update (UIE)
#else
  sampleTimer.pause();
  sampleTimer.setPrescaleFactor(plan.prescaler + 1U);
  sampleTimer.setOverflow(plan.autoreload + 1U, TICK_FORMAT);
  if (!timerInterruptAttached) {
    sampleTimer.attachInterrupt(sampleTimerISR);
    timerInterruptAttached = true;
  }
#endif

#if defined(LA_TIMER_IRQN)
  /* Thiết lập mức ưu tiên ngắt cao nhất cho ngắt Timer */
  NVIC_SetPriority((IRQn_Type)LA_TIMER_IRQN, LA_TIMER_IRQ_PRIORITY);
  NVIC_EnableIRQ((IRQn_Type)LA_TIMER_IRQN);     // Cho phép ngắt trên NVIC
#endif
#if !LA_USE_DIRECT_TIMER_IRQ
  sampleTimer.refresh();
#endif

  activeTimerPlan = plan;
  if (plan_out != nullptr) {
    *plan_out = plan;
  }
  return true;
}

/*
 * Bắt đầu kích hoạt Timer chạy.
 */
extern "C" void la_board_timer_start(void) {
#if LA_USE_DIRECT_TIMER_IRQ
  LA_TIMER_INSTANCE->CNT = 0U;
  LA_TIMER_INSTANCE->SR = 0U;
  LA_TIMER_INSTANCE->CR1 |= TIM_CR1_CEN;        // Bật bit Counter Enable (CEN)
#else
  sampleTimer.refresh();
  sampleTimer.resume();
#endif
}

/*
 * Dừng Timer.
 */
extern "C" void la_board_timer_stop(void) {
#if LA_USE_DIRECT_TIMER_IRQ
  LA_TIMER_INSTANCE->CR1 &= ~TIM_CR1_CEN;       // Tắt bit Counter Enable (CEN)
#else
  sampleTimer.pause();
#endif
}

#if LA_DMA_CAPTURE_COMPILED
/*
 * Dừng các ngoại vi phần cứng DMA phục vụ lấy mẫu.
 */
static void stopDmaCaptureHardware(void) {
  LA_TIMER_INSTANCE->CR1 &= ~TIM_CR1_CEN;       // Dừng Timer
  LA_TIMER_INSTANCE->DIER &= ~TIM_DIER_UDE;     // Tắt phát yêu cầu DMA từ Timer
  LA_DMA_CHANNEL->CCR &= ~DMA_CCR_EN;           // Tắt kênh DMA
}

/*
 * Tính số lượng mẫu cần thu thập trong chế độ trigger tức thời (Immediate).
 */
static uint32_t immediateCaptureSampleCountFor(const la_config_t *config) {
  if (config->posttrigger_samples >= config->max_samples) {
    return config->max_samples;
  }
  return config->posttrigger_samples + 1U;
}

/*
 * Kiểm tra xem cấu hình đo có thể sử dụng chế độ truyền DMA One-Shot hay không.
 * Chỉ hỗ trợ chế độ DMA khi chọn mode TIMER_DMA_GPIO_IDR, trigger kiểu IMMEDIATE,
 * và kích thước dữ liệu nằm trong giới hạn thanh ghi bộ đếm DMA CNDTR (65535).
 */
static bool canUseDmaOneShotFor(const la_config_t *config,
                                const la_trigger_t *trigger) {
  return config->capture_mode == LA_CAPTURE_MODE_TIMER_DMA_GPIO_IDR &&
         trigger->type == LA_TRIGGER_IMMEDIATE &&
         immediateCaptureSampleCountFor(config) <= LA_DMA_MAX_TRANSFER_SAMPLES;
}

static bool canUseDmaOneShot(void) {
  return canUseDmaOneShotFor(&activeConfig, &activeTrigger);
}

/*
 * Thiết lập cấu hình và bắt đầu chạy lấy mẫu bằng cơ chế DMA One-Shot.
 * Tín hiệu sườn xung/tràn từ Timer sẽ tự động kích hoạt kênh DMA đọc thanh ghi GPIO IDR
 * và ghi thẳng vào mảng RAM mà không cần CPU can thiệp.
 */
static bool startDmaCaptureOneShot(uint32_t sampleCount) {
  if (sampleCount == 0U || sampleCount > LA_DMA_MAX_TRANSFER_SAMPLES) {
    return false;
  }

  activeDmaSampleCount = sampleCount;
  RCC->AHBENR |= RCC_AHBENR_DMA1EN;             // Cấp clock cho DMA1
  DMA1->IFCR = LA_DMA_CLEAR_FLAGS;              // Xóa toàn bộ cờ ngắt cũ của DMA

  /* Dừng Timer cấu hình lại */
  LA_TIMER_INSTANCE->CR1 &= ~TIM_CR1_CEN;
  LA_TIMER_INSTANCE->DIER = 0U;
  LA_TIMER_INSTANCE->CNT = 0U;
  LA_TIMER_INSTANCE->SR = 0U;

  /* Thiết lập kênh DMA */
  LA_DMA_CHANNEL->CCR &= ~DMA_CCR_EN;           // Tắt kênh DMA để ghi cấu hình
  LA_DMA_CHANNEL->CPAR = (uint32_t)(uintptr_t)&LA_INPUT_PORT->IDR; // Địa chỉ nguồn: Thanh ghi GPIO IDR
  LA_DMA_CHANNEL->CMAR = (uint32_t)(uintptr_t)captureStorage;     // Địa chỉ đích: Vùng đệm RAM
  LA_DMA_CHANNEL->CNDTR = sampleCount;          // Số lượng phần tử cần chuyển

  /*
   * Cấu hình thanh ghi điều khiển DMA (CCR):
   * - MINC: Tự động tăng địa chỉ bộ nhớ đích (RAM) sau mỗi mẫu.
   * - TCIE: Bật ngắt khi truyền xong gói tin (Transfer Complete Interrupt Enable).
   * - TEIE: Bật ngắt khi xảy ra lỗi truyền dẫn (Transfer Error Interrupt Enable).
   * - PL_0 | PL_1: Đặt mức ưu tiên DMA ở mức cao nhất (Very High).
   * - PSIZE_1: Kích thước dữ liệu đọc ngoại vi là 32-bit (với STM32F1, bắt buộc đọc GPIO IDR kiểu 32-bit/Word).
   */
  LA_DMA_CHANNEL->CCR =
      DMA_CCR_MINC | DMA_CCR_TCIE | DMA_CCR_TEIE | DMA_CCR_PL_0 |
      DMA_CCR_PL_1 | DMA_CCR_PSIZE_1;

  /* Cấu hình ngắt DMA trong NVIC */
  NVIC_SetPriority((IRQn_Type)LA_DMA_IRQN, LA_DMA_IRQ_PRIORITY);
  NVIC_EnableIRQ((IRQn_Type)LA_DMA_IRQN);

  LA_DMA_CHANNEL->CCR |= DMA_CCR_EN;            // Kích hoạt kênh DMA
  LA_TIMER_INSTANCE->DIER = TIM_DIER_UDE;       // Kích hoạt Timer tạo xung trigger gửi tới DMA (Update DMA request)
  LA_TIMER_INSTANCE->CR1 |= TIM_CR1_CEN;        // Bắt đầu chạy Timer phát nhịp
  return true;
}

/*
 * Trình phục vụ ngắt DMA Channel 2. Gọi khi DMA truyền tải xong số mẫu yêu cầu hoặc bị lỗi.
 */
extern "C" void DMA1_Channel2_IRQHandler(void) {
  const uint32_t flags = DMA1->ISR;             // Đọc trạng thái ngắt của DMA1
  if ((flags & (DMA_ISR_TEIF2 | DMA_ISR_TCIF2)) == 0U) {
    return;
  }

  stopDmaCaptureHardware();                     // Dừng phần cứng lấy mẫu
  DMA1->IFCR = LA_DMA_CLEAR_FLAGS;              // Xóa cờ ngắt

  if ((flags & DMA_ISR_TEIF2) != 0U) {
    /* Xử lý khi có lỗi truyền tải DMA */
    dmaTransferErrors++;
    captureContext.status.state = LA_CAPTURE_ERROR;
    captureContext.status.last_error = LA_ERROR_DMA;
  } else {
    /* Đã lấy mẫu thành công */
    const uint32_t sampleCount = activeDmaSampleCount;
    captureContext.status.state = LA_CAPTURE_COMPLETE;
    captureContext.status.write_index = sampleCount;
    captureContext.status.total_samples = sampleCount;
    captureContext.status.trigger_index = 0;
    captureContext.status.actual_sample_rate_hz =
        activeTimerPlan.actual_sample_rate_hz;
    captureContext.status.last_error = LA_ERROR_NONE;
    captureContext.posttrigger_count = sampleCount > 0U ? sampleCount - 1U : 0U;
    captureContext.finalized = true;
  }

  terminalStateSeen = true;
}
#endif

/*
 * Hàm gửi dữ liệu nhị phân về PC thông qua cổng Serial theo từng gói nhỏ (chunk size 64 bytes)
 * để tránh làm quá tải bộ đệm gửi UART TX của vi điều khiển.
 */
extern "C" void la_board_write_bytes_blocking_after_capture(
    const uint8_t *data, size_t len) {
  const size_t chunkSize = 64U;
  size_t offset = 0U;
  while (offset < len) {
    const size_t remaining = len - offset;
    const size_t chunk = remaining > chunkSize ? chunkSize : remaining;
    AnalyzerSerial.write(data + offset, chunk);
    offset += chunk;
  }
  AnalyzerSerial.flush();                        // Đợi gửi xong hoàn toàn dữ liệu
}

/*
 * Đọc nhanh trạng thái logic 8 chân GPIO.
 */
extern "C" uint8_t la_board_read_gpio_snapshot_8ch(void) {
#if LA_USE_DIRECT_GPIO_READ
  return la_board_read_gpio_snapshot_8ch_fast();
#else
  return 0U;
#endif
}

/*
 * Hàm khởi tạo chính cho bo mạch phần cứng.
 */
extern "C" void la_board_init(void) {
  la_board_uart_or_usb_init();
#if defined(LA_UART_IRQN)
  NVIC_SetPriority((IRQn_Type)LA_UART_IRQN, LA_UART_IRQ_PRIORITY);
#endif
  la_board_gpio_init_8ch();
  la_benchmark_init();
}

/*
 * Gửi phản hồi "OK <nội dung>" về máy tính.
 */
static void printOk(const char *text) {
  AnalyzerSerial.print("OK ");
  AnalyzerSerial.println(text);
}

/*
 * Gửi phản hồi lỗi "ERR <nội dung>" về máy tính.
 */
static void printError(const char *text) {
  AnalyzerSerial.print("ERR ");
  AnalyzerSerial.println(text);
}

/*
 * Gửi toàn bộ thông tin siêu dữ liệu cấu hình phần cứng thiết bị (command "INFO") về máy tính.
 */
static void sendInfo(void) {
  AnalyzerSerial.print("INFO ");
  AnalyzerSerial.println(LA_FIRMWARE_VERSION);
  AnalyzerSerial.println("MAGIC SLA8");
  AnalyzerSerial.println("CHANNELS 8");
  AnalyzerSerial.print("RAM_BYTES ");
  AnalyzerSerial.println((uint32_t)LA_BOARD_RAM_BYTES);
  AnalyzerSerial.print("BUFFER ");
  AnalyzerSerial.println((uint32_t)LA_CAPTURE_BUFFER_SAMPLES);
  AnalyzerSerial.print("BUFFER_BYTES ");
  AnalyzerSerial.println((uint32_t)LA_CAPTURE_BUFFER_BYTES);
  AnalyzerSerial.print("RUNTIME_RESERVE_BYTES ");
  AnalyzerSerial.println((uint32_t)LA_MIN_RUNTIME_FREE_BYTES);
  AnalyzerSerial.print("RAMFUNC_BUDGET_BYTES ");
  AnalyzerSerial.println((uint32_t)LA_RAMFUNC_BUDGET_BYTES);
  AnalyzerSerial.print("TIMER_CLOCK ");
  AnalyzerSerial.println(activeTimerPlan.timer_clock_hz);
  AnalyzerSerial.print("DEFAULT_RATE ");
  AnalyzerSerial.println((uint32_t)LA_DEFAULT_SAMPLE_RATE_HZ);
  AnalyzerSerial.print("MAX_TARGET_RATE ");
  AnalyzerSerial.println((uint32_t)LA_MAX_SAMPLE_RATE_HZ_TARGET);
  AnalyzerSerial.print("ISR_MAX_VERIFIED ");
  AnalyzerSerial.println((uint32_t)LA_MAX_ISR_SAMPLE_RATE_HZ_VERIFIED);
  AnalyzerSerial.print("DMA_MAX_VERIFIED ");
  AnalyzerSerial.println((uint32_t)LA_MAX_DMA_SAMPLE_RATE_HZ_VERIFIED);
  AnalyzerSerial.println("PAYLOAD bitpacked_u8");
  AnalyzerSerial.print("CAPTURE_DEFAULT ");
  AnalyzerSerial.println(captureModeName(LA_DEFAULT_CAPTURE_MODE));
  AnalyzerSerial.print("CAPTURE_MODE ");
  AnalyzerSerial.println(captureModeName(activeConfig.capture_mode));
#if LA_DMA_CAPTURE_COMPILED
  AnalyzerSerial.println("DMA ONE_SHOT_IMMEDIATE_VERIFIED_GRAY_HIL");
  AnalyzerSerial.println("DMA_MAP TIM2_UP_DMA1_CHANNEL2_RM0008");
#else
  AnalyzerSerial.println("DMA NOT_COMPILED");
#endif
  AnalyzerSerial.println("HARDWARE_MAX_RATE DMA_5818181_ISR_400000");
  AnalyzerSerial.println("ISR_OVERRUN_DIAG UIF_REASSERT_LOWER_BOUND");
  AnalyzerSerial.println("STACK_CHECK RUNTIME_ESTIMATE_ONLY");
  AnalyzerSerial.println("END INFO");
}

/*
 * Gửi thông tin trạng thái hoạt động hiện thời (command "STATUS") về máy tính.
 */
static void sendStatus(void) {
  AnalyzerSerial.print("STATUS ");
  AnalyzerSerial.println(captureStateName(captureContext.status.state));
  AnalyzerSerial.print("REQUESTED_RATE ");
  AnalyzerSerial.println(activeConfig.sample_rate_hz);
  AnalyzerSerial.print("ACTUAL_RATE ");
  AnalyzerSerial.println(activeTimerPlan.actual_sample_rate_hz);
  AnalyzerSerial.print("TIMER_CLOCK ");
  AnalyzerSerial.println(activeTimerPlan.timer_clock_hz);
  AnalyzerSerial.print("ERROR_PPM ");
  AnalyzerSerial.println(activeTimerPlan.error_ppm);
  AnalyzerSerial.print("SAMPLES ");
  AnalyzerSerial.println(captureContext.status.total_samples);
  AnalyzerSerial.print("TRIGGER_INDEX ");
  AnalyzerSerial.println(captureContext.status.trigger_index);
  AnalyzerSerial.print("OVERFLOW ");
  AnalyzerSerial.println(captureContext.status.overflow_count);
  AnalyzerSerial.print("DROPPED ");
  AnalyzerSerial.println(captureContext.status.dropped_samples);
  AnalyzerSerial.print("ISR_OVERRUNS ");
  AnalyzerSerial.println((uint32_t)timerIsrOverrunCount);
  AnalyzerSerial.print("CAPTURE_MODE ");
  AnalyzerSerial.println(captureModeName(activeConfig.capture_mode));
  AnalyzerSerial.print("ENGINE ");
  AnalyzerSerial.println(activeEngineName());
#if LA_DMA_CAPTURE_COMPILED
  AnalyzerSerial.print("DMA_ERRORS ");
  AnalyzerSerial.println((uint32_t)dmaTransferErrors);
#endif
  AnalyzerSerial.print("BUFFER ");
  AnalyzerSerial.println((uint32_t)LA_CAPTURE_BUFFER_SAMPLES);
  AnalyzerSerial.print("STACK_FREE_EST ");
  AnalyzerSerial.println(estimateRuntimeFreeBytes());
  AnalyzerSerial.println("END STATUS");
}

/*
 * Gửi thông tin kiểm thử hiệu năng CPU DWT (command "BENCH") về máy tính.
 */
static void sendBench(void) {
  const la_timing_budget_t budget = la_calculate_timing_budget(
      activeTimerPlan.timer_clock_hz, activeConfig.sample_rate_hz,
      LA_ESTIMATED_CAPTURE_CYCLES_TIMER_ISR_DIRECT);
  AnalyzerSerial.println("BENCH FIRMWARE_BUILD_ONLY_UNTIL_RUN_ON_BOARD");
  AnalyzerSerial.print("DWT ");
  AnalyzerSerial.println(la_benchmark_is_available() ? "AVAILABLE" : "UNAVAILABLE");
  AnalyzerSerial.print("CYCLES_PER_SAMPLE ");
  AnalyzerSerial.println(budget.cycles_per_sample);
  AnalyzerSerial.print("EST_CAPTURE_CYCLES ");
  AnalyzerSerial.println(budget.estimated_capture_cycles);
  AnalyzerSerial.print("EST_MARGIN_CYCLES ");
  AnalyzerSerial.println(budget.estimated_margin_cycles);
  AnalyzerSerial.print("TIMER_CLOCK ");
  AnalyzerSerial.println(activeTimerPlan.timer_clock_hz);
  AnalyzerSerial.print("ISR_OVERRUNS ");
  AnalyzerSerial.println((uint32_t)timerIsrOverrunCount);
  AnalyzerSerial.print("CAPTURE_MODE ");
  AnalyzerSerial.println(captureModeName(activeConfig.capture_mode));
  AnalyzerSerial.print("ENGINE ");
  AnalyzerSerial.println(activeEngineName());
  AnalyzerSerial.print("ISR_LAST ");
  AnalyzerSerial.println(la_benchmark_get_last_isr_cycles());
  AnalyzerSerial.print("ISR_MIN ");
  AnalyzerSerial.println(la_benchmark_get_min_isr_cycles());
  AnalyzerSerial.print("ISR_MAX ");
  AnalyzerSerial.println(la_benchmark_get_max_isr_cycles());
  AnalyzerSerial.print("ISR_AVG ");
  AnalyzerSerial.println(la_benchmark_get_average_isr_cycles());
  AnalyzerSerial.print("ISR_COUNT ");
  AnalyzerSerial.println(la_benchmark_get_sample_count());
}

/*
 * Cấu hình tần số lấy mẫu.
 */
static bool setRate(uint32_t sampleRateHz) {
  la_board_timer_plan_t plan;
  la_config_t candidate = activeConfig;
  candidate.sample_rate_hz = sampleRateHz;
#if LA_DMA_CAPTURE_COMPILED
  const bool usingDma = canUseDmaOneShotFor(&candidate, &activeTrigger);
#else
  const bool usingDma = false;
#endif
  if (!la_board_sample_rate_supported(sampleRateHz, usingDma) ||
      !la_board_timer_init(sampleRateHz, &plan) ||
      la_capture_validate_config(&candidate, &activeTrigger,
                                 LA_CAPTURE_BUFFER_SAMPLES) != LA_ERROR_NONE) {
    return false;
  }
  activeConfig = candidate;
  activeTimerPlan = plan;
  activeTrigger.timeout_samples = activeConfig.max_samples * 8U;
  return true;
}

/*
 * Cấu hình số mẫu lưu trước trigger.
 */
static bool setPretrigger(uint32_t samples) {
  la_config_t candidate = activeConfig;
  candidate.pretrigger_samples = samples;
  if (candidate.pretrigger_samples + candidate.posttrigger_samples + 1U >
      candidate.max_samples) {
    return false;
  }
  if (la_capture_validate_config(&candidate, &activeTrigger,
                                 LA_CAPTURE_BUFFER_SAMPLES) != LA_ERROR_NONE) {
    return false;
  }
  activeConfig = candidate;
  return true;
}

/*
 * Cấu hình số mẫu lưu sau trigger.
 */
static bool setPosttrigger(uint32_t samples) {
  la_config_t candidate = activeConfig;
  candidate.posttrigger_samples = samples;
  if (candidate.pretrigger_samples + candidate.posttrigger_samples + 1U >
      candidate.max_samples) {
    return false;
  }
  if (la_capture_validate_config(&candidate, &activeTrigger,
                                 LA_CAPTURE_BUFFER_SAMPLES) != LA_ERROR_NONE) {
    return false;
  }
  activeConfig = candidate;
  return true;
}

/*
 * Cấu hình trigger sườn xung.
 */
static bool setEdgeTrigger(la_trigger_edge_t edge, uint32_t channel) {
  if (channel >= LA_CHANNEL_COUNT) {
    return false;
  }
  la_trigger_t candidate = activeTrigger;
  candidate.type = LA_TRIGGER_EDGE;
  candidate.edge = edge;
  candidate.channel = (uint8_t)channel;
  candidate.timeout_samples = activeConfig.max_samples * 8U;
  /* Chế độ trigger sườn chỉ hỗ trợ chạy ngắt (ISR) nên cần kiểm tra giới hạn tần số của ISR */
  if (!la_board_sample_rate_supported(activeConfig.sample_rate_hz, false) ||
      la_capture_validate_config(&activeConfig, &candidate,
                                 LA_CAPTURE_BUFFER_SAMPLES) != LA_ERROR_NONE) {
    return false;
  }
  activeTrigger = candidate;
  return true;
}

/*
 * Cấu hình trigger theo mẫu trạng thái bit.
 */
static bool setPatternTrigger(uint32_t mask, uint32_t value) {
  if (mask > 0xFFU || value > 0xFFU) {
    return false;
  }
  la_trigger_t candidate = activeTrigger;
  candidate.type = LA_TRIGGER_PATTERN;
  candidate.mask = (uint8_t)(mask & 0xFFU);
  candidate.value = (uint8_t)(value & 0xFFU);
  candidate.timeout_samples = activeConfig.max_samples * 8U;
  if (!la_board_sample_rate_supported(activeConfig.sample_rate_hz, false) ||
      la_capture_validate_config(&activeConfig, &candidate,
                                 LA_CAPTURE_BUFFER_SAMPLES) != LA_ERROR_NONE) {
    return false;
  }
  activeTrigger = candidate;
  return true;
}

/*
 * Thiết lập chế độ lấy mẫu (ISR hay DMA).
 */
static bool setCaptureMode(la_capture_mode_t mode) {
  if (mode == LA_CAPTURE_MODE_TIMER_DMA_GPIO_IDR) {
#if !LA_DMA_CAPTURE_COMPILED
    return false;
#endif
  }
  if (mode != LA_CAPTURE_MODE_TIMER_ISR_DIRECT &&
      mode != LA_CAPTURE_MODE_TIMER_DMA_GPIO_IDR) {
    return false;
  }
  la_config_t candidate = activeConfig;
  candidate.capture_mode = mode;
#if LA_DMA_CAPTURE_COMPILED
  const bool usingDma = canUseDmaOneShotFor(&candidate, &activeTrigger);
#else
  const bool usingDma = false;
#endif
  if (!la_board_sample_rate_supported(candidate.sample_rate_hz, usingDma) ||
      la_capture_validate_config(&candidate, &activeTrigger,
                                 LA_CAPTURE_BUFFER_SAMPLES) != LA_ERROR_NONE) {
    return false;
  }
  activeConfig = candidate;
  return true;
}

/*
 * Thiết lập trigger tức thời (Immediate).
 */
static bool setImmediateTrigger(void) {
  la_trigger_t candidate = activeTrigger;
  candidate.type = LA_TRIGGER_IMMEDIATE;
  candidate.timeout_samples = activeConfig.max_samples;
#if LA_DMA_CAPTURE_COMPILED
  const bool usingDma = canUseDmaOneShotFor(&activeConfig, &candidate);
#else
  const bool usingDma = false;
#endif
  if (!la_board_sample_rate_supported(activeConfig.sample_rate_hz, usingDma)) {
    return false;
  }
  activeTrigger = candidate;
  return true;
}

/*
 * Bật trạng thái Arm chuẩn bị lấy mẫu.
 */
static void armCapture(void) {
  if (isCaptureActive()) {
    printError("BUSY");
    return;
  }
  if (!setRate(activeConfig.sample_rate_hz)) {
    printError("BAD_RATE");
    return;
  }

#if LA_DMA_CAPTURE_COMPILED
  const bool useDma = canUseDmaOneShot();
  const uint32_t dmaSampleCount =
      useDma ? immediateCaptureSampleCountFor(&activeConfig) : 0U;
#endif

  const la_error_t err = la_capture_arm(&captureContext, captureStorage,
                                        LA_CAPTURE_BUFFER_SAMPLES,
                                        &activeConfig, &activeTrigger);
  if (err != LA_ERROR_NONE) {
    printError("BAD_CONFIG");
    return;
  }
  captureContext.status.actual_sample_rate_hz =
      activeTimerPlan.actual_sample_rate_hz;

  terminalStateSeen = false;
  timerIsrOverrunCount = 0U;
  digitalWrite(LED_BUILTIN, HIGH);             // Sáng đèn LED báo hiệu đang đo

#if LA_DMA_CAPTURE_COMPILED
  if (useDma) {
    activeCaptureEngine = LA_CAPTURE_MODE_TIMER_DMA_GPIO_IDR;
    if (startDmaCaptureOneShot(dmaSampleCount)) {
      printOk("ARMED");
      return;
    }
    captureContext.status.state = LA_CAPTURE_ERROR;
    captureContext.status.last_error = LA_ERROR_DMA;
    activeCaptureEngine = LA_CAPTURE_MODE_TIMER_ISR_DIRECT;
    digitalWrite(LED_BUILTIN, LOW);
    printError("DMA_START");
    return;
  }
#endif

  activeCaptureEngine = LA_CAPTURE_MODE_TIMER_ISR_DIRECT;
  la_board_timer_start();                       // Kích hoạt Timer bắt đầu tạo ngắt lấy mẫu
  printOk("ARMED");
}

/*
 * Dừng quá trình lấy mẫu logic.
 */
static void stopCapture(void) {
#if LA_DMA_CAPTURE_COMPILED
  if (activeCaptureEngine == LA_CAPTURE_MODE_TIMER_DMA_GPIO_IDR) {
    stopDmaCaptureHardware();
  }
#endif
  la_board_timer_stop();
  if (isCaptureActive()) {
    captureContext.status.state = LA_CAPTURE_IDLE;
  }
  activeCaptureEngine = LA_CAPTURE_MODE_TIMER_ISR_DIRECT;
  digitalWrite(LED_BUILTIN, LOW);               // Tắt đèn LED báo hiệu
  printOk("STOPPED");
}

/*
 * Gửi toàn bộ dữ liệu gói tin logic đã thu được về PC.
 */
static void dumpFrame(void) {
  if (isCaptureActive()) {
    printError("BUSY");
    return;
  }
  if (captureContext.status.state != LA_CAPTURE_COMPLETE &&
      captureContext.status.state != LA_CAPTURE_OVERFLOW &&
      captureContext.status.state != LA_CAPTURE_NO_TRIGGER) {
    printError("NO_FRAME");
    return;
  }

  /* Chuẩn hóa sắp xếp lại bộ đệm pre-trigger ring buffer */
  la_capture_finalize_after_stop(&captureContext);
  la_frame_result_t result;
  /* Dựng Header cho frame */
  const la_error_t err = la_build_frame_header(
      &captureContext, frameHeaderStorage, LA_FRAME_HEADER_LENGTH, &result);
  if (err != LA_ERROR_NONE) {
    printError("FRAME");
    return;
  }

  /*
   * Truyền nhị phân phần Header sau đó tới vùng dữ liệu mẫu đo.
   * Không in ra văn bản text thừa để PC nhận diện frame thô ổn định nhất.
   */
  la_board_write_bytes_blocking_after_capture(frameHeaderStorage,
                                              LA_FRAME_HEADER_LENGTH);
  la_board_write_bytes_blocking_after_capture(captureStorage,
                                              captureContext.status.total_samples);
}

static uint32_t parseUnsigned(const char *text, bool *ok) {
  uint32_t value = 0U;
  *ok = la_parse_u32(text, &value);
  return value;
}

/*
 * Chuyển đổi toàn bộ chuỗi ký tự sang chữ in hoa.
 */
static void uppercaseCommand(char *text) {
  while (*text != '\0') {
    *text = (char)toupper((unsigned char)*text);
    text++;
  }
}

/*
 * Phân tích và xử lý các lệnh văn bản nhận được từ PC.
 */
static void handleCommand(char *cmd) {
  uppercaseCommand(cmd);

  if (isCaptureActive()) {
    /* Khi đang lấy mẫu, chỉ chấp nhận lệnh STOP hoặc STATUS tối giản để tránh gián đoạn ngắt */
    if (strcmp(cmd, "STOP") == 0) {
      stopCapture();
    } else if (strcmp(cmd, "STATUS") == 0) {
      AnalyzerSerial.println("STATUS BUSY");
      AnalyzerSerial.println("END STATUS");
    } else {
      printError("BUSY");
    }
    return;
  }

  if (strcmp(cmd, "PING") == 0) {
    AnalyzerSerial.println("PONG SLA8");
  } else if (strcmp(cmd, "INFO") == 0) {
    sendInfo();
  } else if (strcmp(cmd, "STATUS") == 0) {
    sendStatus();
  } else if (strcmp(cmd, "BENCH") == 0) {
    sendBench();
  } else if (strcmp(cmd, "ARM") == 0) {
    armCapture();
  } else if (strcmp(cmd, "STOP") == 0) {
    stopCapture();
  } else if (strcmp(cmd, "DUMP") == 0) {
    dumpFrame();
  } else if (strcmp(cmd, "CFG MODE ISR") == 0) {
    if (setCaptureMode(LA_CAPTURE_MODE_TIMER_ISR_DIRECT)) {
      printOk("CFG MODE ISR");
    } else {
      printError("BAD_MODE");
    }
  } else if (strcmp(cmd, "CFG MODE DMA") == 0) {
    if (setCaptureMode(LA_CAPTURE_MODE_TIMER_DMA_GPIO_IDR)) {
      printOk("CFG MODE DMA");
    } else {
      printError("BAD_MODE");
    }
  } else if (strncmp(cmd, "CFG RATE ", 9) == 0) {
    bool ok = false;
    const uint32_t rate = parseUnsigned(cmd + 9, &ok);
    if (ok && setRate(rate)) {
      printOk("CFG RATE");
    } else {
      printError("BAD_RATE");
    }
  } else if (strncmp(cmd, "CFG PRE ", 8) == 0) {
    bool ok = false;
    const uint32_t samples = parseUnsigned(cmd + 8, &ok);
    if (ok && setPretrigger(samples)) {
      printOk("CFG PRE");
    } else {
      printError("BAD_PRE");
    }
  } else if (strncmp(cmd, "CFG POST ", 9) == 0) {
    bool ok = false;
    const uint32_t samples = parseUnsigned(cmd + 9, &ok);
    if (ok && setPosttrigger(samples)) {
      printOk("CFG POST");
    } else {
      printError("BAD_POST");
    }
  } else if (strcmp(cmd, "TRIG IMM") == 0) {
    setImmediateTrigger() ? printOk("TRIG IMM") : printError("BAD_RATE");
  } else if (strncmp(cmd, "TRIG RISE ", 10) == 0) {
    bool ok = false;
    const uint32_t ch = parseUnsigned(cmd + 10, &ok);
    ok = ok && setEdgeTrigger(LA_TRIGGER_EDGE_RISING, ch);
    ok ? printOk("TRIG RISE") : printError("BAD_TRIGGER_OR_RATE");
  } else if (strncmp(cmd, "TRIG FALL ", 10) == 0) {
    bool ok = false;
    const uint32_t ch = parseUnsigned(cmd + 10, &ok);
    ok = ok && setEdgeTrigger(LA_TRIGGER_EDGE_FALLING, ch);
    ok ? printOk("TRIG FALL") : printError("BAD_TRIGGER_OR_RATE");
  } else if (strncmp(cmd, "TRIG ANY ", 9) == 0) {
    bool ok = false;
    const uint32_t ch = parseUnsigned(cmd + 9, &ok);
    ok = ok && setEdgeTrigger(LA_TRIGGER_EDGE_ANY, ch);
    ok ? printOk("TRIG ANY") : printError("BAD_TRIGGER_OR_RATE");
  } else if (strncmp(cmd, "TRIG PAT ", 9) == 0) {
    bool ok1 = false;
    bool ok2 = false;
    char *second = strchr(cmd + 9, ' ');
    if (second != nullptr) {
      *second = '\0';
      second++;
      const uint32_t mask = parseUnsigned(cmd + 9, &ok1);
      const uint32_t value = parseUnsigned(second, &ok2);
      if (ok1 && ok2 && setPatternTrigger(mask, value)) {
        printOk("TRIG PAT");
      } else {
        printError("BAD_PATTERN");
      }
    } else {
      printError("BAD_PATTERN");
    }
  } else {
    printError("UNKNOWN");
  }
}

/*
 * Đọc dữ liệu cổng Serial và ghép nối các ký tự tạo thành dòng lệnh hoàn chỉnh.
 */
static void pollCommandInput(void) {
  while (AnalyzerSerial.available() > 0) {
    const char c = (char)AnalyzerSerial.read();
    if (c == '\r' || c == '\n') {
      if (commandLength > 0U) {
        commandBuffer[commandLength] = '\0';
        handleCommand(commandBuffer);
        commandLength = 0U;
      }
    } else if (commandLength < (sizeof(commandBuffer) - 1U)) {
      commandBuffer[commandLength++] = c;
    } else {
      commandLength = 0U;
      printError("CMD_TOO_LONG");
    }
  }
}

/*
 * Cấu hình hệ thống đồng hồ Clock cho vi điều khiển (SystemClock_Config).
 * Hàm này ghi đè cấu hình WEAK mặc định của thư viện STM32duino (thường chỉ dùng HSI 64 MHz).
 * Ưu tiên: Sử dụng thạch anh ngoài HSE 8 MHz nhân PLL với 9 để đạt tần số 72 MHz chuẩn xác (độ lệch ~30ppm).
 * Nếu thạch anh hỏng/không gắn, hệ thống tự động fallback về bộ dao động nội HSI 64 MHz an toàn.
 */
extern "C" void SystemClock_Config(void) {
  RCC_OscInitTypeDef osc = {};
  RCC_ClkInitTypeDef clk = {};

  // --- Ưu tiên: Kích hoạt thạch anh ngoài HSE 8 MHz -> PLL x9 -> Hệ thống 72 MHz ---
  osc.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  osc.HSEState = RCC_HSE_ON;
  osc.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
  osc.PLL.PLLState = RCC_PLL_ON;
  osc.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  osc.PLL.PLLMUL = RCC_PLL_MUL9;

  if (HAL_RCC_OscConfig(&osc) == HAL_OK) {
    clk.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK |
                    RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    clk.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    clk.AHBCLKDivider = RCC_SYSCLK_DIV1;   // HCLK = 72 MHz
    clk.APB1CLKDivider = RCC_HCLK_DIV2;    // PCLK1 = 36 MHz (tần số TIM2 cấp nhịp = PCLK1 * 2 = 72 MHz)
    clk.APB2CLKDivider = RCC_HCLK_DIV1;    // PCLK2 = 72 MHz
    if (HAL_RCC_ClockConfig(&clk, FLASH_LATENCY_2) == HAL_OK) {
      return;  // Cấu hình bằng thạch anh HSE thành công
    }
  }

  // --- Fallback dự phòng: Bộ dao động nội HSI/2 -> PLL x16 -> Hệ thống 64 MHz ---
  osc = RCC_OscInitTypeDef{};
  osc.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  osc.HSIState = RCC_HSI_ON;
  osc.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  osc.PLL.PLLState = RCC_PLL_ON;
  osc.PLL.PLLSource = RCC_PLLSOURCE_HSI_DIV2;
  osc.PLL.PLLMUL = RCC_PLL_MUL16;
  (void)HAL_RCC_OscConfig(&osc);

  clk.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK |
                  RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  clk.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  clk.AHBCLKDivider = RCC_SYSCLK_DIV1;
  clk.APB1CLKDivider = RCC_HCLK_DIV2;
  clk.APB2CLKDivider = RCC_HCLK_DIV1;
  (void)HAL_RCC_ClockConfig(&clk, FLASH_LATENCY_2);
}

/*
 * Hàm thiết lập khởi động ban đầu của Arduino Sketch.
 */
void setup(void) {
  la_board_init();                              // Khởi tạo phần cứng bo mạch (UART, GPIO...)
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);               // Tắt LED báo hiệu
  la_capture_init(&captureContext);             // Khởi tạo máy trạng thái capture
  setRate(LA_DEFAULT_SAMPLE_RATE_HZ);           // Thiết lập tần số lấy mẫu mặc định
  AnalyzerSerial.println("READY SLA8");         // Gửi thông báo sẵn sàng về PC
}

/*
 * Vòng lặp chính của chương trình.
 */
void loop(void) {
  pollCommandInput();                           // Quét nhận các lệnh từ UART

  /* Nếu phát hiện phiên capture đã hoàn tất/kết thúc */
  if (terminalStateSeen) {
#if LA_DMA_CAPTURE_COMPILED
    const bool wasDma =
        activeCaptureEngine == LA_CAPTURE_MODE_TIMER_DMA_GPIO_IDR;
#else
    const bool wasDma = false;
#endif
    /* Tạm thời khóa ngắt để cập nhật biến trạng thái an toàn */
    noInterrupts();
    terminalStateSeen = false;
    interrupts();
    
    la_board_timer_stop();                      // Dừng Timer
    if (!wasDma) {
      /* Nếu chạy chế độ ngắt, tiến hành sắp xếp chuẩn hóa lại bộ đệm pre-trigger */
      la_capture_finalize_after_stop(&captureContext);
    }
    digitalWrite(LED_BUILTIN, LOW);             // Tắt đèn LED báo hiệu bận

    /* Báo sự kiện kết thúc trạng thái đo về máy tính */
    AnalyzerSerial.print("EVENT ");
    AnalyzerSerial.println(captureStateName(captureContext.status.state));
  }
}
