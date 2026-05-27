# Simthetic ROM REST API

The REST API exposes the Hybrid ROM over HTTP, opening it to CI pipelines,
HiL co-simulation, web dashboards, and any HTTP client — no MCP SDK required.

It wraps the same Docker image used by the MCP server. All ROM computation
still happens inside the container; the API server is a thin host-side
coordinator.

---

## Quick Start

### 1. Start the server

```bash
uv run python -m src.rest_api --image simthetic/my-rom:v1
```

The server starts on `http://0.0.0.0:8000`.  
Interactive OpenAPI docs: **http://localhost:8000/docs**

### 2. Health check

```bash
curl http://localhost:8000/api/health
```

```json
{
  "status": "ok",
  "system_name": "BUCK_HYBRID_MLP",
  "rom_version": "2026-03-21-001",
  "dt_s": 5e-05,
  "n_inputs": 3,
  "n_outputs": 4
}
```

### 3. Run a simulation

```bash
curl -X POST http://localhost:8000/api/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "duration_s": 0.05,
    "constant_inputs": {"Vin_int": 40.0, "Rload_int": 5.0},
    "signal_inputs": {
      "DC_int": {"type": "step", "params": {"initial": 0.3, "final": 0.6, "t_step_s": 0.01}}
    }
  }'
```

```json
{
  "run_id": "20260406_143022_123456",
  "n_steps": 1000,
  "duration_s": 0.05,
  "dt_s": 5e-05,
  "ss_detected": true,
  "ss_values": {"V_out": 24.1, "I_out": 4.8},
  "t_settle_s": 0.032,
  "peak_values": {"V_out": 25.3, "I_out": 5.1},
  "files": {
    "plot": "http://localhost:8000/api/results/buck_hybrid_mlp/20260406_143022_123456/plot",
    "json": "http://localhost:8000/api/results/buck_hybrid_mlp/20260406_143022_123456/data?format=json",
    "mat":  "http://localhost:8000/api/results/buck_hybrid_mlp/20260406_143022_123456/data?format=mat"
  }
}
```

---

## CLI Reference

```
uv run python -m src.rest_api [OPTIONS]

Required:
  --image TAG          Docker image tag (e.g. simthetic/my-rom:v1)

Optional:
  --work-dir DIR       Output directory (default: current working directory)
  --host HOST          Bind address (default: 0.0.0.0)
  --port PORT          Listen port (default: 8000)
  --session-ttl SECS   Idle session timeout in seconds (default: 3600)
  --reload             Enable uvicorn auto-reload (development only)
```

---

## Endpoint Reference

### Group 1: ROM Metadata

#### `GET /api/health`
Server status and ROM identity.

#### `GET /api/info`
Full ROM manifest: all input/output channels with names, units, physical
ranges, scaling factors, timestep, and NN architecture.

#### `GET /api/signals`
Available signal types for `signal_inputs` and their required parameters.

---

### Group 2: Batch Simulation

All simulation endpoints accept physical units as specified by the manifest.
The server normalises inputs and denormalises outputs automatically.

#### `POST /api/simulate`

Run a simulation with signal-based inputs.

**Request body:**
```json
{
  "duration_s": 0.05,
  "constant_inputs": {"Vin_int": 40.0, "Rload_int": 5.0},
  "signal_inputs": {
    "DC_int": {
      "type": "step",
      "params": {"initial": 0.3, "final": 0.6, "t_step_s": 0.01}
    }
  }
}
```

- Every ROM input channel must appear in exactly one of `constant_inputs`
  or `signal_inputs`.
- Short simulations (≤500k steps) return `200` + `RunSummary` immediately.
- Long simulations return `202` + `JobStatus` with a `job_id` — poll
  `GET /api/jobs/{job_id}` until `status == "completed"`.

**Signal types:**

| Type | Required params |
|------|----------------|
| `constant` | `value` |
| `step` | `initial`, `final`, `t_step_s` |
| `sine` | `offset`, `amplitude`, `frequency_hz` |
| `ramp` | `start`, `end` |
| `pwm` | `low`, `high`, `frequency_hz`, `duty_cycle` |

#### `POST /api/simulate/hook`

Run a closed-loop simulation with a custom Python hook executed before
every ROM step.

**Request body:**
```json
{
  "duration_s": 0.1,
  "constant_inputs": {"Vin_int": 40.0, "Rload_int": 5.0},
  "initial_inputs": {"DC_int": 0.5},
  "hook_code": "def hook(step_idx, t_s, dt_s, last_outputs, inputs, state):\n    if last_outputs is None:\n        return inputs\n    error = 12.0 - last_outputs['V_out']\n    state['i'] = state.get('i', 0.0) + error * dt_s\n    inputs['DC_int'] = max(0.2, min(0.8, 0.1*error + 5.0*state['i']))\n    return inputs"
}
```

The hook runs **inside Docker**; only `numpy` (as `np`) is available.
No Docker rebuild needed — the hook is sent in the request payload.

Hook signature:
```python
def hook(step_idx, t_s, dt_s, last_outputs, inputs, state):
    # last_outputs is None at step 0
    # state persists across steps (use for integrators, filters, etc.)
    return inputs  # modified dict
```

#### `POST /api/steady-state`

Run to steady state and return settled output values.

**Request body:**
```json
{
  "constant_inputs": {"DC_int": 0.5, "Vin_int": 40.0, "Rload_int": 5.0},
  "max_duration_s": 1.0
}
```

