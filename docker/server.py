"""
server.py — HTTP server bundled into simthetic/my-rom:v1-with-gui.

Runs inside the Docker container. Loads the ROM shared library via the
simthetic_runtime module already present in the base image (/app/src/),
and exposes:

    GET  /                        — the browser GUI (gui/index.html)
    GET  /api/info                — ROM manifest
    POST /api/simulate            — run a simulation (returns inline timeseries)
    POST /api/steady-state        — run to steady state, return settled outputs
    GET  /benchmark/v1.json       — pre-converted V1 benchmark + Simscape ref
    GET  /benchmark/v2.json       — pre-converted V2 benchmark + Simscape ref
    GET  /api/health              — liveness check

The GUI in this repo depends on /api/simulate returning per-sample timeseries
under the `outputs` key (not just outputs_summary). This server honours that
contract.

Static assets live at /app/static/. Benchmark JSONs live at /app/benchmarks/.
The compiled ROM lives at /app/rom/rom.so (set via env SIMTHETIC_ROM_DLL).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# The base image stages simthetic_runtime at /app/src/simthetic_runtime.py.
sys.path.insert(0, "/app/src")
from simthetic_runtime import SimtheticRuntime  # type: ignore  # noqa: E402

ROM_DLL = os.environ.get("SIMTHETIC_ROM_DLL", "/app/rom/rom.so")
STATIC_DIR = Path("/app/static")
BENCH_DIR = Path("/app/benchmarks")
GUI_INDEX = STATIC_DIR / "index.html"

# Load the ROM once at startup and keep it warm across requests.
_runtime = SimtheticRuntime(ROM_DLL)
_runtime.init()

app = FastAPI(title="Simthetic ROM (with GUI)", version="1.0.0")


# ---------------------------------------------------------------------------
# Signal synthesis (self-contained — mirrors src/runtime/signal_generator.py)
# ---------------------------------------------------------------------------

_REQUIRED_PARAMS: dict[str, list[str]] = {
    "constant": ["value"],
    "step":     ["initial", "final", "t_step_s"],
    "sine":     ["offset", "amplitude", "frequency_hz"],
    "ramp":     ["start", "end"],
    "pwm":      ["low", "high", "frequency_hz", "duty_cycle"],
}
_OPTIONAL_PARAMS: dict[str, dict[str, float]] = {"sine": {"phase_deg": 0.0}}


def _make_signal(sig_type: str, params: dict, n: int, dt: float) -> np.ndarray:
    if sig_type not in _REQUIRED_PARAMS:
        raise ValueError(
            f"Unknown signal type '{sig_type}'. "
            f"Valid: {list(_REQUIRED_PARAMS)}"
        )
    missing = [k for k in _REQUIRED_PARAMS[sig_type] if k not in params]
    if missing:
        raise ValueError(f"Signal type '{sig_type}' missing params: {missing}")
    p = {**_OPTIONAL_PARAMS.get(sig_type, {}), **params}
    t = np.arange(n, dtype=np.float64) * dt

    if sig_type == "constant":
        return np.full(n, p["value"], dtype=np.float64)
    if sig_type == "step":
        sig = np.full(n, p["initial"], dtype=np.float64)
        sig[t >= p["t_step_s"]] = p["final"]
        return sig
    if sig_type == "sine":
        phase = np.deg2rad(p["phase_deg"])
        return (
            p["offset"]
            + p["amplitude"]
            * np.sin(2.0 * np.pi * p["frequency_hz"] * t + phase)
        ).astype(np.float64)
    if sig_type == "ramp":
        return np.linspace(p["start"], p["end"], n, dtype=np.float64)
    if sig_type == "pwm":
        period = 1.0 / p["frequency_hz"]
        phase = np.mod(t, period)
        return np.where(
            phase < p["duty_cycle"] * period, p["high"], p["low"]
        ).astype(np.float64)
    raise AssertionError(f"unreachable signal type: {sig_type}")


def _build_input_timeseries(
    manifest: dict,
    constant_inputs: dict[str, float],
    signal_inputs: dict[str, dict],
    duration_s: float,
) -> tuple[dict[str, np.ndarray], int]:
    dt = float(manifest["dt_s"])
    n = max(1, int(round(duration_s / dt)))
    valid = {inp["name"] for inp in manifest["inputs"]}

    overlap = set(constant_inputs) & set(signal_inputs)
    if overlap:
        raise ValueError(f"Channels in both constant and signal: {overlap}")
    unknown = (set(constant_inputs) | set(signal_inputs)) - valid
    if unknown:
        raise ValueError(f"Unknown input channel(s): {unknown}. Valid: {sorted(valid)}")
    missing = valid - (set(constant_inputs) | set(signal_inputs))
    if missing:
        raise ValueError(f"Missing input channel(s): {missing}")

    ts: dict[str, np.ndarray] = {}
    for name, val in constant_inputs.items():
        ts[name] = np.full(n, float(val), dtype=np.float64)
    for name, spec in signal_inputs.items():
        ts[name] = _make_signal(spec.get("type"), spec.get("params", {}), n, dt)
    return ts, n


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------

class SimulateRequest(BaseModel):
    duration_s: float = Field(..., gt=0)
    constant_inputs: dict[str, float] = Field(default_factory=dict)
    signal_inputs: dict[str, dict] = Field(default_factory=dict)


class SteadyStateRequest(BaseModel):
    constant_inputs: dict[str, float]
    max_duration_s: float = 1.0


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict[str, Any]:
    m = _runtime.manifest
    return {
        "status": "ok",
        "system_name": m.get("system_name"),
        "rom_version": m.get("rom_version"),
        "dt_s": m.get("dt_s"),
    }


@app.get("/api/info")
def info() -> dict[str, Any]:
    """Full ROM manifest (channels, units, operating ranges)."""
    return _runtime.manifest


@app.post("/api/simulate")
def simulate(req: SimulateRequest) -> dict[str, Any]:
    """
    Run a simulation and return both per-channel summary stats AND the
    per-sample timeseries inline under `outputs`. The GUI relies on the
    inline `outputs` shape.
    """
    manifest = _runtime.manifest
    try:
        ts, n = _build_input_timeseries(
            manifest, req.constant_inputs, req.signal_inputs, req.duration_s
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    t0 = time.perf_counter()
    try:
        raw = _runtime.run_raw(ts)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"ROM run failed: {exc}") from exc
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    out_arrays = raw["outputs"]
    dt_s = float(raw["dt_s"])

    summary: dict[str, dict[str, float | str]] = {}
    output_units = {o["name"]: o.get("unit", "") for o in manifest.get("outputs", [])}
    for name, arr in out_arrays.items():
        a = np.asarray(arr, dtype=np.float64)
        summary[name] = {
            "mean": float(a.mean()),
            "std":  float(a.std()),
            "min":  float(a.min()),
            "max":  float(a.max()),
            "unit": output_units.get(name, ""),
        }

    t_axis = (np.arange(n, dtype=np.float64) * dt_s).tolist()
    outputs_inline: dict[str, list[float]] = {"t": t_axis}
    for name, arr in out_arrays.items():
        outputs_inline[name] = np.asarray(arr, dtype=np.float64).tolist()

    return {
        "status": "success",
        "dt_s": dt_s,
        "n_steps": int(n),
        "duration_s": req.duration_s,
        "elapsed_ms": elapsed_ms,
        "outputs_summary": summary,
        "outputs": outputs_inline,
    }


@app.post("/api/steady-state")
def steady_state(req: SteadyStateRequest) -> dict[str, Any]:
    manifest = _runtime.manifest
    try:
        ts, n = _build_input_timeseries(
            manifest, req.constant_inputs, {}, req.max_duration_s
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    t0 = time.perf_counter()
    raw = _runtime.run_raw(ts)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    # Average the last 10 % as a steady-state estimate.
    tail = max(10, n // 10)
    ss_values: dict[str, float] = {}
    outputs_at_end: dict[str, float] = {}
    output_units = {o["name"]: o.get("unit", "") for o in manifest.get("outputs", [])}
    for name, arr in raw["outputs"].items():
        a = np.asarray(arr, dtype=np.float64)
        ss_values[name] = float(a[-tail:].mean())
        outputs_at_end[name] = float(a[-1])

    return {
        "status": "success",
        "converged": True,
        "ss_values": ss_values,
        "outputs_at_end": outputs_at_end,
        "elapsed_ms": elapsed_ms,
        "n_steps": int(n),
        "units": output_units,
    }


@app.get("/benchmark/{tag}.json")
def benchmark(tag: str) -> JSONResponse:
    if tag not in ("v1", "v2"):
        raise HTTPException(status_code=404, detail="Unknown benchmark tag")
    path = BENCH_DIR / f"{tag}.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Benchmark {tag}.json not present in image",
        )
    return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))


# Static GUI — must be mounted LAST so it doesn't shadow API routes.
@app.get("/")
def index() -> FileResponse:
    if not GUI_INDEX.exists():
        raise HTTPException(status_code=404, detail="GUI index.html missing from image")
    return FileResponse(str(GUI_INDEX), media_type="text/html")


# Mount the rest of the GUI assets (logo.png, etc.) under root paths.
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/{asset_name}")
def gui_asset(asset_name: str) -> FileResponse:
    """Serve top-level GUI assets like logo.png from /."""
    if "/" in asset_name or asset_name.startswith("."):
        raise HTTPException(status_code=404)
    asset = STATIC_DIR / asset_name
    if not asset.exists() or not asset.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(str(asset))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
