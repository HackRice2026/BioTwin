%% s01_baselines.m -- lock the bar before training anything
%
% Named with a leading letter because MATLAB script names must be valid
% identifiers: a file called 01_baselines.m cannot be run. Later stages follow
% the same s02_, s03_ pattern.
%
% Every later result is measured against these numbers, so they are computed
% first and not revisited.
%
% Three baselines, at four horizons:
%
%   daily-mean      the train-set target mean. The "no information" floor.
%   persistence     future Body Battery = current Body Battery.
%   extrapolation   current + recent slope * horizon, clamped to [0 100].
%
% Persistence is the baseline usually quoted for a slow-moving signal, and it
% flatters a model badly: Body Battery drifts, so simply following the current
% slope is roughly twice as accurate. A model that beats persistence may have
% learned nothing except that slope. Extrapolation is therefore the bar, and it
% uses only information available at prediction time.
%
% VALIDATION ONLY. The test split stays sealed until a model is final; scoring it
% now would make it part of model development.
%
% Rows are 5-minute windows from the same day and are heavily autocorrelated, so
% ~4.5k training rows carry roughly 23 independent days of information. Per-day
% error is reported alongside the pooled figure: the spread across days is the
% honest measure of how much any difference between models can be trusted.
%
% Usage:   run('matlab/s01_baselines.m')
% Outputs: matlab/results/s01_baselines.csv
%          matlab/results/s01_baselines_per_day.csv
%          matlab/results/s01_baselines.png

clear; clc;

% Find the data file rather than assuming a layout. MATLAB Online runs editor
% buffers from a temporary directory, so mfilename('fullpath') does not point at
% the uploaded files; a recursive search from the working directory and from the
% MATLAB Drive root works whether this runs from the repository or from a folder
% someone unzipped.
DATA = '';
roots = {pwd};
if exist('userpath', 'file'); roots{end+1} = userpath; end
roots{end+1} = fullfile(pwd, '..');
for r = 1:numel(roots)
    if isempty(roots{r}) || ~isfolder(roots{r}); continue; end
    hits = dir(fullfile(roots{r}, '**', 'garmin_5min_training.csv'));
    if ~isempty(hits)
        DATA = fullfile(hits(1).folder, hits(1).name);
        break
    end
end
assert(~isempty(DATA), ['Cannot find garmin_5min_training.csv anywhere under %s. ' ...
    'cd to the folder holding it and run again.'], pwd);
fprintf('data: %s\n', DATA);

% Results land beside the repository's matlab/ folder when it exists, otherwise
% next to the data that produced them.
if isfolder('matlab')
    OUTDIR = fullfile('matlab', 'results');
else
    OUTDIR = fullfile(fileparts(DATA), 'results');
end
HORIZONS  = {'30m', 30; '1h', 60; '3h', 180; '6h', 360};
EVAL_SPLIT = "validation";     % deliberately not "test"
BB_MIN    = 0;                 % Body Battery is reported on 0-100
BB_MAX    = 100;

if ~isfolder(OUTDIR); mkdir(OUTDIR); end

T = readtable(DATA, 'TextType', 'string', 'VariableNamingRule', 'preserve');
fprintf('%d rows, %d columns\n', height(T), width(T));

%% Effective sample size: days, not rows
fprintf('\n=== split sizes (rows are 5-minute windows, not independent samples) ===\n');
for s = ["train" "validation" "test"]
    rows = T.split == s;
    nDays = numel(unique(T.garmin_calendar_date(rows)));
    fprintf('  %-11s %5d rows  %3d days  ~%3.0f rows/day\n', ...
        s, sum(rows), nDays, sum(rows) / max(1, nDays));
end

%% Baselines
summary  = table();
perDayAll = table();

for h = 1:size(HORIZONS, 1)
    name    = HORIZONS{h, 1};
    minutes = HORIZONS{h, 2};

    targetCol   = "target_bb_" + name;
    eligibleCol = "eligible_" + name;

    % The eligibility flag marks rows whose target was matched to a real measured
    % point inside the tolerance; rows without one are absent, never filled in.
    isEligible = T.(eligibleCol) == 1;
    haveInputs = ~isnan(T.(targetCol)) & ~isnan(T.bb_current_measured);

    trainRows = T.split == "train"      & isEligible & haveInputs;
    evalRows  = T.split == EVAL_SPLIT   & isEligible & haveInputs;

    if sum(evalRows) < 30
        fprintf('\n%s: only %d eligible rows -- skipped\n', name, sum(evalRows));
        continue
    end

    y       = T.(targetCol)(evalRows);
    current = T.bb_current_measured(evalRows);
    days    = T.garmin_calendar_date(evalRows);

    % Recent slope, in points per minute. The change over the last hour is a
    % causal feature; where it is missing the slope is taken as flat rather than
    % guessed, which makes extrapolation fall back to persistence on that row.
    changePerHour = T.bb_current_change_1h(evalRows);
    changePerHour(isnan(changePerHour)) = 0;
    slope = changePerHour / 60;

    trainMean = mean(T.(targetCol)(trainRows));   % fitted on train only

    predictions = struct( ...
        'daily_mean',    repmat(trainMean, size(y)), ...
        'persistence',   current, ...
        'extrapolation', min(BB_MAX, max(BB_MIN, current + slope * minutes)));

    fprintf('\n=== %s horizon | %s | n = %d | target sd = %.1f ===\n', ...
        name, EVAL_SPLIT, numel(y), std(y));
    fprintf('  %-15s %8s %8s %8s %8s %14s\n', ...
        'baseline', 'MAE', 'RMSE', 'R2', 'bias', 'per-day MAE');

    for f = string(fieldnames(predictions))'
        yhat = predictions.(f);
        m    = scoreBaseline(y, yhat);
        [dayMae, dayNames] = perDayMae(y, yhat, days);

        fprintf('  %-15s %8.2f %8.2f %8.3f %8.2f   %5.2f +/- %.2f\n', ...
            f, m.mae, m.rmse, m.r2, m.bias, mean(dayMae), std(dayMae));

        summary = [summary; table(string(name), minutes, f, numel(y), std(y), ...
            m.mae, m.rmse, m.r2, m.bias, mean(dayMae), std(dayMae), ...
            'VariableNames', {'horizon', 'minutes', 'baseline', 'n', 'target_sd', ...
                              'mae', 'rmse', 'r2', 'bias', 'per_day_mae', 'per_day_sd'})]; %#ok<AGROW>

        perDayAll = [perDayAll; table(repmat(string(name), numel(dayMae), 1), ...
            repmat(f, numel(dayMae), 1), dayNames, dayMae, ...
            'VariableNames', {'horizon', 'baseline', 'day', 'mae'})]; %#ok<AGROW>
    end
