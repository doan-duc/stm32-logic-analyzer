#include <assert.h>
#include <stdint.h>

#include "la_board.h"
#include "la_protocol.h"

static void test_64mhz_timer_clock(void) {
  la_board_timer_plan_t plan;

  assert(la_board_calculate_timer_plan(64000000UL, 100000UL, &plan));
  assert(plan.timer_clock_hz == 64000000UL);
  assert(plan.requested_sample_rate_hz == 100000UL);
  assert(plan.actual_sample_rate_hz == 100000UL);
  assert(plan.prescaler == 0U);
  assert(plan.autoreload == 639U);
  assert(plan.error_ppm == 0);

  assert(la_board_calculate_timer_plan(64000000UL, 1000000UL, &plan));
  assert(plan.actual_sample_rate_hz == 1000000UL);
  assert(plan.prescaler == 0U);
  assert(plan.autoreload == 63U);

  assert(la_board_calculate_timer_plan(64000000UL, 5818182UL, &plan));
  assert(plan.actual_sample_rate_hz == 5818181UL);
  assert(plan.prescaler == 0U);
  assert(plan.autoreload == 10U);
}

static void test_72mhz_timer_clock(void) {
  la_board_timer_plan_t plan;

  assert(la_board_calculate_timer_plan(72000000UL, 100000UL, &plan));
  assert(plan.timer_clock_hz == 72000000UL);
  assert(plan.actual_sample_rate_hz == 100000UL);
  assert(plan.prescaler == 0U);
  assert(plan.autoreload == 719U);
}

static void test_invalid_input(void) {
  la_board_timer_plan_t plan;

  assert(!la_board_calculate_timer_plan(0U, 100000UL, &plan));
  assert(!la_board_calculate_timer_plan(64000000UL, 0U, &plan));
  assert(!la_board_calculate_timer_plan(64000000UL, 5818183UL, &plan));
  assert(!la_board_calculate_timer_plan(64000000UL, 100000UL, 0));
}

static void test_verified_engine_rate_limits(void) {
  assert(la_board_sample_rate_supported(400000UL, false));
  assert(!la_board_sample_rate_supported(400001UL, false));
  assert(la_board_sample_rate_supported(5818182UL, true));
  assert(!la_board_sample_rate_supported(5818183UL, true));
}

static void test_strict_u32_parser(void) {
  uint32_t value = 0U;

  assert(la_parse_u32("100000", &value) && value == 100000UL);
  assert(la_parse_u32("0xFF", &value) && value == 255U);
  assert(la_parse_u32("0", &value) && value == 0U);
  assert(!la_parse_u32("", &value));
  assert(!la_parse_u32("-1", &value));
  assert(!la_parse_u32("100000XYZ", &value));
  assert(!la_parse_u32("0x", &value));
  assert(!la_parse_u32("4294967296", &value));
  assert(!la_parse_u32(0, &value));
  assert(!la_parse_u32("1", 0));
}

int main(void) {
  test_64mhz_timer_clock();
  test_72mhz_timer_clock();
  test_invalid_input();
  test_verified_engine_rate_limits();
  test_strict_u32_parser();
  return 0;
}
