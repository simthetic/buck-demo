# Simthetic — Buck Converter ROM (Public Demo)

**Run a 30× faster surrogate of a MATLAB/Simscape DCDC buck converter as a single Docker container — and talk to it in plain English from Claude Code.**

This repo is the public demo kit for Simthetic's Hybrid Reduced Order Models (ROMs). It pairs the production `simthetic/my-rom:v1` Docker image with a browser GUI, a benchmark reproducibility kit, and a working Claude Code (MCP) integration.

---

## What this is, in 30 seconds

- A **shipped ROM**: `BUCK_HYBRID_MLP v2026-03-21-001`, trained on a single-phase DCDC buck converter (`Vin ∈ [10, 45] V`, `Rload ∈ [1, 10] Ω`, `DC ∈ [0.2, 0.8]`), `dt = 50 µs`.
- A **measured 28–31× speedup** vs. MATLAB/Simscape at < 1.2 % MAE on `V_out` and < 2.6 % MAE on `I_out` across two stress-test vectors. See [`docs/ST-DS-2026-001.pdf`](docs/ST-DS-2026-001.pdf) and the reproducibility kit in [`benchmarks/`](benchmarks/).
- A **clean REST API** + **browser GUI** + **MCP server** — all three driving the same container.

---

## Talk to your converter — Claude Code + MCP

Drop the included [`.mcp.json`](.mcp.json) into any project, open Claude Code, and ask:

> *"Run a 50 ms simulation with Vin = 36 V, DC = 0.5, Rload = 5 Ω and show me V_out."*
>
> *"What's the output current settling time after a step from Rload = 5 Ω to 2 Ω at t = 20 ms?"*
>
> *"Sweep DC from 0.3 to 0.7 in 5 points and tell me where V_out crosses 18 V."*

Claude calls the running container via MCP, parameterises the ROM, reads the result, and answers in natural language. No simulator licence, no MATLAB, no Python notebook — just a chat window.

Full setup: [`docs/MCP_INTEGRATION.md`](docs/MCP_INTEGRATION.md).

---

## Quickstart — one command

```bash
docker pull simthetic/my-rom:v1-with-gui
docker run -p 8000:8000 simthetic/my-rom:v1-with-gui
# open http://localhost:8000
```

The `v1-with-gui` image bundles the compiled ROM, the REST API, the browser GUI, and the pre-converted Simscape reference traces for the two published benchmark vectors. No additional setup.

> The base `simthetic/my-rom:v1` image is the headless stdin/stdout worker used by the MCP server. If you only want the REST/GUI experience, pull `v1-with-gui`. If you want to drive the worker programmatically from your own code, pull `v1`.

---

## Live cloud demo

A hosted version is available at **<https://simthetic.io/demo>**.

Same GUI, same ROM, rate-limited. Use this if you don't want to install Docker.

---

## Reproduce the datasheet numbers

Every number in `docs/ST-DS-2026-001.pdf` was produced from the files in [`benchmarks/`](benchmarks/). To re-derive them on your machine:

1. Pull the ROM image: `docker pull simthetic/my-rom:v1`
2. Run `benchmarks/rom_outputs/run_rom_benchmark.py` to regenerate the ROM outputs.
3. (Optional) Run `benchmarks/simscape_outputs/run_simscape_benchmark.m` and `export_simscape_results.m` in MATLAB to regenerate the Simscape reference traces.
4. Open `benchmarks/buck_accuracy_benchmark.ipynb` to recompute the accuracy metrics.

See [`benchmarks/README.md`](benchmarks/README.md) for details.

---

## Repository layout

```
simthetic-public/
├── README.md                 ← you are here
├── LICENSE                   ← MIT (covers everything in this repo)
├── LICENSE-NOTICE.md         ← ROM binary licence (separate, evaluation-only)
├── .mcp.json                 ← drop into your project for Claude Code integration
├── benchmarks/               ← datasheet reproducibility kit
│   ├── README.md
│   ├── buck_accuracy_benchmark.ipynb
│   ├── input_vectors/        ← published benchmark inputs (.mat + generator)
│   ├── rom_outputs/          ← ROM outputs + runner script
│   ├── simscape_outputs/     ← Simscape reference outputs + MATLAB scripts
│   ├── benchmark_v1.png      ← V1 accuracy plot from the datasheet
│   └── benchmark_v2.png      ← V2 accuracy plot from the datasheet
├── docker/
│   ├── Dockerfile.gui-extension      ← builds simthetic/my-rom:v1-with-gui
│   ├── server.py                     ← HTTP server bundled into the image
│   └── convert_simscape_to_json.py   ← build-time benchmark JSON converter
├── docs/
│   ├── DCDC_BUCK_ACCURACY_BENCHMARK.md
│   ├── MCP_INTEGRATION.md
│   ├── REST_API.md
│   └── ST-DS-2026-001.pdf
├── gui/
│   ├── index.html            ← the browser GUI served at http://localhost:8000/
│   └── logo.png
└── scripts/
    └── mcp_bridge.py         ← MCP stdio server wrapping the REST API
```

---

## License & commercial use

- **Repo contents** (GUI, scripts, docs, benchmark inputs, MCP bridge) — MIT, see [`LICENSE`](LICENSE).
- **ROM binary** inside the Docker image (`rom.so`) — *not* MIT. Distributed under the **Simthetic Evaluation License**: free for local evaluation and benchmarking; a commercial licence is required for production deployment or redistribution. See [`LICENSE-NOTICE.md`](LICENSE-NOTICE.md).
- For pilot benchmarks on your own topology, or for commercial licensing: **<contact@simthetic.io>**.

---

## Get in touch

We build custom ROMs for power electronics, drives, batteries, and thermal systems. If you have a Simscape, PLECS, or first-principles model that is too slow for your control-design loop, HiL bench, or digital-twin product — we want to hear from you.

- Pilot benchmarks: **<contact@simthetic.io>**
- Web: **<https://simthetic.io>**
