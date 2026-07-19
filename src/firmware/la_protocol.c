#include "la_protocol.h"

/*
 * Giải mã một chuỗi ký tự (ASCII) thành số nguyên không dấu 32-bit (uint32_t).
 * Hỗ trợ hệ thập phân (cơ số 10) và hệ thập lục phân (cơ số 16) bắt đầu bằng "0x" hoặc "0X".
 * text: Chuỗi đầu vào.
 * value_out: Con trỏ lưu giá trị kết quả giải mã.
 * Trả về true nếu giải mã thành công, ngược lại trả về false (nếu có ký tự không hợp lệ hoặc tràn số).
 */
bool la_parse_u32(const char *text, uint32_t *value_out) {
  if (text == 0 || value_out == 0 || text[0] == '\0') {
    return false;
  }

  uint32_t base = 10U;                          // Mặc định sử dụng cơ số 10
  uint32_t index = 0U;
  /* Phát hiện tiền tố "0x" hoặc "0X" để chuyển sang cơ số 16 */
  if (text[0] == '0' && (text[1] == 'x' || text[1] == 'X')) {
    base = 16U;
    index = 2U;
    if (text[index] == '\0') {
      return false;                             // Lỗi nếu chỉ có "0x" mà không có số đi kèm
    }
  }

  uint32_t value = 0U;
  for (; text[index] != '\0'; index++) {
    const char character = text[index];
    uint32_t digit;
    
    /* Chuyển đổi ký tự ASCII sang giá trị số tương ứng */
    if (character >= '0' && character <= '9') {
      digit = (uint32_t)(character - '0');
    } else if (character >= 'a' && character <= 'f') {
      digit = 10U + (uint32_t)(character - 'a');
    } else if (character >= 'A' && character <= 'F') {
      digit = 10U + (uint32_t)(character - 'A');
    } else {
      return false;                             // Ký tự không hợp lệ
    }
    
    /* Kiểm tra xem giá trị số có vượt quá cơ số đã chọn hoặc gây tràn kiểu dữ liệu 32-bit hay không */
    if (digit >= base || value > (UINT32_MAX - digit) / base) {
      return false;
    }
    value = value * base + digit;
  }

  *value_out = value;
  return true;
}

/*
 * Hàm phụ trợ ghi một số nguyên 16-bit không dấu vào mảng byte theo dạng Little Endian.
 * out: Con trỏ mảng đích.
 * value: Giá trị cần ghi.
 */
static void la_write_u16_le(uint8_t *out, uint16_t value) {
  out[0] = (uint8_t)(value & 0xFFU);            // Ghi byte thấp
  out[1] = (uint8_t)((value >> 8) & 0xFFU);     // Ghi byte cao
}

/*
 * Hàm phụ trợ ghi một số nguyên 32-bit không dấu vào mảng byte theo dạng Little Endian.
 * out: Con trỏ mảng đích.
 * value: Giá trị cần ghi.
 */
static void la_write_u32_le(uint8_t *out, uint32_t value) {
  out[0] = (uint8_t)(value & 0xFFU);            // Byte 0 (thấp nhất)
  out[1] = (uint8_t)((value >> 8) & 0xFFU);     // Byte 1
  out[2] = (uint8_t)((value >> 16) & 0xFFU);    // Byte 2
  out[3] = (uint8_t)((value >> 24) & 0xFFU);    // Byte 3 (cao nhất)
}

/*
 * Tính toán checksum 32-bit của một khối dữ liệu bằng thuật toán băm FNV-1a.
 * Thuật toán FNV-1a có tốc độ xử lý nhanh, phân tán bit tốt và phù hợp với vi điều khiển.
 * data: Con trỏ mảng dữ liệu đầu vào.
 * length: Độ dài khối dữ liệu cần tính checksum (byte).
 */
uint32_t la_checksum32(const uint8_t *data, uint32_t length) {
  uint32_t checksum = 2166136261UL;             // Giá trị khởi tạo của thuật toán FNV-1a (offset basis)
  uint32_t i;
  for (i = 0U; i < length; i++) {
    checksum ^= data[i];                        // XOR byte dữ liệu hiện tại vào checksum
    checksum *= 16777619UL;                     // Nhân với số nguyên tố FNV (FNV prime)
  }
  return checksum;
}

/*
 * Ánh xạ trạng thái của máy trạng thái capture thành các cờ nhị phân (flag) tương ứng trên frame gửi đi.
 * status: Con trỏ trạng thái capture.
 */
static uint32_t la_frame_flags_from_status(const la_capture_status_t *status) {
  uint32_t flags = 0U;
  /* Nếu phát hiện lỗi tràn bộ đệm */
  if (status->overflow_count != 0U || status->state == LA_CAPTURE_OVERFLOW) {
    flags |= LA_FRAME_FLAG_OVERFLOW;
  }
  /* Nếu kết thúc lấy mẫu mà không gặp trigger */
  if (status->state == LA_CAPTURE_NO_TRIGGER) {
    flags |= LA_FRAME_FLAG_NO_TRIGGER;
  }
  /* Nếu xảy ra lỗi khác trong quá trình đo */
  if (status->state == LA_CAPTURE_ERROR) {
    flags |= LA_FRAME_FLAG_ERROR;
  }
  return flags;
}

/*
 * Xây dựng phần tiêu đề (Header) của gói tin dữ liệu logic gửi về PC.
 * Header chứa đầy đủ các siêu dữ liệu (metadata) đo đạc để PC giải mã, tránh gửi lặp lại thông tin.
 * ctx: Context chứa thông tin phiên capture.
 * header_out: Bộ đệm xuất ra dữ liệu Header.
 * header_capacity: Dung lượng tối đa của bộ đệm Header.
 * result: Con trỏ lưu kết quả tính toán checksum và độ dài gói tin.
 */
