%% run_simscape_benchmark.m
% Run the Buck converter Simscape model with both benchmark input vectors
% and save outputs in a Python-readable format.
%
% USAGE:
%   1. Run generate_input_vectors.py first to produce the two input .mat files
%   2. Set REPO_ROOT below to match your local path
%   3. Run this script section by section (or all at once)
%   4. The output .mat files will appear in notebooks/benchmarks/
%      alongside this script
%
% OUTPUT FORMAT (flat .mat v7.3, readable by Python h5py / scipy.io):
%   time, I_In, I_Out, V_In, V_Out  — all in PHYSICAL units (A / V)
%   Duty_Cyle, R_Load, V_In_Set     — inputs in PHYSICAL units (-, Ω, V)

%% ── Configuration ────────────────────────────────────────────────────────────
REPO_ROOT  = fullfile(fileparts(mfilename('fullpath')), '..', '..');
MDL_PATH   = fullfile(REPO_ROOT, 'MATLAB', 'model', 'BUCK');
THIS_DIR   = fileparts(mfilename('fullpath'));

addpath(MDL_PATH);
addpath(fullfile(REPO_ROOT, 'MATLAB', 'utils'));

MODEL_NAME = 'Buck_converter';
Tsample    = 1e-4;   % 100 µs — must match ROM sample time

load_system(MODEL_NAME);

%% ── Helper: denormalize inputs, run sim, save result ─────────────────────────
function run_and_save(model_name, data, out_path, Tsample)
    % data: struct with individual timeseries fields: t, duty, Vin, Rload
    t          = data.t(:);
    duty       = data.duty(:);      % 0-1
    Vin_phys   = data.Vin(:);      % already in volts
    Rload_phys = data.Rload(:);    % already in ohms

    Tsim   = t(end);
    Tsvec  = (0 : Tsample : Tsim)';

    % External input expected by Buck_converter.slx: [t, duty, Vin, Rload]
    extInput = [t, duty, Vin_phys, Rload_phys];

    % Initial capacitor voltage = first Vin value
    V_Cin = Vin_phys(1);

    in = Simulink.SimulationInput(model_name);
    in = in.setExternalInput(extInput);
    in = in.setVariable('V_Cin', V_Cin);
    in = in.setModelParameter('StopTime', num2str(Tsim));

    fprintf('  Simulating %.0f ms ...\n', Tsim * 1e3);
    simOut = sim(in);

    % ── Extract logged signals ────────────────────────────────────────────
    log = simOut.logsout;

    resample_ts = @(sig) resample(log.getElement(sig).Values, Tsvec).Data;

    time    = Tsvec;
    I_In    = resample_ts('I_in');
    I_Out   = resample_ts('I_out');
    V_In    = resample_ts('V_in');
    V_Out   = resample_ts('V_out');

    % Rebuild input arrays at Tsvec resolution for alignment
    Duty_Cyle  = interp1(t, duty,       Tsvec, 'previous', 'extrap');
    R_Load     = interp1(t, Rload_phys, Tsvec, 'previous', 'extrap');
    V_In_Set   = interp1(t, Vin_phys,   Tsvec, 'previous', 'extrap');

    save(out_path, 'time', 'I_In', 'I_Out', 'V_In', 'V_Out', ...
         'Duty_Cyle', 'R_Load', 'V_In_Set', '-v7.3');
    fprintf('  Saved: %s\n', out_path);
end

%% ── Vector 1: Step load ──────────────────────────────────────────────────────
fprintf('\n=== Vector 1: Step load ===\n');
v1 = load(fullfile(THIS_DIR, 'vector1_step_load_input.mat'));
run_and_save(MODEL_NAME, v1.inputVector, ...
    fullfile(THIS_DIR, 'vector1_simscape_result.mat'), Tsample);

%% ── Vector 2: Ramp Vin + sinusoidal duty ─────────────────────────────────────
fprintf('\n=== Vector 2: Ramp Vin + sinusoidal duty ===\n');
v2 = load(fullfile(THIS_DIR, 'vector2_ramp_vin_input.mat'));
run_and_save(MODEL_NAME, v2.inputVector, ...
    fullfile(THIS_DIR, 'vector2_simscape_result.mat'), Tsample);

fprintf('\nDone. Both result files saved to:\n  %s\n', THIS_DIR);
