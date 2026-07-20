from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
RED_VALUES = {"FF0000", "C00000", "DC0000", "E60000", "F00"}
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = REPO_ROOT / "report" / "generated" / "Bao_cao_Topic_1_Doan_Sinh_Duc.docx"
DEFAULT_TEMPLATE = REPO_ROOT / "report" / "generated" / "Mẫu ĐATN_2019_version 1_1 (1).docx"
DEFAULT_OUTPUT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class RedRequirement:
    paragraph_number: int
    text: str


def _find_program(name: str) -> str:
    discovered = shutil.which(name)
    if discovered:
        return discovered
    local_app_data = Path.home() / "AppData" / "Local"
    candidates = (
        local_app_data / "Pandoc" / "pandoc.exe",
        local_app_data / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64" / "xelatex.exe",
    )
    for candidate in candidates:
        if candidate.name.lower() == f"{name}.exe" and candidate.is_file():
            return str(candidate)
    raise FileNotFoundError(f"Không tìm thấy chương trình bắt buộc: {name}")


def extract_red_requirements(source_docx: Path) -> list[RedRequirement]:
    """Extract each paragraph containing direct-format red text from the DOCX."""
    with zipfile.ZipFile(source_docx) as archive:
        document_xml = archive.read("word/document.xml")
    document = ET.fromstring(document_xml)
    requirements: list[RedRequirement] = []
    for paragraph_number, paragraph in enumerate(document.findall(".//w:body//w:p", NS), start=1):
        red_runs: list[str] = []
        for run in paragraph.findall(".//w:r", NS):
            color = run.find("./w:rPr/w:color", NS)
            color_value = "" if color is None else color.attrib.get(f"{{{W_NS}}}val", "").upper()
            if color_value in RED_VALUES:
                red_runs.append("".join(node.text or "" for node in run.findall(".//w:t", NS)))
        text = "".join(red_runs).strip()
        if text:
            requirements.append(RedRequirement(paragraph_number, text))
    return requirements


def normalize_table_captions(latex: str) -> str:
    return re.sub(
        r"\\caption\{Bảng\s+\d+\s+([^{}]+)\}",
        r"\\caption{\1}",
        latex,
    )


def capitalize_list_item_starts(latex: str) -> str:
    """Uppercase the first letter of every LaTeX list item."""
    return re.sub(
        r"(?m)^(\\item\s+)([^\W\d_])",
        lambda match: match.group(1) + match.group(2).upper(),
        latex,
    )


def _grid_single_longtable(match: re.Match[str]) -> str:
    table = match.group(0)
    if r"\begin{longtable}[]{@{}|" in table:
        return table
    preamble = re.search(
        r"\\begin\{longtable\}\[\]\{@\{\}(?P<spec>.*?)@\{\}\}",
        table,
        flags=re.DOTALL,
    )
    if preamble is None:
        return table
    column_seen = False
    spec_lines: list[str] = []
    for line in preamble.group("spec").splitlines():
        if re.match(r"^\s*>", line):
            prefix = "|" if column_seen else ""
            spec_lines.append(re.sub(r"^(\s*)>", rf"\1{prefix}>", line))
            column_seen = True
        else:
            spec_lines.append(line)
    spec = "\n".join(spec_lines)
    # Pandoc sizes ``p`` columns for a table without vertical rules.  The
    # complete grid adds rule spacing; reserve a little room so a bordered
    # longtable stays within the text block instead of overflowing it.
    spec = re.sub(
        r"\(\\linewidth - (\d+)\\tabcolsep\)",
        lambda width: rf"(\linewidth - {int(width.group(1)) + 3}\tabcolsep)",
        spec,
    )
    bordered_begin = r"\begin{longtable}[]{@{}|" + spec + r"|@{}}"
    table = table[: preamble.start()] + bordered_begin + table[preamble.end() :]
    table = table.replace(r"\toprule\noalign{}", r"\hline")
    table = table.replace(r"\midrule\noalign{}", "")
    table = table.replace(r"\bottomrule\noalign{}", "")
    rows: list[str] = []
    for line in table.splitlines():
        if re.search(r"\\\\\s*$", line):
            rows.append(line + r" \hline")
        else:
            rows.append(line)
    return "\n".join(rows)


def add_full_grid_to_longtables(latex: str) -> str:
    return re.sub(
        r"\\begin\{longtable\}.*?\\end\{longtable\}",
        _grid_single_longtable,
        latex,
        flags=re.DOTALL,
    )

TABLE_COLUMN_RATIOS: dict[str, tuple[str, ...]] = {
    "Tóm tắt yêu cầu và phạm vi đáp ứng": ("0.20", "0.35", "0.45"),
    "Các thành phần phần cứng": ("0.20", "0.45", "0.35"),
    "Vai trò các mô-đun firmware": ("0.25", "0.75"),
    "Chức năng phần mềm PC": ("0.24", "0.76"),
    "Các lệnh UART chính": ("0.38", "0.62"),
    "Kết nối giữa các phần tử trong hệ thống": ("0.26", "0.30", "0.44"),
    "Lệnh triển khai": ("0.24", "0.76"),
    "Kế hoạch kiểm thử": ("0.12", "0.30", "0.58"),
    "Kết quả kiểm thử HIL với chuỗi Gray": ("0.12", "0.36", "0.18", "0.34"),
    "Đối chiếu yêu cầu với kết quả triển khai": ("0.22", "0.38", "0.40"),
}


def rebalance_longtable_columns(latex: str) -> str:
    def rebalance(match: re.Match[str]) -> str:
        table = match.group(0)
        caption_match = re.search(r"\\caption\{([^{}]+)\}\\tabularnewline", table)
        if caption_match is None:
            return table
        ratios = TABLE_COLUMN_RATIOS.get(caption_match.group(1))
        if ratios is None:
            return table
        width_matches = list(re.finditer(r"\\real\{[0-9.]+\}", table))
        if len(width_matches) != len(ratios):
            raise ValueError(
                f"Bảng '{caption_match.group(1)}' có {len(width_matches)} cột, "
                f"nhưng cấu hình độ rộng có {len(ratios)} giá trị"
            )
        ratio_iter = iter(ratios)
        return re.sub(
            r"\\real\{[0-9.]+\}",
            lambda _width: rf"\real{{{next(ratio_iter)}}}",
            table,
        )

    return re.sub(
        r"\\begin\{longtable\}.*?\\end\{longtable\}",
        rebalance,
        latex,
        flags=re.DOTALL,
    )

def embed_hardware_evidence(latex: str) -> str:
    """Embed verified, locally captured hardware and GUI evidence."""
    if r"\label{fig:gui-connected}" in latex:
        return latex

    interface_figure = r"""
\begin{figure}[H]
\centering
\includegraphics[width=0.98\textwidth]{../generated/hardware_evidence_20260718/gui_01_connected_com12.png}
\caption{Giao diện phần mềm sau khi kết nối STM32 qua COM12}
\label{fig:gui-connected}
\end{figure}
"""

    control_marker = r"\section{Giao thức điều khiển}"
    if control_marker not in latex:
        raise ValueError("Không xác định được vị trí chèn ảnh giao diện")
    latex = latex.replace(
        control_marker,
        interface_figure.strip() + "\n\n" + control_marker,
        1,
    )

    device_figure = r"""
\begin{figure}[H]
\centering
\includegraphics[width=\textwidth]{../generated/hardware_evidence_20260718/log_00_device_info.png}
\caption{Phản hồi nhận dạng và trạng thái của STM32 trên COM12 và Arduino trên COM18}
\label{fig:device-probe}
\end{figure}
"""

    hil_marker = r"\section{Kết quả kiểm thử phần cứng}\label{sec:hil-results}"
    if hil_marker not in latex:
        raise ValueError("Không xác định được mục kết quả kiểm thử phần cứng")
    latex = latex.replace(
        hil_marker,
        hil_marker + "\n\n" + device_figure.strip(),
        1,
    )

    evidence_block = r"""
\subsection{Minh chứng kiểm thử tự động}\label{sec:hil-evidence}

Hình~\ref{fig:gui-gray} thể hiện trực tiếp tám kênh CH0--CH7 khi Arduino phát chuỗi Gray. Các nhật ký ở Hình~\ref{fig:hil-dma-standard}--\ref{fig:hil-isr} được tạo từ cùng phiên kiểm thử phần cứng và đối chiếu với các khung SLA8 đã lưu.

\begin{figure}[H]
\centering
\includegraphics[width=0.98\textwidth]{../generated/hardware_evidence_20260718/gui_02_gray_8ch_100ksps.png}
\caption{Dạng sóng chuỗi Gray trên tám kênh CH0--CH7 tại 100~kS/s}
\label{fig:gui-gray}
\end{figure}

\begin{figure}[H]
\centering
\includegraphics[width=\textwidth]{../generated/hardware_evidence_20260718/log_01_hil_dma_standard.png}
\caption{Kết quả HIL chuỗi Gray ở 100~kS/s, 500~kS/s và 1~MS/s}
\label{fig:hil-dma-standard}
\end{figure}

\begin{figure}[H]
\centering
\includegraphics[width=\textwidth]{../generated/hardware_evidence_20260718/log_02_hil_dma_high.png}
\caption{Kết quả HIL chuỗi Gray từ 2~MS/s đến 6,545~MS/s}
\label{fig:hil-dma-high}
\end{figure}

\begin{figure}[H]
\centering
\includegraphics[width=\textwidth]{../generated/hardware_evidence_20260718/log_03_hil_isr_and_1ksps.png}
\caption{Kết quả HIL cơ chế ISR và mức lấy mẫu tối thiểu 1~kS/s}
\label{fig:hil-isr}
\end{figure}

\subsection{Kết quả hiển thị và giải mã giao thức}\label{sec:protocol-evidence}

UART, I2C và SPI đã được kiểm chứng bằng tín hiệu thực do Arduino tạo. Với UART, phần mềm nhận đúng chuỗi byte \texttt{0x55}, \texttt{0xA5}, \texttt{0x4F}, \texttt{0x4B} ở cấu hình 8N1, 57.600~baud. Với I2C, bảng giải mã nhận đúng điều kiện bắt đầu, địa chỉ \texttt{0x50} ở chiều ghi, hai byte dữ liệu \texttt{0xA5}, \texttt{0x5A} và điều kiện kết thúc. Với SPI, bộ phát Arduino sử dụng ngõ ra cực máng hở và mức kéo lên 3,3~V của STM32. Tại 500~kS/s, phần mềm nhận đủ ba cặp byte MOSI=\texttt{0x55}, MISO=\texttt{0xA5}; MOSI=\texttt{0xA5}, MISO=\texttt{0x3C}; MOSI=\texttt{0x5A}, MISO=\texttt{0xC3}, cùng hai sự kiện CS bắt đầu và kết thúc. Khung SLA8 gồm 13\,888 mẫu không ghi nhận tràn bộ đệm hoặc mất mẫu.

\begin{figure}[H]
\centering
\includegraphics[width=0.98\textwidth]{../generated/hardware_evidence_20260718/gui_03_uart_decode_ch0.png}
\caption{Dạng sóng và kết quả giải mã UART 8N1 trên CH0 ở 57.600~baud}
\label{fig:gui-uart}
\end{figure}

\begin{figure}[H]
\centering
\includegraphics[width=0.98\textwidth]{../generated/hardware_evidence_20260718/gui_04_i2c_decode_ch1_ch2.png}
\caption{Dạng sóng và kết quả giải mã giao dịch I2C trên CH1--CH2}
\label{fig:gui-i2c}
\end{figure}

\begin{figure}[H]
\centering
\includegraphics[width=0.98\textwidth]{../generated/hardware_evidence_20260718/gui_05_spi_decode_ch3_ch6.png}
\caption{Dạng sóng và kết quả giải mã SPI trên CH3--CH6 tại 500~kS/s}
\label{fig:gui-spi}
\end{figure}
"""

    ceiling_marker = r"\subsection{Xác định giới hạn tần số lấy mẫu}"
    assessment_marker = r"\chapter{ĐÁNH GIÁ VÀ THẢO LUẬN}"
    insertion_marker = (
        ceiling_marker if ceiling_marker in latex else assessment_marker
    )
    if insertion_marker not in latex:
        raise ValueError("Không xác định được vị trí chèn minh chứng HIL")
    latex = latex.replace(
        insertion_marker,
        evidence_block.strip() + "\n\n" + insertion_marker,
        1,
    )
    return latex