la_error_t la_build_frame_header(const la_capture_context_t *ctx,
                                 uint8_t *header_out,
                                 uint32_t header_capacity,
                                 la_frame_result_t *result) {
  if (ctx == 0 || header_out == 0 || result == 0 || ctx->buffer == 0) {
    return LA_ERROR_NULL;
  }
  if (header_capacity < LA_FRAME_HEADER_LENGTH) {
    return LA_ERROR_FRAME_TOO_SMALL;
  }
  if (ctx->config.channel_count != LA_CHANNEL_COUNT ||
      ctx->config.sample_rate_hz == 0U ||
      ctx->status.total_samples > ctx->buffer_capacity) {
    return LA_ERROR_BAD_SAMPLE_COUNT;
  }

  /* Ghi các trường dữ liệu của Header theo cấu trúc giao thức định sẵn */
  header_out[0] = 'S';                          // Ký tự định danh ma thuật (Magic String: "SLA8")
  header_out[1] = 'L';
  header_out[2] = 'A';
  header_out[3] = '8';
  header_out[4] = LA_FRAME_VERSION;             // Phiên bản khung giao thức
  la_write_u16_le(&header_out[5], LA_FRAME_HEADER_LENGTH); // Độ dài của Header (48 byte)
  header_out[7] = LA_CHANNEL_COUNT;             // Số kênh logic đo đạc (8)
  
  /* Ghi tần số lấy mẫu yêu cầu và tần số lấy mẫu thực tế */
  la_write_u32_le(&header_out[8], ctx->config.sample_rate_hz);
  la_write_u32_le(&header_out[12],
                  ctx->status.actual_sample_rate_hz != 0U
                      ? ctx->status.actual_sample_rate_hz
                      : ctx->config.sample_rate_hz);
                      
  la_write_u32_le(&header_out[16], ctx->status.total_samples); // Tổng số mẫu đo gửi đi
  la_write_u32_le(&header_out[20], (uint32_t)ctx->status.trigger_index); // Vị trí điểm trigger trong mảng
  la_write_u32_le(&header_out[24], la_frame_flags_from_status(&ctx->status)); // Các cờ trạng thái lỗi/tràn
  
  header_out[28] = LA_PAYLOAD_FORMAT_BITPACKED_U8; // Định dạng nén dữ liệu (mỗi byte chứa 8 kênh)
  header_out[29] = 0U;                          // Các byte dự phòng (Reserved)
  header_out[30] = 0U;
  header_out[31] = 0U;
  
  la_write_u32_le(&header_out[32], ctx->status.overflow_count); // Đếm số lần tràn
  la_write_u32_le(&header_out[36], ctx->status.dropped_samples); // Số mẫu bị mất
  la_write_u32_le(&header_out[40], 0U);         // Đặt tạm Checksum Header bằng 0 trước khi tính toán
  la_write_u32_le(&header_out[44], 0U);         // Đặt tạm Checksum Payload bằng 0 trước khi tính toán

  /* Tính toán mã Checksum cho Header (từ byte 0 đến byte 39) */
  const uint32_t header_checksum = la_checksum32(header_out, 40U);
  /* Tính toán mã Checksum cho vùng dữ liệu mẫu đo (Payload) */
  const uint32_t payload_checksum =
      la_checksum32(ctx->buffer, ctx->status.total_samples);
      
  /* Ghi giá trị checksum thật vào 8 byte cuối cùng của Header */
  la_write_u32_le(&header_out[40], header_checksum);
  la_write_u32_le(&header_out[44], payload_checksum);

  /* Cập nhật các thông số đầu ra */
  result->encoded_length = LA_FRAME_HEADER_LENGTH + ctx->status.total_samples;
  result->header_checksum = header_checksum;
  result->payload_checksum = payload_checksum;
  return LA_ERROR_NONE;
}

/*
 * Mã hóa toàn bộ gói tin (Header + Payload) để chuẩn bị truyền đi.
 * ctx: Context chứa thông tin phiên capture.
 * out: Bộ đệm đầu ra chứa toàn bộ gói tin đã mã hóa.
 * out_capacity: Dung lượng tối đa bộ đệm đầu ra.
 * result: Lưu kết quả độ dài và checksum.
 */
la_error_t la_encode_frame(const la_capture_context_t *ctx,
                           uint8_t *out,
                           uint32_t out_capacity,
                           la_frame_result_t *result) {
  if (ctx == 0 || out == 0 || result == 0) {
    return LA_ERROR_NULL;
  }
  const uint32_t payload_len = ctx->status.total_samples;
  const uint32_t total_len = LA_FRAME_HEADER_LENGTH + payload_len;
  if (out_capacity < total_len) {
    return LA_ERROR_FRAME_TOO_SMALL;
  }

  /* Khởi tạo và ghi đè Header lên phần đầu của bộ đệm out */
  la_error_t err = la_build_frame_header(ctx, out, LA_FRAME_HEADER_LENGTH,
                                         result);
  if (err != LA_ERROR_NONE) {
    return err;
  }

  /* Sao chép toàn bộ Payload (dữ liệu mẫu logic) vào vị trí phía sau Header */
  uint32_t i;
  for (i = 0U; i < payload_len; i++) {
    out[LA_FRAME_HEADER_LENGTH + i] = ctx->buffer[i];
  }
  result->encoded_length = total_len;
  return LA_ERROR_NONE;
}