end

%% Where is there room for a model to win?
fprintf('\n=== how much does the best baseline already explain? ===\n');
fprintf('  A negative R2 means the baseline is worse than predicting the mean.\n');
for h = 1:size(HORIZONS, 1)
    name = string(HORIZONS{h, 1});
    rows = summary.horizon == name & summary.baseline == "extrapolation";
    if ~any(rows); continue; end
    fprintf('  %-4s extrapolation MAE %6.2f   R2 %7.3f   target sd %5.1f\n', ...
        name, summary.mae(rows), summary.r2(rows), summary.target_sd(rows));
end
fprintf(['\n  A horizon where extrapolation already has a high R2 leaves little\n' ...
         '  for a model to add. A horizon where its R2 is near or below zero is\n' ...
         '  where following the current trend fails, and where sleep, accumulated\n' ...
         '  load and time awake should carry the prediction instead.\n']);

writetable(summary, fullfile(OUTDIR, 's01_baselines.csv'));
writetable(perDayAll, fullfile(OUTDIR, 's01_baselines_per_day.csv'));
fprintf('\nwrote %s\n', fullfile(OUTDIR, 's01_baselines.csv'));

%% Figure: MAE by horizon, with per-day spread
figure('Name', 'Baseline error by horizon', 'Color', 'w', 'Position', [100 100 900 380]);

subplot(1, 2, 1);
names = unique(summary.baseline, 'stable');
horizonOrder = string(HORIZONS(:, 1))';
hold on;
for f = names'
    rows = summary.baseline == f;
    [~, order] = ismember(summary.horizon(rows), horizonOrder);
    [order, si] = sort(order);
    mae = summary.mae(rows); sd = summary.per_day_sd(rows);
    mae = mae(si); sd = sd(si);
    errorbar(order, mae, sd, '-o', 'LineWidth', 1.6, 'MarkerSize', 6, ...
        'CapSize', 8, 'DisplayName', f);
end
hold off; grid on; box off;
xticks(1:numel(horizonOrder)); xticklabels(horizonOrder); xlim([0.7 numel(horizonOrder) + 0.3]);
xlabel('forecast horizon'); ylabel('MAE (Body Battery points)');
title('Baseline error, validation only');
legend('Location', 'northwest'); legend boxoff;

subplot(1, 2, 2);
rows = summary.baseline == "extrapolation";
[~, order] = ismember(summary.horizon(rows), horizonOrder);
[order, si] = sort(order);
r2 = summary.r2(rows); r2 = r2(si);
bar(order, r2, 0.55, 'FaceColor', [0.16 0.42 0.33], 'EdgeColor', 'none');
yline(0, 'k-', 'worse than the mean', 'LabelHorizontalAlignment', 'left');
grid on; box off;
xticks(1:numel(horizonOrder)); xticklabels(horizonOrder);
xlabel('forecast horizon'); ylabel('R^2 of trend extrapolation');
title('Where trend-following stops working');

pngPath = fullfile(OUTDIR, 's01_baselines.png');
if exist('exportgraphics', 'file')
    exportgraphics(gcf, pngPath, 'Resolution', 150);
else
    print(gcf, pngPath, '-dpng', '-r150');   % releases before R2020a
end
fprintf('wrote %s\n', fullfile(OUTDIR, 's01_baselines.png'));

%% ---------- local functions ----------

function m = scoreBaseline(y, yhat)
    e = y - yhat;
    m.n    = numel(y);
    m.mae  = mean(abs(e));
    m.rmse = sqrt(mean(e .^ 2));
    m.bias = mean(e);
    % R2 against the mean of the evaluated split: negative means the baseline is
    % worse than having predicted that mean, which is a real and useful outcome.
    sst    = sum((y - mean(y)) .^ 2);
    m.r2   = 1 - sum(e .^ 2) / sst;
end

function [dayMae, dayNames] = perDayMae(y, yhat, days)
    % One error per calendar day. Days are the independent unit here, so the
    % spread across them says whether a difference between models is real.
    [g, dayNames] = findgroups(days);
    dayMae = splitapply(@(a, b) mean(abs(a - b)), y, yhat, g);
end