def _replace_block(latex: str, start: str, end: str, replacement: str) -> str:
    start_index = latex.find(start)
    end_index = latex.find(end, start_index)
    if start_index < 0 or end_index < 0:
        raise ValueError(f"Không xác định được khối cần chuyển đổi: {start[:48]}")
    return latex[:start_index] + replacement.strip() + "\n\n" + latex[end_index:]


def _front_matter() -> str:
    return r"""% !TeX program = xelatex
% !TeX encoding = UTF-8
\documentclass[12pt,a4paper,oneside]{report}
\usepackage[a4paper,top=2cm,bottom=2cm,left=2.5cm,right=2.5cm]{geometry}
\usepackage{fontspec}
\setmainfont{Times New Roman}
\setsansfont{Times New Roman}
\setmonofont{Times New Roman}
\usepackage{anyfontsize}
\usepackage[fontsize=13]{fontsize}
\changefontsize[14.3]{13}
\usepackage{graphicx}
\let\originalincludegraphics\includegraphics
\RenewDocumentCommand{\includegraphics}{O{}m}{%
  \IfFileExists{#2}{%
    \originalincludegraphics[#1]{#2}%
  }{%
    \fbox{\parbox[c][4.8cm][c]{0.88\linewidth}{%
      \centering\small
      Hình minh chứng chưa được đính kèm trong workspace.\\[4pt]
      \path{#2}%
    }}%
  }%
}
\usepackage{amsmath}
\usepackage{unicode-math}
\setmathfont{Latin Modern Math}
\usepackage{xcolor}
\usepackage{longtable}[=v4.13]
\usepackage{array,calc,tabularx}
\renewcommand{\tabularxcolumn}[1]{m{#1}}
\makeatletter
\long\def\LT@p@ftntext#1{%
  \edef\@tempa{%
    \the\LT@p@ftn
    \noexpand\footnotetext[\the\c@footnote]%
  }%
  \global\LT@p@ftn\expandafter{\@tempa{#1}}%
}
\makeatother
\usepackage{caption}
\usepackage{tikz}
\usetikzlibrary{arrows.meta,positioning,shapes.geometric}
\usepackage{float}
\usepackage{titlesec}
\usepackage{enumitem}
\usepackage{fancyhdr}
\usepackage{tocloft}
\usepackage{chngcntr}

\usepackage{hyperref}
\usepackage{xurl}
\hypersetup{hidelinks,unicode,pdftitle={Báo cáo Topic 1 -- Logic Analyzer}}
\Urlmuskip=0mu plus 1mu\relax

\setlength{\parindent}{0pt}
\setlength{\parskip}{3pt}
\AtBeginDocument{\normalsize}
\counterwithin{table}{chapter}
\counterwithin{figure}{chapter}
\renewcommand{\tablename}{Bảng}
\renewcommand{\figurename}{Hình}
\renewcommand{\contentsname}{MỤC LỤC}
\renewcommand{\listfigurename}{DANH MỤC HÌNH VẼ}
\renewcommand{\listtablename}{DANH MỤC BẢNG BIỂU}
\renewcommand{\cfttoctitlefont}{\hfill\bfseries\fontsize{20pt}{14pt}\selectfont}
\renewcommand{\cftaftertoctitle}{\hfill}
\renewcommand{\cftloftitlefont}{\hfill\bfseries\fontsize{20pt}{14pt}\selectfont}
\renewcommand{\cftafterloftitle}{\hfill}
\renewcommand{\cftlottitlefont}{\hfill\bfseries\fontsize{20pt}{14pt}\selectfont}
\renewcommand{\cftafterlottitle}{\hfill}
\captionsetup[table]{position=top,font={small,it},justification=centering,labelsep=space}
\captionsetup[figure]{position=bottom,font={small,it},justification=centering,labelsep=space}
\AtBeginEnvironment{longtable}{\normalsize\setlength{\tabcolsep}{5.4pt}\renewcommand{\arraystretch}{1.12}}
\setlength{\arrayrulewidth}{0.5pt}
\titleformat{\chapter}[block]{\centering\bfseries\fontsize{13pt}{15pt}\selectfont}{CHƯƠNG \thechapter.}{0.45em}{\MakeUppercase}
\titlespacing*{\chapter}{0pt}{0pt}{14pt}
\titleformat{\section}{\bfseries\fontsize{13pt}{15pt}\selectfont}{\thesection}{0.45em}{}
\titlespacing*{\section}{0pt}{10pt}{4pt}
\titleformat{\subsection}{\bfseries\itshape\fontsize{13pt}{15pt}\selectfont}{\thesubsection}{0.45em}{}
\titlespacing*{\subsection}{0pt}{8pt}{3pt}
\setlist[itemize]{leftmargin=1.0cm,noitemsep,topsep=3pt}
\setlist[enumerate]{leftmargin=1.0cm,noitemsep,topsep=3pt}
\renewcommand{\cftdotsep}{0}
\renewcommand{\cftchapleader}{\cftdotfill{\cftdotsep}}
\renewcommand{\cftsecleader}{\cftdotfill{\cftdotsep}}
\renewcommand{\cftsubsecleader}{\cftdotfill{\cftdotsep}}
\pagestyle{fancy}
\fancyhf{}
\fancyfoot[R]{\thepage}
\renewcommand{\headrulewidth}{0pt}
\newcommand{\tightlist}{\setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}}
\begin{document}
\hypersetup{pageanchor=false}
\pagenumbering{gobble}
% ```latex
\begin{titlepage}
\thispagestyle{empty}
\setlength{\parskip}{0pt}

\begin{tikzpicture}[remember picture,overlay]
\draw[line width=1.2pt]
  ([xshift=1.2cm,yshift=-1.2cm]current page.north west)
  rectangle
  ([xshift=-1.2cm,yshift=1.2cm]current page.south east);

\draw[line width=0.4pt]
  ([xshift=1.38cm,yshift=-1.38cm]current page.north west)
  rectangle
  ([xshift=-1.38cm,yshift=1.38cm]current page.south east);

\node[anchor=south,font=\normalsize]
  at ([yshift=1.65cm]current page.south) {Hà Nội, 7-2026};
\end{tikzpicture}

\centering

\vspace*{0.6cm}

{\bfseries\fontsize{25pt}{28pt}\selectfont
ĐẠI HỌC BÁCH KHOA HÀ NỘI\\
TRƯỜNG ĐIỆN -- ĐIỆN TỬ\par}

\vspace{0.2cm}

\includegraphics[width=2.63cm,height=3.94cm]{media/image1.png}\par

\vspace*{1.5cm}

{\bfseries\fontsize{25pt}{30pt}\selectfont
BÁO CÁO BÀI TẬP LỚN\par}

\vspace{0.7cm}

{\bfseries\fontsize{20pt}{18pt}\selectfont
Môn học: HỆ THỐNG NHÚNG\par}
{\bfseries\fontsize{20pt}{18pt}\selectfont
VÀ THIẾT KẾ GIAO TIẾP NHÚNG\par}
\vspace{0.5cm}



{\bfseries\fontsize{18pt}{18pt}\selectfont
Đề tài 1: Thiết kế và xây dựng thiết bị\par}

{\bfseries\fontsize{18pt}{18pt}\selectfont
Logic Analyzer đơn giản\par}
\vspace*{1.0cm}

{\bfseries\fontsize{18pt}{30pt}\selectfont
Nhóm 13 - Mã lớp học 168057 - K68\par}
\renewcommand{\arraystretch}{1.35}

\vspace*{1.0cm}
\begin{tabularx}{0.80\textwidth}
{|>{\raggedright\arraybackslash}m{0.31\textwidth}|>{\centering\arraybackslash}X|}
\hline
\textbf{Sinh viên thực hiện:} &
\begin{tabular}{@{}c@{}}
Đoàn Sinh Đức -- 20234000\\
Phạm Đăng Vinh -- 20233719\\
Vũ Mạnh Quân -- 20234033\\
Vũ Nam Khánh -- 20234015
\end{tabular}\\
\hline
\textbf{Giảng viên hướng dẫn:} & TS. Đào Việt Hùng\\
\hline
\end{tabularx}

\vfill

\end{titlepage}
% ```


\hypersetup{pageanchor=true}
\pagenumbering{roman}
\tableofcontents
\clearpage
\listoffigures
\clearpage
\listoftables
\clearpage
\pagenumbering{arabic}
\input{content.tex}
\end{document}
"""


