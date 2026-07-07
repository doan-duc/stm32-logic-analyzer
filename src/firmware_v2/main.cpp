#include <Arduino.h>
#include "board_config.h"
#if !LA_USE_DIRECT_TIMER_IRQ
#include <HardwareTimer.h>
#endif
#include <ctype.h>
#include <stdlib.h>
#include <string.h>

extern "C" {
#include "la_board.h"
#include "la_capture.h"
#include "la_protocol.h"
}

#ifndef LED_BUILTIN
#define LED_BUILTIN PC13
#endif

#if LA_ENABLE_DMA_CAPTURE && defined(DMA1) && defined(DMA1_Channel2) &&        \
    defined(DMA_CCR_EN) && defined(TIM_DIER_UDE)
#define LA_DMA_CAPTURE_COMPILED 1
#else
#define LA_DMA_CAPTURE_COMPILED 0
#endif

#if LA_DMA_CAPTURE_COMPILED
#define LA_DMA_CHANNEL DMA1_Channel2
#define LA_DMA_IRQN DMA1_Channel2_IRQn
#define LA_DMA_CLEAR_FLAGS                                                    \
  (DMA_IFCR_CGIF2 | DMA_IFCR_CTCIF2 | DMA_IFCR_CHTIF2 | DMA_IFCR_CTEIF2)
#endif

static HardwareSerial AnalyzerSerial(LA_UART_RX_PIN, LA_UART_TX_PIN);
#if !LA_USE_DIRECT_TIMER_IRQ
static HardwareTimer sampleTimer(LA_TIMER_INSTANCE);
static bool timerInterruptAttached = false;
#endif

static LA_SAMPLE_TYPE captureStorage[LA_CAPTURE_BUFFER_SAMPLES]
    __attribute__((aligned(4)));
static uint8_t frameHeaderStorage[LA_FRAME_HEADER_LENGTH]
    __attribute__((aligned(4)));
static la_capture_context_t captureContext;
static volatile bool terminalStateSeen = false;
static volatile uint8_t activeCaptureEngine = LA_CAPTURE_MODE_TIMER_ISR_DIRECT;

#if LA_DMA_CAPTURE_COMPILED
static volatile uint32_t activeDmaSampleCount = 0U;
static volatile uint32_t dmaTransferErrors = 0U;
#endif

extern "C" char _end;
extern "C" char _estack;

static char commandBuffer[96];
static uint8_t commandLength = 0U;
static la_board_timer_plan_t activeTimerPlan = {
    LA_DEFAULT_SAMPLE_RATE_HZ,
    LA_DEFAULT_SAMPLE_RATE_HZ,
    0U,
    0U,
    0,
};

static la_config_t activeConfig = {
    LA_DEFAULT_SAMPLE_RATE_HZ,
    LA_CHANNEL_COUNT,
    LA_CAPTURE_BUFFER_SAMPLES,
    LA_DEFAULT_PRETRIGGER_SAMPLES,
    LA_DEFAULT_POSTTRIGGER_SAMPLES,
    0xFFU,
    {0, 1, 2, 3, 4, 5, 6, 7},
    LA_CAPTURE_MODE_TIMER_ISR_DIRECT,
};

static la_trigger_t activeTrigger = {
    LA_TRIGGER_IMMEDIATE,
    0U,
    LA_TRIGGER_EDGE_RISING,
    0xFFU,
    0U,
    LA_CAPTURE_BUFFER_SAMPLES,
};

static bool isCaptureActive(void) {
  const la_capture_state_t state = captureContext.status.state;
  return state == LA_CAPTURE_ARMED || state == LA_CAPTURE_PRETRIGGER ||
         state == LA_CAPTURE_WAIT_TRIGGER || state == LA_CAPTURE_TRIGGERED ||
         state == LA_CAPTURE_POSTTRIGGER;
}

static uint32_t readMainStackPointer(void) {
#if defined(__arm__) || defined(__thumb__)
  uint32_t sp;
  __asm volatile("mrs %0, msp" : "=r"(sp));
  return sp;
#else
  return 0U;
#endif
}

