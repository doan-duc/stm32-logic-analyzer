#include <Arduino.h>
#include <avr/interrupt.h>

#include "generator_modes.h"

static const uint8_t SIGNAL_PINS[8] = {2, 3, 4, 5, 6, 7, 8, 9};
static const uint8_t UART_TX_CHANNEL = 0;
static const uint8_t I2C_SCL_CHANNEL = 1;
static const uint8_t I2C_SDA_CHANNEL = 2;
static const uint8_t SPI_SCK_CHANNEL = 3;
static const uint8_t SPI_MOSI_CHANNEL = 4;
static const uint8_t SPI_MISO_CHANNEL = 5;
static const uint8_t SPI_CS_CHANNEL = 6;
static const uint8_t SPI_UNUSED_CHANNEL = 7;
static const uint32_t DEFAULT_GRAY_STEP_RATE_HZ = 10000UL;
static const uint8_t UART_EXTRA_IDLE_BITS = 3;
static const uint8_t PROTOCOL_START_DELAY_MS = 40;

struct OpenDrainPin {
  volatile uint8_t *mode;
  volatile uint8_t *out;
  uint8_t mask;
};

static OpenDrainPin signal_pins[8];
static volatile uint8_t gray_counter = 0;
static volatile uint8_t aux_counter = 0;
static volatile GeneratorMode active_mode = GENERATOR_DEFAULT_MODE;
static uint32_t gray_step_rate_hz = DEFAULT_GRAY_STEP_RATE_HZ;
static uint32_t next_protocol_ms = 0;
static bool spi_aux_square = false;
static char command_buffer[32];
static uint8_t command_length = 0;

static void od_init(OpenDrainPin &pin, uint8_t arduino_pin) {
  const uint8_t port = digitalPinToPort(arduino_pin);
  pin.mask = digitalPinToBitMask(arduino_pin);
  pin.mode = portModeRegister(port);
  pin.out = portOutputRegister(port);

  const uint8_t old_sreg = SREG;
  cli();
  *pin.out &= (uint8_t)~pin.mask;
  *pin.mode &= (uint8_t)~pin.mask;
  SREG = old_sreg;
}

static inline void od_low(const OpenDrainPin &pin) {
  const uint8_t old_sreg = SREG;
  cli();
  *pin.out &= (uint8_t)~pin.mask;
  *pin.mode |= pin.mask;
  SREG = old_sreg;
}

static inline void od_release(const OpenDrainPin &pin) {
  const uint8_t old_sreg = SREG;
  cli();
  *pin.mode &= (uint8_t)~pin.mask;
  SREG = old_sreg;
}

static inline void od_write(const OpenDrainPin &pin, bool high) {
  high ? od_release(pin) : od_low(pin);
}

static void release_all_signals() {
  for (uint8_t index = 0; index < 8; ++index) {
    od_release(signal_pins[index]);
  }
}

static inline __attribute__((always_inline)) uint8_t binary_to_gray(uint8_t value) {
  return (uint8_t)(value ^ (value >> 1));
}

static inline __attribute__((always_inline)) void write_gray_open_drain(uint8_t gray) {
  const uint8_t low_mask = (uint8_t)~gray;
  // D2..D7 are PD2..PD7; D8..D9 are PB0..PB1. The output latches remain LOW.
  DDRD = (uint8_t)((DDRD & 0x03U) | ((low_mask << 2) & 0xFCU));
  DDRB = (uint8_t)((DDRB & 0xFCU) | ((low_mask >> 6) & 0x03U));
}

static inline __attribute__((always_inline)) void
write_aux_open_drain(uint8_t levels) {
  // Auxiliary logical bits 0..4 map to CH3..CH7 / D5..D9. Preserve D2..D4,
  // which are owned by UART and I2C. A logical HIGH releases the pin; LOW
  // selects output mode while the output latch remains zero (open drain).
  const uint8_t low_mask = (uint8_t)(~levels) & 0x1FU;
  DDRD = (uint8_t)((DDRD & 0x1FU) | ((low_mask << 5) & 0xE0U));
  DDRB = (uint8_t)((DDRB & 0xFCU) | ((low_mask >> 3) & 0x03U));
}