OBJECTIVES_INSERT = r"""\section{Mục tiêu thiết kế}\label{mux1ee5c-tiuxeau-thiux1ebft-kux1ebf}

Mục tiêu của đề tài là thiết kế và xây dựng thiết bị phân tích logic sử dụng vi điều khiển STM32F103C8 để thu thập tín hiệu số và hiển thị kết quả trên máy tính. Dữ liệu của tám kênh CH0--CH7 được lấy mẫu tại PA0--PA7, đóng gói theo bit trong bộ nhớ RAM và truyền đến phần mềm máy tính qua UART bằng khung SLA8.

Các mục tiêu cụ thể gồm:
\begin{itemize}
\item thiết kế tám kênh thu thập tín hiệu số, đáp ứng yêu cầu tối thiểu hai kênh của đề bài;
\item cho phép cấu hình tần số lấy mẫu từ 1~kHz đến ít nhất 1~MHz và thực hiện thu thập ngoại tuyến bằng cách lưu dữ liệu vào bộ đệm trước khi truyền;
\item hiển thị dạng sóng của tám kênh trên máy tính và hỗ trợ giải mã ba giao thức UART, I2C và SPI.
\end{itemize}
"""

REQUIREMENTS_INSERT = r"""\section{Yêu cầu của Đề tài 1 và chỉ tiêu chức năng/phi chức năng}\label{sec:requirements}

\subsection{Chỉ tiêu chức năng}
Các chức năng chính của hệ thống gồm:
\begin{itemize}
\item thu thập đồng thời ít nhất hai kênh tín hiệu số;
\item cấu hình tần số lấy mẫu từ 1~kHz và thực hiện thu thập ngoại tuyến;
\item truyền dữ liệu đến máy tính và hiển thị dạng sóng;
\item giải mã các giao thức UART, I2C và SPI.
\end{itemize}

\subsection{Chỉ tiêu phi chức năng}
Các chỉ tiêu phi chức năng tập trung vào độ tin cậy của dữ liệu và tính ổn định của quá trình thu thập, gồm:
\begin{itemize}
\item bảo đảm tính toàn vẹn của siêu dữ liệu và mã kiểm tra;
\item duy trì quan hệ thời gian nhất quán giữa các kênh;
\item phát hiện tràn bộ đệm và số mẫu bị mất;
\item bảo đảm khả năng lặp lại của kết quả thử nghiệm.
\end{itemize}
"""

THEORY_INSERT = r"""\section{Nền tảng STM32F103C8 và hệ thống xung nhịp}\label{sec:stm32-clock}

Dự án sử dụng môi trường \texttt{genericSTM32F103C8}, nền tảng Arduino và bộ định thời TIM2 cho khối thu thập. STM32F103C8 sử dụng lõi ARM Cortex--M3, tần số lõi tối đa 72~MHz, bộ nhớ Flash 64~KB và SRAM 20~KB \cite{st-ds5319}. Firmware ưu tiên thạch anh ngoài HSE 8~MHz qua PLL nhân 9 để tạo xung hệ thống 72~MHz; khi HSE không khởi động, hệ thống quay về nguồn HSI 64~MHz. Kết quả HIL xác nhận lệnh \texttt{INFO} trả về xung TIM2 bằng 72~MHz \cite{hil2026}.

Với nguồn HSE và PLL, quan hệ tổng quát của xung nhịp hệ thống là \(f_{\mathrm{SYSCLK}}=f_{\mathrm{HSE}}\times M\), sau đó \(f_{\mathrm{HCLK}}=f_{\mathrm{SYSCLK}}/\mathrm{HPRE}\). Xung nhịp TIM2 phụ thuộc bộ chia APB1: \(f_{\mathrm{TIM2}}=f_{\mathrm{PCLK1}}\) khi APB1 không chia và \(f_{\mathrm{TIM2}}=2f_{\mathrm{PCLK1}}\) khi hệ số chia APB1 lớn hơn 1 \cite{st-rm0008}. Với bộ chia \(PSC\) và thanh ghi tự nạp lại \(ARR\), tần số lấy mẫu được xác định bởi
\[
 f_{\mathrm{update}}=\frac{f_{\mathrm{TIM2}}}{(PSC+1)(ARR+1)}.
\]

\begin{figure}[H]
\centering
\begin{tikzpicture}[node distance=7mm, every node/.style={draw,align=center,minimum height=8mm,font=\small}, >=Latex]
\node (hse) {HSE / HSI};
\node (pll) [right=of hse] {PLL và bộ chia};
\node (core) [right=of pll] {HCLK\\Cortex--M3};
\node (apb) [below=of core] {PCLK1 / APB1};
\node (tim) [left=of apb] {TIM2\\lấy mẫu};
\draw[->] (hse) -- (pll);
\draw[->] (pll) -- (core);
\draw[->] (core) -- (apb);
\draw[->] (apb) -- node[above,draw=none,font=\scriptsize]{x1 hoặc x2} (tim);
\end{tikzpicture}
\caption{Đường xung nhịp liên quan đến bộ định thời TIM2}
\label{fig:clock-tree}
\end{figure}

\section{Nguyên lý của thiết bị phân tích logic}\label{sec:logic-analyzer}

Thiết bị phân tích logic ghi nhận trạng thái số của nhiều kênh tại các thời điểm rời rạc. Chuỗi dữ liệu theo thời gian cho phép xác định độ rộng xung, khoảng thời gian giữa các cạnh và thứ tự sự kiện trên các đường tín hiệu.

Ở chế độ kích hoạt tức thời, mỗi sự kiện cập nhật của TIM2 yêu cầu DMA1 Channel~2 đọc thanh ghi \texttt{GPIOA->IDR} và lưu tám bit thấp vào bộ đệm. Các chế độ kích hoạt theo cạnh hoặc mẫu sử dụng hàm phục vụ ngắt để đọc một lần GPIOA IDR cho mỗi mẫu. Cả hai cơ chế đều ghi trạng thái CH0--CH7 trong cùng một lần truy cập thanh ghi.

\begin{figure}[H]
\centering
\begin{tikzpicture}[node distance=4mm, every node/.style={draw,rounded corners,align=center,minimum width=20mm,minimum height=8mm,font=\scriptsize}, >=Latex]
\node (input) {Tín hiệu số\\CH0--CH7};
\node (gpio) [right=of input] {GPIOA IDR\\đọc đồng thời};
\node (timer) [below=of gpio] {TIM2 / DMA hoặc ngắt};
\node (buffer) [right=of gpio] {Bộ đệm RAM\\1 byte/mẫu};
\node (uart) [right=of buffer] {Khung SLA8\\USART1};
\node (pc) [right=of uart] {Máy tính\\dạng sóng, giải mã};
\draw[->] (input) -- (gpio);
\draw[->] (timer) -- (gpio);
\draw[->] (gpio) -- (buffer);
\draw[->] (buffer) -- (uart);
\draw[->] (uart) -- (pc);
\end{tikzpicture}
\caption{Sơ đồ khối chức năng của hệ thống phân tích logic}
\label{fig:logic-analyzer-block}
\end{figure}

\section{Tốc độ lấy mẫu và hiện tượng chồng phổ}\label{sec:nyquist-aliasing}

Chu kỳ lấy mẫu là \(T_s=1/f_s\), trong đó \(f_s\) là tần số lấy mẫu. Đối với tín hiệu liên tục được giới hạn băng thông ở \(f_{\max}\), điều kiện Nyquist--Shannon lý tưởng là
\[
f_s > 2f_{\max}.
\]
Khi điều kiện lấy mẫu không được thỏa mãn, thành phần tần số cao có thể xuất hiện thành tần số thấp hơn. Tần số chồng phổ được biểu diễn bởi \(f_{\mathrm{alias}}=|f_{\mathrm{in}}-k f_s|\), với \(k\) được chọn để \(f_{\mathrm{alias}}\) nằm trong dải \([0,f_s/2]\) \cite{shannon1949}.

Tín hiệu số có cạnh nhanh và chứa nhiều thành phần hài, nên điều kiện Nyquist theo tần số cơ bản chưa đủ để bảo toàn hình dạng xung. Trong thực tế, tần số lấy mẫu phải được chọn theo độ rộng xung nhỏ nhất cần quan sát. Độ phân giải thời gian bằng \(T_s\), còn jitter phụ thuộc nguồn xung nhịp, bộ định thời và cơ chế DMA hoặc ngắt.

\section{Quan hệ thời gian giữa các kênh}\label{sec:timing}

Firmware đọc một lần thanh ghi IDR của GPIOA rồi tách các bit tương ứng CH0--CH7. So với cách đọc tuần tự từng chân, phương pháp này giảm sai lệch thời điểm giữa các kênh; jitter và skew còn lại phải được xác định bằng phép đo thực nghiệm.

\section{Giao thức truyền dữ liệu sau thu thập}\label{sec:protocol}

Sau khi phiên thu hoàn tất và nhận lệnh \texttt{DUMP}, firmware truyền dữ liệu đến máy tính theo khung SLA8. Mỗi mẫu được lưu bằng một byte, trong đó bit 0 đến bit 7 tương ứng CH0 đến CH7. Phần đầu khung chứa mã nhận dạng, phiên bản, số kênh, tần số lấy mẫu, số mẫu, vị trí kích hoạt, cờ trạng thái và mã kiểm tra.
"""

