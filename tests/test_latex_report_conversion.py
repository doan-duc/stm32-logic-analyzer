from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "report" / "latex_topic1"
SOURCE_DOCX = REPO_ROOT / "report" / "generated" / "Bao_cao_Topic_1_Doan_Sinh_Duc.docx"
TEMPLATE_DOCX = REPO_ROOT / "report" / "generated" / "Mẫu ĐATN_2019_version 1_1 (1).docx"

sys.path.insert(0, str(OUTPUT_DIR))

from convert_report import (  # noqa: E402
    add_full_grid_to_longtables,
    build_pdf,
    capitalize_list_item_starts,
    convert_report,
    extract_red_requirements,
    normalize_table_captions,
)


class TestLatexTransformUnit(unittest.TestCase):
    def test_list_items_start_with_uppercase_letters(self) -> None:
        source = "\\item \u0111o jitter\n\\item m\u1edf r\u1ed9ng SPI\n\\item ki\u1ec3m tra DMA"

        converted = capitalize_list_item_starts(source)

        self.assertEqual(
            converted,
            "\\item \u0110o jitter\n\\item M\u1edf r\u1ed9ng SPI\n\\item Ki\u1ec3m tra DMA",
        )

    def test_all_red_word_requirements_are_extracted(self) -> None:
        requirements = extract_red_requirements(SOURCE_DOCX)
        expected = [
            "Đề tài 1: ...",
            "Phần trăm sử dụng AI",
            "Chỉ tiêu chức năng/ Chỉ tiêu phi chức năng",
            "Cơ sở lý thuyết STM32, Xung thạch anh tới tốc độ xử lý của STM32",
            "Thêm ảnh mô tả Lý thuyết,VD ảnh giao thức, stm32, LAXem thuật toán khử nhiễu, aligsing",
            "Có công thức, định lý Nyquist, rõ thêm về aliasing",
            "Lý thuyết về mạch bảo vệ",
            "Sơ đồ khối hoạt động",
            "3.8 Thiết kế Khối mạch bảo vệ",
            "Cách cắm mạch, nối dây, chạy file gì để làm chương trình, thao tác như nào",
            "Khi cap ảnh decode, cap rõ phần start bit, stop bit đối với UART để chèn ảnh vào và chú thích khoanh vùng phần đó (MISO, MOSI)",
        ]

        self.assertCountEqual([item.text for item in requirements], expected)
        self.assertEqual(len({item.paragraph_number for item in requirements}), 11)

    def test_table_grid_adds_vertical_and_horizontal_rules(self) -> None:
        source = r"""\begin{longtable}[]{@{}
  >{\raggedright\arraybackslash}p{0.4\linewidth}
  >{\raggedright\arraybackslash}p{0.6\linewidth}@{}}
\toprule\noalign{}
A & B \\
\midrule\noalign{}
one & two \\
\bottomrule\noalign{}
\end{longtable}"""

        converted = add_full_grid_to_longtables(source)

        self.assertIn(r"\begin{longtable}[]{@{}|", converted)
        self.assertEqual(converted.count("|>"), 1)
        self.assertIn(r"|@{}}", converted)
        self.assertIn(r"A & B \\ \hline", converted)
        self.assertIn(r"one & two \\ \hline", converted)
        self.assertNotIn(r"\toprule", converted)
        self.assertNotIn(r"\midrule", converted)
        self.assertNotIn(r"\bottomrule", converted)

    def test_caption_normalization_removes_legacy_number_only(self) -> None:
        source = (
            r"\caption{Bảng 7 Kịch bản cần chạy trên phần cứng}\tabularnewline"
            "\n"
            r"\caption{Bảng tổng hợp không đánh số sẵn}\tabularnewline"
        )

        converted = normalize_table_captions(source)

        self.assertIn(
            r"\caption{Kịch bản cần chạy trên phần cứng}\tabularnewline",
            converted,
        )
        self.assertIn(
            r"\caption{Bảng tổng hợp không đánh số sẵn}\tabularnewline",
            converted,
        )


class TestLatexConversionIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        convert_report(SOURCE_DOCX, TEMPLATE_DOCX, OUTPUT_DIR, build=False)
        cls.main_tex = (OUTPUT_DIR / "Bao_cao_Topic_1_Doan_Sinh_Duc.tex").read_text(
            encoding="utf-8"
        )
        cls.content_tex = (OUTPUT_DIR / "content.tex").read_text(encoding="utf-8")

    def test_page_and_font_rules_match_requested_template(self) -> None:
        self.assertIn(
            r"\usepackage[a4paper,top=2cm,bottom=2cm,left=3cm,right=2cm]"
            "{geometry}",
            self.main_tex,
        )
        self.assertIn(r"\documentclass[12pt,a4paper,oneside]{report}", self.main_tex)
        self.assertIn(r"\setmainfont{Times New Roman}", self.main_tex)
        self.assertIn(r"\usepackage{amsmath}", self.main_tex)
        self.assertIn(r"\usepackage[fontsize=13]{fontsize}", self.main_tex)
        self.assertIn(r"\changefontsize[14.3]{13}", self.main_tex)
        self.assertIn(r"\setlength{\parindent}{0pt}", self.main_tex)
        self.assertNotIn(r"\setstretch", self.main_tex)
        self.assertIn(r"\renewcommand{\cftdotsep}{0}", self.main_tex)
        self.assertIn(r"\fancyfoot[R]{\thepage}", self.main_tex)
        self.assertIn(r"\captionsetup[table]{position=top,font={small,it},justification=centering,labelsep=space}", self.main_tex)
        self.assertIn(r"\fontsize{25pt}{30pt}\selectfont BÁO CÁO BÀI TẬP LỚN", self.main_tex)
        self.assertIn(r"\fontsize{23pt}{27.6pt}\selectfont THIẾT KẾ VÀ XÂY DỰNG THIẾT BỊ", self.main_tex)
        self.assertIn(r"\captionsetup[figure]{position=bottom,font={small,it},justification=centering,labelsep=space}", self.main_tex)

    def test_all_list_items_start_with_uppercase_letters(self) -> None:
        items = re.findall(r"(?m)^\\item\s+(.+)$", self.content_tex)
        self.assertGreater(len(items), 0)
        for item in items:
            first_letter = next((character for character in item if character.isalpha()), None)
            self.assertIsNotNone(first_letter)
            self.assertTrue(first_letter.isupper(), item)

    def test_live_hardware_evidence_is_embedded(self) -> None:
        evidence_dir = REPO_ROOT / "report" / "generated" / "hardware_evidence_20260718"
        figures = {
            "gui_01_connected_com12.png": "fig:gui-connected",
            "gui_02_gray_8ch_100ksps.png": "fig:gui-gray",
            "gui_03_uart_decode_ch0.png": "fig:gui-uart",
            "gui_04_i2c_decode_ch1_ch2.png": "fig:gui-i2c",
            "gui_05_spi_decode_ch3_ch6.png": "fig:gui-spi",
            "log_00_device_info.png": "fig:device-probe",
            "log_01_hil_dma_standard.png": "fig:hil-dma-standard",
            "log_02_hil_dma_high.png": "fig:hil-dma-high",
            "log_03_hil_isr_and_1ksps.png": "fig:hil-isr",
        }
        for filename, label in figures.items():
            self.assertTrue((evidence_dir / filename).is_file(), filename)
            self.assertIn(filename, self.content_tex)
            self.assertIn(label, self.content_tex)

        self.assertIn("6,545~MS/s", self.content_tex)
        self.assertIn("57.600~baud", self.content_tex)
        self.assertIn("UART, I2C và SPI đã được kiểm chứng", self.content_tex)
        self.assertIn("MOSI=\\texttt{0x55}, MISO=\\texttt{0xA5}", self.content_tex)
        self.assertNotIn("phép thử SPI chờ mạch chuyển mức", self.content_tex)
        self.assertNotIn("23--24 trạng thái Gray", self.content_tex)
    def test_all_tables_use_complete_borders(self) -> None:
        tables = re.findall(
            r"\\begin\{longtable\}.*?\\end\{longtable\}",
            self.content_tex,
            flags=re.DOTALL,
        )
        self.assertGreaterEqual(len(tables), 10)
        for table in tables:
            self.assertIn(r"\begin{longtable}[]{@{}|", table)
            self.assertIn(r"|@{}}", table)
            self.assertIn("|>", table)
            for row in re.findall(r"^.*?\\\\\s*$", table, flags=re.MULTILINE):
                self.assertIn(r"\hline", row)
            self.assertNotRegex(table, r"\\(?:toprule|midrule|bottomrule)")
        self.assertIn(r"\begin{tabularx}{0.88\textwidth}{|p{0.31\textwidth}|X|}", self.main_tex)
        title_table = self.main_tex.split(r"\begin{tabularx}", 1)[1].split(r"\end{tabularx}", 1)[0]
        self.assertNotIn(r"\cline", title_table)
        self.assertGreaterEqual(title_table.count(r"\hline"), 3)

    def test_cover_has_complete_student_and_supervisor_information(self) -> None:
        expected_students = (
            "Đoàn Sinh Đức -- 20234000",
            "Phạm Đăng Vinh -- 20233719",
            "Vũ Mạnh Quân -- 20234033",
            "Vũ Nam Khánh -- 20234015",
        )
        for student in expected_students:
            self.assertIn(student, self.main_tex)
        self.assertIn("Giảng viên hướng dẫn:", self.main_tex)
        self.assertIn("TS. Đào Việt Hùng", self.main_tex)
        self.assertNotIn("[CẦN BỔ SUNG", self.main_tex)

    def test_table_columns_are_balanced_by_content(self) -> None:
        expected_ratios = {
            "Tóm tắt yêu cầu và phạm vi đáp ứng": ("0.20", "0.35", "0.45"),
            "Các thành phần phần cứng": ("0.20", "0.45", "0.35"),
            "Chức năng phần mềm PC": ("0.24", "0.76"),
            "Các lệnh UART chính": ("0.38", "0.62"),
            "Lệnh triển khai": ("0.24", "0.76"),
            "Kế hoạch kiểm thử": ("0.12", "0.30", "0.58"),
        }
        tables = re.findall(
            r"\\begin\{longtable\}.*?\\end\{longtable\}",
            self.content_tex,
            flags=re.DOTALL,
        )
        for caption, ratios in expected_ratios.items():
            table = next(item for item in tables if rf"\caption{{{caption}}}" in item)
            self.assertEqual(re.findall(r"\\real\{([0-9.]+)\}", table), list(ratios))

    def test_content_structure_and_sentinels_are_preserved(self) -> None:
        self.assertEqual(self.content_tex.count(r"\chapter{"), 6)
        self.assertGreaterEqual(self.content_tex.count(r"\section{"), 21)
        self.assertGreaterEqual(self.content_tex.count(r"\caption{"), 7)
        self.assertIn("Đoàn Sinh Đức -- 20234000", self.main_tex)
        self.assertIn("Thiết bị phân tích logic ghi nhận trạng thái số", self.content_tex)
        self.assertIn("python -m platformio run", self.content_tex)
        self.assertIn("TÀI LIỆU THAM KHẢO", self.content_tex)
        self.assertNotIn("MỤC LỤC}\\tabularnewline", self.content_tex)
        self.assertNotIn("Đề tài 1: ...", self.main_tex)

    def test_red_editorial_notes_are_resolved_or_reported_honestly(self) -> None:
        forbidden_notes = (
            "Thêm ảnh mô tả Lý thuyết",
            "Có công thức, định lý Nyquist",
            "Lý thuyết về mạch bảo vệ",
            "Sơ đồ khối hoạt động",
            "Cách cắm mạch, nối dây",
            "Khi cap ảnh decode",
        )
        for note in forbidden_notes:
            self.assertNotIn(note, self.content_tex)

        self.assertNotIn("Phần trăm sử dụng AI", self.content_tex)
        self.assertNotIn("Tỷ lệ sử dụng công cụ AI", self.content_tex)
        self.assertNotIn("Lý thuyết về mạch bảo vệ", self.content_tex)
        self.assertNotIn("3.8 Thiết kế Khối mạch bảo vệ", self.content_tex)
        self.assertIn(r"f_s > 2f_{\max}", self.content_tex)
        self.assertNotIn(r"f_s \ge 2f_{\max}", self.content_tex)
        self.assertIn(r"f_{\mathrm{alias}}", self.content_tex)
        self.assertIn(r"f_{\mathrm{update}}", self.content_tex)
        for topic in ("STM32F103C8", "HSE", "PLL", "PCLK1", "TIM2"):
            self.assertIn(topic, self.content_tex)

        self.assertIn("SCK, MOSI, MISO và CS", self.content_tex)

    def test_formal_prose_has_no_editorial_or_ai_note_language(self) -> None:
        forbidden = (
            "[CẦN BỔ SUNG",
            "[CHƯA CÓ DỮ LIỆU]",
            "VỊ TRÍ CHÈN ẢNH",
            "CHƯA CÓ MINH CHỨNG",
            "Hướng dẫn thu thập minh chứng",
            "không tự điền",
            "không suy diễn",
            "do nhóm cung cấp",
            "repository",
            "source hiện có",
        )
        for phrase in forbidden:
            self.assertNotIn(phrase, self.content_tex)
        self.assertNotIn(r"\evidenceplaceholder", self.main_tex)
        self.assertNotIn(r"\evidenceplaceholder", self.content_tex)

        objective_block = self.content_tex.split(r"\section{Mục tiêu thiết kế}", 1)[1].split(
            r"\section{Yêu cầu của Đề tài 1", 1
        )[0]
        self.assertIn(r"\begin{itemize}", objective_block)
        self.assertGreaterEqual(objective_block.count(r"\item"), 3)

        requirements_block = self.content_tex.split(r"\section{Yêu cầu của Đề tài 1", 1)[1].split(
            r"\begin{longtable}", 1
        )[0]
        self.assertEqual(requirements_block.count(r"\begin{itemize}"), 2)

    def test_input_protection_details_are_not_invented(self) -> None:
        forbidden = (
            "sec:protection-theory",
            "sec:protection-design",
            "fig:protection-principle",
            "st-an4899",
            r"I_{\mathrm{clamp}}",
            r"\cite{st-an4899}",
            "Schmitt trigger",
            "diode/TVS",
            "Hạn dòng",
            "Kẹp ESD",
        )
        for token in forbidden:
            self.assertNotIn(token, self.content_tex)

    def test_report_uses_current_verified_firmware_facts(self) -> None:
        for fact in (
            "bộ nhớ Flash 64~KB",
            "xung TIM2 bằng 72~MHz",
            "UART, I2C và SPI",
            "DMA đến 6,545~MS/s",
            "ISR đến 400~kS/s",
            "khung 8N1",
        ):
            self.assertIn(fact, self.content_tex)

        for stale_fact in (
            "bộ nhớ Flash tối đa 128~KB",
            "firmware_v2",
            r"firmware\_v2",
            "bit chẵn lẻ",
            "5.818.181~S/s",
            "6,228--6,233~MS/s",
            "chưa hỗ trợ SPI",
        ):
            self.assertNotIn(stale_fact, self.content_tex)

    def test_theory_diagrams_and_formal_test_plan_are_present(self) -> None:
        self.assertGreaterEqual(self.content_tex.count(r"\begin{tikzpicture}"), 3)
        self.assertEqual(self.content_tex.count(r"\evidenceplaceholder{"), 0)
        self.assertIn("Kế hoạch kiểm thử", self.content_tex)
        self.assertIn("Kết quả kiểm thử phần cứng", self.content_tex)
        self.assertIn(r"\counterwithin{table}{chapter}", self.main_tex)
        self.assertIn(r"\counterwithin{figure}{chapter}", self.main_tex)

    def test_red_requirement_audit_is_complete(self) -> None:
        audit_path = OUTPUT_DIR / "RED_REQUIREMENTS_AUDIT.md"
        self.assertTrue(audit_path.is_file())
        audit = audit_path.read_text(encoding="utf-8")
        self.assertEqual(audit.count("### Yêu cầu màu đỏ"), 11)
        self.assertIn("Đã loại khỏi báo cáo theo yêu cầu của nhóm", audit)
        self.assertIn("bổ sung ảnh dạng sóng thực tế", audit)
        self.assertIn("ảnh mô hình phần cứng cần được chụp bằng máy ảnh", audit)
        self.assertIn("Không đưa vào báo cáo vì chưa có thiết kế", audit)
        self.assertIn("Không tạo mục thiết kế mạch bảo vệ", audit)
        for item in extract_red_requirements(SOURCE_DOCX):
            self.assertEqual(audit.count(item.text), 1)


class TestLatexConversionEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        convert_report(SOURCE_DOCX, TEMPLATE_DOCX, OUTPUT_DIR, build=False)
        cls.pdf_path = build_pdf(OUTPUT_DIR)

    def test_xelatex_build_creates_readable_pdf(self) -> None:
        self.assertTrue(self.pdf_path.is_file())
        self.assertGreater(self.pdf_path.stat().st_size, 20_000)

        info = subprocess.run(
            ["pdfinfo", str(self.pdf_path)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout
        page_match = re.search(r"^Pages:\s+(\d+)$", info, flags=re.MULTILINE)
        self.assertIsNotNone(page_match)
        self.assertGreaterEqual(int(page_match.group(1)), 13)

    def test_build_log_has_no_missing_glyphs_or_material_overflow(self) -> None:
        build_log = (OUTPUT_DIR / "build.log").read_text(encoding="utf-8")
        self.assertNotIn("Missing character", build_log)
        overflow_widths = [
            float(width)
            for width in re.findall(r"Overfull \\hbox \(([0-9.]+)pt too wide\)", build_log)
        ]
        self.assertTrue(all(width <= 10 for width in overflow_widths), overflow_widths)
    def test_pdf_is_a4_and_embeds_times_new_roman(self) -> None:
        info = subprocess.run(
            ["pdfinfo", str(self.pdf_path)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout
        self.assertIn("Page size:       595.28 x 841.89 pts (A4)", info)

        fonts = subprocess.run(
            ["pdffonts", str(self.pdf_path)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout
        self.assertIn("TimesNewRomanPSMT", fonts)
        self.assertIn("TimesNewRomanPS-BoldMT", fonts)
        self.assertRegex(fonts, r"TimesNewRomanPSMT\s+CID\s+TrueType\s+Identity-H\s+yes\s+yes\s+yes")
    def test_pdf_contains_title_and_final_reference_section(self) -> None:
        result = subprocess.run(
            ["pdftotext", "-enc", "UTF-8", str(self.pdf_path), "-"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        normalized = " ".join(result.stdout.split())
        self.assertIn("THIẾT KẾ VÀ XÂY DỰNG THIẾT BỊ LOGIC", normalized)
        self.assertIn("TÀI LIỆU THAM KHẢO", normalized)


if __name__ == "__main__":
    unittest.main()