static uint32_t estimateRuntimeFreeBytes(void) {
  // Chi la uoc luong luc chay; tran stack that phai do tren board.
  const uintptr_t heapStart = (uintptr_t)&_end;
  const uintptr_t stackPointer = (uintptr_t)readMainStackPointer();
  if (stackPointer <= heapStart) {
    return 0U;
  }
  return (uint32_t)(stackPointer - heapStart);
}

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

static const char *activeEngineName(void) {
  return activeCaptureEngine == LA_CAPTURE_MODE_TIMER_DMA_GPIO_IDR
             ? "TIMER_DMA_GPIO_IDR"
             : "TIMER_ISR_DIRECT";
}

static bool calculateTimerPlan(uint32_t requestedHz,
                               la_board_timer_plan_t *plan) {
  if (requestedHz == 0U || requestedHz > LA_MAX_SAMPLE_RATE_HZ_TARGET ||
      plan == nullptr) {
    return false;
  }

  const uint64_t roundedTicks =
      ((uint64_t)LA_TIMER_CLOCK_HZ + (requestedHz / 2U)) / requestedHz;
  if (roundedTicks == 0U) {
    return false;
  }

  uint64_t prescalerFactor =
      (roundedTicks + LA_TIMER_MAX_ARR) / (LA_TIMER_MAX_ARR + 1ULL);
  if (prescalerFactor == 0U) {
    prescalerFactor = 1U;
  }
  if (prescalerFactor > LA_TIMER_MAX_PRESCALER) {
    return false;
  }

  uint64_t arrTicks = roundedTicks / prescalerFactor;
  if (arrTicks == 0U) {
    arrTicks = 1U;
  }
  if (arrTicks > (LA_TIMER_MAX_ARR + 1ULL)) {
    arrTicks = LA_TIMER_MAX_ARR + 1ULL;
  }

  const uint64_t divider = prescalerFactor * arrTicks;
  const uint32_t actualHz = (uint32_t)(LA_TIMER_CLOCK_HZ / divider);
  const int64_t diff = (int64_t)actualHz - (int64_t)requestedHz;

  plan->requested_sample_rate_hz = requestedHz;
  plan->actual_sample_rate_hz = actualHz;
  plan->prescaler = (uint32_t)(prescalerFactor - 1ULL);
  plan->autoreload = (uint32_t)(arrTicks - 1ULL);
  plan->error_ppm = (int32_t)((diff * 1000000LL) / (int64_t)requestedHz);
  return actualHz != 0U;
}

extern "C" void la_board_uart_or_usb_init(void) {
  AnalyzerSerial.begin(LA_UART_BAUD_RATE);
}

extern "C" void la_board_gpio_init_8ch(void) {
  /*
   * Cac chan capture la input so 3.3 V. Khong noi truc tiep 5 V/cao ap
   * vao GPIO STM32 neu chua co mach bao ve hoac buffer.
   */
  pinMode(LA_CH0_PIN, LA_INPUT_PULL_MODE);
  pinMode(LA_CH1_PIN, LA_INPUT_PULL_MODE);
  pinMode(LA_CH2_PIN, LA_INPUT_PULL_MODE);
  pinMode(LA_CH3_PIN, LA_INPUT_PULL_MODE);
  pinMode(LA_CH4_PIN, LA_INPUT_PULL_MODE);
  pinMode(LA_CH5_PIN, LA_INPUT_PULL_MODE);
  pinMode(LA_CH6_PIN, LA_INPUT_PULL_MODE);
  pinMode(LA_CH7_PIN, LA_INPUT_PULL_MODE);
}

