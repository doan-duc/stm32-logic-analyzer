#include <Arduino.h>
#include <avr/interrupt.h>

static const uint8_t UART_TX_PIN = 2;
static const uint8_t I2C_SCL_PIN = 3;
static const uint8_t I2C_SDA_PIN = 4;
static const uint8_t PULSE_PINS[5] = {5, 6, 7, 8, 9};
static const uint16_t UART_BIT_US = 416;
static const uint8_t UART_EXTRA_IDLE_BITS = 3;

struct OpenDrainPin {
  volatile uint8_t *mode;
  volatile uint8_t *out;
  uint8_t mask;
};

static OpenDrainPin uart_tx;
static OpenDrainPin i2c_scl;
static OpenDrainPin i2c_sda;
static OpenDrainPin pulse_pins[5];

static uint8_t pulse_value = 0;
static uint32_t next_pulse_us = 0;
static uint32_t next_uart_ms = 0;
static uint32_t next_i2c_ms = 0;

static void od_init(OpenDrainPin &pin, uint8_t arduino_pin) {
  const uint8_t port = digitalPinToPort(arduino_pin);
  pin.mask = digitalPinToBitMask(arduino_pin);
  pin.mode = portModeRegister(port);
  pin.out = portOutputRegister(port);

  const uint8_t old_sreg = SREG;
  cli();
  *pin.out &= ~pin.mask;
  *pin.mode &= ~pin.mask;
  SREG = old_sreg;
}

static inline void od_low(const OpenDrainPin &pin) {
  *pin.out &= ~pin.mask;
  *pin.mode |= pin.mask;
}

static inline void od_release(const OpenDrainPin &pin) {
  *pin.mode &= ~pin.mask;
}

static inline void od_write(const OpenDrainPin &pin, bool high) {
  if (high) {
    od_release(pin);
  } else {
    od_low(pin);
  }
}

static void write_pulses(uint8_t value) {
  for (uint8_t bit = 0; bit < 5; ++bit) {
    od_write(pulse_pins[bit], (value >> bit) & 0x01);
  }
}

static void uart_write_byte(uint8_t value) {
  const uint8_t old_sreg = SREG;
  cli();
  od_low(uart_tx);
  delayMicroseconds(UART_BIT_US);
  for (uint8_t bit = 0; bit < 8; ++bit) {
    od_write(uart_tx, (value >> bit) & 0x01);
    delayMicroseconds(UART_BIT_US);
  }
  od_release(uart_tx);
  delayMicroseconds(UART_BIT_US);
  for (uint8_t i = 0; i < UART_EXTRA_IDLE_BITS; ++i) {
    delayMicroseconds(UART_BIT_US);
  }
  SREG = old_sreg;
}

static void i2c_tick() {
  delayMicroseconds(25);
}

static void i2c_start() {
  od_release(i2c_sda);
  od_release(i2c_scl);
  i2c_tick();
  od_low(i2c_sda);
  i2c_tick();
  od_low(i2c_scl);
}

static void i2c_stop() {
  od_low(i2c_sda);
  i2c_tick();
  od_release(i2c_scl);
  i2c_tick();
  od_release(i2c_sda);
  i2c_tick();
}

static void i2c_write_byte(uint8_t value, bool ack_low) {
  for (uint8_t mask = 0x80; mask; mask >>= 1) {
    od_write(i2c_sda, value & mask);
    i2c_tick();
    od_release(i2c_scl);
    i2c_tick();
    od_low(i2c_scl);
  }

  if (ack_low) {
    od_low(i2c_sda);
  } else {
    od_release(i2c_sda);
  }
  i2c_tick();
  od_release(i2c_scl);
  i2c_tick();
  od_low(i2c_scl);
  od_release(i2c_sda);
}

static void send_i2c_frame() {
  i2c_start();
  i2c_write_byte(0x50 << 1, true);
  i2c_write_byte(0xA5, true);
  i2c_write_byte(0x5A, false);
  i2c_stop();
}

void setup() {
  od_init(uart_tx, UART_TX_PIN);
  od_init(i2c_scl, I2C_SCL_PIN);
  od_init(i2c_sda, I2C_SDA_PIN);
  for (uint8_t bit = 0; bit < 5; ++bit) {
    od_init(pulse_pins[bit], PULSE_PINS[bit]);
  }

  write_pulses(0);
}

void loop() {
  const uint32_t now_us = micros();
  const uint32_t now_ms = millis();

  if ((int32_t)(now_us - next_pulse_us) >= 0) {
    next_pulse_us += 2000;
    write_pulses(pulse_value++);
  }

  if ((int32_t)(now_ms - next_uart_ms) >= 0) {
    next_uart_ms += 40;
    uart_write_byte(0x55);
    uart_write_byte(0xA5);
    uart_write_byte('O');
    uart_write_byte('K');
  }

  if ((int32_t)(now_ms - next_i2c_ms) >= 0) {
    next_i2c_ms += 20;
    send_i2c_frame();
  }
}
