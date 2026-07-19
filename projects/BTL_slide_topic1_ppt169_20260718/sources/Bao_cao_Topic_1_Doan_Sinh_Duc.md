<div class="titlepage">

**ĐẠI HỌC BÁCH KHOA HÀ NỘI**

**TRƯỜNG ĐIỆN – ĐIỆN TỬ**

![image1](media/image1.png)

**BÁO CÁO BÀI TẬP LỚN**

**THIẾT KẾ VÀ XÂY DỰNG THIẾT BỊ  
LOGIC ANALYZER ĐƠN GIẢN**

**Đề tài 1: Thiết kế và xây dựng thiết bị Logic Analyzer đơn giản**

<table>
<thead>
<tr>
<th style="text-align: left;"><strong>Sinh viên thực hiện:</strong></th>
<th style="text-align: left;"><table>
<tbody>
<tr>
<td style="text-align: left;">Đoàn Sinh Đức – 20234000</td>
</tr>
<tr>
<td style="text-align: left;">Phạm Đăng Vinh – 20233719</td>
</tr>
<tr>
<td style="text-align: left;">Vũ Mạnh Quân – 20234033</td>
</tr>
<tr>
<td style="text-align: left;">Vũ Nam Khánh – 20234015</td>
</tr>
</tbody>
</table></th>
</tr>
</thead>
<tbody>
<tr>
<td style="text-align: left;"><strong>Giảng viên hướng dẫn:</strong></td>
<td style="text-align: left;">TS. Đào Việt Hùng</td>
</tr>
</tbody>
</table>

Hà Nội, 7-2026

</div>

# TỔNG QUAN VÀ MỤC TIÊU DỰ ÁN

## Đặt vấn đề

Trong thiết kế hệ thống nhúng, việc kiểm tra tín hiệu số không chỉ dừng ở mức xác định logic 0 hoặc 1 tại một thời điểm riêng lẻ. Nhiều lỗi giao tiếp xuất hiện do sai quan hệ thời gian giữa các kênh, sai thứ tự cạnh, thiếu xung đồng bộ hoặc dữ liệu truyền không đúng khung. Vì vậy, một thiết bị phân tích logic (logic analyzer) có khả năng ghi lại nhiều tín hiệu theo thời gian là công cụ quan trọng để quan sát, phân tích và kiểm chứng hoạt động của mạch số.

Đề bài của học phần định hướng xây dựng một mẫu thử nguyên lý của thiết bị phân tích logic. Đề tài 1 tập trung vào kiến trúc phần cứng gọn nhẹ và các chức năng cơ bản gồm lấy mẫu, lưu đệm, truyền dữ liệu, hiển thị dạng sóng trên máy tính.

## Mục tiêu thiết kế

Mục tiêu của đề tài là thiết kế và xây dựng thiết bị phân tích logic sử dụng vi điều khiển STM32F103C8 để thu thập tín hiệu số và hiển thị kết quả trên máy tính. Dữ liệu của tám kênh CH0–CH7 được lấy mẫu tại PA0–PA7, đóng gói theo bit trong bộ nhớ RAM và truyền đến phần mềm máy tính qua UART bằng khung SLA8.

Các mục tiêu cụ thể gồm:

- Thiết kế tám kênh thu thập tín hiệu số, đáp ứng yêu cầu tối thiểu hai kênh của đề bài;

- Cho phép cấu hình tần số lấy mẫu từ 1 kHz đến ít nhất 1 MHz và thực hiện thu thập ngoại tuyến bằng cách lưu dữ liệu vào bộ đệm trước khi truyền;

- Hiển thị dạng sóng của tám kênh trên máy tính và hỗ trợ giải mã ba giao thức UART, I2C và SPI.

## Yêu cầu của Đề tài 1 và chỉ tiêu chức năng/phi chức năng

### Chỉ tiêu chức năng

Các chức năng chính của hệ thống gồm:

- Thu thập đồng thời ít nhất hai kênh tín hiệu số;

- Cấu hình tần số lấy mẫu từ 1 kHz và thực hiện thu thập ngoại tuyến;

- Truyền dữ liệu đến máy tính và hiển thị dạng sóng;

- Giải mã các giao thức UART, I2C và SPI.

### Chỉ tiêu phi chức năng

Các chỉ tiêu phi chức năng tập trung vào độ tin cậy của dữ liệu và tính ổn định của quá trình thu thập, gồm:

- Bảo đảm tính toàn vẹn của siêu dữ liệu và mã kiểm tra;

- Duy trì quan hệ thời gian nhất quán giữa các kênh;

- Phát hiện tràn bộ đệm và số mẫu bị mất;

- Bảo đảm khả năng lặp lại của kết quả thử nghiệm.

<table>
<caption>Tóm tắt yêu cầu và phạm vi đáp ứng</caption>
<thead>
<tr>
<th style="text-align: left;"><div class="minipage">
<p>Hạng mục</p>
</div></th>
<th style="text-align: left;"><div class="minipage">
<p>Yêu cầu theo đề bài</p>
</div></th>
<th style="text-align: left;"><div class="minipage">
<p>Kết quả triển khai</p>
</div></th>
</tr>
</thead>
<tbody>
<tr>
<td style="text-align: left;"><div class="minipage">
<p>Hạng mục</p>
</div></td>
<td style="text-align: left;"><div class="minipage">
<p>Yêu cầu theo đề bài</p>
</div></td>
<td style="text-align: left;"><div class="minipage">
<p>Kết quả triển khai</p>
</div></td>
</tr>
<tr>
<td style="text-align: left;">Số kênh</td>
<td style="text-align: left;">Tối thiểu 2 kênh.</td>
<td style="text-align: left;">Hệ thống được cấu hình tám kênh CH0–CH7.</td>
</tr>
<tr>
<td style="text-align: left;">Tốc độ lấy mẫu</td>
<td style="text-align: left;">Tối thiểu 1 kHz.</td>
<td style="text-align: left;">Firmware và phần mềm cho phép cấu hình từ 1 kHz.</td>
</tr>
<tr>
<td style="text-align: left;">Hiển thị</td>
<td style="text-align: left;">Dạng sóng trên máy tính hoặc màn hình tối thiểu 128x64.</td>
<td style="text-align: left;">Ứng dụng PyQt5/pyqtgraph hiển thị đồng thời tám kênh.</td>
</tr>
<tr>
<td style="text-align: left;">Quan hệ thời gian</td>
<td style="text-align: left;">Phân tích độ chính xác thời gian giữa các kênh.</td>
<td style="text-align: left;">TIM2 điều khiển một lần đọc GPIOA IDR cho mỗi mẫu.</td>
</tr>
<tr>
<td style="text-align: left;">Giải mã giao thức</td>
<td style="text-align: left;">Khuyến khích UART/I2C/SPI.</td>
<td style="text-align: left;">Phần mềm hỗ trợ UART, I2C và SPI.</td>
</tr>
</tbody>
</table>

## Phạm vi thực hiện

Phạm vi đề tài gồm firmware STM32, giao thức khung SLA8, phần mềm máy tính, các bộ giải mã UART, I2C, SPI và chương trình tạo tín hiệu kiểm thử trên Arduino UNO.

# CƠ SỞ LÝ THUYẾT VÀ GIẢI PHÁP

## Nền tảng STM32F103C8 và hệ thống xung nhịp

Dự án sử dụng môi trường `genericSTM32F103C8`, nền tảng Arduino và bộ định thời TIM2 cho khối thu thập. STM32F103C8 sử dụng lõi ARM Cortex–M3, tần số lõi tối đa 72 MHz, bộ nhớ Flash 64 KB và SRAM 20 KB . Firmware ưu tiên thạch anh ngoài HSE 8 MHz qua PLL nhân 9 để tạo xung hệ thống 72 MHz; khi HSE không khởi động, hệ thống quay về nguồn HSI 64 MHz. Kết quả HIL xác nhận lệnh `INFO` trả về xung TIM2 bằng 72 MHz .