static LA_ALWAYS_INLINE LA_RAMFUNC void sampleTimerISR(void) {
#if LA_ENABLE_DWT_BENCHMARK
  la_benchmark_start_cycles();
#endif
  const uint8_t sample = la_board_read_gpio_snapshot_8ch_fast();
  la_capture_isr_fastpath_sample(&captureContext, sample);
#if LA_ENABLE_DWT_BENCHMARK
  la_benchmark_stop_cycles();
#endif

  if (la_capture_state_is_terminal_fast(captureContext.status.state)) {
    // Dung timer bang thanh ghi truc tiep; ISR khong goi UART hay xu ly nang.
#if defined(TIM_CR1_CEN)
    LA_TIMER_INSTANCE->CR1 &= ~TIM_CR1_CEN;
#elif !LA_USE_DIRECT_TIMER_IRQ
    sampleTimer.pause();
#endif
    terminalStateSeen = true;
  }
}

#if LA_USE_DIRECT_TIMER_IRQ
extern "C" void LA_TIMER_IRQ_HANDLER(void) LA_RAMFUNC;
extern "C" void LA_TIMER_IRQ_HANDLER(void) {
  if ((LA_TIMER_INSTANCE->SR & TIM_SR_UIF) != 0U) {
    // Xoa co update som de IRQ ke tiep khong bi tre; phan lay mau o sau rat ngan.
    LA_TIMER_INSTANCE->SR = 0U;
    sampleTimerISR();
  }
}
#endif

