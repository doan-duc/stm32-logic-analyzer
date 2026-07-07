#include "la_capture.h"

#if defined(STM32F1xx)
#include "stm32f1xx.h"
#elif defined(STM32F4xx)
#include "stm32f4xx.h"
#elif defined(STM32L4xx)
#include "stm32l4xx.h"
#endif

static uint32_t last_isr_cycles = 0U;
static uint32_t max_isr_cycles = 0U;
static uint32_t min_isr_cycles = 0xFFFFFFFFUL;
static uint32_t total_isr_cycles = 0U;
static uint32_t sample_count = 0U;
static uint32_t start_cycles = 0U;
static bool dwt_available = false;

void la_benchmark_init(void) {
#if defined(LA_ENABLE_DWT_BENCHMARK) && LA_ENABLE_DWT_BENCHMARK &&             \
    defined(DWT) && defined(CoreDebug) && defined(CoreDebug_DEMCR_TRCENA_Msk)
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CYCCNT = 0U;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
  dwt_available = (DWT->CTRL & DWT_CTRL_CYCCNTENA_Msk) != 0U;
#else
  dwt_available = false;
#endif
}

void la_benchmark_start_cycles(void) {
#if defined(LA_ENABLE_DWT_BENCHMARK) && LA_ENABLE_DWT_BENCHMARK &&             \
    defined(DWT)
  if (dwt_available) {
    start_cycles = DWT->CYCCNT;
  }
#else
  start_cycles = 0U;
#endif
}

void la_benchmark_stop_cycles(void) {
#if defined(LA_ENABLE_DWT_BENCHMARK) && LA_ENABLE_DWT_BENCHMARK &&             \
    defined(DWT)
  if (dwt_available) {
    const uint32_t now = DWT->CYCCNT;
    last_isr_cycles = now - start_cycles;
    if (last_isr_cycles > max_isr_cycles) {
      max_isr_cycles = last_isr_cycles;
    }
    if (last_isr_cycles < min_isr_cycles) {
      min_isr_cycles = last_isr_cycles;
    }
    total_isr_cycles += last_isr_cycles;
    sample_count++;
  }
#else
  // Khong co DWT thi khong tao so do gia.
  last_isr_cycles = 0U;
#endif
}

bool la_benchmark_is_available(void) { return dwt_available; }

uint32_t la_benchmark_get_last_isr_cycles(void) { return last_isr_cycles; }

uint32_t la_benchmark_get_max_isr_cycles(void) { return max_isr_cycles; }

uint32_t la_benchmark_get_min_isr_cycles(void) {
  return sample_count == 0U ? 0U : min_isr_cycles;
}

uint32_t la_benchmark_get_average_isr_cycles(void) {
  return sample_count == 0U ? 0U : (total_isr_cycles / sample_count);
}

uint32_t la_benchmark_get_sample_count(void) { return sample_count; }
