#include <assert.h>

#include "generator_modes.h"

static void test_combined_mode_is_the_default() {
  assert(GENERATOR_DEFAULT_MODE == MODE_BOTH);
  assert(generator_mode_emits_uart(MODE_BOTH));
  assert(generator_mode_emits_i2c(MODE_BOTH));
  assert(generator_mode_emits_spi(MODE_BOTH));
  assert(generator_mode_emits_aux(MODE_BOTH));
  assert(generator_mode_period_ms(MODE_BOTH) == 40U);
}

static void test_single_protocol_modes_stay_isolated() {
  assert(generator_mode_emits_uart(MODE_UART));
  assert(!generator_mode_emits_i2c(MODE_UART));
  assert(!generator_mode_emits_aux(MODE_UART));
  assert(generator_mode_period_ms(MODE_UART) == 1U);
  assert(generator_uart_bit_us(MODE_UART) == 14U);
  assert(!generator_mode_emits_spi(MODE_UART));

  assert(!generator_mode_emits_uart(MODE_I2C));
  assert(generator_mode_emits_i2c(MODE_I2C));
  assert(!generator_mode_emits_aux(MODE_I2C));
  assert(generator_mode_period_ms(MODE_I2C) == 2U);
  assert(generator_i2c_tick_us(MODE_I2C) == 1U);
  assert(!generator_mode_emits_spi(MODE_I2C));

  assert(!generator_mode_emits_uart(MODE_SPI));
  assert(!generator_mode_emits_i2c(MODE_SPI));
  assert(!generator_mode_emits_aux(MODE_SPI));
  assert(generator_mode_period_ms(MODE_SPI) == 20U);
  assert(generator_spi_half_period_us(MODE_SPI) == 5U);
  assert(generator_mode_emits_spi(MODE_SPI));

  assert(!generator_mode_emits_uart(MODE_GRAY));
  assert(!generator_mode_emits_i2c(MODE_GRAY));
  assert(!generator_mode_emits_aux(MODE_GRAY));
  assert(generator_mode_period_ms(MODE_GRAY) == 0U);
  assert(!generator_mode_emits_spi(MODE_GRAY));

  assert(generator_uart_bit_us(MODE_BOTH) == 416U);
  assert(generator_i2c_tick_us(MODE_BOTH) == 25U);
}

static void test_auxiliary_channels_are_binary_dividers() {
  assert(GENERATOR_AUX_STEP_RATE_HZ == 4000U);
  assert(GENERATOR_AUX_CHANNEL_COUNT == 5U);
  assert(generator_aux_levels(0U) == 0x00U);
  assert(generator_aux_levels(1U) == 0x01U);
  assert(generator_aux_levels(2U) == 0x02U);
  assert(generator_aux_levels(4U) == 0x04U);
  assert(generator_aux_levels(8U) == 0x08U);
  assert(generator_aux_levels(16U) == 0x10U);
  assert(generator_aux_levels(31U) == 0x1FU);
  assert(generator_aux_levels(32U) == 0x00U);

  const uint8_t expected_transitions[GENERATOR_AUX_CHANNEL_COUNT] = {
      64U, 32U, 16U, 8U, 4U};
  const uint32_t expected_millihz[GENERATOR_AUX_CHANNEL_COUNT] = {
      2000000UL, 1000000UL, 500000UL, 250000UL, 125000UL};
  for (uint8_t channel = 0U; channel < GENERATOR_AUX_CHANNEL_COUNT; ++channel) {
    uint8_t transitions = 0U;
    uint8_t previous =
        (uint8_t)((generator_aux_levels(0U) >> channel) & 0x01U);
    for (uint8_t step = 1U; step <= 64U; ++step) {
      const uint8_t levels = generator_aux_levels(step);
      assert((levels & 0xE0U) == 0U);
      const uint8_t actual = (uint8_t)((levels >> channel) & 0x01U);
      const uint8_t expected = (uint8_t)((step >> channel) & 0x01U);
      assert(actual == expected);
      if (actual != previous) {
        ++transitions;
      }
      previous = actual;
    }
    assert(transitions == expected_transitions[channel]);
    const uint32_t actual_millihz =
        (uint32_t)GENERATOR_AUX_STEP_RATE_HZ * 1000UL / (2UL << channel);
    assert(actual_millihz == expected_millihz[channel]);
  }
}

static void test_mode_command_parser() {
  GeneratorMode parsed = MODE_GRAY;

  assert(generator_parse_mode_command("MODE BOTH", &parsed));
  assert(parsed == MODE_BOTH);
  assert(generator_parse_mode_command("MODE UART", &parsed));
  assert(parsed == MODE_UART);
  assert(generator_parse_mode_command("MODE I2C", &parsed));
  assert(parsed == MODE_I2C);
  assert(generator_parse_mode_command("MODE SPI", &parsed));
  assert(parsed == MODE_SPI);
  assert(generator_parse_mode_command("MODE GRAY", &parsed));
  assert(parsed == MODE_GRAY);

  assert(!generator_parse_mode_command("MODE UNKNOWN", &parsed));
  assert(!generator_parse_mode_command(nullptr, &parsed));
  assert(!generator_parse_mode_command("MODE BOTH", nullptr));
}

static void test_gray_rate_command_and_timer_plan() {
  uint32_t rate_hz = 0U;
  uint16_t compare = 0U;
  uint32_t actual_rate_hz = 0U;

  assert(generator_parse_gray_rate_command("GRAY RATE 100000", &rate_hz));
  assert(rate_hz == 100000UL);
  assert(!generator_parse_gray_rate_command("GRAY RATE 0", &rate_hz));
  assert(!generator_parse_gray_rate_command("GRAY RATE 100000X", &rate_hz));
  assert(!generator_parse_gray_rate_command("RATE 100000", &rate_hz));
  assert(!generator_parse_gray_rate_command(nullptr, &rate_hz));
  assert(!generator_parse_gray_rate_command("GRAY RATE 100000", nullptr));

  assert(generator_gray_timer_plan(16000000UL, 100000UL, &compare,
                                   &actual_rate_hz));
  assert(compare == 19U);
  assert(actual_rate_hz == 100000UL);
  assert(generator_gray_timer_plan(16000000UL, 10000UL, &compare,
                                   &actual_rate_hz));
  assert(compare == 199U);
  assert(actual_rate_hz == 10000UL);
  assert(!generator_gray_timer_plan(16000000UL, 0U, &compare,
                                    &actual_rate_hz));
  assert(!generator_gray_timer_plan(16000000UL, 2000000UL, &compare,
                                    &actual_rate_hz));
}

int main() {
  test_combined_mode_is_the_default();
  test_single_protocol_modes_stay_isolated();
  test_auxiliary_channels_are_binary_dividers();
  test_mode_command_parser();
  test_gray_rate_command_and_timer_plan();
  return 0;
}
