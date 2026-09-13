%% s03_models.m -- which model, if any, beats the rules?
%
% Named with a leading letter because MATLAB script names must be valid
% identifiers.
%
% Scored on VALIDATION. That makes these numbers comparable to Stage 1 for the
% first time: Stage 2 measured leave-one-day-out on TRAIN, which is the right way
% to choose features but says nothing about held-out days.
%
% Validation is five days. Five days confirm; they do not measure. The pooled MAE
% is quoted alongside a paired per-day comparison so the weakness is visible
% rather than hidden in a single number.
%
% The test split stays sealed. It is scored once, in Stage 5, on one final model.
%
% Models compared at each horizon:
%
%   the best Stage 1 rule        recomputed on exactly these rows
%   ridge, controls only         current BB + its change + hour sin/cos
%   ridge, controls + physiology the predictors Stage 2 chose
%   bagged trees                 \  Statistics and Machine Learning Toolbox;
%   boosted trees (LSBoost)       > skipped with a message if unavailable, so the
%   Gaussian process             /  script still runs on a base licence
%
% Requires base MATLAB; the three ensemble/GPR models additionally require the
% Statistics and Machine Learning Toolbox.
%
% Usage:   run('matlab/s03_models.m')   % after s02_features.m
% Outputs: matlab/results/s03_models.csv
%          matlab/results/s03_models.png

clear; clc;

HORIZONS = {'30m', 30; '1h', 60; '3h', 180; '6h', 360};
CONTROLS = {'bb_current_measured', 'bb_current_change_1h', 'hour_sin', 'hour_cos'};
RIDGE_LAMBDA = 1.0;
BB_MIN = 0; BB_MAX = 100;

%% Locate inputs
CLEAN    = findFile('garmin_5min_training.csv');
IMPUTED  = findFile('garmin_5min_training_imputed.csv');
SELECTED = findFile('s02_selected_features.csv');
assert(~isempty(CLEAN) && ~isempty(IMPUTED), 'Cannot find the training CSVs.');
assert(~isempty(SELECTED), 'Run s02_features.m first: s02_selected_features.csv is missing.');
fprintf('clean:    %s\nimputed:  %s\nselected: %s\n', CLEAN, IMPUTED, SELECTED);

if isfolder('matlab'); OUTDIR = fullfile('matlab', 'results');
else; OUTDIR = fullfile(fileparts(CLEAN), 'results'); end
if ~isfolder(OUTDIR); mkdir(OUTDIR); end

C = readtable(CLEAN,   'TextType', 'string', 'VariableNamingRule', 'preserve');
I = readtable(IMPUTED, 'TextType', 'string', 'VariableNamingRule', 'preserve');
S = readtable(SELECTED, 'TextType', 'string', 'VariableNamingRule', 'preserve');

% Re-encode the binary text predictors exactly as Stage 2 did, so the selected
% names resolve.
for p = string(I.Properties.VariableNames)
    if ~isstring(I.(p)); continue; end
    levels = unique(I.(p));
    if numel(levels) ~= 2; continue; end
    counts = arrayfun(@(L) sum(I.(p) == L), levels);
    [~, rare] = min(counts);
    I.(matlab.lang.makeValidName(p + "_is_" + levels(rare))) = double(I.(p) == levels(rare));
end

hasStats = exist('fitrensemble', 'file') == 2 && exist('fitrgp', 'file') == 2;
if ~hasStats
    fprintf(['\nStatistics and Machine Learning Toolbox not available: the tree ' ...
             'ensembles and\nGaussian process are skipped. Ridge and the rules ' ...
             'still run.\n']);
end

results = table();