Với nguồn HSE và PLL, quan hệ tổng quát của xung nhịp hệ thống là $`f_{\mathrm{SYSCLK}}=f_{\mathrm{HSE}}\times M`$, sau đó $`f_{\mathrm{HCLK}}=f_{\mathrm{SYSCLK}}/\mathrm{HPRE}`$. Xung nhịp TIM2 phụ thuộc bộ chia APB1: $`f_{\mathrm{TIM2}}=f_{\mathrm{PCLK1}}`$ khi APB1 không chia và $`f_{\mathrm{TIM2}}=2f_{\mathrm{PCLK1}}`$ khi hệ số chia APB1 lớn hơn 1 . Với bộ chia $`PSC`$ và thanh ghi tự nạp lại $`ARR`$, tần số lấy mẫu được xác định bởi
``` math
f_{\mathrm{update}}=\frac{f_{\mathrm{TIM2}}}{(PSC+1)(ARR+1)}.
```

<figure id="fig:clock-tree" data-latex-placement="H">

<figcaption>Đường xung nhịp liên quan đến bộ định thời TIM2</figcaption>
</figure>

## Nguyên lý của thiết bị phân tích logic

Thiết bị phân tích logic ghi nhận trạng thái số của nhiều kênh tại các thời điểm rời rạc. Chuỗi dữ liệu theo thời gian cho phép xác định độ rộng xung, khoảng thời gian giữa các cạnh và thứ tự sự kiện trên các đường tín hiệu.

Ở chế độ kích hoạt tức thời, mỗi sự kiện cập nhật của TIM2 yêu cầu DMA1 Channel 2 đọc thanh ghi `GPIOA->IDR` và lưu tám bit thấp vào bộ đệm. Các chế độ kích hoạt theo cạnh hoặc mẫu sử dụng hàm phục vụ ngắt để đọc một lần GPIOA IDR cho mỗi mẫu. Cả hai cơ chế đều ghi trạng thái CH0–CH7 trong cùng một lần truy cập thanh ghi.

<figure id="fig:logic-analyzer-block" data-latex-placement="H">

<figcaption>Sơ đồ khối chức năng của hệ thống phân tích logic</figcaption>
</figure>

## Tốc độ lấy mẫu và hiện tượng chồng phổ

Chu kỳ lấy mẫu là $`T_s=1/f_s`$, trong đó $`f_s`$ là tần số lấy mẫu. Đối với tín hiệu liên tục được giới hạn băng thông ở $`f_{\max}`$, điều kiện Nyquist–Shannon lý tưởng là
``` math
f_s > 2f_{\max}.
```
Khi điều kiện lấy mẫu không được thỏa mãn, thành phần tần số cao có thể xuất hiện thành tần số thấp hơn. Tần số chồng phổ được biểu diễn bởi $`f_{\mathrm{alias}}=|f_{\mathrm{in}}-k f_s|`$, với $`k`$ được chọn để $`f_{\mathrm{alias}}`$ nằm trong dải $`[0,f_s/2]`$ .

Tín hiệu số có cạnh nhanh và chứa nhiều thành phần hài, nên điều kiện Nyquist theo tần số cơ bản chưa đủ để bảo toàn hình dạng xung. Trong thực tế, tần số lấy mẫu phải được chọn theo độ rộng xung nhỏ nhất cần quan sát. Độ phân giải thời gian bằng $`T_s`$, còn jitter phụ thuộc nguồn xung nhịp, bộ định thời và cơ chế DMA hoặc ngắt.

## Quan hệ thời gian giữa các kênh

Firmware đọc một lần thanh ghi IDR của GPIOA rồi tách các bit tương ứng CH0–CH7. So với cách đọc tuần tự từng chân, phương pháp này giảm sai lệch thời điểm giữa các kênh; jitter và skew còn lại phải được xác định bằng phép đo thực nghiệm.

## Giao thức truyền dữ liệu sau thu thập

Sau khi phiên thu hoàn tất và nhận lệnh `DUMP`, firmware truyền dữ liệu đến máy tính theo khung SLA8. Mỗi mẫu được lưu bằng một byte, trong đó bit 0 đến bit 7 tương ứng CH0 đến CH7. Phần đầu khung chứa mã nhận dạng, phiên bản, số kênh, tần số lấy mẫu, số mẫu, vị trí kích hoạt, cờ trạng thái và mã kiểm tra.

# THIẾT KẾ HỆ THỐNG

## Kiến trúc tổng thể

Hệ thống gồm ba lớp chức năng. Lớp phần cứng bao gồm bo mạch STM32 và tám kênh tín hiệu vào. Lớp chương trình nhúng thực hiện lấy mẫu, quản lý điều kiện kích hoạt, lưu bộ đệm và đóng gói khung SLA8. Lớp phần mềm máy tính điều khiển phiên thu, hiển thị dạng sóng và giải mã giao thức.

## Thiết kế phần cứng

Phần cứng sử dụng vi điều khiển STM32F103C8. Tám kênh CH0–CH7 được ánh xạ tới PA0–PA7. Giao tiếp với máy tính sử dụng USART1 tại PA9 (TX) và PA10 (RX), với tốc độ 1.000.000 baud. Tín hiệu tại các chân GPIO sử dụng mức logic 3,3 V.

| **Thành phần** | **Cấu hình** | **Chức năng/Ghi chú** |
|:---|:---|:---|
| Bo mạch và vi điều khiển | STM32F103C8, nền tảng Arduino | TIM2 điều khiển quá trình lấy mẫu bằng DMA hoặc ngắt. |
| Kênh đo | CH0–CH7 ánh xạ tới PA0–PA7 | Đọc đồng thời tám bit thấp của GPIOA IDR. |
| Giao tiếp máy tính | USART1 trên PA9/PA10, 1.000.000 baud | Truyền lệnh điều khiển và khung dữ liệu SLA8. |
| Nguồn tín hiệu thử | Arduino UNO | Tạo chuỗi Gray, UART, I2C và SPI bằng ngõ ra cực máng hở; mức HIGH do điện trở kéo lên 3,3 V tại STM32 tạo ra. |

Các thành phần phần cứng

## Thiết kế firmware

Firmware thực hiện chuỗi công việc gồm khởi tạo ngoại vi, nhận cấu hình, thiết lập TIM2, lựa chọn DMA hoặc ISR, thu thập mẫu và đóng gói dữ liệu thành khung SLA8. Các chức năng được phân chia theo mô-đun cấu hình phần cứng, thu thập, giao thức và đánh giá hiệu năng.

<table>
<caption>Vai trò các mô-đun firmware</caption>
<thead>
<tr>
<th style="text-align: left;"><div class="minipage">
<p>Mô-đun</p>
</div></th>
<th style="text-align: left;"><div class="minipage">
<p>Vai trò</p>
</div></th>
</tr>
</thead>
<tbody>
<tr>
<td style="text-align: left;"><div class="minipage">
<p>Mô-đun</p>
</div></td>
<td style="text-align: left;"><div class="minipage">
<p>Vai trò</p>
</div></td>
</tr>
<tr>
<td style="text-align: left;">board_config.h</td>
<td style="text-align: left;">Định nghĩa số kênh, chân PA0–PA7, UART PA9/PA10, TIM2, bộ đệm và tần số lấy mẫu.</td>
</tr>
<tr>
<td style="text-align: left;">main.cpp</td>
<td style="text-align: left;">Điều phối lệnh UART, TIM2, trạng thái thu thập và truyền khung dữ liệu.</td>
</tr>
<tr>
<td style="text-align: left;">la_capture.h/c</td>
<td style="text-align: left;">Quản lý trạng thái thu thập, tiền kích hoạt, hậu kích hoạt và hàm phục vụ ngắt.</td>
</tr>
<tr>
<td style="text-align: left;">la_protocol.h/c</td>
<td style="text-align: left;">Tạo phần đầu khung SLA8, mã kiểm tra và siêu dữ liệu.</td>
</tr>
<tr>
<td style="text-align: left;">la_benchmark.c</td>
<td style="text-align: left;">Cung cấp phép đo chu kỳ bằng DWT khi biên dịch với tùy chọn tương ứng; bản firmware kiểm thử HIL không sử dụng tùy chọn này.</td>
</tr>
<tr>
<td style="text-align: left;">la_board.h/c</td>
<td style="text-align: left;">Tính PSC/ARR, tần số thực tế và giới hạn tốc độ của cơ chế DMA, ISR.</td>
</tr>
</tbody>
</table>

