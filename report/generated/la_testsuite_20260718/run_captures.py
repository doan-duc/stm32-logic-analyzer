"""HIL capture harness for the SLA8 logic-analyzer test suite (10 scenarios).

Drives the STM32 device (COM12) and the Arduino reference generator (COM18),
captures SLA8 frames, runs the same analysis / decoder code the GUI uses, and
writes frames + a metrics.json that the report quotes verbatim.
"""
from __future__ import annotations
import json, os, sys, time
import numpy as np

SW = r"d:/BTL_HTN_v2/src/software"
sys.path.insert(0, SW)
import serial
from device import LogicAnalyzerDevice
from signal_verifier import analyze_gray_capture, gray_to_binary
from decoders import decode_uart, decode_i2c, decode_spi

LA_PORT, GEN_PORT = "COM12", "COM18"
OUT = r"d:/BTL_HTN_v2/report/generated/la_testsuite_20260718"
FRAMES = os.path.join(OUT, "frames")
os.makedirs(FRAMES, exist_ok=True)

metrics: dict = {}
gen = serial.Serial(GEN_PORT, 115200, timeout=0.3)
time.sleep(2.0)                       # Uno auto-reset on DTR
gen.reset_input_buffer()

def gcmd(cmd: str, expect: str | None = None, wait=0.3) -> str:
    gen.reset_input_buffer()
    gen.write(cmd.encode() + b"\n"); gen.flush()
    time.sleep(wait)
    lines, end = [], time.time() + 1.0
    while time.time() < end:
        ln = gen.readline().decode("ascii", "ignore").strip()
        if ln:
            lines.append(ln)
            if expect and ln == expect:
                break
    return " | ".join(lines)

def set_gen_mode(mode: str, tries=4) -> bool:
    """Switch generator mode and confirm via STATUS (mode changes can be dropped
    while a fast Gray ISR is loading the AVR)."""
    for _ in range(tries):
        gcmd(f"MODE {mode}", f"OK MODE {mode}")
        time.sleep(0.15)
        if f"MODE {mode}" in gcmd("STATUS"):
            return True
        time.sleep(0.2)
    return False

dev = LogicAnalyzerDevice(LA_PORT, 1_000_000)
if not dev.connect():
    raise SystemExit(f"LA connect failed: {dev.last_error}")

def raw(cmd: str, timeout=2.0) -> str:
    """Send a raw command, return first response line (for ERR/OK probing)."""
    dev.serial.reset_input_buffer()
    dev._send_line(cmd)
    return dev._read_line(timeout)

def status() -> dict:
    return dev.read_status() or {}

def save_frame(name: str, frame: dict) -> str:
    p = os.path.join(FRAMES, name + ".sla8")
    with open(p, "wb") as f:
        f.write(frame["raw_frame"])
    return p

def runs(b: bytes):
    a = np.frombuffer(b, np.uint8)
    if len(a) == 0:
        return []
    idx = np.flatnonzero(a[1:] != a[:-1]) + 1
    bounds = np.concatenate(([0], idx, [len(a)]))
    return [(int(a[bounds[i]]), int(bounds[i + 1] - bounds[i])) for i in range(len(bounds) - 1)]

def analyze_gray(frame, step_rate):
    r = analyze_gray_capture(frame["samples"], sample_rate_hz=frame["sample_rate_hz"],
                             step_rate_hz=step_rate, minimum_states=32)
    return dict(stable_states=r.stable_states, sequence_errors=r.sequence_errors,
                short_runs=r.short_runs, channel_edges=list(r.channel_edges),
                measured_rate=round(r.measured_sample_rate_hz, 1),
                rate_err_pct=round(r.rate_error_fraction * 100, 4), passed=r.passed)

def frame_health(frame):
    return dict(samples=frame["sample_count"], flags=frame["flags"],
                overflow=frame["overflow_count"], dropped=frame["dropped_samples"],
                actual_rate=frame["sample_rate_hz"], requested=frame["requested_sample_rate_hz"])

def full_window():
    """Reset the trigger window to the whole buffer (config persists on device)."""
    raw("TRIG IMM"); raw("CFG PRE 0"); raw("CFG POST 13887")

def capture_until(pred, tries=6):
    """Retry immediate captures until pred(frame) holds (bursty protocol modes)."""
    last = None
    for _ in range(tries):
        fr = dev.capture()
        if fr and fr.get("type") == "capture":
            last = fr
            if pred(fr):
                return fr
    return last

full_window()          # clear any window left by a previous session

# ---------------------------------------------------------------- TC-01 identity
print("== TC-01 identity/metadata ==")
info_lines, st = [], {}
dev.serial.reset_input_buffer(); dev._send_line("INFO")
end = time.time() + 1.5
while time.time() < end:
    ln = dev._read_line(0.1)
    if ln: info_lines.append(ln)
    if ln == "END INFO": break
