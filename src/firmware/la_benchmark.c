#include "la_capture.h"

/*
 * Nhập các file tiêu đề của thư viện HAL tương ứng với dòng chip STM32 được sử dụng.
 */
#if defined(STM32F1xx)
#include "stm32f1xx.h"
#elif defined(STM32F4xx)
#include "stm32f4xx.h"
#elif defined(STM32L4xx)
#include "stm32l4xx.h"
#endif

/*
 * Các biến tĩnh toàn cục lưu trữ thông tin đo đạc chu kỳ CPU chạy ngắt (ISR):
 * - last_isr_cycles: Số chu kỳ CPU tiêu tốn trong lần ngắt (ISR) gần nhất.
 * - max_isr_cycles: Số chu kỳ CPU tiêu tốn nhiều nhất (tệ nhất) ghi nhận được.
 * - min_isr_cycles: Số chu kỳ CPU tiêu tốn ít nhất (tốt nhất) ghi nhận được.
 * - total_isr_cycles: Tổng số chu kỳ CPU tiêu tốn qua tất cả các lần ngắt.
 * - sample_count: Tổng số mẫu ngắt đã đo đạc.
 * - start_cycles: Giá trị thanh ghi DWT->CYCCNT tại thời điểm bắt đầu đo.
 * - dwt_available: Trạng thái cho biết bộ đếm DWT có khả dụng và hoạt động được không.
 */
static uint32_t last_isr_cycles = 0U;
static uint32_t max_isr_cycles = 0U;
static uint32_t min_isr_cycles = 0xFFFFFFFFUL;
static uint32_t total_isr_cycles = 0U;
static uint32_t sample_count = 0U;
static uint32_t start_cycles = 0U;
static bool dwt_available = false;

/*
 * Hàm khởi tạo bộ đo đạc chu kỳ CPU (DWT Benchmark).
 * Kích hoạt khối debug DWT (Data Watchpoint and Trace) trên nhân ARM Cortex-M.
 */
void la_benchmark_init(void) {
#if defined(LA_ENABLE_DWT_BENCHMARK) && LA_ENABLE_DWT_BENCHMARK &&             \
    defined(DWT) && defined(CoreDebug) && defined(CoreDebug_DEMCR_TRCENA_Msk)
  /* Kích hoạt bit TRCENA trong thanh ghi DEMCR của CoreDebug để mở nguồn cho DWT */
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  /* Đặt lại bộ đếm chu kỳ về 0 */
  DWT->CYCCNT = 0U;
  /* Cho phép bộ đếm chu kỳ (CYCCNT) bắt đầu hoạt động */
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
  /* Kiểm tra xem bit kích hoạt bộ đếm đã thực sự được bật chưa để gán trạng thái khả dụng */
  dwt_available = (DWT->CTRL & DWT_CTRL_CYCCNTENA_Msk) != 0U;
#else
  /* Nếu cấu hình tắt đo đạc hoặc MCU không hỗ trợ DWT */
  dwt_available = false;
#endif
}

/*
 * Bắt đầu ghi nhận thời điểm đo chu kỳ CPU (thường gọi ở đầu hàm ngắt ISR).
 */
void la_benchmark_start_cycles(void) {
#if defined(LA_ENABLE_DWT_BENCHMARK) && LA_ENABLE_DWT_BENCHMARK &&             \
    defined(DWT)
  if (dwt_available) {
    /* Đọc giá trị bộ đếm chu kỳ hiện tại của CPU */
    start_cycles = DWT->CYCCNT;
  }
#else
  start_cycles = 0U;
#endif
}

/*
 * Kết thúc ghi nhận chu kỳ CPU và cập nhật các thống kê (thường gọi ở cuối hàm ngắt ISR).
 */
void la_benchmark_stop_cycles(void) {
#if defined(LA_ENABLE_DWT_BENCHMARK) && LA_ENABLE_DWT_BENCHMARK &&             \
    defined(DWT)
  if (dwt_available) {
    /* Lấy giá trị chu kỳ CPU hiện tại */
    const uint32_t now = DWT->CYCCNT;
    /* Tính toán số chu kỳ đã trôi qua kể từ lúc gọi start_cycles */
    last_isr_cycles = now - start_cycles;
    
    /* Cập nhật số chu kỳ lớn nhất (tệ nhất) */
    if (last_isr_cycles > max_isr_cycles) {
      max_isr_cycles = last_isr_cycles;
    }
    /* Cập nhật số chu kỳ nhỏ nhất (tốt nhất) */
    if (last_isr_cycles < min_isr_cycles) {
      min_isr_cycles = last_isr_cycles;
    }
    /* Cộng dồn để tính trung bình */
    total_isr_cycles += last_isr_cycles;
    /* Tăng số đếm số mẫu ngắt đã ghi nhận */
    sample_count++;
  }
#else
  /* Không có DWT thì không tạo số đo giả */
  last_isr_cycles = 0U;
#endif
}

/*
 * Trả về trạng thái bộ đo chu kỳ DWT có khả dụng hay không.
 */
bool la_benchmark_is_available(void) { return dwt_available; }

/*
 * Lấy số chu kỳ CPU của lần ngắt gần nhất.
 */
uint32_t la_benchmark_get_last_isr_cycles(void) { return last_isr_cycles; }

/*
 * Lấy số chu kỳ CPU lớn nhất (tệ nhất) đã đo được.
 */
uint32_t la_benchmark_get_max_isr_cycles(void) { return max_isr_cycles; }

/*
 * Lấy số chu kỳ CPU nhỏ nhất (tốt nhất) đã đo được.
 * Trả về 0 nếu chưa có mẫu đo nào.
 */
uint32_t la_benchmark_get_min_isr_cycles(void) {
  return sample_count == 0U ? 0U : min_isr_cycles;
}

/*
 * Tính toán và trả về số chu kỳ CPU trung bình tiêu tốn cho một lần ngắt.
 * Trả về 0 nếu chưa có mẫu đo nào.
 */
uint32_t la_benchmark_get_average_isr_cycles(void) {
  return sample_count == 0U ? 0U : (total_isr_cycles / sample_count);
}

/*
 * Lấy tổng số lần ngắt đã thực hiện đo đạc.
 */
uint32_t la_benchmark_get_sample_count(void) { return sample_count; }
