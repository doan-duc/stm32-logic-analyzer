#ifndef BOARD_CONFIG_H
#define BOARD_CONFIG_H

#include <stdbool.h>
#include <stdint.h>

#ifndef LA_CHANNEL_COUNT
#define LA_CHANNEL_COUNT 8U
#endif

#define LA_SAMPLE_TYPE uint8_t
#define LA_DEFAULT_SAMPLE_RATE_HZ 100000UL
#define LA_MAX_SAMPLE_RATE_HZ_TARGET 1000000UL

#ifndef LA_BOARD_RAM_BYTES
#if defined(STM32F103x6)
#define LA_BOARD_RAM_BYTES 10240U
#elif defined(STM32F103xB) || defined(STM32F103x8)
#define LA_BOARD_RAM_BYTES 20480U
#elif defined(STM32F401xC)
#define LA_BOARD_RAM_BYTES 65536U
#elif defined(STM32F401xE)
#define LA_BOARD_RAM_BYTES 98304U
#elif defined(STM32F411xE)
#define LA_BOARD_RAM_BYTES 131072U
#else
#define LA_BOARD_RAM_BYTES 20480U
#endif
#endif

#ifndef LA_CAPTURE_BUFFER_SAMPLES
#if LA_BOARD_RAM_BYTES <= 10240U
#define LA_CAPTURE_BUFFER_SAMPLES 6656U
#elif LA_BOARD_RAM_BYTES <= 20480U
#define LA_CAPTURE_BUFFER_SAMPLES 14080U
#else
#define LA_CAPTURE_BUFFER_SAMPLES 49152U
#endif
#endif

#if LA_BOARD_RAM_BYTES <= 10240U
#define LA_MIN_RUNTIME_FREE_BYTES 1536U
#define LA_STATIC_OVERHEAD_BUDGET_BYTES 1536U
#elif LA_BOARD_RAM_BYTES <= 20480U
#define LA_MIN_RUNTIME_FREE_BYTES 4096U
#define LA_STATIC_OVERHEAD_BUDGET_BYTES 1792U
#else
#define LA_MIN_RUNTIME_FREE_BYTES 8192U
#define LA_STATIC_OVERHEAD_BUDGET_BYTES 4096U
#endif

#define LA_RAMFUNC_BUDGET_BYTES 512U
#define LA_CAPTURE_BUFFER_BYTES \
  ((uint32_t)(LA_CAPTURE_BUFFER_SAMPLES * sizeof(LA_SAMPLE_TYPE)))

#if defined(__cplusplus)
#define LA_STATIC_ASSERT(expr, msg) static_assert((expr), msg)
#else
#define LA_STATIC_ASSERT(expr, msg) _Static_assert((expr), msg)
#endif

LA_STATIC_ASSERT(
    ((LA_CAPTURE_BUFFER_SAMPLES * sizeof(LA_SAMPLE_TYPE)) +
     LA_RAMFUNC_BUDGET_BYTES + LA_STATIC_OVERHEAD_BUDGET_BYTES +
     LA_MIN_RUNTIME_FREE_BYTES) <= LA_BOARD_RAM_BYTES,
    "LA_CAPTURE_BUFFER_SAMPLES exceeds estimated RAM budget");

#define LA_DEFAULT_PRETRIGGER_SAMPLES 0U
#define LA_DEFAULT_POSTTRIGGER_SAMPLES (LA_CAPTURE_BUFFER_SAMPLES - 1U)

#ifndef LA_RAMFUNC
#define LA_RAMFUNC __attribute__((section(".RamFunc")))
#endif

#ifndef LA_ALWAYS_INLINE
#define LA_ALWAYS_INLINE inline __attribute__((always_inline))
#endif

#define LA_BOARD_NAME "generic_stm32_arduino_sla8"
#define LA_FIRMWARE_VERSION "SLA8-FW-V2-P3A1"

/*
 * Mac dinh dung PA0..PA7 vi UART debug o PA9/PA10 va SWD o PA13/PA14.
 * Co the doi sang PB0..PB7 bang cach sua cac macro LA_CHx_PIN va LA_INPUT_PORT.
 * Luu y PB3/PB4 co the xung dot JTAG tren mot so dong STM32.
 */
#ifndef LA_INPUT_PORT
#define LA_INPUT_PORT GPIOA
#endif

#define LA_INPUT_MASK 0x00FFUL
#define LA_INPUT_SHIFT 0U
#define LA_INPUT_CONTIGUOUS_LOW8 1
#define LA_INPUT_CONTIGUOUS_SHIFTED 0
#define LA_INPUT_SINGLE_PORT 1