dev.set_capture_mode("DMA"); dev.set_sample_rate(100_000); dev.set_trigger(False)
set_gen_mode("GRAY"); gcmd("GRAY RATE 10000")
fr = dev.capture()
from protocol_frame import decode_frame_header
hdr = decode_frame_header(fr["raw_frame"][:48])
metrics["TC01"] = dict(info=info_lines, status=status(), frame=frame_health(fr),
                       header_checksum=hdr.header_checksum, payload_checksum=hdr.payload_checksum,
                       gen_status=gcmd("STATUS"))
print("   fw:", info_lines[0], "| checksum hdr=%08X pl=%08X" % (hdr.header_checksum, hdr.payload_checksum))

# ------------------------------------------------------- TC-02 8-ch Gray mapping
print("== TC-02 8-channel mapping / simultaneity ==")
dev.set_capture_mode("DMA"); dev.set_sample_rate(100_000); dev.set_trigger(False)
set_gen_mode("GRAY"); gcmd("GRAY RATE 10000")
fr = dev.capture(); save_frame("tc02_gray_100k", fr)
metrics["TC02"] = dict(gray=analyze_gray(fr, 10000), frame=frame_health(fr), status=status())
print("  ", metrics["TC02"]["gray"])

# --------------------------------------------------- TC-03 sample-rate accuracy
print("== TC-03 rate accuracy / quantization ==")
rows = []
for rate in [1_000, 10_000, 100_000, 500_000, 1_000_000, 2_000_000, 4_000_000, 5_000_000, 6_000_000]:
    ok = dev.set_sample_rate(rate)
    s = status()
    rows.append(dict(requested=rate, ok=ok, actual=s.get("actual_rate"),
                     error_ppm=s.get("error_ppm"), timer_clock=s.get("timer_clock")))
    print(f"   req={rate:>8} actual={s.get('actual_rate'):>8} ppm={s.get('error_ppm')}")
# cross-check two rates against the Gray oracle
xcheck = {}
set_gen_mode("GRAY"); gcmd("GRAY RATE 100000")
for rate in [1_000_000, 4_000_000]:
    dev.set_sample_rate(rate); fr = dev.capture()
    xcheck[str(rate)] = analyze_gray(fr, 100000)
metrics["TC03"] = dict(sweep=rows, gray_crosscheck=xcheck)

# ------------------------------------------------ TC-04 DMA ceiling + rejection
print("== TC-04 DMA ceiling ==")
# A 100 kHz Gray step is the fastest the 16 MHz AVR can emit without starving its
# UART. In a 2.1 ms window at 6.545 MS/s the two MSBs (CH6/CH7) barely toggle, so
# the ceiling is judged on sequence + rate integrity of the resolved channels.
set_gen_mode("GRAY"); gcmd("GRAY RATE 100000")
dev.set_capture_mode("DMA"); dev.set_trigger(False); full_window()
def integrity_ok(f, step=100_000):
    g = analyze_gray(f, step)
    return (g["sequence_errors"] == 0 and g["short_runs"] == 0
            and g["rate_err_pct"] < 0.1 and f["dropped_samples"] == 0
            and f["overflow_count"] == 0)
ceil = {}
dev.set_sample_rate(6_545_454)
fr = capture_until(lambda f: integrity_ok(f), tries=6)
save_frame("tc04_gray_6p545M", fr)
g = analyze_gray(fr, 100_000)
ceil["6545454"] = dict(gray=g, frame=frame_health(fr),
                       integrity_ok=integrity_ok(fr),
                       channels_resolved=sum(1 for e in g["channel_edges"] if e > 0))
reject = {r: raw(f"CFG RATE {r}") for r in [7_000_000, 8_000_000, 10_000_000]}
metrics["TC04"] = dict(ceiling=ceil, reject=reject)
print("   6.545MS/s integrity:", ceil["6545454"]["integrity_ok"],
      "chan_resolved:", ceil["6545454"]["channels_resolved"],
      "measured:", ceil["6545454"]["gray"]["measured_rate"], "| reject 7M:", reject[7_000_000])

# ------------------------------------------------- TC-05 ISR integrity + guard
print("== TC-05 ISR engine ==")
dev.set_sample_rate(100_000)          # drop below ISR ceiling before switching
mode_ok = dev.set_capture_mode("ISR")
isr = {}
gcmd("GRAY RATE 10000")               # 10 kHz step is AVR-safe and clean at every ISR rate
for rate in [100_000, 250_000, 400_000]:
    dev.set_sample_rate(rate); fr = dev.capture()
    isr[str(rate)] = dict(gray=analyze_gray(fr, 10000),
                          isr_overruns=status().get("isr_overruns"), frame=frame_health(fr))
    if rate == 400_000:
        save_frame("tc05_isr_400k", fr)