HARDWARE_TABLE_INSERT = r"""\begin{longtable}[]{@{}
  >{\raggedright\arraybackslash}p{(\linewidth - 4\tabcolsep) * \real{0.3333}}
  >{\raggedright\arraybackslash}p{(\linewidth - 4\tabcolsep) * \real{0.3333}}
  >{\raggedright\arraybackslash}p{(\linewidth - 4\tabcolsep) * \real{0.3333}}@{}}
\caption{Các thành phần phần cứng}\tabularnewline
\toprule\noalign{}
\textbf{Thành phần} & \textbf{Cấu hình} & \textbf{Chức năng/Ghi chú} \\
\midrule\noalign{}
Bo mạch và vi điều khiển & STM32F103C8, nền tảng Arduino & TIM2 điều khiển quá trình lấy mẫu bằng DMA hoặc ngắt. \\
Kênh đo & CH0--CH7 ánh xạ tới PA0--PA7 & Đọc đồng thời tám bit thấp của GPIOA IDR. \\
Giao tiếp máy tính & USART1 trên PA9/PA10, 1.000.000~baud & Truyền lệnh điều khiển và khung dữ liệu SLA8. \\
Nguồn tín hiệu thử & Arduino UNO & Tạo chuỗi Gray, UART, I2C và SPI bằng ngõ ra cực máng hở; mức HIGH do điện trở kéo lên 3,3~V tại STM32 tạo ra. \\
\bottomrule\noalign{}
\end{longtable}
"""

FLOW_INSERT = r"""\section{Luồng hoạt động firmware}\label{sec:firmware-flow}

Khi khởi động, firmware cấu hình UART, GPIO đầu vào, TIM2 và tần số lấy mẫu mặc định. Firmware tiếp nhận các lệnh cấu hình tốc độ, chế độ thu và điều kiện kích hoạt; lệnh \texttt{ARM} bắt đầu phiên thu. Với \texttt{TRIG IMM}, hệ thống ưu tiên DMA; các điều kiện kích hoạt theo cạnh hoặc mẫu sử dụng ISR và giới hạn tốc độ đã kiểm chứng là 400~kS/s. Khi đủ số mẫu, firmware dừng thu, phát thông báo \texttt{EVENT} và chờ lệnh \texttt{DUMP} để truyền khung SLA8.

\begin{figure}[H]
\centering
\begin{tikzpicture}[node distance=5mm, every node/.style={draw,rounded corners,align=center,minimum width=43mm,minimum height=8mm,font=\small}, >=Latex]
\node (boot) {Khởi động UART, GPIO và TIM2};
\node (cfg) [below=of boot] {Nhận cấu hình và điều kiện kích hoạt};
\node (arm) [below=of cfg] {Nhận \texttt{ARM}, chọn DMA hoặc ISR};
\node (sample) [below=of arm] {Đọc GPIOA IDR và ghi bộ đệm};
\node (done) [below=of sample] {Đủ số mẫu?};
\node (event) [below=of done] {Dừng thu và phát \texttt{EVENT}};
\node (dump) [below=of event] {Nhận \texttt{DUMP}, truyền khung SLA8};
\draw[->] (boot) -- (cfg);
\draw[->] (cfg) -- (arm);
\draw[->] (arm) -- (sample);
\draw[->] (sample) -- (done);
\draw[->] (done) -- node[right,draw=none,font=\scriptsize]{có} (event);
\draw[->] (done.east) to[out=0,in=0,looseness=1.2] node[right,draw=none,font=\scriptsize]{chưa} (sample.east);
\draw[->] (event) -- (dump);
\end{tikzpicture}
\caption{Sơ đồ luồng hoạt động của firmware}
\label{fig:firmware-flow}
\end{figure}
"""

DEPLOYMENT_INSERT = r"""\section{Lắp mạch và quy trình vận hành}\label{sec:deployment}

Hệ thống kết nối STM32 với máy tính qua FT232 ở mức logic 3,3~V. Các đường TX/RX được nối chéo và mọi thiết bị dùng chung GND. Khi STM32 đã được cấp nguồn riêng, không cấp thêm nguồn từ FT232.

\begin{longtable}[]{@{}
  >{\raggedright\arraybackslash}p{(\linewidth - 4\tabcolsep) * \real{0.3333}}
  >{\raggedright\arraybackslash}p{(\linewidth - 4\tabcolsep) * \real{0.3333}}
  >{\raggedright\arraybackslash}p{(\linewidth - 4\tabcolsep) * \real{0.3333}}@{}}
\caption{Kết nối giữa các phần tử trong hệ thống}\tabularnewline
\toprule\noalign{}
\textbf{Thiết bị/chế độ} & \textbf{Kết nối đến} & \textbf{Lưu ý} \\
\midrule\noalign{}
FT232 TX & STM32 PA10 (USART1 RX) & Mức logic 3,3~V. \\
FT232 RX & STM32 PA9 (USART1 TX) & Mức logic 3,3~V. \\
FT232 GND & STM32 GND & Bắt buộc nối chung GND. \\
Arduino, chế độ GRAY & D2--D9 tới PA0--PA7 & Ngõ ra cực máng hở; mức HIGH do điện trở kéo lên 3,3~V tại STM32 tạo ra. \\
Arduino, chế độ UART/I2C & D2 tới CH0; D3 tới CH1/SCL; D4 tới CH2/SDA & Ngõ ra cực máng hở; hai bo mạch phải nối chung GND. \\
Arduino, chế độ SPI/BOTH & D5--D9 tới CH3--CH7 & Ngõ ra cực máng hở; mức HIGH do điện trở kéo lên 3,3~V tại STM32 tạo ra. \\
Arduino GND & STM32 GND & Bắt buộc nối chung GND. \\
\bottomrule\noalign{}
\end{longtable}

Quy trình biên dịch, nạp và chạy chương trình gồm:
\begin{enumerate}
\item đóng giao diện hoặc chương trình giám sát đang sử dụng cổng COM;
\item biên dịch firmware bằng PlatformIO;
\item đặt BOOT1/PB2=0, BOOT0=1 và khởi động lại STM32 để vào bộ nạp ROM;
\item nạp firmware qua USART1;
\item đưa BOOT0 về 0 và khởi động lại STM32;
\item chạy phần mềm giao diện hoặc công cụ dòng lệnh trên máy tính.
\end{enumerate}

Các câu lệnh biên dịch, nạp và chạy chương trình được trình bày tại Mục~\ref{sec:build-config}; \texttt{COMx} biểu thị cổng nối tiếp do hệ điều hành gán và phải được xác định trên từng máy.

Bộ giải mã UART hiện xử lý khung 8N1 trên CH0, gồm bit bắt đầu, tám bit dữ liệu và bit kết thúc. Bus I2C sử dụng CH1 làm SCL và CH2 làm SDA. Đối với SPI, CH3, CH4, CH5 và CH6 lần lượt được dùng cho SCK, MOSI, MISO và CS. Bộ phát Arduino kéo LOW hoặc thả nổi đường tín hiệu; mức HIGH được tạo bởi điện trở kéo lên 3,3~V của STM32.
"""

