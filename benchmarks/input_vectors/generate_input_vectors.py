"""
Generate MATLAB-compatible input vectors for the Buck converter accuracy benchmark.

Each .mat file contains individual timeseries variables (not a packed matrix):
  t          - time vector [s]
  duty       - duty cycle  [0-1]
  Vin        - input voltage [V]  (physical units)
  Rload      - load resistance [Ω] (physical units)

Load in MATLAB via:
  data = load('vector1_step_load_input.mat');
  % data.t, data.duty, data.Vin, data.Rload are all column vectors
  inputVector = [data.t, data.duty, data.Vin/50, data.Rload/10];
"""

import numpy as np
import scipy.io as sio
from pathlib import Path

OUT_DIR = Path(__file__).parent
DT = 1e-4  # 100 µs sample time (10 kHz), matching ROM training


# ── Vector 1: Step load ──────────────────────────────────────────────────────
# Vin = 24 V constant, duty = 0.5 constant
# Rload: 1 Ω → 0.1 Ω at t=25 ms → 1 Ω at t=100 ms
# Duration: 250 ms

T1 = 0.250
t1 = np.arange(0, T1, DT)
N1 = len(t1)

duty1  = np.full(N1, 0.5)
vin1   = np.full(N1, 24.0)          # V
rload1 = np.ones(N1) * 10.0         # Ω
rload1[t1 >= 0.025] = 1.0
rload1[t1 >= 0.100] = 10.0

sio.savemat(
    str(OUT_DIR / "vector1_step_load_input.mat"),
    {"t": t1, "duty": duty1, "Vin": vin1, "Rload": rload1},
    do_compression=True,
)
print(f"Saved vector1_step_load_input.mat  ({N1} samples, {T1*1e3:.0f} ms)  vars: t, duty, Vin, Rload")


# ── Vector 2: Vin ramp + sinusoidal duty ─────────────────────────────────────
# Rload = 0.5 Ω constant
# Vin: linear ramp 20 V → 40 V over first 100 ms, then holds at 40 V
# Duty: 100 Hz sinusoid between 40 % and 50 % for full 250 ms
# Duration: 250 ms

T2 = 0.250
t2 = np.arange(0, T2, DT)
N2 = len(t2)

rload2 = np.full(N2, 5.0)                                    # Ω
vin2   = np.minimum(20.0 + (40.0 - 20.0) * t2 / 0.1, 40.0) # V
duty2  = 0.45 + 0.05 * np.sin(2 * np.pi * 100 * t2)         # 40–50 %

sio.savemat(
    str(OUT_DIR / "vector2_ramp_vin_input.mat"),
    {"t": t2, "duty": duty2, "Vin": vin2, "Rload": rload2},
    do_compression=True,
)
print(f"Saved vector2_ramp_vin_input.mat   ({N2} samples, {T2*1e3:.0f} ms)  vars: t, duty, Vin, Rload")
