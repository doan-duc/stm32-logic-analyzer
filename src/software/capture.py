import numpy as np

class Capture:
    def __init__(self, samples, sample_period_ns, num_channels=8):
        """
        Khởi tạo đối tượng Capture chứa và quản lý dữ liệu sóng thu thập được.

        samples: bytes hoặc bytearray, mỗi byte chứa trạng thái đóng gói của 8 kênh logic.
        sample_period_ns: chu kỳ lấy mẫu tính bằng nano giây (ns).
        num_channels: số lượng kênh logic đo đạc (mặc định là 8).
        """
        self.num_channels = num_channels
        self.sample_period_ns = sample_period_ns
        self.samples = bytes(samples)
        self.sample_count = len(samples)
        
        # Giải nén (unpack) luồng byte thô thành mảng bit riêng biệt cho từng kênh
        self.channels = self._unpack_channels(samples)
        
        # Tạo trục thời gian (đơn vị: giây) tương ứng với từng mẫu dữ liệu
        self.time = np.arange(self.sample_count) * (sample_period_ns / 1e9)
    
    def _unpack_channels(self, samples):
        """
        Giải nén luồng byte dữ liệu thô thu được thành các mảng bit riêng biệt của từng kênh.
        
        Trả về danh sách chứa các mảng numpy đại diện cho mức tín hiệu logic (0 hoặc 1) của mỗi kênh.
        """
        channels = []
        # Chuyển đổi dữ liệu nhị phân thô thành mảng số nguyên không dấu 8-bit bằng numpy để tăng tốc độ tính toán
        sample_array = np.frombuffer(samples, dtype=np.uint8)
        
        for ch in range(self.num_channels):
            # Trích xuất bit thứ 'ch' từ mỗi byte mẫu đo bằng phép dịch bit và AND với 1
            channel_data = (sample_array >> ch) & 0x01
            channels.append(channel_data)
        
        return channels
    
    def get_channel(self, ch_num):
        """
        Lấy mảng dữ liệu logic của một kênh đo cụ thể.
        
        ch_num: Số thứ tự kênh cần lấy (0 đến num_channels-1).
        """
        return self.channels[ch_num]
    
    def get_sample_rate_mhz(self):
        """
        Tính toán và trả về tần số lấy mẫu hiện tại theo đơn vị MHz.
        """
        return 1000.0 / self.sample_period_ns
 
    def append_samples(self, new_samples):
        """
        Nối thêm các mẫu nhị phân mới thu thập được vào phiên capture hiện tại.
        Thường dùng cho chế độ hiển thị sóng cuộn (rolling buffer) hoặc đo liên tục.
        
        new_samples: bytes hoặc bytearray mới.
        """
        if not new_samples:
            return

        # Nối byte thô vào biến lưu trữ chung
        self.samples += bytes(new_samples)
            
        # Giải nén gói mẫu mới này
        new_channels = self._unpack_channels(new_samples)
        
        # Nối dữ liệu kênh mới vào các kênh cũ sử dụng hàm concatenate của numpy
        for ch in range(self.num_channels):
            self.channels[ch] = np.concatenate((self.channels[ch], new_channels[ch]))
        
        # Tính toán và nối thêm mốc thời gian tương ứng cho các mẫu mới
        new_count = len(new_samples)
        start_time = self.time[-1] + (self.sample_period_ns / 1e9) if len(self.time) > 0 else 0
        new_time = start_time + np.arange(new_count) * (self.sample_period_ns / 1e9)
        
        self.time = np.concatenate((self.time, new_time))
        self.sample_count += new_count

    def trim_start(self, count):
        """
        Cắt bỏ một lượng số mẫu 'count' từ đầu mảng dữ liệu (dùng để giải phóng RAM cho rolling buffer).
        
        count: Số lượng mẫu cần xóa ở phía đầu.
        """
        if count <= 0:
            return
        if count >= self.sample_count:
            # Luôn giữ lại ít nhất 1 mẫu để tránh lỗi mảng trống
            count = self.sample_count - 1
            
        # Cắt bỏ phần tử ở đầu mảng của từng kênh
        for ch in range(self.num_channels):
            self.channels[ch] = self.channels[ch][count:]
            
        self.samples = self.samples[count:]
        self.time = self.time[count:]
        self.sample_count -= count

    def keep_duration(self, duration_seconds):
        """
        Chỉ giữ lại dữ liệu sóng ở khoảng thời gian 'duration_seconds' gần nhất và cắt bỏ dữ liệu cũ hơn.
        
        duration_seconds: Khoảng thời gian (giây) tối đa muốn giữ lại dữ liệu.
        """
        if self.sample_count == 0:
            return
            
        # Tính toán số lượng mẫu tối đa tương ứng với thời lượng yêu cầu
        max_samples = int(duration_seconds * (1e9 / self.sample_period_ns))
        
        # Nếu tổng số mẫu hiện có vượt quá số mẫu tối đa cho phép, tiến hành cắt bỏ phần thừa ở đầu
        if self.sample_count > max_samples:
            trim_count = self.sample_count - max_samples
            self.trim_start(trim_count)