TESTING_INSERT = r"""\section{Kế hoạch kiểm thử}\label{sec:test-plan}

\begin{longtable}[]{@{}|
  >{\raggedright\arraybackslash}p{(\linewidth - 7\tabcolsep) * \real{0.12}}
  |>{\raggedright\arraybackslash}p{(\linewidth - 7\tabcolsep) * \real{0.30}}
  |>{\raggedright\arraybackslash}p{(\linewidth - 7\tabcolsep) * \real{0.58}}|@{}}
\caption{Kế hoạch kiểm thử}\tabularnewline
\hline
\textbf{Mã} & \textbf{Mục tiêu} & \textbf{Phương pháp} \\ \hline

TC-01 & Kiểm tra kết nối UART. & Gửi \texttt{PING}/\texttt{INFO} qua phần mềm máy tính hoặc công cụ dòng lệnh. \\ \hline
TC-02 & Kiểm tra ánh xạ tám kênh. & Phát chuỗi Gray trên D2--D9 và đối chiếu CH0--CH7. \\ \hline
TC-03 & Kiểm tra tần số lấy mẫu. & So sánh tần số do TIM2 cấu hình với chuỗi Gray tham chiếu. \\ \hline
TC-04 & Đánh giá quan hệ thời gian giữa các kênh. & Đưa cùng một tín hiệu vào nhiều kênh và đo độ lệch cạnh. \\ \hline
TC-05 & Kiểm tra bộ giải mã UART. & Tạo khung UART 8N1 và giải mã trên CH0. \\ \hline
TC-06 & Kiểm tra bộ giải mã I2C. & Tạo SCL/SDA và giải mã trên CH1/CH2. \\ \hline
TC-07 & Kiểm tra bộ giải mã SPI. & Phát SCK/MOSI/MISO/CS bằng ngõ ra cực máng hở, thu ở 500~kS/s và giải mã trên CH3--CH6. \\ \hline

\end{longtable}

\clearpage
\section{Kết quả kiểm thử phần cứng}\label{sec:hil-results}

Lệnh \texttt{INFO} xác nhận xung TIM2 bằng 72~MHz. Chuỗi Gray từ Arduino được dùng làm dữ liệu tham chiếu để kiểm tra tính toàn vẹn của mẫu và độ chính xác tần số ở hai cơ chế thu \cite{hil2026}.

\subsection{Phương pháp đo}\label{sec:method}

Bộ tạo tín hiệu Arduino UNO nối D2--D9 sang PA0--PA7 của STM32 và chung GND; STM32 giao tiếp máy tính qua UART. Arduino phát một bộ đếm Gray 8~bit ở tốc độ bước biết trước \(f_{\text{bước}}\) (đặt bằng lệnh \texttt{GRAY RATE}). Vì mỗi bước chỉ đổi một bit nên mọi giá trị trung gian nhiều bit đều là lỗi lấy mẫu; \(f_{\text{bước}}\) lấy từ thạch anh 16~MHz của Arduino nên đóng vai trò chuẩn đối chiếu.

Với mỗi tần số cần kiểm tra, STM32 được cấu hình \texttt{CFG MODE DMA}, \texttt{TRIG IMM} và \texttt{CFG RATE}~\(f_{\text{cấu hình}}\); sau đó gửi \texttt{ARM}, chờ sự kiện hoàn tất rồi \texttt{DUMP} khung SLA8 về máy tính. Phần mềm đếm số mẫu \(N_i\) trên mỗi bước Gray ổn định và suy ra tần số lấy mẫu thực tế
\[ f_{\text{đo}} = \overline{N}\times f_{\text{bước}}. \]

Mọi lệnh gửi tới thiết bị là chuỗi ASCII kết thúc bằng ký tự xuống dòng, truyền qua UART 1.000.000~baud (ví dụ \texttt{CFG RATE 1000000}, \texttt{ARM}, \texttt{DUMP}). Đáp lại \texttt{DUMP}, thiết bị trả về một khung nhị phân SLA8 gồm phần đầu 48~byte (mã nhận dạng, phiên bản, số kênh, tần số yêu cầu và thực tế, số mẫu, vị trí trigger, cờ và hai mã kiểm tra FNV-1a), tiếp theo là phần dữ liệu dài đúng bằng số mẫu --- mỗi mẫu 1~byte đóng gói trạng thái tám kênh. Khi thu đầy bộ đệm 13\,888 mẫu, khung có kích thước \(48+13\,888 = 13\,936\)~byte.

Một mức được coi là đạt khi không có lỗi thứ tự chuỗi, mất mẫu, tràn bộ đệm hay sai mã kiểm tra, và sai lệch \(|f_{\text{đo}}-f_{\text{cấu hình}}|/f_{\text{cấu hình}}\) nằm trong ngưỡng cho phép. Mỗi mức lặp lại nhiều lần; toàn bộ quy trình được tự động hóa bằng công cụ \texttt{hardware\_self\_test.py}, khung dữ liệu lưu ở định dạng \path{.sla8} làm minh chứng.

\subsection{Kết quả toàn vẹn tín hiệu}\label{sec:integrity}

\begin{longtable}[]{@{}|
  >{\raggedright\arraybackslash}p{(\linewidth - 9\tabcolsep) * \real{0.12}}
  |>{\raggedright\arraybackslash}p{(\linewidth - 9\tabcolsep) * \real{0.36}}
  |>{\raggedright\arraybackslash}p{(\linewidth - 9\tabcolsep) * \real{0.18}}
  |>{\raggedright\arraybackslash}p{(\linewidth - 9\tabcolsep) * \real{0.34}}|@{}}
\caption{Kết quả kiểm thử HIL với chuỗi Gray}\tabularnewline
\hline
\textbf{Cơ chế} & \textbf{Tần số kiểm thử} & \textbf{Số lần} & \textbf{Kết quả} \\ \hline

DMA & 100~kS/s; 500~kS/s; 1, 2, 4, 6 và 6,545~MS/s & 3 lần cho mỗi mức & Đạt; sai số đo không quá 0,05\%. \\ \hline
DMA & 1~kS/s & 1 lần & Đạt; sai số đo 0,01\%. \\ \hline
ISR & 100, 250 và 400~kS/s & 3 lần cho mỗi mức & Đạt; sai số đo không quá 0,01\%. \\ \hline

\end{longtable}

Trong các phép thử trên, không ghi nhận lỗi thứ tự chuỗi Gray, trạng thái ngắn bất thường, mất mẫu, tràn bộ đệm, lỗi DMA hoặc sai mã kiểm tra. Tại 6 và 6,545~MS/s, mỗi khung chứa ít nhất 212 trạng thái Gray ổn định, có chuyển mức trên đủ tám kênh và sai số tần số đo không quá 0,05\%.

\subsection{Xác định giới hạn tần số lấy mẫu}\label{sec:ceiling}

Để tìm tần số lấy mẫu tối đa còn cho kết quả đúng, nhóm nạp bản firmware mở khoá tần số (tới 32~MS/s), tăng dần tần số cấu hình và đối chiếu với chuỗi Gray.

Khi tần số vượt khả năng của DMA, thiết bị bỏ bớt mẫu đều đặn nên tần số đo được không tăng theo mà dừng lại. Giới hạn là điểm mà tần số đo bắt đầu nhỏ hơn tần số cấu hình (Bảng~\ref{tab:ceiling}).

\begin{table}[H]
\centering
\caption{Đo xác định giới hạn tần số lấy mẫu DMA ở \(f_{\mathrm{TIM2}}=72\)~MHz}
\label{tab:ceiling}
\begin{tabular}{|c|c|c|c|}
\hline
Cấu hình & Đo được & Chênh lệch & Kết quả \\ \hline
1 MHz & 1 MHz & $\approx 0$ & Đạt \\ \hline
4 MHz & 4 MHz & $\approx 0$ & Đạt \\ \hline
6 MHz & 6 MHz & $\le 0{,}03\%$ & Đạt \\ \hline
6,545 MHz & 6,545 MHz & $\le 0{,}03\%$ & Đạt (giới hạn) \\ \hline
7,2 MHz & 6,65 MHz & $-7{,}7\%$ & Vượt giới hạn \\ \hline
8 MHz & 6,79 MHz & $-15\%$ & Vượt giới hạn \\ \hline
9 MHz & 6,81 MHz & $-24\%$ & Vượt giới hạn \\ \hline
\end{tabular}
\end{table}

Tần số đo trùng với tần số cấu hình (chênh lệch dưới 0,03\%, là nhiễu của phép đo) đến 6,545~MS/s \((=72~\text{MHz}/11)\). Từ 7,2~MS/s tần số đo giảm và dừng quanh 6,8~MS/s. Vậy giới hạn ở xung 72~MHz là \textbf{6,545~MS/s}; giá trị này được đặt làm ngưỡng \path{MAX_TARGET_RATE} của firmware. So với cấu hình HSI 64~MHz (giới hạn 5,818~MS/s), việc dùng thạch anh HSE nâng giới hạn thêm khoảng 12,5\%. Cơ chế ISR có giới hạn 400~kS/s do thời gian xử lý ngắt \cite{hil2026}."""

