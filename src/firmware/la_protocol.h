#ifndef LA_PROTOCOL_H
#define LA_PROTOCOL_H

#include "la_capture.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Phiên bản khung giao thức truyền dữ liệu hiện tại */
#define LA_FRAME_VERSION 2U

/* Kích thước của Header của gói tin (48 byte) */
#define LA_FRAME_HEADER_LENGTH 48U

/* Định dạng Payload: Mỗi byte chứa trạng thái đóng gói của 8 kênh */
#define LA_PAYLOAD_FORMAT_BITPACKED_U8 1U

/* Các cờ bit báo hiệu trạng thái/lỗi của frame dữ liệu */
#define LA_FRAME_FLAG_OVERFLOW 0x00000001UL   // Lỗi tràn bộ đệm
#define LA_FRAME_FLAG_NO_TRIGGER 0x00000002UL // Dừng capture mà không kích hoạt trigger (do timeout)
#define LA_FRAME_FLAG_ERROR 0x00000004UL      // Gặp lỗi chung trong quá trình capture

/*
 * Cấu trúc dữ liệu Header của frame truyền gói tin qua cổng Serial.
 * Sử dụng thuộc tính `__attribute__((packed))` để ép buộc trình biên dịch 
 * không chèn các byte căn lề (padding) trống vào giữa các trường, đảm bảo
 * đúng layout truyền nhận nhị phân (48 byte).
 */
typedef struct __attribute__((packed)) {
  uint8_t magic[4];                             // Magic identifier (Ví dụ: "SLA8")
  uint8_t version;                              // Phiên bản khung gói tin
  uint16_t header_length;                       // Kích thước Header (48 byte)
  uint8_t channel_count;                        // Số kênh logic đo đạc (8)
  uint32_t sample_rate_hz;                      // Tần số lấy mẫu yêu cầu (Hz)
  uint32_t actual_sample_rate_hz;               // Tần số lấy mẫu thực tế (Hz)
  uint32_t total_samples;                       // Tổng số mẫu đã đo đạc trong gói tin
  int32_t trigger_index;                        // Vị trí mẫu điểm trigger phát hiện được
  uint32_t flags;                               // Các cờ trạng thái lỗi (overflow, no trigger...)
  uint8_t payload_format;                       // Định dạng nén dữ liệu mẫu
  uint8_t reserved[3];                          // Các byte dự phòng để mở rộng sau này
  uint32_t overflow_count;                      // Tổng số lần xảy ra tràn bộ đệm
  uint32_t dropped_samples;                     // Số mẫu bị mất trong phiên capture
  uint32_t header_checksum;                     // Mã kiểm lỗi của Header
  uint32_t payload_checksum;                    // Mã kiểm lỗi của Payload (mẫu đo)
} la_frame_header_t;

/*
 * Kiểm tra tĩnh tại thời điểm biên dịch để đảm bảo cấu trúc `la_frame_header_t`
 * có kích thước chính xác là 48 bytes trên mọi dòng MCU và thiết lập biên dịch.
 */
#if defined(__cplusplus)
static_assert(sizeof(la_frame_header_t) == LA_FRAME_HEADER_LENGTH,
              "SLA8 wire header layout must remain 48 bytes");
#else
_Static_assert(sizeof(la_frame_header_t) == LA_FRAME_HEADER_LENGTH,
               "SLA8 wire header layout must remain 48 bytes");
#endif

/*
 * Cấu trúc chứa kết quả mã hóa gói tin:
 * - encoded_length: Tổng chiều dài của gói tin sau khi đóng gói (Header + Payload) (byte).
 * - header_checksum: Mã checksum đã tính của Header.
 * - payload_checksum: Mã checksum đã tính của Payload.
 */
typedef struct {
  uint32_t encoded_length;
  uint32_t header_checksum;
  uint32_t payload_checksum;
} la_frame_result_t;

/*
 * Hàm tính toán mã checksum 32-bit của khối dữ liệu (bằng FNV-1a).
 */
uint32_t la_checksum32(const uint8_t *data, uint32_t length);

/*
 * Hàm giải mã chuỗi ASCII thành số nguyên không dấu 32-bit.
 */
bool la_parse_u32(const char *text, uint32_t *value_out);

/*
 * Hàm xây dựng phần Header cho gói tin gửi về PC.
 */
la_error_t la_build_frame_header(const la_capture_context_t *ctx,
                                 uint8_t *header_out,
                                 uint32_t header_capacity,
                                 la_frame_result_t *result);

/*
 * Hàm đóng gói toàn bộ gói tin dữ liệu (Header + Dữ liệu mẫu) gửi về PC.
 */
la_error_t la_encode_frame(const la_capture_context_t *ctx,
                           uint8_t *out,
                           uint32_t out_capacity,
                           la_frame_result_t *result);

#ifdef __cplusplus
}
#endif

#endif
