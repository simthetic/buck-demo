# Talk to the ROM with Claude Code — MCP integration

This guide walks you through wiring the running Docker ROM into [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) so you can drive simulations from natural-language prompts.

The MCP server in this repo is **a thin Python bridge that wraps the ROM's REST API**. It's deliberately minimal (~150 lines) so you can read it, audit it, and modify it. The full-featured MCP server in the main Simthetic repo has more tools (sessions, hook-based control loops, custom plotting); this bridge exposes the three tools that cover 90 % of interactive use.

## 1. Prerequisites

| Tool | Version | Why |
|---|---|---|
| Docker | any recent | To run the ROM container |
| Python | ≥ 3.10 | For the MCP bridge script |
| [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) | latest | The MCP client |

Install the one Python dependency the bridge needs:

```bash
pip install httpx mcp
```

## 2. Start the ROM container

```bash
docker pull simthetic/my-rom:v1-with-gui
docker run -d --name simthetic-rom -p 8000:8000 simthetic/my-rom:v1-with-gui
```

Verify it's up:

```bash
curl http://localhost:8000/api/info
```

You should see a JSON manifest listing the inputs (`Vin_int`, `Rload_int`, `DC_int`) and outputs (`V_out`, `I_out`, `V_in`, `I_in`).

## 3. Drop `.mcp.json` into your project

This repo already contains a working `.mcp.json` at the root. Copy it into the project directory where you'll run Claude Code (or merge with an existing `.mcp.json`).

```json
{
  "mcpServers": {
    "simthetic-rom": {
      "type": "stdio",
      "command": "python",
      "args": ["scripts/mcp_bridge.py", "--base-url", "http://localhost:8000"]
    }
  }
}
```

The bridge script lives at [`scripts/mcp_bridge.py`](../scripts/mcp_bridge.py) in this repo. If you place `.mcp.json` somewhere else, adjust the path to the script (absolute paths work too).

Restart Claude Code in that directory. It will discover the `simthetic-rom` MCP server and expose its three tools:

- `get_rom_info` — returns the ROM manifest (channels, units, operating ranges, timestep)
- `run_simulation` — runs a finite-duration simulation with constant + signal inputs
- `get_steady_state` — runs to steady state and returns settled output values

## 4. Three prompts to try

### Prompt 1 — "Show me a transient"

> Run a 50 ms simulation with Vin = 36 V, DC = 0.5, Rload = 5 Ω and show me V_out.

What happens:
1. Claude calls `get_rom_info` to learn the channel names.
2. Claude calls `run_simulation` with `duration_s = 0.05`, `constant_inputs = {Vin_int: 36, DC_int: 0.5, Rload_int: 5}`.
3. The bridge forwards the request to `POST /api/simulate` on the container.
4. The container runs the ROM (≈ 0.5 s wall-clock for 50 ms simulated) and returns inline timeseries plus a summary.
5. Claude renders or summarises the V_out trace.

### Prompt 2 — "Find a steady-state point"

> What's the steady-state output voltage at Vin = 24 V, DC = 0.4, Rload = 2 Ω?

Expected result: Claude calls `get_steady_state`, the ROM runs out to settlement, the bridge returns `ss_values`, and Claude answers something like *"V_out settles at 9.58 V (I_out = 4.79 A) after ≈ 8 ms"*.

### Prompt 3 — "Compare two operating points"

> Compare a step-load response between Rload = 5 Ω and 2 Ω at t = 20 ms (Vin = 24 V, DC = 0.5). Show the settling time on V_out for both.

Expected behaviour: Claude issues two `run_simulation` calls (or one with a `step` signal on `Rload_int`), reads the resulting traces, computes a 2 % settling-time band on V_out, and reports the difference between the two cases. The bridge passes a `step` signal type through to the ROM:

```json
{
  "duration_s": 0.1,
  "constant_inputs": {"Vin_int": 24, "DC_int": 0.5},
  "signal_inputs": {
    "Rload_int": {"type": "step", "params": {"initial": 5.0, "final": 2.0, "t_step_s": 0.02}}
  }
}
```

## 5. Supported signal types

For time-varying inputs, the ROM accepts these `signal_inputs` entries (mirrors the REST API):

| Type | Required params |
|---|---|
| `constant` | `value` |
| `step` | `initial`, `final`, `t_step_s` |
| `ramp` | `start`, `end` |
| `sine` | `offset`, `amplitude`, `frequency_hz` (optional `phase_deg`) |
| `pwm` | `low`, `high`, `frequency_hz`, `duty_cycle` |

Every ROM input channel must appear in exactly one of `constant_inputs` or `signal_inputs`. Claude will figure this out from `get_rom_info`.

## 6. Troubleshooting

- **`Connection refused` from the bridge** — make sure the container is running and port 8000 is mapped. `docker ps` should show `simthetic-rom`.
- **`Unknown input channel` errors** — Claude is hallucinating a channel name. Force it to call `get_rom_info` first by saying *"first list the input channels then run…"*.
- **`HTTP 400: out of envelope`** — the requested operating point is outside the trained range (`Vin ∈ [10, 45] V`, `Rload ∈ [1, 10] Ω`, `DC ∈ [0.2, 0.8]`). Either change the prompt or ask for a re-fit.
- **Claude doesn't see the server** — check `.mcp.json` syntax, restart Claude Code in the same directory, and watch `claude --debug mcp` if needed.

## 7. Going further

The bridge in this repo is intentionally minimal. The main Simthetic repo ships a richer MCP server with:

- Stateful sessions (drive the ROM step-by-step from your code)
- Custom Python hooks (closed-loop control, PI/PID, adaptive setpoints)
- Plot regeneration
- Docker image management

Contact [contact@simthetic.io](mailto:contact@simthetic.io) if you want access to the full server for your evaluation.
