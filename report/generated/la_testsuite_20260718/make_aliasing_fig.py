"""Nyquist/aliasing figure (TC-06): CH0 (a 50 kHz square from the Gray LSB)
captured above and below the Nyquist rate."""
import os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SW = r"d:/BTL_HTN_v2/src/software"; sys.path.insert(0, SW)
from protocol_frame import decode_frame
OUT = r"d:/BTL_HTN_v2/report/generated/la_testsuite_20260718"
F = os.path.join(OUT, "frames")

def ch0(name):
    fr = decode_frame(open(os.path.join(F, name + ".sla8"), "rb").read())
    s = np.frombuffer(fr.samples, np.uint8) & 1
    t = np.arange(len(s)) / fr.actual_sample_rate_hz * 1e3  # ms
    return t, s, fr.actual_sample_rate_hz

t_ok, s_ok, fs_ok = ch0("tc06_adequate_1M")
t_al, s_al, fs_al = ch0("tc06_under_30k")

fig, ax = plt.subplots(2, 1, figsize=(9.2, 4.6))
fig.subplots_adjust(hspace=0.5, left=0.09, right=0.98, top=0.9, bottom=0.12)

m = t_ok <= 0.4      # 400 us -> ten 25 kHz periods, correctly resolved
ax[0].step(t_ok[m], s_ok[m], where="post", color="#1f77b4", lw=1.4)
ax[0].set_title(f"(a) fs = {fs_ok/1e6:.1f} MS/s  (fs > 2 fin): CH0 25 kHz resolved correctly",
                fontsize=10, loc="left")

m = t_al <= 1.2      # 1.2 ms -> the aliased ~5 kHz beat
ax[1].step(t_al[m], s_al[m], where="post", color="#d62728", lw=1.4)
ax[1].set_title(f"(b) fs = {fs_al/1e3:.0f} kS/s  (fs < 2 fin): 25 kHz aliases to a false ~5 kHz pattern",
                fontsize=10, loc="left")

for a in ax:
    a.set_ylim(-0.3, 1.3); a.set_yticks([0, 1]); a.set_ylabel("CH0")
    a.grid(True, alpha=0.25)
ax[0].set_xlabel("Thoi gian (ms)"); ax[1].set_xlabel("Thoi gian (ms)")
out = os.path.join(OUT, "figs", "fig_tc06_aliasing.png")
fig.savefig(out, dpi=150)
print("wrote", out)
