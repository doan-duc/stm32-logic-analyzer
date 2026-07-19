#ifndef BOARD_CONFIG_H
#define BOARD_CONFIG_H

#include <stdbool.h>
#include <stdint.h>

/* 
 * Số lượng kênh đo Logic Analyzer (mặc định là 8 kênh).
 */
#ifndef LA_CHANNEL_COUNT
#define LA_CHANNEL_COUNT 8U
#endif

/*
 * Kiểu dữ liệu lưu trữ cho mỗi mẫu logic. Do đo 8 kênh nên mỗi mẫu có kích thước là 1 byte (uint8_t).
 */
#define LA_SAMPLE_TYPE uint8_t

/*
 * Tần số lấy mẫu mặc định khi khởi động thiết bị, đơn vị Hz (mặc định là 100 kHz).
 */
#define LA_DEFAULT_SAMPLE_RATE_HZ 100000UL

/*
 * Cấu hình dung lượng RAM của bo mạch STM32 tương ứng được chọn lúc biên dịch.
 * Dung lượng RAM được định nghĩa bằng bytes để làm căn cứ tính toán bộ đệm dữ liệu.
 */
#ifndef LA_BOARD_RAM_BYTES
#if defined(STM32F103x6)
#define LA_BOARD_RAM_BYTES 10240U     // STM32F103C6 có 10 KB RAM
#elif defined(STM32F103xB) || defined(STM32F103x8)
#define LA_BOARD_RAM_BYTES 20480U     // STM32F103C8/CB có 20 KB RAM
#elif defined(STM32F401xC)
#define LA_BOARD_RAM_BYTES 65536U     // STM32F401CC có 64 KB RAM
#elif defined(STM32F401xE)
#define LA_BOARD_RAM_BYTES 98304U     // STM32F401CE có 96 KB RAM
#elif defined(STM32F411xE)
#define LA_BOARD_RAM_BYTES 131072U    // STM32F411CE có 128 KB RAM
#else
#define LA_BOARD_RAM_BYTES 20480U     // Mặc định dự phòng là 20 KB RAM
#endif
#endif

/*
 * Tính toán dung lượng bộ đệm mẫu dữ liệu tối đa dựa trên dung lượng RAM thực tế của MCU.
 * Việc phân bổ bộ đệm cần chừa lại một phần RAM cho các hoạt động runtime của hệ thống.
 */
#ifndef LA_CAPTURE_BUFFER_SAMPLES
#if LA_BOARD_RAM_BYTES <= 10240U
#define LA_CAPTURE_BUFFER_SAMPLES 6656U     // Cho MCU 10 KB RAM
#elif LA_BOARD_RAM_BYTES <= 20480U
#define LA_CAPTURE_BUFFER_SAMPLES 13888U    // Cho MCU 20 KB RAM
#else
#define LA_CAPTURE_BUFFER_SAMPLES 49152U    // Cho các dòng F4 nhiều RAM hơn
#endif
#endif

/*
 * Cấu hình giới hạn bộ nhớ dự phòng an toàn để tránh xung đột Stack/Heap.
 * LA_MIN_RUNTIME_FREE_BYTES: Dung lượng RAM tối thiểu phải giữ trống khi chạy ứng dụng.
 * LA_STATIC_OVERHEAD_BUDGET_BYTES: Bộ nhớ ước tính dành cho các biến tĩnh toàn cục khác.
 */
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

/*
 * Dung lượng RAM tối đa ước tính phân bổ cho các hàm thực thi trên RAM (.RamFunc).
 */
#define LA_RAMFUNC_BUDGET_BYTES 512U

/*
 * Tính toán tổng kích thước bộ đệm (byte) dựa trên số lượng mẫu và kiểu dữ liệu mẫu.
 */
#define LA_CAPTURE_BUFFER_BYTES \
  ((uint32_t)(LA_CAPTURE_BUFFER_SAMPLES * sizeof(LA_SAMPLE_TYPE)))

