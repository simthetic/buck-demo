# Benchmarks — datasheet reproducibility kit

This folder contains the exact files used to produce every number in
[`docs/ST-DS-2026-001.pdf`](../docs/ST-DS-2026-001.pdf). Run the steps below
and you should land within rounding of the published metrics.

## What's in here

| File | What it is |
|---|---|
| `buck_accuracy_benchmark.ipynb` | Loads ROM + Simscape outputs, computes MAE/RMSE/MaxErr, plots overlays |
| `benchmark_v1.png`, `benchmark_v2.png` | Final accuracy plots shipped in the datasheet |
| `input_vectors/vector1_step_load_input.mat` | V1 input (Rload step at 25 ms and 100 ms) |
| `input_vectors/vector2_ramp_vin_input.mat` | V2 input (Vin ramp + 100 Hz duty sine) |
| `input_vectors/generate_input_vectors.py` | Regenerates both `.mat` input files from scratch |
| `input_vectors/run_simscape_benchmark.m` | MATLAB script that drives the Simscape model with each input |
| `rom_outputs/rom_vector{1,2}_output_*ms.mat` | ROM outputs from the Docker container |
| `rom_outputs/run_rom_benchmark.py` | Python runner that talks to the ROM container and saves the `.mat` outputs |
| `simscape_outputs/simscape_v{1,2}_dcdc_buck.mat` | Simscape reference outputs (HDF5/MATLAB v7.3) |
| `simscape_outputs/export_simscape_results.m` | MATLAB script that exports the Simscape `out` struct to the `.mat` files above |

## How to reproduce

### 1. Reproduce the ROM outputs

```bash
docker pull simthetic/my-rom:v1
cd benchmarks/rom_outputs
python run_rom_benchmark.py
# writes rom_vector1_output_*ms.mat and rom_vector2_output_*ms.mat
```

Expected wall-clock per run: 600–900 ms on a modern laptop (matches the
filenames in this folder).

### 2. (Optional) Reproduce the Simscape reference

This step requires MATLAB R2023b+ with Simscape Electrical. Skip it if you
just want to verify the ROM accuracy numbers — the reference traces are
already bundled.

```matlab
% From MATLAB, in this folder
cd benchmarks/simscape_outputs
run_simscape_benchmark      % runs the Simulink model with V1 then V2 inputs
export_simscape_results     % writes simscape_v{1,2}_dcdc_buck.mat
```

Reference wall-clock on a typical Windows workstation: ≈ 23 s per vector.

### 3. Recompute the accuracy metrics

```bash
cd benchmarks
jupyter notebook buck_accuracy_benchmark.ipynb
# Run-all
```

The notebook reloads the four `.mat` files, interpolates the Simscape trace
onto the ROM time grid, prints the per-signal MAE / RMSE / MaxErr table
shown in the datasheet, and regenerates `benchmark_v1.png` and
`benchmark_v2.png`.

## Why the published `MaxErr` numbers are intentionally large

The per-sample MaxErr metrics include the *first sample after the load
step*, where the ROM and the Simscape solver disagree on phase by a single
50 µs ROM step (because the step lands between two ROM samples). Look at
the **MAE** column for the engineering-relevant accuracy. See
`docs/ST-DS-2026-001.pdf` §4 footnotes for the full discussion.