## Luồng hoạt động firmware

Khi khởi động, firmware cấu hình UART, GPIO đầu vào, TIM2 và tần số lấy mẫu mặc định. Firmware tiếp nhận các lệnh cấu hình tốc độ, chế độ thu và điều kiện kích hoạt; lệnh `ARM` bắt đầu phiên thu. Với `TRIG IMM`, hệ thống ưu tiên DMA; các điều kiện kích hoạt theo cạnh hoặc mẫu sử dụng ISR và giới hạn tốc độ đã kiểm chứng là 400 kS/s. Khi đủ số mẫu, firmware dừng thu, phát thông báo `EVENT` và chờ lệnh `DUMP` để truyền khung SLA8.

<figure id="fig:firmware-flow" data-latex-placement="H">

<figcaption>Sơ đồ luồng hoạt động của firmware</figcaption>
</figure>

## Thiết kế phần mềm PC

Phần mềm máy tính được xây dựng bằng Python, PyQt5 và pyqtgraph. Ứng dụng quản lý kết nối nối tiếp, cấu hình phiên thu, nhận và kiểm tra khung SLA8, tách tám kênh từ dữ liệu đóng gói theo bit và hiển thị dạng sóng. Giao diện cho phép chọn cổng COM, tần số lấy mẫu, chế độ thu thập, điều kiện kích hoạt và các bộ giải mã UART, I2C, SPI.

<table>
<caption>Chức năng phần mềm PC</caption>
<thead>
<tr>
<th style="text-align: left;"><div class="minipage">
<p>Chức năng</p>
</div></th>
<th style="text-align: left;"><div class="minipage">
<p>Mô tả</p>
</div></th>
</tr>
</thead>
<tbody>
<tr>
<td style="text-align: left;"><div class="minipage">
<p>Chức năng</p>
</div></td>
<td style="text-align: left;"><div class="minipage">
<p>Mô tả</p>
</div></td>
</tr>
<tr>
<td style="text-align: left;">Kết nối thiết bị</td>
<td style="text-align: left;">Mở cổng nối tiếp, gửi PING, đọc INFO và lấy thông tin bộ đệm, tần số.</td>
</tr>
<tr>
<td style="text-align: left;">Thu thập ngoại tuyến</td>
<td style="text-align: left;">Gửi lệnh ARM, chờ EVENT, yêu cầu DUMP, đọc khung SLA8 và kiểm tra mã kiểm tra.</td>
</tr>
<tr>
<td style="text-align: left;">Hiển thị dạng sóng</td>
<td style="text-align: left;">Vẽ tám kênh, hỗ trợ phóng to, thu nhỏ, cuộn và theo dõi dữ liệu.</td>
</tr>
<tr>
<td style="text-align: left;">Cập nhật liên tục</td>
<td style="text-align: left;">Lặp phiên thu ngoại tuyến bằng QTimer để cập nhật dạng sóng.</td>
</tr>
<tr>
<td style="text-align: left;">Giải mã</td>
<td style="text-align: left;">Hỗ trợ UART, I2C và SPI trên dữ liệu đã thu.</td>
</tr>
<tr>
<td style="text-align: left;">Dòng lệnh</td>
<td style="text-align: left;">Lưu một khung SLA8 để phân tích sau phiên thu.</td>
</tr>
</tbody>
</table>

<figure id="fig:gui-connected" data-latex-placement="H">
![fig_gui_overview](../generated/la_testsuite_20260718/figs/fig_gui_overview.png)
<figcaption>Giao diện phần mềm sau khi kết nối STM32 qua COM12, hiển thị đồng thời tám kênh</figcaption>
</figure>

## Giao thức điều khiển

<table>
<caption>Các lệnh UART chính</caption>
<thead>
<tr>
<th style="text-align: left;"><div class="minipage">
<p>Lệnh</p>
</div></th>
<th style="text-align: left;"><div class="minipage">
<p>Ý nghĩa</p>
</div></th>
</tr>
</thead>
<tbody>
<tr>
<td style="text-align: left;"><div class="minipage">
<p>Lệnh</p>
</div></td>
<td style="text-align: left;"><div class="minipage">
<p>Ý nghĩa</p>
</div></td>
</tr>
<tr>
<td style="text-align: left;">PING</td>
<td style="text-align: left;">Kiểm tra thiết bị, phản hồi PONG SLA8.</td>
</tr>
<tr>
<td style="text-align: left;">INFO</td>
<td style="text-align: left;">Trả về phiên bản firmware, số kênh, dung lượng bộ đệm và dải tần số lấy mẫu.</td>
</tr>
<tr>
<td style="text-align: left;">STATUS</td>
<td style="text-align: left;">Trả về trạng thái thu thập, tần số thực tế, số mẫu, số lần tràn bộ đệm và số mẫu bị mất.</td>
</tr>
<tr>
<td style="text-align: left;">CFG RATE &lt;Hz&gt;</td>
<td style="text-align: left;">Cấu hình tốc độ lấy mẫu.</td>
</tr>
<tr>
<td style="text-align: left;">TRIG IMM</td>
<td style="text-align: left;">Kích hoạt ngay.</td>
</tr>
<tr>
<td style="text-align: left;">TRIG RISE/FALL/ANY &lt;kênh&gt;</td>
<td style="text-align: left;">Kích hoạt theo cạnh trên kênh được chọn.</td>
</tr>
<tr>
<td style="text-align: left;">TRIG PAT &lt;mặt nạ&gt; &lt;giá trị&gt;</td>
<td style="text-align: left;">Kích hoạt khi mẫu thỏa mặt nạ và giá trị.</td>
</tr>
<tr>
<td style="text-align: left;">ARM</td>
<td style="text-align: left;">Bắt đầu phiên thu thập.</td>
</tr>
<tr>
<td style="text-align: left;">DUMP</td>
<td style="text-align: left;">Truyền khung SLA8 sau khi phiên thu kết thúc.</td>
</tr>
</tbody>
</table>

## Công cụ tạo tín hiệu thử

Arduino UNO được sử dụng làm nguồn tín hiệu tham chiếu, tạo chuỗi Gray, UART, I2C và SPI bằng ngõ ra cực máng hở để phục vụ các phép thử thu thập, hiển thị dạng sóng và giải mã giao thức.

# TRIỂN KHAI VÀ KIỂM THỬ

## Lắp mạch và quy trình vận hành

Hệ thống kết nối STM32 với máy tính qua FT232 ở mức logic 3,3 V. Các đường TX/RX được nối chéo và mọi thiết bị dùng chung GND. Khi STM32 đã được cấp nguồn riêng, không cấp thêm nguồn từ FT232.

| **Thiết bị/chế độ** | **Kết nối đến** | **Lưu ý** |
|:---|:---|:---|
| FT232 TX | STM32 PA10 (USART1 RX) | Mức logic 3,3 V. |
| FT232 RX | STM32 PA9 (USART1 TX) | Mức logic 3,3 V. |
| FT232 GND | STM32 GND | Bắt buộc nối chung GND. |
| Arduino, chế độ GRAY | D2–D9 tới PA0–PA7 | Ngõ ra cực máng hở; mức HIGH do điện trở kéo lên 3,3 V tại STM32 tạo ra. |
| Arduino, chế độ UART/I2C | D2 tới CH0; D3 tới CH1/SCL; D4 tới CH2/SDA | Ngõ ra cực máng hở; hai bo mạch phải nối chung GND. |
| Arduino, chế độ SPI/BOTH | D5–D9 tới CH3–CH7 | Ngõ ra cực máng hở; mức HIGH do điện trở kéo lên 3,3 V tại STM32 tạo ra. |
| Arduino GND | STM32 GND | Bắt buộc nối chung GND. |

