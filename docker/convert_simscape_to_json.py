"""
convert_simscape_to_json.py — Build-time converter for Simscape .mat → JSON.

Reads the two Simscape reference .mat files in `benchmarks/simscape_outputs/`
and produces `v1.json` and `v2.json` in the schema the GUI expects:

    {
      "duration_s": 0.250,
      "dt_s": 5e-5,
      "inputs": {
        "constant_inputs": {...},
        "signal_inputs":   {...}
      },
      "reference": {
        "t":     [...],
        "V_in":  [...],
        "V_out": [...],
        "I_in":  [...],
        "I_out": [...]
      },
      "simscape_time_s": 23.384
    }

The Simscape .mat files store data as MATLAB timeseries objects (MCOS) — the
raw float arrays live under `#refs#/<slot>`. The slot mapping below was
derived (and verified) in `benchmarks/buck_accuracy_benchmark.ipynb` (the
`SIM_REF_MAP` constant).

Reference traces are decimated to the ROM's 50 µs grid (every 10th sample of
the 5 µs Simscape signal) to keep the JSON small (~5000 samples instead of
~50000).

Usage
-----
    python convert_simscape_to_json.py <in_dir> <out_dir>

    in_dir must contain v1.mat and v2.mat (Simscape outputs).
    out_dir will be created if needed and will contain v1.json + v2.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import h5py
import numpy as np


# Slot mapping in #refs# — same for v1.mat and v2.mat because both come from
# the same Simulink model with the same logging order:
#   V_in_set → V_in → Duty_Cyle → R_load → V_out → I_out → I_in
SIM_REF_MAP: dict[str, str] = {
    "V_in_set":  "6b",
    "V_in":      "W",
    "Duty_Cyle": "y",
    "R_load":    "kb",
    "V_out":     "rc",
    "I_out":     "Hb",
    "I_in":      "Nc",
}

# Reference-side Simscape execution wall-clock times — measured on the
# workstation that produced the original .mat files.
SIMSCAPE_TIME_S: dict[str, float] = {
    "v1": 23.384,
    "v2": 22.606,
}

# Duration of both reference traces. Both vectors are 250 ms long.
DURATION_S = 0.250

# ROM timestep — used to decimate the dense Simscape trace to a chart-friendly
# resolution. The decimated reference still matches the published accuracy
# numbers because the underlying signals are slow vs. 50 µs.
ROM_DT_S = 5e-5
DECIMATION = 10  # Simscape ~5 µs → keep every 10th sample → 50 µs

# Inputs that produced each reference. These mirror the canonical generator
# in `benchmarks/input_vectors/generate_input_vectors.py`.
INPUTS_V1: dict[str, dict] = {
    "constant_inputs": {
        "Vin_int": 24.0,
        "DC_int":  0.5,
    },
    # Rload: 10 → 1 at t=25 ms → 10 at t=100 ms.
    # The benchmark JSON contract only carries one step per signal; for the
    # double-step case we serialise the first step and let the GUI overlay the
    # full Simscape reference for shape comparison.
    "signal_inputs": {
        "Rload_int": {
            "type": "step",
            "params": {"initial": 10.0, "final": 1.0, "t_step_s": 0.025},
        }
    },
}

INPUTS_V2: dict[str, dict] = {
    "constant_inputs": {
        "Rload_int": 5.0,
    },
    # Vin: linear ramp 20 → 40 V over the first 100 ms (then held at 40 V).
    # DC:  100 Hz sine, offset 0.45, amplitude 0.05.
    "signal_inputs": {
        "Vin_int": {
            "type": "ramp",
            "params": {"start": 20.0, "end": 40.0},
        },
        "DC_int": {
            "type": "sine",
            "params": {"offset": 0.45, "amplitude": 0.05, "frequency_hz": 100.0},
        },
    },
}

VECTOR_INPUTS: dict[str, dict] = {"v1": INPUTS_V1, "v2": INPUTS_V2}


def _load_simscape_reference(mat_path: Path) -> dict[str, np.ndarray]:
    """Return decimated reference arrays keyed by canonical signal names."""
    out: dict[str, np.ndarray] = {}
    with h5py.File(str(mat_path), "r") as h:
        for name, slot in SIM_REF_MAP.items():
            out[name] = h[f"#refs#/{slot}"][:].ravel()
    n = len(out["V_out"])
    t = np.linspace(0.0, DURATION_S * (n - 1) / n, n)
    # Decimate everything by DECIMATION.
    sl = slice(None, None, DECIMATION)
    out["t"] = t[sl]
    for k in list(out):
        if k == "t":
            continue
        out[k] = out[k][sl]
    return out


def _build_json(tag: str, ref: dict[str, np.ndarray]) -> dict:
    return {
        "tag": tag,
        "duration_s": DURATION_S,
        "dt_s": ROM_DT_S,
        "inputs": VECTOR_INPUTS[tag],
        "reference": {
            "t":     ref["t"].tolist(),
            "V_in":  ref["V_in"].tolist(),
            "V_out": ref["V_out"].tolist(),
            "I_in":  ref["I_in"].tolist(),
            "I_out": ref["I_out"].tolist(),
        },
        "simscape_time_s": SIMSCAPE_TIME_S[tag],
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: convert_simscape_to_json.py <in_dir> <out_dir>", file=sys.stderr)
        return 2
    in_dir = Path(argv[1])
    out_dir = Path(argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    for tag in ("v1", "v2"):
        mat_path = in_dir / f"{tag}.mat"
        if not mat_path.exists():
            print(f"error: {mat_path} not found", file=sys.stderr)
            return 1
        ref = _load_simscape_reference(mat_path)
        out = _build_json(tag, ref)
        out_path = out_dir / f"{tag}.json"
        out_path.write_text(json.dumps(out), encoding="utf-8")
        n = len(ref["t"])
        kb = out_path.stat().st_size / 1024
        print(f"  wrote {out_path}  ({n} samples, {kb:.1f} KB)")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