for h = 1:size(HORIZONS, 1)
    name = string(HORIZONS{h, 1});
    horizonMin = HORIZONS{h, 2};
    targetCol = "target_bb_" + name;

    usable = C.("eligible_" + name) == 1 & ~isnan(C.(targetCol)) & ~isnan(C.bb_current_measured);
    trRows = find(C.split == "train"      & usable);
    vaRows = find(C.split == "validation" & usable);

    yTr = C.(targetCol)(trRows);
    yVa = C.(targetCol)(vaRows);
    daysVa = C.garmin_calendar_date(vaRows);

    added = S.predictor(S.horizon == name & S.role == "added");
    featureSets = { ...
        "ridge: controls only",                                    string(CONTROLS); ...
        sprintf("ridge: controls + %d physiology", numel(added)), [string(CONTROLS), added']};

    fprintf('\n=== %s | train %d rows | validation %d rows over %d days ===\n', ...
        name, numel(yTr), numel(yVa), numel(unique(daysVa)));

    %% The best Stage 1 rule, recomputed on exactly these validation rows
    current = C.bb_current_measured(vaRows);
    change  = C.bb_current_change_1h(vaRows);
    change(isnan(change)) = 0;
    extrap = min(BB_MAX, max(BB_MIN, current + change / 60 * horizonMin));

    targetHour = hour(C.local_timestamp + minutes(horizonMin));
    climate = repmat(mean(yTr), 24, 1);
    for hh = 0:23
        sel = false(height(C), 1); sel(trRows) = targetHour(trRows) == hh;
        if any(sel); climate(hh + 1) = mean(C.(targetCol)(sel)); end
    end
    clock = climate(targetHour(vaRows) + 1);

    predictions = containers.Map();
    predictions('baseline: extrapolation')    = extrap;
    predictions('baseline: time_of_day')      = clock;
    predictions('baseline: trend_plus_clock') = min(BB_MAX, max(BB_MIN, (extrap + clock) / 2));

    %% Ridge, then the toolbox models on the physiology set
    for k = 1:size(featureSets, 1)
        label = featureSets{k, 1};
        cols  = cellstr(featureSets{k, 2});
        Xtr = table2array(I(trRows, cols));
        Xva = table2array(I(vaRows, cols));
        predictions(char(label)) = min(BB_MAX, max(BB_MIN, ...
            ridgePredict(Xtr, yTr, Xva, RIDGE_LAMBDA)));

        if hasStats && k == size(featureSets, 1)
            % Trees and a Gaussian process get the same predictors the ridge had,
            % so any difference is the model rather than the information.
            bagged = fitrensemble(Xtr, yTr, 'Method', 'Bag');
            predictions('bagged trees') = min(BB_MAX, max(BB_MIN, predict(bagged, Xva)));

            boosted = fitrensemble(Xtr, yTr, 'Method', 'LSBoost', ...
                'NumLearningCycles', 200, 'LearnRate', 0.05);
            predictions('boosted trees') = min(BB_MAX, max(BB_MIN, predict(boosted, Xva)));

            gp = fitrgp(Xtr, yTr, 'Standardize', true, 'KernelFunction', 'ardsquaredexponential');
            predictions('gaussian process') = min(BB_MAX, max(BB_MIN, predict(gp, Xva)));
        end
    end

    %% Score, and compare per day
    labels = predictions.keys;
    fprintf('  %-36s %8s %8s %8s\n', 'model', 'MAE', 'RMSE', 'R2');
    % Per-day errors are stored as a vector in one fixed day order, so two
    % models can be differenced day by day.
    dayIdx = findgroups(daysVa);
    perDay = containers.Map();
    for L = labels
        yhat = predictions(L{1});
        m = scoreModel(yVa, yhat);
        perDay(L{1}) = splitapply(@(a, b) mean(abs(a - b)), yVa, yhat, dayIdx);
        fprintf('  %-36s %8.2f %8.2f %8.3f\n', L{1}, m.mae, m.rmse, m.r2);
        results = [results; table(name, string(L{1}), "validation", numel(yVa), ...
            m.mae, m.rmse, m.r2, ...
            'VariableNames', {'horizon', 'model', 'split', 'n', 'mae', 'rmse', 'r2'})]; %#ok<AGROW>
    end

    % Did anything beat the best rule? Paired over validation days, which is the
    % comparison that survives a small sample better than the pooled figure.
    %
    % Two comparisons, because they are not the same claim:
    %
    %   the physiology ridge  pre-specified -- Stage 2 chose its predictors on
    %                         TRAIN, so validation is untouched and this figure
    %                         is an honest estimate
    %   the best fitted model picked by looking at this very validation table,
    %                         so its margin is optimistic by construction and is
    %                         a lead to confirm in Stage 5, not a result
    %
    % Reporting only the first is what made an earlier version of this script
    % print "the best rule still wins" at 3h while its own table showed the
    % bagged trees ahead of every rule.
    ruleLabels = labels(startsWith(string(labels), "baseline:"));
    ruleMae = cellfun(@(L) scoreModel(yVa, predictions(L)).mae, ruleLabels);
    [~, bi] = min(ruleMae);
    bestRule = ruleLabels{bi};

    fittedLabels = labels(~startsWith(string(labels), "baseline:"));
    fittedMae = cellfun(@(L) scoreModel(yVa, predictions(L)).mae, fittedLabels);
    [~, fi] = min(fittedMae);
    bestFitted = fittedLabels{fi};

    physLabel = char(featureSets{end, 1});
    contenders = {physLabel, 'pre-specified'};
    if ~strcmp(bestFitted, physLabel)
        contenders = [contenders; {bestFitted, 'chosen on validation'}];
    end

    for c = 1:size(contenders, 1)
        label = contenders{c, 1};
        d = perDay(bestRule) - perDay(label);   % same day order for both
        fprintf(['  %s vs %s: %+.2f +/- %.2f MAE paired over %d days, ' ...
                 'better on %d/%d (%s)\n'], label, bestRule, mean(d), ...
                 std(d) / sqrt(numel(d)), numel(d), sum(d > 0), numel(d), ...
                 contenders{c, 2});
        results = [results; table(name, ...
            "paired: " + string(label) + " vs " + string(bestRule), ...
            "validation", numel(d), mean(d), std(d) / sqrt(numel(d)), ...
            sum(d > 0), 'VariableNames', ...
            {'horizon', 'model', 'split', 'n', 'mae', 'rmse', 'r2'})]; %#ok<AGROW>
    end

    % The verdict names whichever model actually leads the table, so it can no
    % longer contradict the rows printed above it.
    physGain = mean(perDay(bestRule) - perDay(physLabel));
    if physGain > 0
        fprintf('  -> the pre-specified physiology model improves on %s here\n', bestRule);
    elseif min(fittedMae) < min(ruleMae)
        fprintf(['  -> the pre-specified predictors did not transfer, but %s ' ...
                 'leads the table\n     (%.2f vs %.2f MAE for %s). Chosen by ' ...
                 'looking at validation, so treat it as a\n     candidate for ' ...
                 'Stage 5 rather than a win.\n'], bestFitted, min(fittedMae), ...
                 min(ruleMae), bestRule);
    else
        fprintf(['  -> %s still wins here; no fitted model beat it, on the ' ...
                 'pooled figure or paired\n'], bestRule);
    end
end

writetable(results, fullfile(OUTDIR, 's03_models.csv'));
fprintf('\nwrote %s\n', fullfile(OUTDIR, 's03_models.csv'));

%% Figure: every model against the best rule, per horizon
figure('Name', 'Models vs rules', 'Color', 'w', 'Position', [100 100 980 400]);
plotRows = results(~startsWith(results.model, "paired:"), :);
names = unique(plotRows.horizon, 'stable');
for i = 1:numel(names)
    subplot(1, numel(names), i);
    rows = plotRows.horizon == names(i);
    labels = plotRows.model(rows); mae = plotRows.mae(rows);
    [mae, ord] = sort(mae); labels = labels(ord);
    colours = repmat([0.55 0.58 0.54], numel(mae), 1);
    colours(startsWith(labels, "baseline:"), :) = ...
        repmat([0.16 0.42 0.33], sum(startsWith(labels, "baseline:")), 1);
    barh(categorical(labels, labels), mae, 0.6, 'FaceColor', 'flat', 'CData', colours);
    grid on; box off; xlabel('validation MAE');
    title(names(i)); set(gca, 'FontSize', 8);
end
sgtitle('Validation MAE: green are rules, grey are fitted models');
pngPath = fullfile(OUTDIR, 's03_models.png');
if exist('exportgraphics', 'file')
    exportgraphics(gcf, pngPath, 'Resolution', 150);
else
    print(gcf, pngPath, '-dpng', '-r150');
end
fprintf('wrote %s\n', pngPath);

%% ---------- local functions ----------

function p = findFile(nameWanted)
    % Search the working directory, the MATLAB Drive root and the parent, so the
    % script runs from the repository or from a folder someone unzipped.
    p = '';
    roots = {pwd};
    if exist('userpath', 'file'); roots{end+1} = userpath; end
    roots{end+1} = fullfile(pwd, '..');
    for r = 1:numel(roots)
        if isempty(roots{r}) || ~isfolder(roots{r}); continue; end
        hit = dir(fullfile(roots{r}, '**', nameWanted));
        if ~isempty(hit); p = fullfile(hit(1).folder, hit(1).name); return; end
    end
end

function m = scoreModel(y, yhat)
    e = y - yhat;
    m.mae  = mean(abs(e));
    m.rmse = sqrt(mean(e .^ 2));
    m.r2   = 1 - sum(e .^ 2) / sum((y - mean(y)) .^ 2);
end

function yhat = ridgePredict(Xtr, ytr, Xte, lambda)
    mu = mean(Xtr, 1);
    sg = std(Xtr, 0, 1);
    sg(sg == 0 | isnan(sg)) = 1;
    Ztr = (Xtr - mu) ./ sg;
    Zte = (Xte - mu) ./ sg;
    yBar = mean(ytr);
    beta = (Ztr' * Ztr + lambda * eye(size(Ztr, 2))) \ (Ztr' * (ytr - yBar));
    yhat = Zte * beta + yBar;
end