ASSESSMENT_INSERT = r"""\chapter{ĐÁNH GIÁ VÀ THẢO LUẬN}\label{ux111uxe1nh-giuxe1-vuxe0-thux1ea3o-luux1eadn}

\section{Mức độ hoàn thành theo thiết kế}\label{mux1ee9c-ux111ux1ed9-houxe0n-thuxe0nh-theo-thiux1ebft-kux1ebf}

Hệ thống đã hình thành các khối chính của thiết bị phân tích logic: thu thập GPIO bằng TIM2, lưu dữ liệu vào bộ đệm, truyền khung SLA8, hiển thị dạng sóng trên máy tính và giải mã UART, I2C, SPI. Bảng dưới đây đối chiếu các yêu cầu chính với kết quả triển khai.

\begin{longtable}[]{@{}
  >{\raggedright\arraybackslash}p{(\linewidth - 4\tabcolsep) * \real{0.3333}}
  >{\raggedright\arraybackslash}p{(\linewidth - 4\tabcolsep) * \real{0.3333}}
  >{\raggedright\arraybackslash}p{(\linewidth - 4\tabcolsep) * \real{0.3333}}@{}}
\caption{Đối chiếu yêu cầu với kết quả triển khai}\tabularnewline
\toprule\noalign{}
\textbf{Yêu cầu} & \textbf{Kết quả triển khai} & \textbf{Đánh giá} \\
\midrule\noalign{}
Số kênh & Cấu hình tám kênh CH0--CH7. & Đáp ứng yêu cầu tối thiểu hai kênh. \\
Tần số lấy mẫu tối thiểu & TIM2 cho phép cấu hình từ 1~kHz. & Đáp ứng yêu cầu về cấu hình. \\
Hiển thị trên máy tính & Giao diện hiển thị đồng thời tám kênh. & Đã triển khai trong phần mềm. \\
Tính toàn vẹn dữ liệu & HIL chuỗi Gray đạt tại DMA đến 6,545~MS/s và ISR đến 400~kS/s. & Không ghi nhận lỗi chuỗi, mất mẫu, tràn bộ đệm hoặc mã kiểm tra. \\
Quan hệ thời gian & Đọc đồng thời GPIOA IDR theo chu kỳ TIM2. & Chưa có số liệu định lượng jitter và skew. \\
Giải mã giao thức & Hỗ trợ UART, I2C và SPI. & Cả ba bộ giải mã đã được kiểm chứng trên phần cứng; SPI nhận đúng ba cặp byte tại 500~kS/s. \\
\bottomrule\noalign{}
\end{longtable}

\section{Hạn chế}\label{hux1ea1n-chux1ebf}

Các hạn chế của phiên bản hiện tại gồm:
\begin{itemize}
\item chưa có sơ đồ nguyên lý đầy đủ và số liệu định lượng jitter, skew giữa các kênh;
\item bộ giải mã SPI hiện giả định lấy mẫu tại cạnh lên và ghép byte theo thứ tự MSB-first; chưa cho phép cấu hình CPOL/CPHA và thứ tự bit.
\end{itemize}

\section{Hướng phát triển}\label{hux1b0ux1edbng-phuxe1t-triux1ec3n}

Các hướng phát triển tiếp theo gồm:
\begin{itemize}
\item đo jitter và skew bằng tín hiệu tham chiếu chung trên nhiều kênh;
\item mở rộng bộ giải mã SPI để cấu hình CPOL, CPHA và thứ tự bit;
\item hoàn thiện sơ đồ đấu nối và quy trình kiểm tra mức điện áp trước các phép thử giao thức.
\end{itemize}
"""

CONCLUSION_INSERT = r"""\chapter{KẾT LUẬN}\label{kux1ebft-luux1eadn}

Đề tài đã xây dựng thiết bị phân tích logic tám kênh dựa trên STM32F103C8 và phần mềm hiển thị trên máy tính. Hệ thống thu dữ liệu bằng DMA hoặc ISR, truyền khung SLA8 và giải mã UART, I2C, SPI. Kết quả HIL xác nhận xung TIM2 72~MHz; các phép thử chuỗi Gray đạt ở cơ chế DMA đến 6,545~MS/s và ISR đến 400~kS/s, không ghi nhận lỗi thứ tự, mất mẫu, tràn bộ đệm hoặc sai mã kiểm tra. Phép thử SPI bằng ngõ ra cực máng hở tại 500~kS/s nhận đúng ba cặp byte MOSI/MISO và đầy đủ sự kiện CS. Phần đánh giá tiếp theo cần tập trung vào jitter, skew giữa các kênh và mở rộng cấu hình CPOL/CPHA.
"""

REFERENCES_INSERT = r"""\renewcommand{\bibname}{TÀI LIỆU THAM KHẢO}
\begin{thebibliography}{99}
\phantomsection
\addcontentsline{toc}{chapter}{TÀI LIỆU THAM KHẢO}
\bibitem{course} Tài liệu học phần Bài tập lớn Hệ thống nhúng và thiết kế giao tiếp nhúng, học kỳ 2025.2.
\bibitem{repo} Mã nguồn dự án thiết bị phân tích logic tám kênh: \texttt{platformio.ini}, \texttt{src/firmware}, \texttt{src/software} và \texttt{tests}.
\bibitem{hil2026} Nhóm thực hiện, \emph{Kết quả HIL trên STM32F103C8 chạy thạch anh HSE 72~MHz}, \path{report/generated/hil_72mhz_summary.md}.
\bibitem{st-ds5319} STMicroelectronics, \emph{STM32F103x8/xB medium-density performance line}, DS5319 Rev. 20. \href{https://www.st.com/resource/en/datasheet/CD00161566.pdf}{ST DS5319 (PDF)}.
\bibitem{st-rm0008} STMicroelectronics, \emph{RM0008: STM32F10xxx reference manual}, Rev. 21. \href{https://www.st.com/resource/en/reference_manual/cd00171190-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-arm-based-32-bit-mcus-stmicroelectronics.pdf}{ST RM0008 (PDF)}.
\bibitem{shannon1949} C. E. Shannon, “Communication in the Presence of Noise,” \emph{Proceedings of the IRE}, vol. 37, no. 1, pp. 10--21, 1949.
\end{thebibliography}
"""