extern "C" bool la_board_timer_init(uint32_t sample_rate_hz,
                                    la_board_timer_plan_t *plan_out) {
  la_board_timer_plan_t plan;
  if (!calculateTimerPlan(sample_rate_hz, &plan)) {
    return false;
  }

#if LA_USE_DIRECT_TIMER_IRQ
  LA_TIMER_ENABLE_CLOCK();
  LA_TIMER_INSTANCE->CR1 = 0U;
  LA_TIMER_INSTANCE->PSC = (uint16_t)plan.prescaler;
  LA_TIMER_INSTANCE->ARR = (uint16_t)plan.autoreload;
  LA_TIMER_INSTANCE->CNT = 0U;
  LA_TIMER_INSTANCE->EGR = TIM_EGR_UG;
  LA_TIMER_INSTANCE->SR = 0U;
  LA_TIMER_INSTANCE->DIER = TIM_DIER_UIE;
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
  NVIC_SetPriority((IRQn_Type)LA_TIMER_IRQN, LA_TIMER_IRQ_PRIORITY);
  NVIC_EnableIRQ((IRQn_Type)LA_TIMER_IRQN);
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

extern "C" void la_board_timer_start(void) {
#if LA_USE_DIRECT_TIMER_IRQ
  LA_TIMER_INSTANCE->CNT = 0U;
  LA_TIMER_INSTANCE->SR = 0U;
  LA_TIMER_INSTANCE->CR1 |= TIM_CR1_CEN;
#else
  sampleTimer.refresh();
  sampleTimer.resume();
#endif
}

extern "C" void la_board_timer_stop(void) {
#if LA_USE_DIRECT_TIMER_IRQ
  LA_TIMER_INSTANCE->CR1 &= ~TIM_CR1_CEN;
#else
  sampleTimer.pause();
#endif
}

#if LA_DMA_CAPTURE_COMPILED
static void stopDmaCaptureHardware(void) {
  LA_TIMER_INSTANCE->CR1 &= ~TIM_CR1_CEN;
  LA_TIMER_INSTANCE->DIER &= ~TIM_DIER_UDE;
  LA_DMA_CHANNEL->CCR &= ~DMA_CCR_EN;
}

static uint32_t immediateCaptureSampleCount(void) {
  if (activeConfig.posttrigger_samples >= activeConfig.max_samples) {
    return activeConfig.max_samples;
  }
  return activeConfig.posttrigger_samples + 1U;
}

static bool canUseDmaOneShot(void) {
  // DMA v2 hien chi an toan cho immediate; trigger khac fallback ISR.
  return activeConfig.capture_mode == LA_CAPTURE_MODE_TIMER_DMA_GPIO_IDR &&
         activeTrigger.type == LA_TRIGGER_IMMEDIATE &&
         immediateCaptureSampleCount() <= LA_DMA_MAX_TRANSFER_SAMPLES;
}

static bool startDmaCaptureOneShot(uint32_t sampleCount) {
  if (sampleCount == 0U || sampleCount > LA_DMA_MAX_TRANSFER_SAMPLES) {
    return false;
  }

  activeDmaSampleCount = sampleCount;
  RCC->AHBENR |= RCC_AHBENR_DMA1EN;
  DMA1->IFCR = LA_DMA_CLEAR_FLAGS;

  LA_TIMER_INSTANCE->CR1 &= ~TIM_CR1_CEN;
  LA_TIMER_INSTANCE->DIER = 0U;
  LA_TIMER_INSTANCE->CNT = 0U;
  LA_TIMER_INSTANCE->SR = 0U;

  LA_DMA_CHANNEL->CCR &= ~DMA_CCR_EN;
  LA_DMA_CHANNEL->CPAR = (uint32_t)(uintptr_t)&LA_INPUT_PORT->IDR;
  LA_DMA_CHANNEL->CMAR = (uint32_t)(uintptr_t)captureStorage;
  LA_DMA_CHANNEL->CNDTR = sampleCount;
  /*
   * TIM2_UP kich DMA1 Channel2. DMA chi lay byte thap cua IDR
   * nen PA0..PA7 vao thang buffer uint8_t.
   */
  LA_DMA_CHANNEL->CCR =
      DMA_CCR_MINC | DMA_CCR_TCIE | DMA_CCR_TEIE | DMA_CCR_PL_0 | DMA_CCR_PL_1;

  NVIC_SetPriority((IRQn_Type)LA_DMA_IRQN, LA_DMA_IRQ_PRIORITY);
  NVIC_EnableIRQ((IRQn_Type)LA_DMA_IRQN);

  LA_DMA_CHANNEL->CCR |= DMA_CCR_EN;
  LA_TIMER_INSTANCE->DIER = TIM_DIER_UDE;
  LA_TIMER_INSTANCE->CR1 |= TIM_CR1_CEN;
  return true;
}

extern "C" void DMA1_Channel2_IRQHandler(void) {
  const uint32_t flags = DMA1->ISR;
  if ((flags & (DMA_ISR_TEIF2 | DMA_ISR_TCIF2)) == 0U) {
    return;
  }

  stopDmaCaptureHardware();
  DMA1->IFCR = LA_DMA_CLEAR_FLAGS;

  if ((flags & DMA_ISR_TEIF2) != 0U) {
    dmaTransferErrors++;
    captureContext.status.state = LA_CAPTURE_ERROR;
    captureContext.status.last_error = LA_ERROR_DMA;
  } else {
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
  AnalyzerSerial.flush();
}

extern "C" uint8_t la_board_read_gpio_snapshot_8ch(void) {
#if LA_USE_DIRECT_GPIO_READ
  return la_board_read_gpio_snapshot_8ch_fast();
#else
  return 0U;
#endif
}

extern "C" void la_board_init(void) {
  la_board_uart_or_usb_init();
#if defined(LA_UART_IRQN)
  NVIC_SetPriority((IRQn_Type)LA_UART_IRQN, LA_UART_IRQ_PRIORITY);
#endif
  la_board_gpio_init_8ch();
  la_benchmark_init();
}

static bool validateActiveConfig(void) {
  return la_capture_validate_config(&activeConfig, &activeTrigger,
                                    LA_CAPTURE_BUFFER_SAMPLES) ==
         LA_ERROR_NONE;
}

static void printOk(const char *text) {
  AnalyzerSerial.print("OK ");
  AnalyzerSerial.println(text);
}

static void printError(const char *text) {
  AnalyzerSerial.print("ERR ");
  AnalyzerSerial.println(text);
}

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
  AnalyzerSerial.print("DEFAULT_RATE ");
  AnalyzerSerial.println((uint32_t)LA_DEFAULT_SAMPLE_RATE_HZ);
  AnalyzerSerial.print("MAX_TARGET_RATE ");
  AnalyzerSerial.println((uint32_t)LA_MAX_SAMPLE_RATE_HZ_TARGET);
  AnalyzerSerial.println("PAYLOAD bitpacked_u8");
  AnalyzerSerial.print("CAPTURE_DEFAULT ");
  AnalyzerSerial.println(captureModeName(LA_CAPTURE_MODE_TIMER_ISR_DIRECT));
  AnalyzerSerial.print("CAPTURE_MODE ");
  AnalyzerSerial.println(captureModeName(activeConfig.capture_mode));
#if LA_DMA_CAPTURE_COMPILED
  // Mapping da xac nhan voi core/RM0008; toc do toi da phai do tren board.
  AnalyzerSerial.println("DMA ONE_SHOT_IMMEDIATE_ENABLED_UNVERIFIED");
  AnalyzerSerial.println("DMA_MAP TIM2_UP_DMA1_CHANNEL2_RM0008");
#else
  AnalyzerSerial.println("DMA NOT_COMPILED");
#endif
  AnalyzerSerial.println("HARDWARE_MAX_RATE NOT_MEASURED_YET");
  AnalyzerSerial.println("DMA_MAX_RATE MEASURE_ON_BOARD");
  AnalyzerSerial.println("STACK_CHECK RUNTIME_ESTIMATE_ONLY");
}

static void sendStatus(void) {
  AnalyzerSerial.print("STATUS ");
  AnalyzerSerial.println(captureStateName(captureContext.status.state));
  AnalyzerSerial.print("REQUESTED_RATE ");
  AnalyzerSerial.println(activeConfig.sample_rate_hz);
  AnalyzerSerial.print("ACTUAL_RATE ");
  AnalyzerSerial.println(activeTimerPlan.actual_sample_rate_hz);
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
}

static void sendBench(void) {
  const la_timing_budget_t budget = la_calculate_timing_budget(
      LA_TIMER_CLOCK_HZ, activeConfig.sample_rate_hz,
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

static bool setRate(uint32_t sampleRateHz) {
  la_board_timer_plan_t plan;
  la_config_t candidate = activeConfig;
  candidate.sample_rate_hz = sampleRateHz;
  if (!la_board_timer_init(sampleRateHz, &plan) ||
      la_capture_validate_config(&candidate, &activeTrigger,
                                 LA_CAPTURE_BUFFER_SAMPLES) != LA_ERROR_NONE) {
    return false;
  }
  activeConfig = candidate;
  activeTimerPlan = plan;
  activeTrigger.timeout_samples = activeConfig.max_samples * 8U;
  return true;
}

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

static bool setEdgeTrigger(la_trigger_edge_t edge, uint32_t channel) {
  if (channel >= LA_CHANNEL_COUNT) {
    return false;
  }
  activeTrigger.type = LA_TRIGGER_EDGE;
  activeTrigger.edge = edge;
  activeTrigger.channel = (uint8_t)channel;
  activeTrigger.timeout_samples = activeConfig.max_samples * 8U;
  return validateActiveConfig();
}

static bool setPatternTrigger(uint32_t mask, uint32_t value) {
  activeTrigger.type = LA_TRIGGER_PATTERN;
  activeTrigger.mask = (uint8_t)(mask & 0xFFU);
  activeTrigger.value = (uint8_t)(value & 0xFFU);
  activeTrigger.timeout_samples = activeConfig.max_samples * 8U;
  return validateActiveConfig();
}

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
  activeConfig.capture_mode = mode;
  return validateActiveConfig();
}

static void setImmediateTrigger(void) {
  activeTrigger.type = LA_TRIGGER_IMMEDIATE;
  activeTrigger.timeout_samples = activeConfig.max_samples;
}

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
  const uint32_t dmaSampleCount = useDma ? immediateCaptureSampleCount() : 0U;
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
  digitalWrite(LED_BUILTIN, HIGH);

#if LA_DMA_CAPTURE_COMPILED
  if (useDma) {
    activeCaptureEngine = LA_CAPTURE_MODE_TIMER_DMA_GPIO_IDR;
    if (startDmaCaptureOneShot(dmaSampleCount)) {
      printOk("ARMED");
      return;
    }
  }
#endif

  activeCaptureEngine = LA_CAPTURE_MODE_TIMER_ISR_DIRECT;
  la_board_timer_start();
  printOk("ARMED");
}

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
  digitalWrite(LED_BUILTIN, LOW);
  printOk("STOPPED");
}

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

  la_capture_finalize_after_stop(&captureContext);
  la_frame_result_t result;
  const la_error_t err = la_build_frame_header(
      &captureContext, frameHeaderStorage, LA_FRAME_HEADER_LENGTH, &result);
  if (err != LA_ERROR_NONE) {
    printError("FRAME");
    return;
  }

  // DUMP thanh cong chi gui byte SLA8, khong chen text de host parse an toan.
  la_board_write_bytes_blocking_after_capture(frameHeaderStorage,
                                              LA_FRAME_HEADER_LENGTH);
  la_board_write_bytes_blocking_after_capture(captureStorage,
                                              captureContext.status.total_samples);
}