static inline uint8_t generator_both_aux_levels(uint8_t counter) {
  // Keep a single auxiliary square wave on CH7 (D9) when BOTH is active.
  return (uint8_t)((counter & 0x01U) ? 0x00U : 0x10U);
}

ISR(TIMER1_COMPA_vect) {
  if (active_mode == MODE_GRAY) {
    write_gray_open_drain(binary_to_gray(gray_counter));
    gray_counter++;
} else if (active_mode == MODE_BOTH) {
    write_aux_open_drain(generator_both_aux_levels(aux_counter));
    aux_counter++;
  }
}

static void stop_waveform_timer() {
  const uint8_t old_sreg = SREG;
  cli();
  TIMSK1 = 0U;
  TCCR1B = 0U;
  SREG = old_sreg;
}

static void start_gray_timer() {
  uint16_t compare = 0U;
  uint32_t actual_rate_hz = 0U;
  if (!generator_gray_timer_plan(F_CPU, gray_step_rate_hz, &compare,
                                 &actual_rate_hz)) {
    return;
  }
  gray_step_rate_hz = actual_rate_hz;

  const uint8_t old_sreg = SREG;
  cli();
  PORTD &= 0x03U;
  PORTB &= 0xFCU;
  gray_counter = 0U;
  write_gray_open_drain(binary_to_gray(gray_counter++));
  TCCR1A = 0U;
  TCCR1B = 0U;
  TCNT1 = 0U;
  OCR1A = compare;
  TIFR1 = _BV(OCF1A);
  TCCR1B = _BV(WGM12) | _BV(CS11);
  TIMSK1 = _BV(OCIE1A);
  SREG = old_sreg;
}

static void start_aux_timer() {
  static_assert(F_CPU % (8UL * GENERATOR_AUX_STEP_RATE_HZ) == 0,
                "GENERATOR_AUX_STEP_RATE_HZ must divide the Timer1 clock");
  const uint16_t compare =
      (uint16_t)(F_CPU / (8UL * GENERATOR_AUX_STEP_RATE_HZ) - 1UL);

  const uint8_t old_sreg = SREG;
  cli();
  PORTD &= 0x1FU;
  PORTB &= 0xFCU;
  aux_counter = 0U;
  write_aux_open_drain(generator_aux_levels(aux_counter++));
  TCCR1A = 0U;
  TCCR1B = 0U;
  TCNT1 = 0U;
  OCR1A = compare;
  TIFR1 = _BV(OCF1A);
  TCCR1B = _BV(WGM12) | _BV(CS11);
  TIMSK1 = _BV(OCIE1A);
  SREG = old_sreg;
}

static void uart_write_byte(uint8_t value) {
  const OpenDrainPin &tx = signal_pins[UART_TX_CHANNEL];
  const uint16_t bit_us = generator_uart_bit_us(active_mode);
  od_low(tx);
  delayMicroseconds(bit_us);
  for (uint8_t bit = 0; bit < 8; ++bit) {
    od_write(tx, ((value >> bit) & 0x01U) != 0U);
    delayMicroseconds(bit_us);
  }
  od_release(tx);
  delayMicroseconds(bit_us);
  for (uint8_t bit = 0; bit < UART_EXTRA_IDLE_BITS; ++bit) {
    delayMicroseconds(bit_us);
  }
}

static void send_uart_frame() {
  uart_write_byte(0x55U);
  uart_write_byte(0xA5U);
  uart_write_byte('O');
  uart_write_byte('K');
}

static inline void i2c_tick() {
  delayMicroseconds(generator_i2c_tick_us(active_mode));
}