/*
 * Macro kiểm tra tĩnh (Static Assert) tại thời điểm biên dịch.
 * Đảm bảo trình biên dịch C hoặc C++ đều hỗ trợ kiểm tra tính hợp lệ của phân bổ bộ nhớ.
 */
#if defined(__cplusplus)
#define LA_STATIC_ASSERT(expr, msg) static_assert((expr), msg)
#else
#define LA_STATIC_ASSERT(expr, msg) _Static_assert((expr), msg)
#endif

/*
 * Kiểm tra xem tổng RAM chiếm dụng (Bộ đệm + RAMFunc + RAM tĩnh + RAM Runtime trống tối thiểu)
 * có vượt quá tổng dung lượng RAM vật lý của vi điều khiển hay không.
 */
LA_STATIC_ASSERT(
    ((LA_CAPTURE_BUFFER_SAMPLES * sizeof(LA_SAMPLE_TYPE)) +
     LA_RAMFUNC_BUDGET_BYTES + LA_STATIC_OVERHEAD_BUDGET_BYTES +
     LA_MIN_RUNTIME_FREE_BYTES) <= LA_BOARD_RAM_BYTES,
    "LA_CAPTURE_BUFFER_SAMPLES exceeds estimated RAM budget");

/*
 * Cấu hình số mẫu lưu trữ trước và sau khi kích hoạt trigger.
 * Mặc định không lưu mẫu pre-trigger, lưu tất cả mẫu sau trigger.
 */
#define LA_DEFAULT_PRETRIGGER_SAMPLES 0U
#define LA_DEFAULT_POSTTRIGGER_SAMPLES (LA_CAPTURE_BUFFER_SAMPLES - 1U)

/*
 * Định nghĩa thuộc tính đặt các hàm quan trọng vào phân vùng RAM (.RamFunc).
 * Việc chạy code trên RAM sẽ nhanh hơn và có chu kỳ truy xuất ổn định hơn trên Flash.
 */
#ifndef LA_RAMFUNC
#define LA_RAMFUNC __attribute__((section(".RamFunc")))
#endif

/*
 * Ép buộc trình biên dịch phải inline hàm (nhúng trực tiếp code của hàm vào nơi gọi)
 * giúp triệt tiêu hoàn toàn chi phí gọi hàm (function call overhead), tối ưu hóa thời gian thực thi.
 */
#ifndef LA_ALWAYS_INLINE
#define LA_ALWAYS_INLINE inline __attribute__((always_inline))
#endif

/*
 * Tên bo mạch nhận diện và phiên bản firmware hiện tại gửi về cho phần mềm PC.
 */
#define LA_BOARD_NAME "generic_stm32_arduino_sla8"
#ifndef LA_FIRMWARE_VERSION
#define LA_FIRMWARE_VERSION "SLA8-FW-V2-P5"
#endif

/*
 * Mặc định sử dụng GPIOA chân PA0 đến PA7 làm các kênh đo Logic Analyzer.
 * Sử dụng GPIOA vì cổng UART debug dùng PA9/PA10 và cổng nạp SWD dùng PA13/PA14, không bị chồng chéo.
 * Có thể cấu hình sang GPIOB (chân PB0..PB7) tuy nhiên cần lưu ý PB3/PB4 thường dùng cho JTAG.
 */
#ifndef LA_INPUT_PORT
#define LA_INPUT_PORT GPIOA
#endif

/*
 * Mặt nạ bit (Mask) và số bit dịch (Shift) để trích xuất dữ liệu từ thanh ghi đầu vào GPIO IDR.
 */
#define LA_INPUT_MASK 0x00FFUL
#define LA_INPUT_SHIFT 0U

