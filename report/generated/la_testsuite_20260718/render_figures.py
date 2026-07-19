"""Render clean GUI figures for the SLA8 test-suite report from saved frames.

Uses the real PyQt5/pyqtgraph application widgets (window rendered off-screen and
grabbed), so every figure is an authentic screenshot of the analyzer software.
"""
import os, sys, time
import numpy as np
from PyQt5.QtWidgets import QApplication
import pyqtgraph as pg

SW = r"d:/BTL_HTN_v2/src/software"
sys.path.insert(0, SW); sys.path.insert(0, os.path.join(SW, "gui"))
OUT = r"d:/BTL_HTN_v2/report/generated/la_testsuite_20260718"
FRAMES = os.path.join(OUT, "frames")
FIGS = os.path.join(OUT, "figs"); os.makedirs(FIGS, exist_ok=True)

app = QApplication(sys.argv)
from protocol_frame import decode_frame
from capture import Capture
from decoders import decode_uart, decode_i2c, decode_spi
from gui.main_window import MainWindow
from gui.styles import COLORS
pg.setConfigOptions(useOpenGL=False, enableExperimental=False, antialias=True)


def load(name):
    fr = decode_frame(open(os.path.join(FRAMES, name + ".sla8"), "rb").read())
    cap = Capture(fr.samples, 1_000_000_000.0 / fr.actual_sample_rate_hz)
    return fr, cap


def make_window():
    w = MainWindow()
    w.resize(1640, 1000)
    w.move(-5000, -5000)
    # give the decode table more height so all rows are visible in the figure
    w.content_splitter.setSizes([560, 380])
    w.show(); app.processEvents()
    return w


def set_status(w, rate_hz, text="Connected"):
    w.update_status_indicator("connected", text)
    w.sample_rate_label.setText(f"Rate: {rate_hz/1e6:.2f} MHz")


def channel(cap, ch):
    return np.frombuffer(cap.samples, np.uint8) >> ch & 1


def zoom(w, cap, t_start_s, t_end_s):
    w.waveform_view.plot_widget.setXRange(t_start_s, t_end_s, padding=0)


def add_marker(w, t_s, label):
    ln = pg.InfiniteLine(pos=t_s, angle=90,
                         pen=pg.mkPen(color="#ffd166", width=2, style=pg.QtCore.Qt.DashLine))
    w.waveform_view.plot_widget.addItem(ln)
    txt = pg.TextItem(label, color="#ffd166", anchor=(0, 1))
    txt.setPos(t_s, 8.4)
    w.waveform_view.plot_widget.addItem(txt)


def annotate(w, t_s, y, label, color="#ffffff"):
    txt = pg.TextItem(label, color=color, anchor=(0.5, 1.0),
                      fill=pg.mkBrush(30, 30, 30, 210))
    txt.setPos(t_s, y)
    w.waveform_view.plot_widget.addItem(txt)


def grab(w, name):
    end = time.time() + 0.8
    while time.time() < end:
        app.processEvents(); time.sleep(0.02)
    path = os.path.join(FIGS, name + ".png")
    w.grab().save(path)
    print("  wrote", name)
    w.close()


def us(x):  # microseconds -> seconds
    return x / 1e6


# ---- fig: TC-02 eight-channel Gray -----------------------------------------
fr, cap = load("tc02_gray_100k")
w = make_window(); set_status(w, fr.actual_sample_rate_hz); w.current_capture = cap
w.waveform_view.display_capture(cap)
zoom(w, cap, 0, us(5100))                     # ~51 Gray steps: CH0..CH5 all toggle
grab(w, "fig_tc02_gray8ch")

# ---- fig: TC-04 ceiling 6.545 MS/s -----------------------------------------
fr, cap = load("tc04_gray_6p545M")
w = make_window(); set_status(w, fr.actual_sample_rate_hz, "Connected  6.545 MS/s")
w.current_capture = cap; w.waveform_view.display_capture(cap)
zoom(w, cap, 0, us(60))                       # ~40 steps at 100 kHz Gray / 6.545 MS/s
grab(w, "fig_tc04_ceiling")

# ---- fig: TC-05 ISR 400 kS/s -----------------------------------------------
fr, cap = load("tc05_isr_400k")
w = make_window(); set_status(w, fr.actual_sample_rate_hz, "Connected  ISR 400 kS/s")
w.current_capture = cap; w.waveform_view.display_capture(cap)
zoom(w, cap, 0, us(600))
grab(w, "fig_tc05_isr")