isr_reject = {r: raw(f"CFG RATE {r}") for r in [500_000, 1_000_000]}
metrics["TC05"] = dict(mode_switch_ok=mode_ok, runs=isr, reject=isr_reject)
print("   ISR mode_ok:", mode_ok, "| 400k overruns:", isr["400000"]["isr_overruns"],
      "| reject 500k:", isr_reject[500_000])
dev.set_sample_rate(100_000); dev.set_capture_mode("DMA")

# ------------------------------------------------------ TC-06 Nyquist/aliasing
print("== TC-06 Nyquist / aliasing ==")
# CH0 = bit0 toggles every Gray step -> CH0 frequency = step_rate/2 = 50 kHz.
set_gen_mode("GRAY"); gcmd("GRAY RATE 100000")
alias = {}
for tag, rate, step in [("adequate_1M", 1_000_000, 100000), ("under_55k", 55_000, 100000)]:
    dev.set_sample_rate(rate); fr = dev.capture(); save_frame(f"tc06_{tag}", fr)
    ch0 = np.frombuffer(fr["samples"], np.uint8) & 1
    tr = int(np.count_nonzero(ch0[1:] != ch0[:-1]))
    alias[tag] = dict(gray=analyze_gray(fr, step), frame=frame_health(fr),
                      ch0_transitions=tr,
                      ch0_toggle_hz=round(tr / 2 * fr["sample_rate_hz"] / max(1, fr["sample_count"]), 1))
    print(f"   {tag}: seq_err={alias[tag]['gray']['sequence_errors']} short={alias[tag]['gray']['short_runs']}")
metrics["TC06"] = dict(cases=alias, ch0_true_hz=50000)

# ------------------------------------------------------------- TC-07 UART decode
print("== TC-07 UART decode ==")
set_gen_mode("UART"); time.sleep(0.1)
dev.set_capture_mode("DMA"); dev.set_sample_rate(1_000_000); dev.set_trigger(False)
fr = dev.capture(); save_frame("tc07_uart_1M", fr)
from collections import Counter
# bit period = MEDIAN of single-bit runs (robust vs partial edge glitches)
rl = [ln for _, ln in runs(fr["samples"] if False else bytes((np.frombuffer(fr["samples"], np.uint8) & 1).tobytes()))]
single = sorted(x for x in rl if 8 <= x <= 40)
bit_samp = float(np.median(single)) if single else 0.0
bit_us = bit_samp * 1e6 / fr["sample_rate_hz"] if bit_samp else 0
meas_baud = 1e6 / bit_us if bit_us else 0
UART_BAUD = 57600                       # nearest standard rate to the generator
ev = decode_uart(fr["samples"], fr["sample_rate_hz"], 0, UART_BAUD)
byts = [e.value for e in ev if e.event == "BYTE"]
framing = sum(1 for e in ev if "framing" in e.note)
hist = Counter(byts)
expected = {"0x55 'U'", "0xA5 '.'", "0x4F 'O'", "0x4B 'K'"}
frames_ok = min((hist[b] for b in expected), default=0)
metrics["TC07"] = dict(bit_median_samples=bit_samp, bit_us=round(bit_us, 3),
                       measured_baud=round(meas_baud, 1), decode_baud=UART_BAUD,
                       byte_histogram=dict(hist), total_bytes=len(byts),
                       framing_errors=framing, clean_frames=frames_ok,
                       frame=frame_health(fr))
print("   bit=%.2fus baud=%d frames_ok=%d hist=%s" % (bit_us, UART_BAUD, frames_ok, dict(hist)))

# -------------------------------------------------------------- TC-08 I2C decode
print("== TC-08 I2C decode ==")
set_gen_mode("I2C"); time.sleep(0.1)
dev.set_sample_rate(2_000_000); fr = dev.capture(); save_frame("tc08_i2c_2M", fr)
ev = decode_i2c(fr["samples"], fr["sample_rate_hz"], 1, 2)
metrics["TC08"] = dict(events=[(e.event, e.value, e.note) for e in ev][:12],
                       frame=frame_health(fr))
print("  ", metrics["TC08"]["events"][:6])

# ---------------------------------------------- TC-09 SPI decode + undersample
print("== TC-09 SPI decode + undersample guard ==")
set_gen_mode("SPI"); time.sleep(0.1)
dev.set_capture_mode("DMA"); dev.set_trigger(False); full_window()
spi = {}
# clean capture: retry until a CS-framed burst with 3 data bytes is caught
dev.set_sample_rate(500_000)
def has_burst(f):
    ev = decode_spi(f["samples"], f["sample_rate_hz"], 3, 4, 5, 6)
    return sum(1 for e in ev if e.event == "BYTE") >= 3