Kết nối giữa các phần tử trong hệ thống

Quy trình biên dịch, nạp và chạy chương trình gồm:

1.  Đóng giao diện hoặc chương trình giám sát đang sử dụng cổng COM;

2.  Biên dịch firmware bằng PlatformIO;

3.  Đặt BOOT1/PB2=0, BOOT0=1 và khởi động lại STM32 để vào bộ nạp ROM;

4.  Nạp firmware qua USART1;

5.  Đưa BOOT0 về 0 và khởi động lại STM32;

6.  Chạy phần mềm giao diện hoặc công cụ dòng lệnh trên máy tính.

Các câu lệnh biên dịch, nạp và chạy chương trình được trình bày tại Mục <a href="#sec:build-config" data-reference-type="ref" data-reference="sec:build-config">4.2</a>; `COMx` biểu thị cổng nối tiếp do hệ điều hành gán và phải được xác định trên từng máy.

Bộ giải mã UART hiện xử lý khung 8N1 trên CH0, gồm bit bắt đầu, tám bit dữ liệu và bit kết thúc. Bus I2C sử dụng CH1 làm SCL và CH2 làm SDA. Đối với SPI, CH3, CH4, CH5 và CH6 lần lượt được dùng cho SCK, MOSI, MISO và CS. Bộ phát Arduino kéo LOW hoặc thả nổi đường tín hiệu; mức HIGH được tạo bởi điện trở kéo lên 3,3 V của STM32.

## Cấu hình biên dịch

<table>
<caption>Lệnh triển khai</caption>
<thead>
<tr>
<th style="text-align: left;"><div class="minipage">
<p>Mục đích</p>
</div></th>
<th style="text-align: left;"><div class="minipage">
<p>Lệnh</p>
</div></th>
</tr>
</thead>
<tbody>
<tr>
<td style="text-align: left;"><div class="minipage">
<p>Mục đích</p>
</div></td>
<td style="text-align: left;"><div class="minipage">
<p>Lệnh</p>
</div></td>
</tr>
<tr>
<td style="text-align: left;">Biên dịch firmware mặc định</td>
<td style="text-align: left;">python -m platformio run -e c8_serial</td>
</tr>
<tr>
<td style="text-align: left;">Nạp firmware qua UART</td>
<td style="text-align: left;">python -m platformio run -e c8_serial --target upload --upload-port COMx</td>
</tr>
<tr>
<td style="text-align: left;">Chạy giao diện PC</td>
<td style="text-align: left;">python src\software\main.py</td>
</tr>
<tr>
<td style="text-align: left;">Thu thập bằng công cụ dòng lệnh</td>
<td style="text-align: left;">python src\software\tools\serial_capture.py COMx capture.sla8 --baud 1000000 --rate 100000 --timeout 10</td>
</tr>
<tr>
<td style="text-align: left;">Biên dịch bản mở rộng dải tần đánh giá</td>
<td style="text-align: left;">python -m platformio run -e c8_serial_benchmark</td>
</tr>
</tbody>
</table>

## Kế hoạch kiểm thử

Kế hoạch kiểm thử được xây dựng theo quan điểm kiểm thử một thiết bị phân tích logic độc lập: mỗi kịch bản vừa xác nhận một chức năng, vừa đặt hệ thống vào điều kiện biên nhằm phát hiện sai sót về thời gian, toàn vẹn dữ liệu hoặc giải mã. Nguồn tín hiệu chuẩn là bộ tạo Arduino UNO (thạch anh 16 MHz) mô tả ở Mục <a href="#cuxf4ng-cux1ee5-tux1ea1o-tuxedn-hiux1ec7u-thux1eed" data-reference-type="ref" data-reference="cuxf4ng-cux1ee5-tux1ea1o-tuxedn-hiux1ec7u-thux1eed">3.7</a>, đóng vai trò tín hiệu tham chiếu (oracle) đã biết trước giá trị. Mười kịch bản trong Bảng <a href="#tab:test-plan" data-reference-type="ref" data-reference="tab:test-plan">4.1</a> phủ các nhóm: kết nối và toàn vẹn khung, ánh xạ kênh và quan hệ thời gian, độ chính xác và trần tần số lấy mẫu, giới hạn Nyquist, giải mã ba giao thức và hệ thống kích hoạt phần cứng.

<div id="tab:test-plan">

| **Mã** | **Mục tiêu** | **Phương pháp và tiêu chí đạt** |
|:---|:---|:---|
| **Mã** | **Mục tiêu** | **Phương pháp và tiêu chí đạt** |
| TC-01 | Toàn vẹn nhận dạng và khung dữ liệu. | Truy vấn `PING`/`INFO`/`STATUS` và kiểm tra mã kiểm tra của mọi khung `DUMP`. Đạt khi nhận dạng đúng (magic SLA8, 8 kênh, xung 72 MHz, đệm 13 888) và cả hai mã kiểm tra FNV-1a hợp lệ. |
| TC-02 | Ánh xạ tám kênh và tính đồng thời. | Phát chuỗi Gray 8 bit (mỗi bước đổi đúng một bit) vào PA0–PA7; thu ở 100 kS/s. Đạt khi cả tám kênh có chuyển mức, không có lỗi thứ tự và không xuất hiện trạng thái trung gian nhiều bit. |
| TC-03 | Độ chính xác tần số lấy mẫu và lượng tử hóa bộ chia. | Quét `CFG RATE` và đọc `ACTUAL_RATE`, `ERROR_PPM`; đối chiếu chéo với oracle Gray. Đạt khi các ước số nguyên của 72 MHz cho sai số 0 ppm và mức không chia hết được báo cáo trung thực. |
| TC-04 | Trần tốc độ DMA và từ chối vượt ngưỡng. | Thu Gray tại 6,545 MS/s; lần lượt yêu cầu 7, 8 và 10 MS/s. Đạt khi 6,545 MS/s cho dữ liệu sạch (sai số $`<0{,}1\%`$, 0 mất mẫu, 0 tràn) và các mức cao hơn bị firmware từ chối. |
| TC-05 | Cơ chế ISR và bộ đếm tràn ngắt. | Thu Gray bằng ISR tại 100, 250 và 400 kS/s; đọc `ISR_OVERRUNS`; yêu cầu 500 kS/s. Đạt khi 0 lỗi thứ tự, không tràn ngắt tới 400 kS/s và mức cao hơn bị từ chối. |
| TC-06 | Điều kiện Nyquist và chồng phổ. | Lấy mẫu tín hiệu CH0 25 kHz ở trên (1 MS/s) và dưới (30 kS/s) ngưỡng Nyquist. Đạt khi mức đủ tái tạo đúng, còn mức thiếu tạo tần số giả và bị bộ kiểm tra Gray phát hiện. |
| TC-07 | Giải mã UART 8N1 với start/stop bit. | Phát `0x55`, `0xA5`, `‘O’`, `‘K’`; thu ở 1 MS/s; giải mã CH0 ở 57.600 baud. Đạt khi bốn byte đúng và không có lỗi khung. |
| TC-08 | Giải mã I2C có ACK/NACK. | Phát địa chỉ `0x50` (ghi), dữ liệu `0xA5` (ACK) và `0x5A` (NACK). Đạt khi các sự kiện START, ADDR, DATA, ACK/NACK và STOP được nhận đúng. |
| TC-09 | Giải mã SPI và bảo vệ thiếu mẫu. | Thu SPI ở 500 kS/s (đủ mẫu) và ở 150 kS/s (thiếu mẫu). Đạt khi mức đủ nhận đúng ba cặp MOSI/MISO cùng sự kiện CS, còn mức thiếu phát cảnh báo UNDERSAMPLED và không phát byte sai. |
| TC-10 | Định vị kích hoạt theo cạnh và mẫu. | Kích hoạt `TRIG FALL` trên CH6 với tiền kích hoạt 1500 mẫu; kiểm tra vị trí trigger và các lệnh `TRIG PAT`, kênh không hợp lệ. Đạt khi trigger đúng cạnh, vùng tiền kích hoạt đầy tín hiệu nền và mọi lệnh sai bị từ chối. |