---

### Group 3: Results & Files

After any simulation, results are saved to:
```
<work_dir>/tmp/<rom_id>/<run_id>/
    sim.json       — full result (always present)
    sim.mat        — MATLAB v5 data
    sim_plot.png   — time-series plot
    sim.csv        — CSV (generated on demand)
```

#### `GET /api/results/{rom_id}/{run_id}`
Result metadata summary.

#### `GET /api/results/{rom_id}/{run_id}/plot`
Download the plot PNG.

#### `GET /api/results/{rom_id}/{run_id}/data?format=json|mat|csv`
Download simulation data. CSV is generated on demand if not yet present.

#### `POST /api/results/{rom_id}/{run_id}/plot`
Regenerate the plot with custom options.

```json
{
  "channels": ["V_out", "I_out"],
  "title": "Step response",
  "show_inputs": true
}
```

---

### Group 4: Stateful Sessions

Sessions keep a persistent Docker container alive for step-by-step
execution. Use this for HiL co-simulation, MATLAB cosim, RL environments,
or any workflow that interleaves ROM steps with external logic.

#### `POST /api/sessions`
Create a session (starts a container). Returns `session_id`.

```json
{ "initial_inputs": null }
```

Response (`201 Created`):
```json
{
  "session_id": "a3f9b2c1d4e5",
  "created_at": "2026-04-06T14:30:22Z",
  "last_active": "2026-04-06T14:30:22Z",
  "step_count": 0,
  "rom_info": {"system_name": "BUCK_HYBRID_MLP", "dt_s": 5e-05, ...}
}
```

#### `POST /api/sessions/{session_id}/step`
Execute one ROM timestep.

```json
{ "inputs": {"DC_int": 0.5, "Vin_int": 40.0, "Rload_int": 5.0} }
```

Response:
```json
{ "outputs": {"V_out": 12.1, "I_out": 2.4}, "step_count": 1, "t_s": 5e-05 }
```

#### `GET /api/sessions/{session_id}/state`
Export the internal ROM state vector (for branching / rollback).

#### `PUT /api/sessions/{session_id}/state`
Restore state from a saved snapshot.

```json
{ "state": [0.12, -0.03, 0.45, 0.87] }
```

#### `DELETE /api/sessions/{session_id}`
Terminate the container and free resources. Always call this when finished.

#### `GET /api/sessions`
List all active sessions.

---

### Group 5: Async Jobs

#### `GET /api/jobs/{job_id}`

Poll a long-running simulation job.

```json
{
  "job_id": "a1b2c3d4e5f6",
  "status": "completed",
  "created_at": "2026-04-06T14:30:00Z",
  "completed_at": "2026-04-06T14:30:45Z",
  "result": { ...RunSummary... },
  "error": null
}
```

---

### Group 6: Infrastructure

#### `POST /api/build?tag=simthetic/my-rom:v1&no_cache=false`
Build or rebuild the Docker image. Runs `docker build` on the host.

---

## Session Lifecycle

```
POST /api/sessions          → session_id
POST /api/sessions/{id}/step  (repeat N times)
GET  /api/sessions/{id}/state → save snapshot
POST /api/sessions/{id}/step  (branch A)
PUT  /api/sessions/{id}/state → restore snapshot
POST /api/sessions/{id}/step  (branch B)
DELETE /api/sessions/{id}   → free container
```

---

## Async Job Pattern

```python
import requests, time

# Submit long simulation
resp = requests.post("http://localhost:8000/api/simulate", json={
    "duration_s": 10.0,
    "constant_inputs": {...},
    "signal_inputs": {...},
})
if resp.status_code == 202:
    job_id = resp.json()["job_id"]
    # Poll until done
    while True:
        status = requests.get(f"http://localhost:8000/api/jobs/{job_id}").json()
        if status["status"] in ("completed", "failed"):
            break
        time.sleep(1.0)
    result = status["result"]
```

---

## CI/CD Integration Example

```yaml
# .github/workflows/rom-regression.yml
name: ROM Regression

on: [push]

jobs:
  simulate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Start ROM API server
        run: |
          uv run python -m src.rest_api --image simthetic/my-rom:v1 --port 8000 &
          sleep 5  # wait for startup

      - name: Run step response regression
        run: |
          python tests/regression/test_step_response.py

      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: sim-results
          path: tmp/
```

---

## vs. MCP Interface

| | MCP Server | REST API |
|---|---|---|
| Transport | stdio (LLM agents only) | HTTP (any client) |
| Signal generation | On-host, spec-based | On-host, spec-based |
| Stateful sessions | No | Yes (persistent Docker) |
| Result files | Host filesystem | HTTP download |
| Hook simulation | Yes | Yes |
| CI/CD integration | No | Yes |
| Authentication | None (local) | None V1 (use reverse proxy) |

Both interfaces use the same Docker image and the same runtime code.
There is no functional difference in simulation accuracy.

---

## Notes

- **No authentication** in V1. For production exposure, place behind a
  reverse proxy (nginx, Caddy) with appropriate auth.
- **Result files persist** in `<work_dir>/tmp/` until manually deleted.
  Add a cron job or CI step to prune old runs if disk space is a concern.
- **Sessions are in-memory**: restarting the server terminates all active
  sessions. Build your client to handle reconnection gracefully.