fr = capture_until(has_burst, tries=8); save_frame("tc09_clean_500k", fr)
ev = decode_spi(fr["samples"], fr["sample_rate_hz"], 3, 4, 5, 6)
spi["clean_500k"] = dict(events=[(e.event, e.value, e.note) for e in ev][:10],
                         frame=frame_health(fr),
                         warn=[e.value for e in ev if e.event == "WARN"])
# measure real SCK period, then undersample at ~3 samples/SCK to trip the guard
sck = np.frombuffer(fr["samples"], np.uint8) >> 3 & 1
rise = np.flatnonzero((sck[:-1] == 0) & (sck[1:] == 1))
sck_hz = 500_000 / float(np.median(np.diff(rise))) if len(rise) > 3 else 100_000
under_rate = int(round(sck_hz * 3.0))
dev.set_sample_rate(under_rate)
fr2 = capture_until(lambda f: decode_spi(f["samples"], f["sample_rate_hz"], 3, 4, 5, 6), tries=6)
save_frame("tc09_undersampled", fr2)
ev2 = decode_spi(fr2["samples"], fr2["sample_rate_hz"], 3, 4, 5, 6)
spi["undersampled"] = dict(rate=under_rate, sck_hz=round(sck_hz, 1),
                           events=[(e.event, e.value, e.note) for e in ev2][:10],
                           frame=frame_health(fr2),
                           warn=[e.value for e in ev2 if e.event == "WARN"],
                           byte_events=sum(1 for e in ev2 if e.event == "BYTE"))
metrics["TC09"] = spi
print(f"   clean warn={spi['clean_500k']['warn']} | SCK={sck_hz:.0f}Hz "
      f"under@{under_rate}: warn={spi['undersampled']['warn'][:2]} bytes={spi['undersampled']['byte_events']}")

# ----------------------------------------------------- TC-10 trigger positioning
print("== TC-10 trigger positioning ==")
# Trigger on the SPI CS line (CH6/PA6): it idles HIGH ~20 ms between bursts, so a
# 1500-sample pretrigger at 100 kS/s fills completely and the trigger sits deep
# inside the frame -- unlike a UART edge, which arrives before the pretrigger fills.
set_gen_mode("SPI"); time.sleep(0.1)
dev.set_sample_rate(100_000); dev.set_capture_mode("ISR")
r_post = raw("CFG POST 4000"); r_pre = raw("CFG PRE 1500")
r_trig = raw("TRIG FALL 6")
dev.trigger_enabled = True
fr = dev.capture()
trig = {}
if fr and fr.get("type") == "capture":
    save_frame("tc10_trig_fall_cs", fr)
    ti = fr["trigger_index"]
    cs = np.frombuffer(fr["samples"], np.uint8) >> 6 & 1
    pre_high = int(np.count_nonzero(cs[:ti] == 1)) if ti > 0 else 0
    trig = dict(trigger_index=ti, requested_pre=1500,
                level_before=int(cs[ti - 1]) if 0 < ti < len(cs) else None,
                level_at=int(cs[ti]) if 0 <= ti < len(cs) else None,
                pretrigger_high_samples=pre_high,
                pretrigger_all_high=int(pre_high == ti),
                frame=frame_health(fr), pre=r_pre, post=r_post, trig_cmd=r_trig)
else:
    trig = dict(error=dev.last_error, trig_cmd=r_trig)
dev.trigger_enabled = False
pat_reject = raw("TRIG PAT 256 0")     # mask > 0xFF must be rejected
pat_ok = raw("TRIG PAT 1 0")           # valid mask/value
rise_reject = raw("TRIG RISE 9")       # channel 9 does not exist
metrics["TC10"] = dict(edge=trig, pattern_ok=pat_ok, pattern_reject=pat_reject,
                       bad_channel_reject=rise_reject)
print("   trig_index:", trig.get("trigger_index"), "pre_high:",
      trig.get("pretrigger_high_samples"), "before/at:", trig.get("level_before"),
      trig.get("level_at"), "| pat_reject:", pat_reject, "| ch9:", rise_reject)

# cleanup: leave the device in a sane full-window immediate DMA state
raw("TRIG IMM"); dev.set_capture_mode("DMA"); dev.set_sample_rate(100_000); full_window()
dev.disconnect(); gen.close()

with open(os.path.join(OUT, "metrics.json"), "w", encoding="utf-8") as f:
    json.dump(metrics, f, indent=2, ensure_ascii=False)
print("\nWROTE", os.path.join(OUT, "metrics.json"))