Kế hoạch mười kịch bản kiểm thử thiết bị phân tích logic

</div>

## Kết quả kiểm thử phần cứng

Phần này trình bày kết quả thực hiện mười kịch bản của Bảng <a href="#tab:test-plan" data-reference-type="ref" data-reference="tab:test-plan">4.1</a> trên hệ thống phần cứng thật: bo mạch STM32 trên cổng COM12 và bộ tạo tín hiệu Arduino trên cổng COM18. Toàn bộ phép đo được điều khiển tự động; mỗi khung SLA8 thu về đều được kiểm tra mã kiểm tra trước khi phân tích, và các khung được lưu ở định dạng làm minh chứng . Các số liệu dưới đây được trích trực tiếp từ kết quả đo, không phải giá trị thiết kế.

### Toàn vẹn nhận dạng và khung dữ liệu (TC-01)

Lệnh `INFO` và `STATUS` xác nhận cấu hình thiết bị đúng như thiết kế: phiên bản firmware, xung định thời TIM2 bằng 72 MHz (chạy thạch anh HSE), dung lượng bộ đệm và dải tốc độ. Mỗi khung trả về từ lệnh `DUMP` mang hai mã kiểm tra FNV-1a độc lập cho phần đầu và phần dữ liệu; phần mềm từ chối khung nếu bất kỳ mã nào sai. Trong toàn bộ quá trình kiểm thử, không có khung nào bị loại vì sai mã kiểm tra. Bảng <a href="#tab:identity" data-reference-type="ref" data-reference="tab:identity">4.2</a> liệt kê các trường nhận dạng chính đọc được từ thiết bị.

<div id="tab:identity">

| **Trường** | **Giá trị đo được** |
|:---|:---|
| **Trường** | **Giá trị đo được** |
| Phiên bản firmware | `SLA8-FW-V2-P5` |
| Mã nhận dạng khung | `SLA8`, phiên bản 2, phần đầu 48 byte |
| Số kênh | (CH0–CH7 $`\to`$ PA0–PA7) |
| Xung định thời TIM2 |  000 000 Hz (thạch anh HSE) |
| Dung lượng bộ đệm |  888 mẫu (13 888 byte) |
| Trần tốc độ DMA / ISR |  545 454 S/s / 400 000 S/s |
| Mã kiểm tra khung | FNV-1a 32 bit cho phần đầu và phần dữ liệu, hợp lệ trên mọi khung |

Trường nhận dạng và trạng thái đọc từ thiết bị (TC-01)

</div>

### Phương pháp đo

Bộ tạo tín hiệu Arduino UNO nối D2–D9 sang PA0–PA7 của STM32 và chung GND; STM32 giao tiếp máy tính qua UART. Arduino phát một bộ đếm Gray 8 bit ở tốc độ bước biết trước $`f_{\text{bước}}`$ (đặt bằng lệnh `GRAY RATE`). Vì mỗi bước chỉ đổi một bit nên mọi giá trị trung gian nhiều bit đều là lỗi lấy mẫu; $`f_{\text{bước}}`$ lấy từ thạch anh 16 MHz của Arduino nên đóng vai trò chuẩn đối chiếu.

Với mỗi tần số cần kiểm tra, STM32 được cấu hình `CFG MODE DMA`, `TRIG IMM` và `CFG RATE` $`f_{\text{cấu hình}}`$; sau đó gửi `ARM`, chờ sự kiện hoàn tất rồi `DUMP` khung SLA8 về máy tính. Phần mềm đếm số mẫu $`N_i`$ trên mỗi bước Gray ổn định và suy ra tần số lấy mẫu thực tế
``` math
f_{\text{đo}} = \overline{N}\times f_{\text{bước}}.
```

Mọi lệnh gửi tới thiết bị là chuỗi ASCII kết thúc bằng ký tự xuống dòng, truyền qua UART 1.000.000 baud (ví dụ `CFG RATE 1000000`, `ARM`, `DUMP`). Đáp lại `DUMP`, thiết bị trả về một khung nhị phân SLA8 gồm phần đầu 48 byte (mã nhận dạng, phiên bản, số kênh, tần số yêu cầu và thực tế, số mẫu, vị trí trigger, cờ và hai mã kiểm tra FNV-1a), tiếp theo là phần dữ liệu dài đúng bằng số mẫu — mỗi mẫu 1 byte đóng gói trạng thái tám kênh. Khi thu đầy bộ đệm 13 888 mẫu, khung có kích thước $`48+13\,888 = 13\,936`$ byte.

Một mức được coi là đạt khi không có lỗi thứ tự chuỗi, mất mẫu, tràn bộ đệm hay sai mã kiểm tra, và sai lệch $`|f_{\text{đo}}-f_{\text{cấu hình}}|/f_{\text{cấu hình}}`$ nằm trong ngưỡng cho phép. Mỗi mức lặp lại nhiều lần; toàn bộ quy trình được tự động hóa bằng công cụ `hardware_self_test.py`, khung dữ liệu lưu ở định dạng làm minh chứng.

### Kết quả toàn vẹn tín hiệu

<div id="tab:integrity-summary">

| **Cơ chế** | **Tần số kiểm thử** | **Số lần** | **Kết quả** |
|:---|:---|:---|:---|
| DMA |  kS/s; 500 kS/s; 1, 2, 4, 6 và 6,545 MS/s | lần cho mỗi mức | Đạt; sai số đo không quá 0,05%. |
| DMA |  kS/s | lần | Đạt; sai số đo 0,01%. |
| ISR | , 250 và 400 kS/s | lần cho mỗi mức | Đạt; sai số đo không quá 0,01%. |

Tổng hợp kết quả toàn vẹn tín hiệu với oracle Gray (TC-02, TC-04, TC-05)

</div>

Trong toàn bộ các phép thử ở Bảng <a href="#tab:integrity-summary" data-reference-type="ref" data-reference="tab:integrity-summary">4.3</a>, không ghi nhận lỗi thứ tự chuỗi Gray, trạng thái ngắn bất thường, mất mẫu, tràn bộ đệm, lỗi DMA hoặc sai mã kiểm tra. Tại 6 và 6,545 MS/s, mỗi khung chứa ít nhất 212 trạng thái Gray ổn định và sai số tần số đo không quá 0,05%.

### Ánh xạ tám kênh và quan hệ thời gian (TC-02)

Hình <a href="#fig:gui-gray" data-reference-type="ref" data-reference="fig:gui-gray">4.1</a> là dạng sóng thu được khi Arduino phát bộ đếm Gray phản xạ 8 bit ở tốc độ bước 10 kS/s, lấy mẫu ở 100 kS/s bằng cơ chế DMA. Cả tám kênh CH0–CH7 đều thể hiện quan hệ tần số giảm một nửa đặc trưng của bộ đếm nhị phân; số lần chuyển mức đếm được lần lượt là 694, 347, 174, 87, 43, 21, 11 và 11, xác nhận đủ tám đường được ánh xạ đúng tới PA0–PA7.

Vì mỗi bước Gray chỉ đổi đúng một bit, bất kỳ sai lệch thời điểm (skew) nào giữa các kênh sẽ tạo ra một trạng thái trung gian nhiều bit tồn tại ngắn. Trong 1 389 trạng thái ổn định thu được, phần mềm không phát hiện trạng thái trung gian nào và không có lỗi thứ tự ($`0/1\,389`$). Kết quả này chứng minh độ lệch thời gian giữa các kênh nhỏ hơn một chu kỳ lấy mẫu, phù hợp với việc firmware đọc đồng thời tám bit qua một lần truy cập thanh ghi `GPIOA->IDR`.

