#ifndef SLA8_GENERATOR_MODES_H
#define SLA8_GENERATOR_MODES_H

#include <stdint.h>
#include <string.h>

enum GeneratorMode : uint8_t {
  MODE_GRAY,
  MODE_UART,
  MODE_I2C,
  MODE_BOTH,
  MODE_SPI,
};

static const GeneratorMode GENERATOR_DEFAULT_MODE = MODE_BOTH;
static const bool GENERATOR_SPI_OPEN_DRAIN = true;
static const uint16_t GENERATOR_AUX_STEP_RATE_HZ = 4000U;
static const uint8_t GENERATOR_AUX_CHANNEL_COUNT = 5U;

static inline bool generator_mode_emits_uart(GeneratorMode mode) {
  return mode == MODE_UART || mode == MODE_BOTH;
}

static inline bool generator_mode_emits_i2c(GeneratorMode mode) {
  return mode == MODE_I2C || mode == MODE_BOTH;
}

static inline bool generator_mode_emits_spi(GeneratorMode mode) {
  return mode == MODE_SPI || mode == MODE_BOTH;
}

static inline bool generator_mode_emits_aux(GeneratorMode mode) {
  // CH3..CH6 are owned by SPI in MODE_BOTH. The auxiliary Timer1 writer
  // updates CH3..CH7 as a group, so enabling it here corrupts SCK/MOSI/MISO/CS.
  // Keep the auxiliary timer disabled until it has dedicated, non-SPI pins.
  (void)mode;
  return false;
}

static inline uint8_t generator_aux_levels(uint8_t counter) {
  return counter & ((1U << GENERATOR_AUX_CHANNEL_COUNT) - 1U);
}

static inline uint16_t generator_mode_period_ms(GeneratorMode mode) {
  if (mode == MODE_UART) {
    return 1U;
  }
  if (mode == MODE_I2C) {
    return 2U;
  }
  if (mode == MODE_SPI) {
    return 20U;
  }
  if (mode == MODE_BOTH) {
    return 40U;
  }
  return 0U;
}

static inline uint16_t generator_uart_bit_us(GeneratorMode mode) {
  return mode == MODE_UART ? 14U : 416U;
}

static inline uint8_t generator_i2c_tick_us(GeneratorMode mode) {
  return mode == MODE_I2C ? 1U : 25U;
}

static inline uint8_t generator_spi_half_period_us(GeneratorMode mode) {
  if (mode == MODE_SPI) {
    return 5U;
  }
  if (mode == MODE_BOTH) {
    return 25U;
  }
  return 0U;
}

static inline bool generator_parse_mode_command(const char *command,
                                                GeneratorMode *mode) {
  if (command == nullptr || mode == nullptr) {
    return false;
  }
  if (strcmp(command, "MODE GRAY") == 0) {
    *mode = MODE_GRAY;
    return true;
  }
  if (strcmp(command, "MODE UART") == 0) {
    *mode = MODE_UART;
    return true;
  }
  if (strcmp(command, "MODE I2C") == 0) {
    *mode = MODE_I2C;
    return true;
  }
  if (strcmp(command, "MODE SPI") == 0) {
    *mode = MODE_SPI;
    return true;
  }
  if (strcmp(command, "MODE BOTH") == 0) {
    *mode = MODE_BOTH;
    return true;
  }
  return false;
}

static inline bool generator_parse_gray_rate_command(const char *command,
                                                     uint32_t *rate_hz) {
  static const char prefix[] = "GRAY RATE ";
  if (command == nullptr || rate_hz == nullptr ||
      strncmp(command, prefix, sizeof(prefix) - 1U) != 0) {
    return false;
  }

  const char *cursor = command + sizeof(prefix) - 1U;
  if (*cursor == '\0') {
    return false;
  }
  uint32_t value = 0U;
  while (*cursor != '\0') {
    if (*cursor < '0' || *cursor > '9') {
      return false;
    }
    const uint8_t digit = (uint8_t)(*cursor - '0');
    if (value > (UINT32_MAX - digit) / 10U) {
      return false;
    }
    value = value * 10U + digit;
    ++cursor;
  }
  if (value == 0U) {
    return false;
  }
  *rate_hz = value;
  return true;
}

static inline bool generator_gray_timer_plan(uint32_t cpu_hz,
                                             uint32_t requested_rate_hz,
                                             uint16_t *compare,
                                             uint32_t *actual_rate_hz) {
  static const uint32_t prescaler = 8U;
  if (cpu_hz == 0U || requested_rate_hz == 0U || compare == nullptr ||
      actual_rate_hz == nullptr) {
    return false;
  }
  const uint64_t denominator = (uint64_t)prescaler * requested_rate_hz;
  const uint64_t ticks = ((uint64_t)cpu_hz + denominator / 2U) / denominator;
  // Keep at least two CPU/prescaler ticks between interrupts so the 16 MHz
  // AVR never accepts rates above the deliberately bounded 1 MHz ceiling.
  if (ticks < 2U || ticks > 65536U) {
    return false;
  }
  *compare = (uint16_t)(ticks - 1U);
  *actual_rate_hz = (uint32_t)((uint64_t)cpu_hz / (prescaler * ticks));
  return true;
}

#endif