static uint32_t parseUnsigned(const char *text, bool *ok) {
  char *end = nullptr;
  const unsigned long value = strtoul(text, &end, 0);
  *ok = (end != text);
  return (uint32_t)value;
}

static void uppercaseCommand(char *text) {
  while (*text != '\0') {
    *text = (char)toupper((unsigned char)*text);
    text++;
  }
}

static void handleCommand(char *cmd) {
  uppercaseCommand(cmd);

  if (isCaptureActive()) {
    if (strcmp(cmd, "STOP") == 0) {
      stopCapture();
    } else if (strcmp(cmd, "STATUS") == 0) {
      // Khi dang capture chi tra loi rat ngan de khong canh tranh CPU/UART.
      AnalyzerSerial.println("STATUS BUSY");
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
    setImmediateTrigger();
    printOk("TRIG IMM");
  } else if (strncmp(cmd, "TRIG RISE ", 10) == 0) {
    bool ok = false;
    const uint32_t ch = parseUnsigned(cmd + 10, &ok);
    ok = ok && setEdgeTrigger(LA_TRIGGER_EDGE_RISING, ch);
    ok ? printOk("TRIG RISE") : printError("BAD_CHANNEL");
  } else if (strncmp(cmd, "TRIG FALL ", 10) == 0) {
    bool ok = false;
    const uint32_t ch = parseUnsigned(cmd + 10, &ok);
    ok = ok && setEdgeTrigger(LA_TRIGGER_EDGE_FALLING, ch);
    ok ? printOk("TRIG FALL") : printError("BAD_CHANNEL");
  } else if (strncmp(cmd, "TRIG ANY ", 9) == 0) {
    bool ok = false;
    const uint32_t ch = parseUnsigned(cmd + 9, &ok);
    ok = ok && setEdgeTrigger(LA_TRIGGER_EDGE_ANY, ch);
    ok ? printOk("TRIG ANY") : printError("BAD_CHANNEL");
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

void setup(void) {
  la_board_init();
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);
  la_capture_init(&captureContext);
  setRate(LA_DEFAULT_SAMPLE_RATE_HZ);
  AnalyzerSerial.println("READY SLA8");
}

void loop(void) {
  pollCommandInput();

  if (terminalStateSeen) {
#if LA_DMA_CAPTURE_COMPILED
    const bool wasDma =
        activeCaptureEngine == LA_CAPTURE_MODE_TIMER_DMA_GPIO_IDR;
#else
    const bool wasDma = false;
#endif
    noInterrupts();
    terminalStateSeen = false;
    interrupts();
    la_board_timer_stop();
    if (!wasDma) {
      la_capture_finalize_after_stop(&captureContext);
    }
    digitalWrite(LED_BUILTIN, LOW);

    AnalyzerSerial.print("EVENT ");
    AnalyzerSerial.println(captureStateName(captureContext.status.state));
  }
}