<figure id="fig:gui-gray" data-latex-placement="H">
![fig_tc02_gray8ch](../generated/la_testsuite_20260718/figs/fig_tc02_gray8ch.png)
<figcaption>Chuỗi Gray tám kênh CH0–CH7 tại 100 kS/s; quan hệ tần số giảm một nửa xác nhận ánh xạ kênh đúng và không có trạng thái trung gian</figcaption>
</figure>

### Độ chính xác tần số lấy mẫu (TC-03)

Tần số lấy mẫu được sinh từ xung TIM2 72 MHz qua bộ chia $`(PSC+1)(ARR+1)`$. Với các mức là ước số nguyên của 72 MHz, thiết bị đạt sai số lượng tử bằng không; với các mức không chia hết, firmware chọn bộ chia gần nhất và báo cáo trung thực tần số thực tế qua trường `ACTUAL_RATE` và `ERROR_PPM`. Bảng <a href="#tab:rate-accuracy" data-reference-type="ref" data-reference="tab:rate-accuracy">4.4</a> trình bày kết quả quét tần số; các mức chia hết được đối chiếu chéo bằng oracle Gray cho sai số đo dưới 0,01%.

<div id="tab:rate-accuracy">

| **Yêu cầu** | **Thực tế** | **Sai số (ppm)** | **Ghi chú** |
|:--:|:--:|:--:|:--:|
| 1 kS/s | 1 kS/s | 0 | Ước số nguyên của 72 MHz |
| 100 kS/s | 100 kS/s | 0 | Ước số nguyên của 72 MHz |
| 500 kS/s | 500 kS/s | 0 | Ước số nguyên của 72 MHz |
| 1 MS/s | 1 MS/s | 0 | Ước số nguyên của 72 MHz |
| 2 MS/s | 2 MS/s | 0 | Ước số nguyên của 72 MHz |
| 4 MS/s | 4 MS/s | 0 | Ước số nguyên của 72 MHz |
| 6 MS/s | 6 MS/s | 0 | $`=72\text{~MHz}/12`$ |
| 5 MS/s | 5,142857 MS/s | +28 571 | $`=72\text{~MHz}/14`$; lệch danh định +2,86% |

Độ chính xác tần số lấy mẫu đo trực tiếp (TC-03)

</div>

### Trần tốc độ DMA và cơ chế ISR (TC-04, TC-05)

Ở cơ chế DMA, thiết bị lấy mẫu sạch tới trần 6,545 MS/s $`(=72\text{~MHz}/11)`$. Hình <a href="#fig:gui-ceiling" data-reference-type="ref" data-reference="fig:gui-ceiling">4.2</a> là dạng sóng chuỗi Gray tại mức trần này: các cạnh số vẫn được phân giải rõ ràng, tần số đo được 6,5460 MS/s lệch 0,008% so với cấu hình, khung 13 888 mẫu không có mẫu mất hay tràn bộ đệm. Khi yêu cầu 7, 8 hoặc 10 MS/s, firmware trả về `ERR BAD_RATE` thay vì âm thầm bỏ mẫu; đây là hành vi đúng của một thiết bị đo, không báo cáo tốc độ mà nó không bảo đảm.

<figure id="fig:gui-ceiling" data-latex-placement="H">
![fig_tc04_ceiling](../generated/la_testsuite_20260718/figs/fig_tc04_ceiling.png)
<figcaption>Thu chuỗi Gray tại trần DMA 6,545 MS/s; các cạnh số được phân giải rõ, sai số tần số 0,008%</figcaption>
</figure>

Cơ chế ISR dùng cho các điều kiện kích hoạt theo cạnh và mẫu đạt tới 400 kS/s. Hình <a href="#fig:gui-isr" data-reference-type="ref" data-reference="fig:gui-isr">4.3</a> là chuỗi Gray thu bằng ISR ở 400 kS/s; ở cả ba mức 100, 250 và 400 kS/s, bộ đếm tràn ngắt `ISR_OVERRUNS` bằng không và không có lỗi thứ tự. Tương tự cơ chế DMA, yêu cầu 500 kS/s ở chế độ ISR bị từ chối với `ERR BAD_RATE`.

<figure id="fig:gui-isr" data-latex-placement="H">
![fig_tc05_isr](../generated/la_testsuite_20260718/figs/fig_tc05_isr.png)
<figcaption>Thu chuỗi Gray bằng cơ chế ISR tại 400 kS/s; không có lỗi thứ tự và không tràn ngắt</figcaption>
</figure>

### Điều kiện Nyquist và hiện tượng chồng phổ (TC-06)

Để minh hoạ giới hạn Nyquist trên chính thiết bị, tín hiệu CH0 (một xung vuông 25 kHz sinh từ bit thấp của chuỗi Gray) được lấy mẫu ở hai mức. Ở 1 MS/s $`(f_s > 2f_{\text{in}})`$, dạng sóng được tái tạo đúng với tần số biểu kiến 24,99 kHz. Ở 30 kS/s $`(f_s < 2f_{\text{in}})`$, tín hiệu 25 kHz bị gập phổ thành thành phần giả khoảng 5 kHz $`(|25-30|~\text{kHz})`$ như Hình <a href="#fig:aliasing" data-reference-type="ref" data-reference="fig:aliasing">4.4</a>; đồng thời bộ kiểm tra Gray phát hiện 13 886 trạng thái ngắn bất thường, xác nhận điều kiện lấy mẫu không đủ. Kết quả này khẳng định nguyên tắc: tần số lấy mẫu phải được chọn theo độ rộng xung nhỏ nhất cần quan sát chứ không chỉ theo tần số cơ bản.

<figure id="fig:aliasing" data-latex-placement="H">
![fig_tc06_aliasing](../generated/la_testsuite_20260718/figs/fig_tc06_aliasing.png)
<figcaption>Hiện tượng chồng phổ: tín hiệu CH0 25 kHz được tái tạo đúng ở 1 MS/s (a) nhưng bị gập thành  5 kHz khi lấy mẫu ở 30 kS/s (b)</figcaption>
</figure>

### Giải mã giao thức UART, I2C và SPI (TC-07–TC-09)

Ba bộ giải mã được kiểm chứng bằng tín hiệu thật do Arduino tạo qua ngõ ra cực máng hở, mức HIGH do điện trở kéo lên 3,3 V của STM32 tạo ra. Kết quả tóm tắt trong Bảng <a href="#tab:protocol-decode" data-reference-type="ref" data-reference="tab:protocol-decode">4.5</a>.

<div id="tab:protocol-decode">

| **Giao thức** | **Cấu hình thu** | **Kết quả giải mã** |
|:---|:---|:---|
| UART 8N1 (CH0) | 1 MS/s, 57.600 baud | `0x55, 0xA5, ‘O’, ‘K’`; 0 lỗi khung |
| I2C (CH1/CH2) | 2 MS/s | START, ADDR `0x50` W (ACK), |
|  |  | DATA `0xA5` (ACK), `0x5A` (NACK), STOP |
| SPI (CH3–CH6) | 500 kS/s | CS$`\downarrow`$; MOSI/MISO = `55/A5`, `A5/3C`, |
|  |  | `5A/C3`; CS$`\uparrow`$ |

Kết quả giải mã ba giao thức từ tín hiệu tham chiếu (TC-07–TC-09)

</div>

Với UART (Hình <a href="#fig:gui-uart" data-reference-type="ref" data-reference="fig:gui-uart">4.5</a>), độ rộng một bit đo được là 18 $`\mu`$s, tương ứng 57.600 baud; qua cả khung thu 13,9 ms bộ giải mã phục hồi đúng bốn byte tham chiếu lặp lại mười ba lần mà không có lỗi khung. Bit khởi đầu (cạnh xuống trên đường nghỉ mức cao) và bit dừng được đánh dấu trực tiếp trên dạng sóng và trong bảng sự kiện.

