"""
mcp_bridge.py — Tiny MCP stdio server wrapping the Simthetic ROM REST API.

The full-featured MCP server lives in the main Simthetic source tree and
talks to the ROM container over stdin/stdout. This public bridge is much
smaller: it speaks MCP on stdio and forwards every tool call to the
`simthetic/my-rom:v1-with-gui` container's HTTP API on localhost:8000.

It exposes the three tools that cover the vast majority of interactive use:

    get_rom_info        → GET  /api/info
    run_simulation      → POST /api/simulate
    get_steady_state    → POST /api/steady-state

Requirements
------------
    pip install httpx mcp

Usage
-----
    python scripts/mcp_bridge.py --base-url http://localhost:8000

…or, more commonly, wired into Claude Code via the repo's `.mcp.json`.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP


def _base_url() -> str:
    """Resolve the ROM REST base URL from CLI args or environment."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--base-url", default=None)
    args, _ = parser.parse_known_args()
    return (
        args.base_url
        or os.environ.get("SIMTHETIC_ROM_URL")
        or "http://localhost:8000"
    )


BASE_URL = _base_url()
HTTP_TIMEOUT = 600.0  # seconds — long enough for any in-envelope simulation

mcp = FastMCP(
    name="Simthetic ROM (public bridge)",
    instructions=(
        "You have access to a Simthetic Hybrid ROM running as a Docker "
        "container exposed over HTTP at "
        f"{BASE_URL}. "
        "Always call get_rom_info first to learn the exact input/output "
        "channel names, units, and operating ranges. Never guess signal "
        "names or physical ranges. Construct run_simulation calls with "
        "every input channel covered exactly once across constant_inputs "
        "and signal_inputs."
    ),
)


def _client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=HTTP_TIMEOUT)


def _raise_for_status(resp: httpx.Response) -> None:
    if resp.is_success:
        return
    try:
        detail = resp.json()
    except Exception:
        detail = resp.text
    raise RuntimeError(f"HTTP {resp.status_code} from {resp.url}: {detail}")


# ---------------------------------------------------------------------------
# Tool: get_rom_info
# ---------------------------------------------------------------------------

@mcp.tool()
def get_rom_info() -> dict[str, Any]:
    """
    Return the ROM manifest: system name, ROM version, sample time, list of
    input channels (with names, units, physical operating ranges) and output
    channels.

    Always call this first before constructing any simulation request — it
    tells you the exact channel names and the legal range for every input.
    """
    with _client() as c:
        r = c.get("/api/info")
    _raise_for_status(r)
    return r.json()


# ---------------------------------------------------------------------------
# Tool: run_simulation
# ---------------------------------------------------------------------------

@mcp.tool()
def run_simulation(
    duration_s: float,
    constant_inputs: dict[str, float],
    signal_inputs: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """
    Run the ROM for a given duration with the supplied input profile.

    Parameters
    ----------
    duration_s : float
        Total simulation duration in seconds. The ROM's fixed timestep
        (typically 50 µs) sets the resolution.
    constant_inputs : dict[str, float]
        Input channels held at a constant physical value throughout.
        Example: {"Vin_int": 24.0, "Rload_int": 5.0}
    signal_inputs : dict[str, dict] or None
        Time-varying input channels. Each value is
        {"type": "<signal_type>", "params": {<params>}}.
        Supported signal types:
            constant — params: {value}
            step     — params: {initial, final, t_step_s}
            ramp     — params: {start, end}
            sine     — params: {offset, amplitude, frequency_hz}
            pwm      — params: {low, high, frequency_hz, duty_cycle}
        Example: {"DC_int": {"type": "step",
                              "params": {"initial": 0.4, "final": 0.6,
                                         "t_step_s": 0.02}}}

    Every ROM input channel must appear in exactly one of constant_inputs or
    signal_inputs. Call get_rom_info() to see the channel names.

    Returns
    -------
    A dict with:
        outputs_summary : per-channel mean/std/min/max
        outputs         : full per-sample timeseries (t, plus each output channel)
        dt_s            : ROM timestep
        n_steps         : number of samples
        elapsed_ms      : wall-clock execution time on the ROM
    """
    body: dict[str, Any] = {
        "duration_s": duration_s,
        "constant_inputs": constant_inputs,
        "signal_inputs": signal_inputs or {},
    }
    with _client() as c:
        r = c.post("/api/simulate", json=body)
    _raise_for_status(r)
    return r.json()


# ---------------------------------------------------------------------------
# Tool: get_steady_state
# ---------------------------------------------------------------------------

@mcp.tool()
def get_steady_state(
    constant_inputs: dict[str, float],
    max_duration_s: float = 1.0,
) -> dict[str, Any]:
    """
    Run the ROM out to steady state and return the settled output values.

    Faster than run_simulation for operating-point queries — internally the
    ROM stops as soon as all outputs have settled.

    Parameters
    ----------
    constant_inputs : dict[str, float]
        All ROM input channels at their desired operating point. Must cover
        every input channel — call get_rom_info() to see the names.
    max_duration_s : float
        Hard upper bound on simulated time (default 1.0 s).

    Returns
    -------
    A dict with:
        converged       : True if the ROM detected steady state
        ss_values       : steady-state value for each output channel
        t_settle_s      : settling time in seconds (None if not converged)
        outputs_at_end  : raw final-step values (use if not converged)
    """
    body = {
        "constant_inputs": constant_inputs,
        "max_duration_s": max_duration_s,
    }
    with _client() as c:
        r = c.post("/api/steady-state", json=body)
    _raise_for_status(r)
    return r.json()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Probe the API once so we fail loudly if the container isn't up.
    try:
        with _client() as c:
            r = c.get("/api/info")
            r.raise_for_status()
    except Exception as exc:
        sys.stderr.write(
            f"[simthetic mcp_bridge] Cannot reach ROM API at {BASE_URL}.\n"
            f"[simthetic mcp_bridge] Did you `docker run -p 8000:8000 "
            "simthetic/my-rom:v1-with-gui`?\n"
            f"[simthetic mcp_bridge] Underlying error: {exc}\n"
        )
        sys.exit(1)
    mcp.run()


if __name__ == "__main__":
    main()
