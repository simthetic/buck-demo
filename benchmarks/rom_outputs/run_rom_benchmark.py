"""
run_rom_benchmark.py
Run ROM simulations for vector1 and vector2 input .mat files and save outputs.

Usage:
    uv run python notebooks/benchmarks/run_rom_benchmark.py
"""

from __future__ import annotations

import base64
import json
import subprocess
import time
from pathlib import Path

import numpy as np
import scipy.io as sio

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DOCKER_IMAGE = "simthetic/my-rom:v1"
ROM_DT_S = 0.00005  # 50 µs (from get_rom_info)

BENCHMARKS_DIR = Path(__file__).parent
INPUT_FILES = {
    "vector1": BENCHMARKS_DIR / "vector1_step_load_input.mat",
    "vector2": BENCHMARKS_DIR / "vector2_ramp_vin_input.mat",
}

# Map .mat variable names → ROM channel names
INPUT_MAP = {
    "duty":  "DC_int",
    "Vin":   "Vin_int",
    "Rload": "Rload_int",
}

OUTPUT_NAMES = ["I_in", "V_in", "I_out", "V_out"]


# ---------------------------------------------------------------------------
# Docker I/O helpers (same protocol as docker_runtime.py)
# ---------------------------------------------------------------------------

def _encode(arr: np.ndarray) -> str:
    return base64.b64encode(
        np.ascontiguousarray(arr, dtype=np.float64).tobytes()
    ).decode("ascii")


def _decode(s: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(s), dtype=np.float64)


def call_docker_run_raw(input_timeseries: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Send a run_raw request to Docker and return decoded output arrays."""
    payload = json.dumps({
        "action": "run_raw",
        "inputs": {name: _encode(arr) for name, arr in input_timeseries.items()},
    }).encode()

    result = subprocess.run(
        ["docker", "run", "--rm", "-i", DOCKER_IMAGE],
        input=payload,
        capture_output=True,
        timeout=300,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Docker error: {result.stderr.decode()}")

    response = json.loads(result.stdout.decode())
    if response.get("status") != "ok":
        raise RuntimeError(f"ROM runner error: {response.get('message', 'unknown')}")

    return {name: _decode(b64) for name, b64 in response["outputs"].items()}


# ---------------------------------------------------------------------------
# Upsampling (zero-order hold: repeat each sample to match ROM dt)
# ---------------------------------------------------------------------------

def zoh_upsample(arr: np.ndarray, input_dt: float) -> np.ndarray:
    """Upsample using zero-order hold to ROM_DT_S resolution."""
    ratio = round(input_dt / ROM_DT_S)
    if ratio == 1:
        return arr
    return np.repeat(arr, ratio)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_vector(name: str, mat_path: Path) -> None:
    print(f"\n{'='*60}")
    print(f"  Running: {name}  ({mat_path.name})")
    print(f"{'='*60}")

    # Load input .mat
    data = sio.loadmat(str(mat_path))
    t_in = data["t"].flatten()
    input_dt = float(t_in[1] - t_in[0])
    n_in = len(t_in)

    print(f"  Input:  {n_in} steps @ {input_dt*1e6:.0f} µs = {t_in[-1]*1000:.1f} ms")

    # Build ROM input timeseries (physical units, upsampled to ROM dt)
    rom_inputs: dict[str, np.ndarray] = {}
    for mat_var, rom_ch in INPUT_MAP.items():
        arr = data[mat_var].flatten().astype(np.float64)
        rom_inputs[rom_ch] = zoh_upsample(arr, input_dt)

    n_steps = len(next(iter(rom_inputs.values())))
    t_rom = np.arange(n_steps) * ROM_DT_S
    print(f"  ROM:    {n_steps} steps @ {ROM_DT_S*1e6:.0f} µs = {t_rom[-1]*1000:.1f} ms")

    # Run simulation and measure wall-clock time
    print("  Calling Docker ... ", end="", flush=True)
    t_start = time.perf_counter()
    outputs = call_docker_run_raw(rom_inputs)
    t_end = time.perf_counter()
    elapsed_s = t_end - t_start
    print(f"done in {elapsed_s:.3f} s")

    # Print summary statistics
    for ch in OUTPUT_NAMES:
        arr = outputs[ch]
        print(f"    {ch:8s}  mean={arr.mean():.4f}  min={arr.min():.4f}  max={arr.max():.4f}")

    # Downsample outputs back to original input dt for alignment (optional)
    # Kept at ROM resolution for full fidelity
    out_mat = {
        "t":           t_rom.reshape(1, -1),
        "elapsed_s":   np.array([[elapsed_s]]),
        "sim_dt_s":    np.array([[ROM_DT_S]]),
        "n_steps":     np.array([[n_steps]]),
    }
    for ch in OUTPUT_NAMES:
        out_mat[ch] = outputs[ch].reshape(1, -1)

    # Mirror input channels at ROM resolution too
    for rom_ch, arr in rom_inputs.items():
        out_mat[f"in_{rom_ch}"] = arr.reshape(1, -1)

    # Save
    out_path = BENCHMARKS_DIR / f"rom_{name}_output.mat"
    sio.savemat(str(out_path), out_mat)
    print(f"  Saved -> {out_path.name}")
    print(f"  Execution time: {elapsed_s:.3f} s  ({elapsed_s*1000:.1f} ms)")


def main() -> None:
    for name, path in INPUT_FILES.items():
        if not path.exists():
            print(f"ERROR: {path} not found, skipping.")
            continue
        run_vector(name, path)
    print("\nAll done.")


if __name__ == "__main__":
    main()