<figure id="fig:gui-uart" data-latex-placement="H">
![fig_tc07_uart](../generated/la_testsuite_20260718/figs/fig_tc07_uart.png)
<figcaption>Giải mã UART 8N1 trên CH0 ở 57.600 baud; bảng sự kiện thể hiện START (mức thấp), byte <code>0x55</code>, STOP</figcaption>
</figure>

Với I2C (Hình <a href="#fig:gui-i2c" data-reference-type="ref" data-reference="fig:gui-i2c">4.6</a>), bộ giải mã phân biệt đúng điều kiện START/STOP, hướng ghi của địa chỉ `0x50`, và trạng thái ACK/NACK của từng byte dữ liệu — byte `0xA5` được máy thu xác nhận (ACK) còn byte cuối `0x5A` bị từ chối (NACK) đúng theo kịch bản của bộ phát.

<figure id="fig:gui-i2c" data-latex-placement="H">
![fig_tc08_i2c](../generated/la_testsuite_20260718/figs/fig_tc08_i2c.png)
<figcaption>Giải mã giao dịch I2C trên CH1 (SCL)/CH2 (SDA): START, địa chỉ <code>0x50</code> W, dữ liệu ACK/NACK, STOP</figcaption>
</figure>

Với SPI ở 500 kS/s (Hình <a href="#fig:gui-spi" data-reference-type="ref" data-reference="fig:gui-spi">4.7</a>), bộ giải mã bắt cạnh xuống của CS làm mốc khung, đọc song song MOSI (CH4) và MISO (CH5) tại cạnh lên của SCK (CH3) và ghép đủ ba cặp byte cùng sự kiện CS kết thúc.

<figure id="fig:gui-spi" data-latex-placement="H">
![fig_tc09_spi](../generated/la_testsuite_20260718/figs/fig_tc09_spi.png)
<figcaption>Giải mã SPI trên CH3–CH6 tại 500 kS/s: CS bắt đầu, ba cặp MOSI/MISO, CS kết thúc</figcaption>
</figure>

Kịch bản TC-09 còn kiểm tra hành vi của bộ giải mã khi tín hiệu bị lấy mẫu thiếu. Khi thu cùng giao dịch SPI ở 150 kS/s (chỉ khoảng ba mẫu cho mỗi chu kỳ SCK), bộ giải mã không phát byte có thể sai mà phát cảnh báo `UNDERSAMPLED` kèm thông tin “chu kỳ SCK ngắn nhất chỉ có 3 mẫu, cần tối thiểu 4” (Hình <a href="#fig:gui-spi-under" data-reference-type="ref" data-reference="fig:gui-spi-under">4.8</a>). Đây là cơ chế bảo vệ quan trọng: thiết bị từ chối đưa ra kết quả không đáng tin thay vì báo cáo dữ liệu sai.

<figure id="fig:gui-spi-under" data-latex-placement="H">
![fig_tc09_spi_undersampled](../generated/la_testsuite_20260718/figs/fig_tc09_spi_undersampled.png)
<figcaption>Cùng giao dịch SPI khi lấy mẫu thiếu ở 150 kS/s: bộ giải mã phát cảnh báo <code>UNDERSAMPLED</code> và không phát byte sai</figcaption>
</figure>

### Định vị kích hoạt theo cạnh và mẫu (TC-10)

Hệ thống kích hoạt phần cứng được kiểm tra bằng lệnh `TRIG FALL 6` trên đường CS (CH6) — đường này nghỉ mức cao khoảng 20 ms giữa hai giao dịch SPI, đủ để lấp đầy vùng tiền kích hoạt. Với cấu hình tiền kích hoạt 1500 mẫu ở 100 kS/s, phiên thu dừng đúng tại cạnh xuống của CS: khung có 1490 mẫu tiền kích hoạt đều ở mức cao (nền nghỉ), tiếp theo là điểm kích hoạt và vùng hậu kích hoạt chứa giao dịch SPI (Hình <a href="#fig:gui-trigger" data-reference-type="ref" data-reference="fig:gui-trigger">4.9</a>). Vị trí trigger được đánh dấu bằng vạch dọc.

Các lệnh kích hoạt không hợp lệ đều bị firmware từ chối: `TRIG PAT 256 0` (mặt nạ vượt 8 bit) trả về `ERR BAD_PATTERN`, còn `TRIG RISE 9` (kênh không tồn tại) trả về `ERR BAD_TRIGGER_OR_RATE`; lệnh hợp lệ `TRIG PAT 1 0` được chấp nhận. Điều này xác nhận lớp kiểm tra tham số của giao thức điều khiển hoạt động đúng.

<figure id="fig:gui-trigger" data-latex-placement="H">
![fig_tc10_trigger](../generated/la_testsuite_20260718/figs/fig_tc10_trigger.png)
<figcaption>Kích hoạt theo cạnh xuống trên CH6 (CS): vùng tiền kích hoạt nghỉ mức cao, vạch dọc là điểm trigger, vùng hậu kích hoạt chứa giao dịch SPI</figcaption>
</figure>

### Xác định giới hạn tần số lấy mẫu

Kịch bản TC-04 xác nhận thiết bị sản phẩm từ chối mọi tần số vượt 6,545 MS/s. Để xác định giá trị trần này ngay từ đầu, một bản firmware đánh giá được mở khoá tần số (tới 32 MS/s), tăng dần tần số cấu hình và đối chiếu với chuỗi Gray.

Khi tần số vượt khả năng của DMA, thiết bị bỏ bớt mẫu đều đặn nên tần số đo được không tăng theo mà bão hoà. Giới hạn là điểm mà tần số đo bắt đầu nhỏ hơn tần số cấu hình (Bảng <a href="#tab:ceiling" data-reference-type="ref" data-reference="tab:ceiling">4.6</a>).

<div id="tab:ceiling">

| Cấu hình  |  Đo được  |    Chênh lệch    |    Kết quả     |
|:---------:|:---------:|:----------------:|:--------------:|
|   1 MHz   |   1 MHz   |  $`\approx 0`$   |      Đạt       |
|   4 MHz   |   4 MHz   |  $`\approx 0`$   |      Đạt       |
|   6 MHz   |   6 MHz   | $`\le 0{,}03\%`$ |      Đạt       |
| 6,545 MHz | 6,545 MHz | $`\le 0{,}03\%`$ | Đạt (giới hạn) |
|  7,2 MHz  | 6,65 MHz  |   $`-7{,}7\%`$   | Vượt giới hạn  |
|   8 MHz   | 6,79 MHz  |    $`-15\%`$     | Vượt giới hạn  |
|   9 MHz   | 6,81 MHz  |    $`-24\%`$     | Vượt giới hạn  |

Đo xác định giới hạn tần số lấy mẫu DMA ở $`f_{\mathrm{TIM2}}=72`$ MHz

</div>

Tần số đo trùng với tần số cấu hình (chênh lệch dưới 0,03%, là nhiễu của phép đo) đến 6,545 MS/s $`(=72~\text{MHz}/11)`$. Từ 7,2 MS/s tần số đo giảm và bão hoà quanh 6,8 MS/s. Vậy giới hạn ở xung 72 MHz là **6,545 MS/s**; giá trị này được đặt làm ngưỡng của firmware sản phẩm, và kịch bản TC-04 xác nhận firmware này từ chối mọi yêu cầu vượt ngưỡng. So với cấu hình HSI 64 MHz (giới hạn 5,818 MS/s), việc dùng thạch anh HSE nâng giới hạn thêm khoảng 12,5%. Cơ chế ISR có giới hạn 400 kS/s do thời gian xử lý ngắt .

### Tổng hợp kết quả mười kịch bản

Bảng <a href="#tab:test-summary" data-reference-type="ref" data-reference="tab:test-summary">4.7</a> tổng hợp kết quả mười kịch bản. Toàn bộ đều đạt tiêu chí đề ra; đáng chú ý, các kịch bản biên (TC-04, TC-05, TC-09, TC-10) cho thấy thiết bị xử lý điều kiện vượt giới hạn và tín hiệu không đủ tin cậy một cách an toàn — từ chối tần số vượt trần và cảnh báo khi lấy mẫu thiếu thay vì phát dữ liệu sai.