static void i2c_start() {
  od_release(signal_pins[I2C_SDA_CHANNEL]);
  od_release(signal_pins[I2C_SCL_CHANNEL]);
  i2c_tick();
  od_low(signal_pins[I2C_SDA_CHANNEL]);
  i2c_tick();
  od_low(signal_pins[I2C_SCL_CHANNEL]);
}

static void i2c_stop() {
  od_low(signal_pins[I2C_SDA_CHANNEL]);
  i2c_tick();
  od_release(signal_pins[I2C_SCL_CHANNEL]);
  i2c_tick();
  od_release(signal_pins[I2C_SDA_CHANNEL]);
  i2c_tick();
}

static void i2c_write_byte(uint8_t value, bool ack_low) {
  for (uint8_t mask = 0x80U; mask != 0U; mask >>= 1) {
    od_write(signal_pins[I2C_SDA_CHANNEL], (value & mask) != 0U);
    i2c_tick();
    od_release(signal_pins[I2C_SCL_CHANNEL]);
    i2c_tick();
    od_low(signal_pins[I2C_SCL_CHANNEL]);
  }

  ack_low ? od_low(signal_pins[I2C_SDA_CHANNEL])
          : od_release(signal_pins[I2C_SDA_CHANNEL]);
  i2c_tick();
  od_release(signal_pins[I2C_SCL_CHANNEL]);
  i2c_tick();
  od_low(signal_pins[I2C_SCL_CHANNEL]);
  od_release(signal_pins[I2C_SDA_CHANNEL]);
}

static void spi_write_byte(uint8_t mosi_value, uint8_t miso_value) {
  const uint16_t half_period_us = generator_spi_half_period_us(active_mode);
  for (uint8_t mask = 0x80U; mask != 0U; mask >>= 1) {
    od_write(signal_pins[SPI_MOSI_CHANNEL], (mosi_value & mask) != 0U);
    od_write(signal_pins[SPI_MISO_CHANNEL], (miso_value & mask) != 0U);
    delayMicroseconds(half_period_us);
    od_write(signal_pins[SPI_SCK_CHANNEL], true);
    delayMicroseconds(half_period_us);
    od_write(signal_pins[SPI_SCK_CHANNEL], false);
  }
}

static void send_spi_frame() {
  spi_aux_square = !spi_aux_square;
  od_write(signal_pins[SPI_UNUSED_CHANNEL], spi_aux_square);
  od_write(signal_pins[SPI_CS_CHANNEL], false);
  delayMicroseconds(generator_spi_half_period_us(active_mode));

  spi_write_byte(0x55U, 0xA5U);
  spi_write_byte(0xA5U, 0x3CU);
  spi_write_byte(0x5AU, 0xC3U);

  od_write(signal_pins[SPI_CS_CHANNEL], true);
  od_write(signal_pins[SPI_SCK_CHANNEL], false);
  od_write(signal_pins[SPI_MOSI_CHANNEL], true);
  od_write(signal_pins[SPI_MISO_CHANNEL], true);
}

static void send_i2c_frame() {
  i2c_start();
  i2c_write_byte(0x50U << 1, true);
  i2c_write_byte(0xA5U, true);
  i2c_write_byte(0x5AU, false);
  i2c_stop();
}

static const __FlashStringHelper *mode_name(GeneratorMode mode) {
  switch (mode) {
  case MODE_GRAY:
    return F("GRAY");
  case MODE_UART:
    return F("UART");
  case MODE_I2C:
    return F("I2C");
  case MODE_BOTH:
    return F("BOTH");
  case MODE_SPI:
    return F("SPI");
  default:
    return F("UNKNOWN");
  }
}

