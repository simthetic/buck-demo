%% export_simscape_results.m
% Re-exports the Simscape SimulationOutput .mat files into flat arrays
% that Python / scipy.io can read.
%
% Run this once in MATLAB (the same folder as this script).
% The original files are not modified.

THIS_DIR = fileparts(mfilename('fullpath'));

export_sim(fullfile(THIS_DIR, 'simscape_v1_23s384488.mat'),  ...
           fullfile(THIS_DIR, 'simscape_v1_exported.mat'));

export_sim(fullfile(THIS_DIR, 'simscape_v2_22s606119.mat'),  ...
           fullfile(THIS_DIR, 'simscape_v2_exported.mat'));

fprintf('\nDone — exported files ready for Python.\n');

% ─────────────────────────────────────────────────────────────────────────────
function export_sim(in_path, out_path)
    fprintf('Loading %s ...\n', in_path);
    S = load(in_path);   % loads variable 'out' (Simulink.SimulationOutput)
    out = S.out;

    % Time vector
    time = out.tout;

    % Logged signals — adjust element names if your model uses different labels
    logsout = out.logsout;

    get = @(name) logsout.getElement(name).Values;

    V_Out    = interp1(get('V_out').Time,    get('V_out').Data,    time, 'linear', 'extrap');
    I_Out    = interp1(get('I_out').Time,    get('I_out').Data,    time, 'linear', 'extrap');
    I_In     = interp1(get('I_in').Time,     get('I_in').Data,     time, 'linear', 'extrap');
    V_In     = interp1(get('V_in').Time,     get('V_in').Data,     time, 'linear', 'extrap');
    Duty_Cyle = interp1(get('DC').Time,      get('DC').Data,       time, 'previous', 'extrap');
    R_Load   = interp1(get('R_load').Time,   get('R_load').Data,   time, 'previous', 'extrap');
    V_In_Set = interp1(get('V_in_set').Time, get('V_in_set').Data, time, 'previous', 'extrap');

    save(out_path, 'time', 'V_Out', 'I_Out', 'I_In', 'V_In', ...
         'Duty_Cyle', 'R_Load', 'V_In_Set', '-v7');
    fprintf('  Saved %d samples → %s\n', numel(time), out_path);
end