# ---- fig: TC-07 UART decode with start/stop bits ---------------------------
fr, cap = load("tc07_uart_1M")
ev = decode_uart(fr.samples, fr.actual_sample_rate_hz, 0, 57600)
starts = [e for e in ev if e.event == "START"]
t0 = us(starts[0].time_us) if starts else 0
w = make_window(); set_status(w, fr.actual_sample_rate_hz); w.current_capture = cap
w.waveform_view.display_capture(cap)
w.protocol_combo.setCurrentText("UART"); w.on_decode_protocol_changed()
w.baud_combo.setCurrentText("57600"); w.decode_current_capture()
zoom(w, cap, t0 - us(40), t0 + us(360))       # ~2 UART bytes: start + data + stop
if starts:
    annotate(w, t0, 7.9, "START", "#ff5252")
    stops = [e for e in ev if e.event == "STOP" and e.time_us >= starts[0].time_us]
    if stops:
        annotate(w, us(stops[0].time_us), 7.9, "STOP", "#33d9b2")
grab(w, "fig_tc07_uart")

# ---- fig: TC-08 I2C decode -------------------------------------------------
fr, cap = load("tc08_i2c_2M")
ev = decode_i2c(fr.samples, fr.actual_sample_rate_hz, 1, 2)
st = [e for e in ev if e.event == "START"]
sp = [e for e in ev if e.event == "STOP"]
t0 = us(st[0].time_us) if st else 0
t1 = us(sp[0].time_us) if sp else t0 + us(150)
w = make_window(); set_status(w, fr.actual_sample_rate_hz); w.current_capture = cap
w.waveform_view.display_capture(cap)
w.protocol_combo.setCurrentText("I2C"); w.on_decode_protocol_changed()
w.decode_current_capture()
zoom(w, cap, t0 - us(15), t1 + us(20))
grab(w, "fig_tc08_i2c")

# ---- fig: TC-09 SPI decode (clean) -----------------------------------------
fr, cap = load("tc09_clean_500k")
ev = decode_spi(fr.samples, fr.actual_sample_rate_hz, 3, 4, 5, 6)
cslow = [e for e in ev if e.event == "CS" and e.value == "LOW"]
cshigh = [e for e in ev if e.event == "CS" and e.value == "HIGH"]
t0 = us(cslow[0].time_us) if cslow else 0
t1 = us(cshigh[0].time_us) if cshigh else t0 + us(600)
w = make_window(); set_status(w, fr.actual_sample_rate_hz); w.current_capture = cap
w.waveform_view.display_capture(cap)
w.protocol_combo.setCurrentText("SPI"); w.on_decode_protocol_changed()
w.decode_current_capture()
zoom(w, cap, t0 - us(30), t1 + us(30))
grab(w, "fig_tc09_spi")

# ---- fig: TC-09 SPI undersampled (guard) -----------------------------------
fr, cap = load("tc09_undersampled")
w = make_window(); set_status(w, fr.actual_sample_rate_hz, "Connected  150 kS/s (undersampled)")
w.current_capture = cap; w.waveform_view.display_capture(cap)
w.protocol_combo.setCurrentText("SPI"); w.on_decode_protocol_changed()
w.decode_current_capture()
sck = channel(cap, 3)
edges = np.flatnonzero((sck[:-1] == 0) & (sck[1:] == 1))
if len(edges):
    t0 = cap.time[edges[0]]
    zoom(w, cap, t0 - us(20), t0 + us(500))
grab(w, "fig_tc09_spi_undersampled")

# ---- fig: TC-10 trigger positioning ----------------------------------------
fr, cap = load("tc10_trig_fall_cs")
w = make_window(); set_status(w, fr.actual_sample_rate_hz, "Connected  TRIG FALL CH6")
w.current_capture = cap; w.waveform_view.display_capture(cap)
ti = fr.trigger_index
t_trig = cap.time[ti] if 0 <= ti < len(cap.time) else 0
zoom(w, cap, max(0, t_trig - us(16000)), t_trig + us(6000))
add_marker(w, t_trig, f"  TRIGGER  (idx {ti})")
grab(w, "fig_tc10_trigger")

print("done ->", FIGS)