static void set_mode(GeneratorMode mode) {
  stop_waveform_timer();
  release_all_signals();
  active_mode = mode;
  if (mode == MODE_GRAY) {
    start_gray_timer();
    next_protocol_ms = 0U;
  } else {
    if (generator_mode_emits_aux(mode)) {
      start_aux_timer();
    }
    if (mode == MODE_SPI || mode == MODE_BOTH) {
      od_write(signal_pins[SPI_SCK_CHANNEL], false);
      od_write(signal_pins[SPI_MOSI_CHANNEL], true);
      od_write(signal_pins[SPI_MISO_CHANNEL], true);
      od_write(signal_pins[SPI_CS_CHANNEL], true);
      spi_aux_square = false;
      od_write(signal_pins[SPI_UNUSED_CHANNEL], spi_aux_square);
    }
    // Let the USB command response finish before the first timing-sensitive burst.
    next_protocol_ms = millis() + PROTOCOL_START_DELAY_MS;
  }
}

static void handle_command(char *command) {
  for (char *cursor = command; *cursor != '\0'; ++cursor) {
    *cursor = (char)toupper((unsigned char)*cursor);
  }

  GeneratorMode requested_mode = MODE_GRAY;
  uint32_t requested_gray_rate_hz = 0U;
  if (generator_parse_mode_command(command, &requested_mode)) {
    set_mode(requested_mode);
  } else if (generator_parse_gray_rate_command(command,
                                                &requested_gray_rate_hz)) {
    uint16_t compare = 0U;
    uint32_t actual_rate_hz = 0U;
    if (!generator_gray_timer_plan(F_CPU, requested_gray_rate_hz, &compare,
                                   &actual_rate_hz)) {
      Serial.println(F("ERR BAD_GRAY_RATE"));
      return;
    }
    gray_step_rate_hz = actual_rate_hz;
    if (active_mode == MODE_GRAY) {
      start_gray_timer();
    }
    Serial.print(F("OK GRAY RATE "));
    Serial.println(gray_step_rate_hz);
    return;
  } else if (strcmp(command, "STATUS") == 0) {
    Serial.print(F("MODE "));
    Serial.println(mode_name(active_mode));
    Serial.print(F("GRAY_RATE "));
    Serial.println(gray_step_rate_hz);
    return;
  } else if (strcmp(command, "PING") == 0) {
    Serial.println(F("PONG SLA8-GEN"));
    return;
  } else {
    Serial.println(F("ERR UNKNOWN"));
    return;
  }

  Serial.print(F("OK MODE "));
  Serial.println(mode_name(active_mode));
}

static void poll_serial_commands() {
  while (Serial.available() > 0) {
    const char c = (char)Serial.read();
    if (c == '\r' || c == '\n') {
      if (command_length > 0U) {
        command_buffer[command_length] = '\0';
        handle_command(command_buffer);
        command_length = 0U;
      }
    } else if (command_length < sizeof(command_buffer) - 1U) {
      command_buffer[command_length++] = c;
    } else {
      command_length = 0U;
      Serial.println(F("ERR CMD_TOO_LONG"));
    }
  }
}

void setup() {
  Serial.begin(115200);
  for (uint8_t index = 0; index < 8; ++index) {
    od_init(signal_pins[index], SIGNAL_PINS[index]);
  }
  set_mode(GENERATOR_DEFAULT_MODE);
  Serial.println(F("READY SLA8-GEN"));
}

void loop() {
  poll_serial_commands();

  const uint32_t now_ms = millis();
  if ((int32_t)(now_ms - next_protocol_ms) < 0) {
    return;
  }
  const uint16_t period_ms = generator_mode_period_ms(active_mode);
  if (period_ms == 0U) {
    return;
  }

  // Use now + period rather than += period: a delayed loop never catches up in
  // a burst. UART is emitted first so a PA0 falling-edge capture also contains
  // the following I2C transaction.
  next_protocol_ms = now_ms + period_ms;
  if (generator_mode_emits_uart(active_mode)) {
    send_uart_frame();
  }
  if (generator_mode_emits_i2c(active_mode)) {
    send_i2c_frame();
  }
  if (generator_mode_emits_spi(active_mode)) {
    send_spi_frame();
  }
}