/*
 * Cấu hình vị trí sắp xếp của các chân tín hiệu đầu vào:
 * LA_INPUT_CONTIGUOUS_LOW8: 8 chân tín hiệu nằm liên tục từ bit 0 tới bit 7 (PA0-PA7).
 * LA_INPUT_CONTIGUOUS_SHIFTED: 8 chân tín hiệu nằm liên tục nhưng bị dịch (ví dụ bit 8 đến bit 15).
 * LA_INPUT_SINGLE_PORT: Các chân nằm trên cùng một Port vật lý (nhưng có thể không liên tục).
 */
#define LA_INPUT_CONTIGUOUS_LOW8 1
#define LA_INPUT_CONTIGUOUS_SHIFTED 0
#define LA_INPUT_SINGLE_PORT 1

/*
 * Khai báo định danh các chân phần cứng tương ứng cho các kênh 0 đến 7.
 */
#define LA_CH0_PIN PA0
#define LA_CH1_PIN PA1
#define LA_CH2_PIN PA2
#define LA_CH3_PIN PA3
#define LA_CH4_PIN PA4
#define LA_CH5_PIN PA5
#define LA_CH6_PIN PA6
#define LA_CH7_PIN PA7

/*
 * Thứ tự bit tương ứng trong thanh ghi dữ liệu đầu vào.
 */
#define LA_CH0_BIT 0U
#define LA_CH1_BIT 1U
#define LA_CH2_BIT 2U
#define LA_CH3_BIT 3U
#define LA_CH4_BIT 4U
#define LA_CH5_BIT 5U
#define LA_CH6_BIT 6U
#define LA_CH7_BIT 7U

/*
 * Chân UART được cấu hình để truyền thông với PC.
 * TX = PA9, RX = PA10 (của USART1).
 */
#define LA_UART_RX_PIN PA10
#define LA_UART_TX_PIN PA9

/*
 * Tốc độ Baud Rate truyền UART. Đặt tốc độ cao 1 Mbps để gửi dữ liệu nhanh về PC.
 */
#define LA_UART_BAUD_RATE 1000000UL

/*
 * Cấu hình phần cứng Timer làm bộ tạo nhịp lấy mẫu.
 * Mặc định sử dụng TIM2.
 */
#define LA_TIMER_INSTANCE TIM2
#define LA_TIMER_IRQN TIM2_IRQn
#define LA_TIMER_IRQ_HANDLER TIM2_IRQHandler

/*
 * Mức ưu tiên ngắt của hệ thống. Ngắt Timer lấy mẫu được ưu tiên cao nhất (0) để đảm bảo độ chính xác thời gian.
 * Ngắt DMA (1) và ngắt UART truyền nhận dữ liệu (2) có độ ưu tiên thấp hơn.
 */
#define LA_TIMER_IRQ_PRIORITY 0U
#define LA_DMA_IRQ_PRIORITY 1U
#define LA_UART_IRQN USART1_IRQn
#define LA_UART_IRQ_PRIORITY 2U

/*
 * Sử dụng ngắt trực tiếp từ Timer để lấy mẫu (thay vì qua API HAL).
 */
#define LA_USE_DIRECT_TIMER_IRQ 1

/*
 * Macro kích hoạt cấp nguồn cấp clock cho bộ Timer TIM2.
 */
#define LA_TIMER_ENABLE_CLOCK() __HAL_RCC_TIM2_CLK_ENABLE()

/*
 * Cấu hình tối ưu hiệu năng:
 * LA_USE_HAL_INIT = 0: Không dùng các hàm khởi tạo cồng kềnh của HAL, tự cấu hình ghi đè thanh ghi để chạy nhanh hơn.
 * LA_USE_DIRECT_GPIO_READ = 1: Đọc trực tiếp từ thanh ghi IDR thay vì gọi hàm HAL_GPIO_ReadPin.
 */
#define LA_USE_HAL_INIT 0
#define LA_USE_DIRECT_GPIO_READ 1