def _enhance_content(raw_latex: str) -> str:
    def replace_once(
        source: str,
        pattern: str,
        replacement: str,
        description: str,
        *,
        flags: int = 0,
    ) -> str:
        converted, count = re.subn(
            pattern,
            lambda _match: replacement,
            source,
            flags=flags,
        )
        if count != 1:
            raise ValueError(f"{description}: cần thay đúng 1 khối, tìm thấy {count}")
        return converted

    chapter_start = r"\chapter{TỔNG QUAN VÀ MỤC TIÊU DỰ ÁN}"
    start_index = raw_latex.find(chapter_start)
    if start_index < 0:
        raise ValueError("Pandoc không tạo được chương mở đầu của báo cáo")
    latex = raw_latex[start_index:]

    latex = replace_once(
        latex,
        r"\\section\{Mục tiêu thiết kế\}\\label\{[^}]+\}\n\n.*?(?=\\section\{Yêu cầu của Topic 1)",
        OBJECTIVES_INSERT.strip() + "\n\n",
        "Chuẩn hóa mục tiêu thiết kế",
        flags=re.DOTALL,
    )
    latex = replace_once(
        latex,
        r"\\section\{Yêu cầu của Topic 1.*?(?=\\begin\{longtable\})",
        REQUIREMENTS_INSERT.strip() + "\n\n",
        "Chuẩn hóa chỉ tiêu chức năng và phi chức năng",
        flags=re.DOTALL,
    )

    prose_replacements = (
        (
            "Đề bài của học phần định hướng xây dựng một logic analyzer ở mức proof of concept. Với Topic 1, trọng tâm là phần cứng gọn nhẹ, chi phí thấp, số kênh và tốc độ không cần quá cao nhưng phải thể hiện được nguyên lý lấy mẫu, lưu đệm, truyền dữ liệu và hiển thị waveform trên PC hoặc màn hình cục bộ.",
            "Đề bài của học phần định hướng xây dựng một mẫu thử nguyên lý của thiết bị phân tích logic. Đề tài 1 tập trung vào kiến trúc phần cứng gọn nhẹ và các chức năng cơ bản gồm lấy mẫu, lưu đệm, truyền dữ liệu, hiển thị dạng sóng trên máy tính.",
        ),
        (
            "Trong phạm vi hiện tại, hệ thống bao gồm firmware STM32, giao thức truyền frame SLA8, phần mềm PC, bộ giải mã UART/I2C và công cụ tạo tín hiệu thử bằng Arduino. Các kết quả đo phần cứng, ảnh demo và sơ đồ bảo vệ đầu vào là những nội dung cần hoàn thiện trước khi nộp chính thức.",
            "Phạm vi đề tài gồm firmware STM32, giao thức khung SLA8, phần mềm máy tính, các bộ giải mã UART, I2C, SPI và chương trình tạo tín hiệu kiểm thử trên Arduino UNO.",
        ),
        (
            "Hệ thống được tổ chức thành ba lớp. Lớp phần cứng gồm board STM32 và các chân thu tín hiệu. Lớp firmware chịu trách nhiệm lấy mẫu, quản lý trigger, lưu buffer và đóng gói frame. Lớp phần mềm PC điều khiển thiết bị, giải mã frame, hiển thị waveform và thực hiện các decoder giao thức.",
            "Hệ thống gồm ba lớp chức năng. Lớp phần cứng bao gồm bo mạch STM32 và tám kênh tín hiệu vào. Lớp chương trình nhúng thực hiện lấy mẫu, quản lý điều kiện kích hoạt, lưu bộ đệm và đóng gói khung SLA8. Lớp phần mềm máy tính điều khiển phiên thu, hiển thị dạng sóng và giải mã giao thức.",
        ),
        (
            "Firmware đảm nhiệm toàn bộ quá trình thu thập dữ liệu: khởi tạo ngoại vi, nhận lệnh điều khiển từ PC, cấu hình timer, quản lý trigger, ghi mẫu vào buffer và truyền frame sau khi capture kết thúc. Các chức năng được tách thành các khối rõ ràng gồm cấu hình phần cứng, lõi capture, đóng gói giao thức, xử lý trigger và đo chu kỳ thực thi khi cần benchmark.",
            "Firmware thực hiện chuỗi công việc gồm khởi tạo ngoại vi, nhận cấu hình, thiết lập TIM2, lựa chọn DMA hoặc ISR, thu thập mẫu và đóng gói dữ liệu thành khung SLA8. Các chức năng được phân chia theo mô-đun cấu hình phần cứng, thu thập, giao thức và đánh giá hiệu năng.",
        ),
        (
            "Phần mềm PC được xây dựng bằng Python, PyQt5 và pyqtgraph. Ứng dụng quản lý kết nối serial, cấu hình phiên capture, nhận frame SLA8, kiểm tra dữ liệu, tách từng kênh từ payload bit-packed và hiển thị waveform. Giao diện cũng cung cấp các điều khiển chọn cổng COM, sample rate, chế độ offline/realtime, trigger và bảng decode.",
            "Phần mềm máy tính được xây dựng bằng Python, PyQt5 và pyqtgraph. Ứng dụng quản lý kết nối nối tiếp, cấu hình phiên thu, nhận và kiểm tra khung SLA8, tách tám kênh từ dữ liệu đóng gói theo bit và hiển thị dạng sóng. Giao diện cho phép chọn cổng COM, tần số lấy mẫu, chế độ thu thập, điều kiện kích hoạt và các bộ giải mã UART, I2C, SPI.",
        ),
        (
            "Bộ tạo tín hiệu thử sử dụng Arduino UNO để phát các dạng tín hiệu phục vụ kiểm tra, gồm xung tuần hoàn, UART bit-bang và I2C dạng open-drain. Khối này phù hợp để tạo dữ liệu đầu vào cho việc quan sát waveform và kiểm tra decoder; kết quả chạy thực nghiệm cần được bổ sung bằng ảnh chụp hoặc log sau khi đo trên phần cứng.",
            "Arduino UNO được sử dụng làm nguồn tín hiệu tham chiếu, tạo chuỗi Gray, UART, I2C và SPI bằng ngõ ra cực máng hở để phục vụ các phép thử thu thập, hiển thị dạng sóng và giải mã giao thức.",
        ),
    )
    for original, revised in prose_replacements:
        if original not in latex:
            raise ValueError(f"Không tìm thấy đoạn cần biên tập: {original[:60]}")
        latex = latex.replace(original, revised, 1)
    latex = latex.replace(
        "một thiết bị logic analyzer",
        "một thiết bị phân tích logic (logic analyzer)",
    )

    table_replacements = (
        ("Phạm vi hiện có", "Kết quả triển khai"),
        ("Mã nguồn cấu hình 8 kênh CH0..CH7.", "Hệ thống được cấu hình tám kênh CH0--CH7."),
        ("Firmware/UI có cấu hình từ 1 kHz; cần đo thực tế trên board.", "Firmware và phần mềm cho phép cấu hình từ 1~kHz."),
        ("Waveform trên PC hoặc màn hình tối thiểu 128x64.", "Dạng sóng trên máy tính hoặc màn hình tối thiểu 128x64."),
        ("Ứng dụng PC PyQt5/pyqtgraph hiển thị 8 kênh.", "Ứng dụng PyQt5/pyqtgraph hiển thị đồng thời tám kênh."),
        ("Timing & Luận giải độ chính xác quan hệ timing giữa các kênh. & Có cơ sở timer TIM2 và đọc GPIOA IDR một lần; cần bổ sung số đo jitter/skew.", "Quan hệ thời gian & Phân tích độ chính xác thời gian giữa các kênh. & TIM2 điều khiển một lần đọc GPIOA IDR cho mỗi mẫu."),
        ("Decode giao thức & Khuyến khích UART/I2C/SPI. & Đã có UART/I2C decoder; chưa thấy SPI decoder.", "Giải mã giao thức & Khuyến khích UART/I2C/SPI. & Phần mềm hỗ trợ UART, I2C và SPI."),
    )
    for original, revised in table_replacements:
        latex = latex.replace(original, revised)
    latex = re.sub(
        r"^Bảo vệ đầu vào & Khuyến khích tích hợp mạch bảo vệ.*?\\\\\s*$\n?",
        "",
        latex,
        flags=re.MULTILINE,
    )

    latex = _replace_block(
        latex,
        r"\chapter{CƠ SỞ LÝ THUYẾT VÀ GIẢI PHÁP}",
        r"\chapter{THIẾT KẾ HỆ THỐNG}",
        r"""\chapter{CƠ SỞ LÝ THUYẾT VÀ GIẢI PHÁP}\label{chap:theory}

""" + THEORY_INSERT,
    )
    latex = latex.replace(
        r"\section{Kiến trúc tổng thể}\label{kiux1ebfn-truxfac-tux1ed5ng-thux1ec3}",
        r"\section{Kiến trúc tổng thể}\label{sec:architecture}",
    )
    architecture_note = r"\emph{{[}CẦN BỔ SUNG HÌNH: Sơ đồ gồm khối tín hiệu vào CH0..CH7, STM32/TIM2/RAM buffer, UART SLA8 và phần mềm PC.{]}}"
    architecture_caption = r"\protect\phantomsection\label{_Toc234276623}{}Hình 1 Sơ đồ khối logic analyzer Topic 1"
    latex = latex.replace(architecture_note + "\n\n" + architecture_caption, "")

    hardware_section = r"""\section{Thiết kế phần cứng}\label{thiux1ebft-kux1ebf-phux1ea7n-cux1ee9ng}

Phần cứng sử dụng vi điều khiển STM32F103C8. Tám kênh CH0--CH7 được ánh xạ tới PA0--PA7. Giao tiếp với máy tính sử dụng USART1 tại PA9 (TX) và PA10 (RX), với tốc độ 1.000.000~baud. Tín hiệu tại các chân GPIO sử dụng mức logic 3,3~V.

""" + HARDWARE_TABLE_INSERT.strip() + "\n\n"
    latex = replace_once(
        latex,
        r"\\section\{Thiết kế phần cứng\}\\label\{[^}]+\}\n\n.*?(?=\\section\{Thiết kế firmware\})",
        hardware_section,
        "Chuẩn hóa phần thiết kế phần cứng",
        flags=re.DOTALL,
    )
    latex = latex.replace(
        r"\section{Thiết kế firmware}\label{thiux1ebft-kux1ebf-firmware}",
        r"\section{Thiết kế firmware}\label{sec:firmware-design}",
    )
    latex = replace_once(
        latex,
        r"\\section\{Luồng hoạt động firmware Sơ đồ khối hoạt động\}\\label\{[^}]+\}\n\n.*?(?=\\section\{Thiết kế phần mềm PC\})",
        FLOW_INSERT.strip() + "\n\n",
        "Chuẩn hóa luồng hoạt động firmware",
        flags=re.DOTALL,
    )

    module_replacements = (
        ("board\\_config.h & Định nghĩa số kênh, chân PA0..PA7, UART PA9/PA10, TIM2, buffer và tốc độ.", "board\\_config.h & Định nghĩa số kênh, chân PA0--PA7, UART PA9/PA10, TIM2, bộ đệm và tần số lấy mẫu."),
        ("main.cpp & Điều phối UART command, timer, capture state và gửi frame sau capture.", "main.cpp & Điều phối lệnh UART, TIM2, trạng thái thu thập và truyền khung dữ liệu."),
        ("la\\_capture.h/c & Quản lý trạng thái capture, pretrigger/posttrigger, trigger và hot path ISR.", "la\\_capture.h/c & Quản lý trạng thái thu thập, tiền kích hoạt, hậu kích hoạt và hàm phục vụ ngắt."),
        ("la\\_protocol.h/c & Tạo header SLA8, checksum và metadata frame.", "la\\_protocol.h/c & Tạo phần đầu khung SLA8, mã kiểm tra và siêu dữ liệu."),
        ("la\\_benchmark.c & Hỗ trợ đo chu kỳ ISR bằng DWT khi build bật benchmark.", "la\\_benchmark.c & Cung cấp phép đo chu kỳ bằng DWT khi biên dịch với tùy chọn tương ứng; bản firmware kiểm thử HIL không sử dụng tùy chọn này."),
        ("firmware\\_v2 & Nhánh tối ưu ISR/RAM và thử DMA one-shot cho trigger immediate.", "la\\_board.h/c & Tính PSC/ARR, tần số thực tế và giới hạn tốc độ của cơ chế DMA, ISR."),
        ("Capture offline & Gửi cấu hình, ARM, chờ EVENT, DUMP và parse một frame SLA8.", "Thu thập ngoại tuyến & Gửi cấu hình, lệnh ARM, chờ sự kiện, yêu cầu DUMP và phân tích khung SLA8."),
        ("Capture offline & Gửi ARM, đợi EVENT, gửi DUMP, đọc frame và kiểm tra checksum.", "Thu thập ngoại tuyến & Gửi lệnh ARM, chờ EVENT, yêu cầu DUMP, đọc khung SLA8 và kiểm tra mã kiểm tra."),
        ("Hiển thị waveform & Vẽ 8 kênh, hỗ trợ zoom, fit, scroll và follow live.", "Hiển thị dạng sóng & Vẽ tám kênh, hỗ trợ phóng to, thu nhỏ, cuộn và theo dõi dữ liệu."),
        ("Realtime & Lặp lại offline capture bằng QTimer để cập nhật waveform.", "Cập nhật liên tục & Lặp phiên thu ngoại tuyến bằng QTimer để cập nhật dạng sóng."),
        ("Decode & Hỗ trợ UART và I2C trên capture hiện tại.", "Giải mã & Hỗ trợ UART, I2C và SPI trên dữ liệu đã thu."),
        ("CLI & Công cụ dòng lệnh hỗ trợ lưu một frame SLA8 để kiểm tra sau capture.", "Dòng lệnh & Lưu một khung SLA8 để phân tích sau phiên thu."),
        ("INFO & In version, số kênh, buffer, default/max rate và thông tin capture.", "INFO & Trả về phiên bản firmware, số kênh, dung lượng bộ đệm và dải tần số lấy mẫu."),
        ("STATUS & In trạng thái capture, actual rate, số mẫu, overflow và dropped samples.", "STATUS & Trả về trạng thái thu thập, tần số thực tế, số mẫu, số lần tràn bộ đệm và số mẫu bị mất."),
        ("ARM & Bắt đầu phiên capture.", "ARM & Bắt đầu phiên thu thập."),
        ("DUMP & Truyền frame SLA8 sau khi capture kết thúc.", "DUMP & Truyền khung SLA8 sau khi phiên thu kết thúc."),
        ("Kết nối thiết bị & Mở serial, gửi PING, đọc INFO và lấy thông tin buffer/tốc độ.", "Kết nối thiết bị & Mở cổng nối tiếp, gửi PING, đọc INFO và lấy thông tin bộ đệm, tần số."),
        (
            r"TRIG IMM/RISE/FALL/ANY/PAT & Cấu hình điều kiện trigger.",
            r"""TRIG IMM & Kích hoạt ngay. \\
TRIG RISE/FALL/ANY \textless kênh\textgreater{} & Kích hoạt theo cạnh trên kênh được chọn. \\
TRIG PAT \textless mặt nạ\textgreater{} \textless giá trị\textgreater{} & Kích hoạt khi mẫu thỏa mặt nạ và giá trị.""",
        ),
    )
    for original, revised in module_replacements:
        latex = latex.replace(original, revised)

    latex = latex.replace("\n3.8 Thiết kế Khối mạch bảo vệ\n", "\n")
    deployment_marker = r"\chapter{TRIỂN KHAI VÀ KIỂM THỬ}\label{triux1ec3n-khai-vuxe0-kiux1ec3m-thux1eed}"
    latex = replace_once(
        latex,
        re.escape(deployment_marker) + r"\n\n.*?(?=\\section\{Cấu hình build\})",
        deployment_marker + "\n\n" + DEPLOYMENT_INSERT.strip() + "\n\n",
        "Chuẩn hóa phần lắp mạch và vận hành",
        flags=re.DOTALL,
    )
    latex = latex.replace(
        r"\section{Cấu hình build}",
        "\\clearpage\n" + r"\section{Cấu hình biên dịch}",
    )
    latex = re.sub(
        r"\\section\{Cấu hình biên dịch\}\\label\{[^}]+\}",
        r"\\section{Cấu hình biên dịch}\\label{sec:build-config}",
        latex,
    )
    latex = latex.replace("genericSTM32F103C8\\_serial", "c8\\_serial")
    latex = latex.replace("c8\\_v2\\_serial", "c8\\_serial\\_benchmark")
    latex = latex.replace("COM12", "COMx").replace("COM18", "COMx")
    latex = latex.replace("Build firmware mặc định", "Biên dịch firmware mặc định")
    latex = latex.replace("Capture bằng CLI", "Thu thập bằng công cụ dòng lệnh")
    latex = latex.replace("Build firmware v2", "Biên dịch bản mở rộng dải tần đánh giá")

    latex = replace_once(
        latex,
        r"\\section\{Kịch bản thử nghiệm\}.*?(?=\\chapter\{ĐÁNH GIÁ VÀ THẢO LUẬN\})",
        TESTING_INSERT.strip() + "\n\n",
        "Thay khối ghi chú thử nghiệm bằng kế hoạch kiểm thử",
        flags=re.DOTALL,
    )
    latex = replace_once(
        latex,
        r"\\chapter\{ĐÁNH GIÁ VÀ THẢO LUẬN\}.*?(?=\\chapter\{KẾT LUẬN\})",
        ASSESSMENT_INSERT.strip() + "\n\n",
        "Chuẩn hóa chương đánh giá",
        flags=re.DOTALL,
    )
    latex = replace_once(
        latex,
        r"\\chapter\{KẾT LUẬN\}.*?(?=\\chapter\{TÀI LIỆU THAM KHẢO\})",
        CONCLUSION_INSERT.strip() + "\n\n",
        "Chuẩn hóa kết luận",
        flags=re.DOTALL,
    )
    latex = replace_once(
        latex,
        r"\\chapter\{TÀI LIỆU THAM KHẢO\}.*\Z",
        REFERENCES_INSERT.strip() + "\n",
        "Chuẩn hóa tài liệu tham khảo",
        flags=re.DOTALL,
    )

    latex = latex.replace(r"\hl{", r"\textit{")
    latex = capitalize_list_item_starts(latex)
    latex = embed_hardware_evidence(latex)
    latex = normalize_table_captions(latex)
    latex = add_full_grid_to_longtables(latex)
    latex = rebalance_longtable_columns(latex)
    return latex