#define LA_CH0_PIN PA0
#define LA_CH1_PIN PA1
#define LA_CH2_PIN PA2
#define LA_CH3_PIN PA3
#define LA_CH4_PIN PA4
#define LA_CH5_PIN PA5
#define LA_CH6_PIN PA6
#define LA_CH7_PIN PA7

#define LA_CH0_BIT 0U
#define LA_CH1_BIT 1U
#define LA_CH2_BIT 2U
#define LA_CH3_BIT 3U
#define LA_CH4_BIT 4U
#define LA_CH5_BIT 5U
#define LA_CH6_BIT 6U
#define LA_CH7_BIT 7U

#define LA_UART_RX_PIN PA10
#define LA_UART_TX_PIN PA9
#define LA_UART_BAUD_RATE 1000000UL

#define LA_TIMER_INSTANCE TIM2
#define LA_TIMER_IRQN TIM2_IRQn
#define LA_TIMER_IRQ_HANDLER TIM2_IRQHandler
#define LA_TIMER_IRQ_PRIORITY 0U
#define LA_DMA_IRQ_PRIORITY 1U
#define LA_UART_IRQN USART1_IRQn
#define LA_UART_IRQ_PRIORITY 2U
#define LA_TIMER_CLOCK_HZ 72000000UL
#define LA_TIMER_MAX_PRESCALER 65536UL
#define LA_TIMER_MAX_ARR 65535UL
#define LA_USE_DIRECT_TIMER_IRQ 1
#define LA_TIMER_ENABLE_CLOCK() __HAL_RCC_TIM2_CLK_ENABLE()

#define LA_USE_HAL_INIT 0
#define LA_USE_DIRECT_GPIO_READ 1
#ifndef LA_ENABLE_DWT_BENCHMARK
#define LA_ENABLE_DWT_BENCHMARK 0
#endif
#ifndef LA_ENABLE_DMA_CAPTURE
#define LA_ENABLE_DMA_CAPTURE 1
#endif
#define LA_ENABLE_DMA_CAPTURE_EXPERIMENTAL LA_ENABLE_DMA_CAPTURE
#define LA_DMA_MAX_TRANSFER_SAMPLES 65535U
#define LA_USB_CDC_ENABLE 0

/* Test Arduino khong dien tro: dung pull-up 3.3V noi va Arduino chi keo LOW. */
#define LA_INPUT_PULL_MODE INPUT_PULLUP

static const uint8_t LA_BOARD_INPUT_MAPPING[LA_CHANNEL_COUNT] = {
    0, 1, 2, 3, 4, 5, 6, 7,
};

static inline uint8_t la_pack_gpio_snapshot_from_idr(uint32_t idr) {
#if LA_INPUT_CONTIGUOUS_LOW8 || LA_INPUT_CONTIGUOUS_SHIFTED
  return (uint8_t)((idr & LA_INPUT_MASK) >> LA_INPUT_SHIFT);
#elif LA_INPUT_SINGLE_PORT
  /*
   * Neu pin khong lien tiep tren cung port, van chi doc IDR mot lan roi pack bit.
   * Duong mac dinh low8 khong di qua nhanh nay.
   */
  uint8_t packed = 0U;
  packed |= (idr & (1UL << LA_CH0_BIT)) ? (1U << 0) : 0U;
  packed |= (idr & (1UL << LA_CH1_BIT)) ? (1U << 1) : 0U;
  packed |= (idr & (1UL << LA_CH2_BIT)) ? (1U << 2) : 0U;
  packed |= (idr & (1UL << LA_CH3_BIT)) ? (1U << 3) : 0U;
  packed |= (idr & (1UL << LA_CH4_BIT)) ? (1U << 4) : 0U;
  packed |= (idr & (1UL << LA_CH5_BIT)) ? (1U << 5) : 0U;
  packed |= (idr & (1UL << LA_CH6_BIT)) ? (1U << 6) : 0U;
  packed |= (idr & (1UL << LA_CH7_BIT)) ? (1U << 7) : 0U;
  return packed;
#else
  /* Mapping nhieu port can doc moi port mot lan va co skew lien port. */
  return (uint8_t)((idr & LA_INPUT_MASK) >> LA_INPUT_SHIFT);
#endif
}

#if defined(ARDUINO)
static inline uint8_t la_board_read_gpio_snapshot_8ch_fast(void) {
  // Doc mot lan toan bo IDR de giam lech thoi gian giua 8 kenh.
  const uint32_t idr = LA_INPUT_PORT->IDR;
  return la_pack_gpio_snapshot_from_idr(idr);
}
#endif

#endif