/*
 * Kích hoạt đo đạc hiệu năng thông qua bộ đếm chu kỳ DWT (Data Watchpoint and Trace).
 */
#ifndef LA_ENABLE_DWT_BENCHMARK
#define LA_ENABLE_DWT_BENCHMARK 0
#endif

/*
 * Cho phép/Không cho phép sử dụng DMA để truyền dữ liệu tự động từ thanh ghi GPIO IDR vào RAM.
 */
#ifndef LA_ENABLE_DMA_CAPTURE
#define LA_ENABLE_DMA_CAPTURE 1
#endif
#define LA_ENABLE_DMA_CAPTURE_EXPERIMENTAL LA_ENABLE_DMA_CAPTURE

/*
 * Kích thước truyền tải dữ liệu DMA tối đa trong một lần cấu hình (giới hạn thanh ghi CNDTR là 65535 mẫu).
 */
#define LA_DMA_MAX_TRANSFER_SAMPLES 65535U

/*
 * Không sử dụng USB CDC (chuyển đổi cổng COM ảo qua USB) mà sử dụng UART thuần.
 */
#define LA_USB_CDC_ENABLE 0

/*
 * Cấu hình chế độ điện trở kéo của các chân đo đầu vào.
 * Sử dụng INPUT_PULLUP (kéo lên nguồn 3.3V) giúp đầu vào không bị trôi lơ lửng khi không cắm thiết bị đo.
 */
#define LA_INPUT_PULL_MODE INPUT_PULLUP

/*
 * Mảng ánh xạ các kênh đầu vào logic sang chân tương ứng trên MCU.
 */
static const uint8_t LA_BOARD_INPUT_MAPPING[LA_CHANNEL_COUNT] = {
    0, 1, 2, 3, 4, 5, 6, 7,
};

/*
 * Hàm phụ trợ inline để đóng gói trạng thái đọc từ thanh ghi đầu vào GPIO IDR (32-bit) thành 1 byte (8-bit) duy nhất.
 * idr: Giá trị đọc được từ thanh ghi IDR.
 */
static inline uint8_t la_pack_gpio_snapshot_from_idr(uint32_t idr) {
#if LA_INPUT_CONTIGUOUS_LOW8 || LA_INPUT_CONTIGUOUS_SHIFTED
  /* Nếu các chân nằm liên tiếp, chỉ cần lọc qua mặt nạ bit và dịch bit để lấy giá trị nhanh nhất. */
  return (uint8_t)((idr & LA_INPUT_MASK) >> LA_INPUT_SHIFT);
#elif LA_INPUT_SINGLE_PORT
  /*
   * Nếu các pin không nằm liên tiếp trên cùng một cổng, đọc thanh ghi IDR một lần 
   * rồi dùng phép so sánh bit dịch bit để đóng gói lại thành 1 byte.
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
  /* Nếu các chân nằm rải rác trên nhiều cổng khác nhau (sẽ cần đọc nhiều lần IDR của các cổng),
   * tuy nhiên trường hợp này sẽ gây trễ thời gian (skew) giữa các chân tín hiệu. Mặc định dùng cách cơ bản. */
  return (uint8_t)((idr & LA_INPUT_MASK) >> LA_INPUT_SHIFT);
#endif
}

#if defined(ARDUINO)
/*
 * Hàm đọc nhanh trạng thái 8 kênh đầu vào khi đang chạy trong môi trường Arduino.
 * Trả về 1 byte biểu thị trạng thái của 8 chân đo logic.
 */
static inline uint8_t la_board_read_gpio_snapshot_8ch_fast(void) {
  // Đọc toàn bộ giá trị thanh ghi IDR một lần duy nhất để hạn chế tối đa độ lệch thời gian (skew) giữa các kênh.
  const uint32_t idr = LA_INPUT_PORT->IDR;
  return la_pack_gpio_snapshot_from_idr(idr);
}
#endif

#endif