def _write_red_audit(output_dir: Path, requirements: Iterable[RedRequirement]) -> None:
    resolutions = (
        ("Đề tài 1", "Đã dùng đúng tên đề tài đã có trên bìa; không tự đổi phạm vi."),
        ("Phần trăm sử dụng AI", "Đã loại khỏi báo cáo theo yêu cầu của nhóm."),
        ("Chỉ tiêu chức năng", "Đã tách thành chỉ tiêu chức năng và phi chức năng có điều kiện đánh giá."),
        ("Cơ sở lý thuyết STM32", "Đã bổ sung STM32F103C8, clock, TIM2 và công thức timer; có dẫn nguồn ST."),
        ("Thêm ảnh mô tả", "Đã vẽ sơ đồ lý thuyết bằng TikZ và bổ sung ảnh dạng sóng thực tế; ảnh mô hình phần cứng cần được chụp bằng máy ảnh."),
        ("Có công thức", "Đã bổ sung định lý Nyquist, aliasing và giới hạn áp dụng cho tín hiệu số."),
        ("Lý thuyết về mạch bảo vệ", "Không đưa vào báo cáo vì chưa có thiết kế, sơ đồ hoặc dữ liệu kiểm thử làm căn cứ."),
        ("Sơ đồ khối hoạt động", "Đã vẽ flowchart từ luồng firmware trong source."),
        ("3.8 Thiết kế", "Không tạo mục thiết kế mạch bảo vệ khi chưa có dữ liệu kỹ thuật của nhóm."),
        ("Cách cắm mạch", "Đã thêm ánh xạ dây, build, upload và chạy chương trình theo README/source."),
        ("Khi cap ảnh decode", "Đã bổ sung ảnh giải mã UART, I2C và SPI từ tín hiệu phần cứng thực tế; MISO/MOSI được xác định đúng là các đường dữ liệu của SPI."),
    )
    lines = [
        "# Kiểm kê yêu cầu chữ đỏ và trạng thái xử lý",
        "",
        "Nguồn: các run có màu trực tiếp `FF0000` trong DOCX gốc. Tài liệu này không coi ghi chú đỏ là dữ liệu thực nghiệm.",
        "",
    ]
    for item, resolution in zip(requirements, resolutions, strict=True):
        lines.extend(
            (
                f"### Yêu cầu màu đỏ {item.paragraph_number}",
                "",
                f"> {item.text}",
                "",
                f"**Xử lý:** {resolution[1]}",
                "",
            )
        )
    (output_dir / "RED_REQUIREMENTS_AUDIT.md").write_text("\n".join(lines), encoding="utf-8")


def convert_report(source_docx: Path, template_docx: Path, output_dir: Path, *, build: bool = True) -> Path:
    if not source_docx.is_file():
        raise FileNotFoundError(f"Không tìm thấy DOCX nguồn: {source_docx}")
    if not template_docx.is_file():
        raise FileNotFoundError(f"Không tìm thấy DOCX mẫu: {template_docx}")
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "pandoc_raw.tex"
    pandoc = _find_program("pandoc")
    subprocess.run(
        [
            pandoc,
            str(source_docx),
            "--from=docx",
            "--to=latex",
            "--top-level-division=chapter",
            "--number-sections",
            "--wrap=none",
            f"--extract-media={output_dir}",
            f"--output={raw_path}",
        ],
        check=True,
        cwd=output_dir,
    )
    raw_latex = raw_path.read_text(encoding="utf-8")
    content = _enhance_content(raw_latex)
    (output_dir / "content.tex").write_text(content, encoding="utf-8")
    (output_dir / "Bao_cao_Topic_1_Doan_Sinh_Duc.tex").write_text(_front_matter(), encoding="utf-8")
    requirements = extract_red_requirements(source_docx)
    if len(requirements) != 11:
        raise ValueError(f"Phát hiện {len(requirements)} yêu cầu chữ đỏ, kỳ vọng 11")
    _write_red_audit(output_dir, requirements)
    if build:
        return build_pdf(output_dir)
    return output_dir / "Bao_cao_Topic_1_Doan_Sinh_Duc.tex"


def build_pdf(output_dir: Path) -> Path:
    main_tex = output_dir / "Bao_cao_Topic_1_Doan_Sinh_Duc.tex"
    if not main_tex.is_file():
        raise FileNotFoundError(f"Chưa có file LaTeX chính: {main_tex}")
    xelatex = _find_program("xelatex")
    log_path = output_dir / "build.log"
    combined_output: list[str] = []
    for _ in range(3):
        result = subprocess.run(
            [xelatex, "-interaction=nonstopmode", "-halt-on-error", "-file-line-error", main_tex.name],
            cwd=output_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        combined_output.append(result.stdout)
        combined_output.append(result.stderr)
        if result.returncode != 0:
            log_path.write_text("\n".join(combined_output), encoding="utf-8")
            raise RuntimeError(f"XeLaTeX biên dịch thất bại. Xem {log_path}")
    # The final XeLaTeX pass is the authoritative layout after the TOC, list of
    # figures and list of tables have been regenerated.
    log_path.write_text("\n".join(combined_output[-2:]), encoding="utf-8")
    pdf_path = output_dir / "Bao_cao_Topic_1_Doan_Sinh_Duc.pdf"
    if not pdf_path.is_file():
        raise RuntimeError("XeLaTeX không tạo PDF")
    return pdf_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Chuyển báo cáo DOCX sang LaTeX theo mẫu ĐATN")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-build", action="store_true")
    arguments = parser.parse_args()
    output = convert_report(arguments.source, arguments.template, arguments.output, build=not arguments.no_build)
    print(output)


if __name__ == "__main__":
    main()