<div id="tab:test-summary">

| **Mã** | **Kết quả chính** | **Kết luận** |
|:---|:---|:---|
| **Mã** | **Kết quả chính** | **Kết luận** |
| TC-01 | Nhận dạng đúng, xung 72 MHz, mã kiểm tra hợp lệ trên mọi khung. | Đạt |
| TC-02 | Đủ tám kênh chuyển mức; 0 lỗi thứ tự; skew $`<`$ 1 chu kỳ mẫu. | Đạt |
| TC-03 | Ước số nguyên của 72 MHz: 0 ppm; mức không chia hết báo cáo trung thực. | Đạt |
| TC-04 | Sạch tại 6,545 MS/s (sai số 0,008%); từ chối 7–10 MS/s. | Đạt |
| TC-05 | ISR 100–400 kS/s: 0 tràn ngắt, 0 lỗi thứ tự; từ chối 500 kS/s. | Đạt |
| TC-06 | Tái tạo đúng ở 1 MS/s; phát hiện chồng phổ ở 30 kS/s. | Đạt |
| TC-07 | Bốn byte UART đúng, 0 lỗi khung ở 57.600 baud. | Đạt |
| TC-08 | START/ADDR/ACK/NACK/DATA/STOP đúng. | Đạt |
| TC-09 | Giải mã đủ ở 500 kS/s; cảnh báo `UNDERSAMPLED` ở 150 kS/s. | Đạt |
| TC-10 | Trigger đúng cạnh với tiền kích hoạt 1490 mẫu; từ chối lệnh sai. | Đạt |

Tổng hợp kết quả mười kịch bản kiểm thử

</div>

# ĐÁNH GIÁ VÀ THẢO LUẬN

## Mức độ hoàn thành theo thiết kế

Hệ thống đã hình thành các khối chính của thiết bị phân tích logic: thu thập GPIO bằng TIM2, lưu dữ liệu vào bộ đệm, truyền khung SLA8, hiển thị dạng sóng trên máy tính và giải mã UART, I2C, SPI. Bảng dưới đây đối chiếu các yêu cầu chính với kết quả triển khai.

| **Yêu cầu** | **Kết quả triển khai** | **Đánh giá** |
|:---|:---|:---|
| Số kênh | Cấu hình tám kênh CH0–CH7 (TC-02). | Vượt yêu cầu tối thiểu hai kênh. |
| Tần số lấy mẫu | Cấu hình từ 1 kHz tới 6,545 MS/s; ước số nguyên của 72 MHz đạt 0 ppm (TC-03, TC-04). | Vượt yêu cầu tối thiểu 1 kHz. |
| Hiển thị trên máy tính | Giao diện hiển thị đồng thời tám kênh với dạng sóng và bảng giải mã. | Đã triển khai và minh chứng trên phần cứng. |
| Tính toàn vẹn dữ liệu | Oracle Gray đạt tại DMA tới 6,545 MS/s và ISR tới 400 kS/s (TC-04, TC-05). | Không lỗi chuỗi, mất mẫu, tràn bộ đệm hay mã kiểm tra; vượt trần bị từ chối. |
| Quan hệ thời gian | Đọc đồng thời `GPIOA->IDR`; không có trạng thái trung gian trong 1 389 bước Gray (TC-02). | Đã định lượng: độ lệch giữa các kênh nhỏ hơn một chu kỳ lấy mẫu. |
| Giải mã giao thức | UART, I2C, SPI kiểm chứng trên phần cứng; có bảo vệ khi lấy mẫu thiếu (TC-07–TC-09). | Ba bộ giải mã đúng; bộ giải mã SPI cảnh báo thay vì phát byte sai. |
| Kích hoạt phần cứng | Kích hoạt theo cạnh/mẫu với tiền kích hoạt; kiểm tra tham số (TC-10). | Định vị trigger đúng; lệnh không hợp lệ bị từ chối. |

Đối chiếu yêu cầu với kết quả triển khai

## Hạn chế

Các hạn chế của phiên bản hiện tại gồm:

- Độ lệch thời gian giữa các kênh mới được chặn trên ở mức nhỏ hơn một chu kỳ lấy mẫu (TC-02); chưa đo trực tiếp jitter tuyệt đối bằng nguồn tham chiếu ổn định độc lập, và chưa có sơ đồ nguyên lý phần cứng đầy đủ;

- Bộ giải mã SPI hiện giả định lấy mẫu tại cạnh lên và ghép byte theo thứ tự MSB-first; chưa cho phép cấu hình CPOL/CPHA và thứ tự bit;

- Giới hạn 400 kS/s của cơ chế ISR khiến các điều kiện kích hoạt theo cạnh và mẫu không dùng được ở dải tần cao như cơ chế DMA tức thời.

## Hướng phát triển

Các hướng phát triển tiếp theo gồm:

- Đo jitter và skew bằng tín hiệu tham chiếu chung trên nhiều kênh;

- Mở rộng bộ giải mã SPI để cấu hình CPOL, CPHA và thứ tự bit;

- Hoàn thiện sơ đồ đấu nối và quy trình kiểm tra mức điện áp trước các phép thử giao thức.

# KẾT LUẬN

Đề tài đã xây dựng thiết bị phân tích logic tám kênh dựa trên STM32F103C8 và phần mềm hiển thị trên máy tính. Hệ thống thu dữ liệu bằng DMA hoặc ISR, truyền khung SLA8 và giải mã UART, I2C, SPI. Thiết bị được đánh giá bằng mười kịch bản kiểm thử có tín hiệu tham chiếu, phủ từ toàn vẹn khung dữ liệu, ánh xạ kênh và quan hệ thời gian, độ chính xác và trần tần số lấy mẫu, giới hạn Nyquist, đến ba bộ giải mã giao thức và hệ thống kích hoạt phần cứng.

Kết quả cho thấy xung TIM2 đạt 72 MHz; oracle Gray đạt ở cơ chế DMA tới 6,545 MS/s và ISR tới 400 kS/s mà không có lỗi thứ tự, mất mẫu, tràn bộ đệm hay sai mã kiểm tra, với độ lệch giữa các kênh nhỏ hơn một chu kỳ lấy mẫu. Ba bộ giải mã hoạt động đúng trên tín hiệu thật. Quan trọng hơn, các kịch bản biên cho thấy thiết bị hành xử an toàn: từ chối tần số vượt trần thay vì âm thầm bỏ mẫu, và cảnh báo khi tín hiệu bị lấy mẫu thiếu thay vì phát dữ liệu sai. Hướng phát triển tiếp theo tập trung vào đo jitter tuyệt đối, mở rộng cấu hình CPOL/CPHA cho bộ giải mã SPI và nâng trần tốc độ của cơ chế kích hoạt theo cạnh.

<div class="thebibliography">

99

Tài liệu học phần Bài tập lớn Hệ thống nhúng và thiết kế giao tiếp nhúng, học kỳ 2025.2. Mã nguồn dự án thiết bị phân tích logic tám kênh: `platformio.ini`, `src/firmware`, `src/software` và `tests`. Nhóm thực hiện, *Kết quả HIL trên STM32F103C8 chạy thạch anh HSE 72 MHz*, . STMicroelectronics, *STM32F103x8/xB medium-density performance line*, DS5319 Rev. 20. [ST DS5319 (PDF)](https://www.st.com/resource/en/datasheet/CD00161566.pdf). STMicroelectronics, *RM0008: STM32F10xxx reference manual*, Rev. 21. [ST RM0008 (PDF)](https://www.st.com/resource/en/reference_manual/cd00171190-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-arm-based-32-bit-mcus-stmicroelectronics.pdf). C. E. Shannon, “Communication in the Presence of Noise,” *Proceedings of the IRE*, vol. 37, no. 1, pp. 10–21, 1949.

</div>
