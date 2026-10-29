# Worst spectral line at or above 394 Hz for Focus-style gamma bursts.
# Scratch evidence for design log 2026-10-28 (o); not engine or reference code.
# 250 Hz gamma PAC carrier, AM at the gamma rate, 50 ms bursts (full width,
# tapers inside) centered on each peak of a 6 Hz theta reference.
# Components at 394 Hz or above collide with a 450 Hz theta reference (444 to
# 456 Hz) under the 50 Hz spacing rule; a line counts if within 40 dB of the
# layer's strongest line.
import numpy as np

fs = 48000
t = np.arange(fs) / fs  # 1 s holds whole theta, carrier, and AM periods
theta = 6.0
fc = 250.0
W = 0.050


def time_from_theta_peak():
    return ((t * theta + 0.5) % 1.0 - 0.5) / theta


def depth(taper):
    a = np.abs(time_from_theta_peak())
    h = W / 2
    d = np.zeros_like(t)
    if taper == 0:
        d[a <= h] = 1
    else:
        d[a <= h - taper] = 1
        m = (a > h - taper) & (a <= h)
        x = (a[m] - (h - taper)) / taper
        d[m] = 0.5 * (1 + np.cos(np.pi * x))  # raised-cosine edge
    return d


def envelope(gamma_hz, taper, mode):
    d = depth(taper)
    am = np.cos(2 * np.pi * gamma_hz * time_from_theta_peak())  # AM peak at burst center
    if mode == "depth":  # carrier plays continuously, burst gates AM depth
        return 1 - d * (1 - am) / 2
    return d * (1 + am) / 2  # carrier gated, silent between bursts


def worst_line_db(gamma_hz, taper, mode):
    x = envelope(gamma_hz, taper, mode) * np.sin(2 * np.pi * fc * t)
    X = np.abs(np.fft.rfft(x))
    f = np.fft.rfftfreq(len(x), 1 / fs)
    db = 20 * np.log10(X / X.max() + 1e-300)
    return db[f >= 394].max()


if __name__ == "__main__":
    tapers = [0, 0.002, 0.005, 0.010, 0.0125]
    for mode in ["depth", "gate"]:
        for gamma_hz in [40, 45, 60]:
            row = " ".join(f"{worst_line_db(gamma_hz, tp, mode):7.1f}" for tp in tapers)
            print(f"{mode:5} {gamma_hz} Hz, taper 0/2/5/10/12.5 ms: {row}")
