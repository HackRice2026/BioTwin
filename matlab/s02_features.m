%% s02_features.m -- reduce 92 predictors to the few that generalise
%
% Named with a leading letter because MATLAB script names must be valid
% identifiers.
%
% Why this comes before any model:
%
% The training split holds 4491 rows but only 23 calendar days, and consecutive
% 5-minute windows from one day are nearly identical. The effective sample size
% is therefore about 23, not 4491. Ninety-two predictors against 23 independent
% observations will fit noise, and a row-shuffled check would hide it because
% neighbouring rows land on both sides of the split.
%
% So every step here is grouped by calendar day:
%
%   1. drop predictors that are near-constant across TRAIN
%   2. rank the rest by correlation with the target, computed within each day and
%      then averaged, so one long day cannot dominate the ranking
%   3. add them greedily, skipping any that duplicate an already-chosen predictor
%   4. choose how many to keep by leave-one-DAY-out cross-validation, taking the
%      smallest set within one standard error of the best -- the simpler model
%      when the evidence cannot separate them
%
% TRAIN ONLY. Selecting features against validation would leak it into the model
% before Stage 3 ever compares anything.
%
% The ridge regression used here is a probe, not a candidate model: it gives a
% consistent yardstick for comparing feature counts. Stage 3 chooses the model.
%
% Requires base MATLAB only.
%
% Usage:   run('matlab/s02_features.m')
% Outputs: matlab/results/s02_selected_features.csv
%          matlab/results/s02_selection_curve.csv
%          matlab/results/s02_features.png

clear; clc;

HORIZONS      = {'30m', 30; '1h', 60; '3h', 180; '6h', 360};
MAX_FEATURES  = 40;      % ceiling for the search, not a target
REDUNDANT_ABS = 0.90;    % |r| above this counts as a duplicate predictor
NEAR_CONSTANT = 0.99;    % a level holding this share of TRAIN rows is constant
RIDGE_LAMBDA  = 1.0;     % mild, on standardised predictors

%% Locate inputs
DATA = ''; MANIFEST = '';
roots = {pwd};
if exist('userpath', 'file'); roots{end+1} = userpath; end
roots{end+1} = fullfile(pwd, '..');
for r = 1:numel(roots)
    if isempty(roots{r}) || ~isfolder(roots{r}); continue; end
    if isempty(DATA)
        hit = dir(fullfile(roots{r}, '**', 'garmin_5min_training_imputed.csv'));
        if ~isempty(hit); DATA = fullfile(hit(1).folder, hit(1).name); end
    end
    if isempty(MANIFEST)
        hit = dir(fullfile(roots{r}, '**', 'garmin_feature_manifest.csv'));
        if ~isempty(hit); MANIFEST = fullfile(hit(1).folder, hit(1).name); end
    end
end
assert(~isempty(DATA) && ~isempty(MANIFEST), ...
    ['Need garmin_5min_training_imputed.csv and garmin_feature_manifest.csv. ' ...
     'cd to the folder holding them and run again.']);
fprintf('data:     %s\nmanifest: %s\n', DATA, MANIFEST);

if isfolder('matlab'); OUTDIR = fullfile('matlab', 'results');
else; OUTDIR = fullfile(fileparts(DATA), 'results'); end
if ~isfolder(OUTDIR); mkdir(OUTDIR); end

T = readtable(DATA, 'TextType', 'string', 'VariableNamingRule', 'preserve');
M = readtable(MANIFEST, 'TextType', 'string', 'VariableNamingRule', 'preserve');
predictors = M.column(M.role == "predictor");

% The imputed table is used because a linear probe needs complete values. Its
% gaps were filled with a short causal forward-fill and TRAIN-only medians, so
% no validation or test information reaches the predictors.

%% Encode the three binary text predictors, drop the originals
textCols = strings(0);
for p = predictors'
    if isstring(T.(p)); textCols(end+1) = p; end %#ok<AGROW>
end
for p = textCols
    levels = unique(T.(p));
    % Every text predictor in this dataset is binary; encode against the rarer
    % level so the indicator reads as "the unusual case happened".
    counts = arrayfun(@(L) sum(T.(p) == L), levels);
    [~, rare] = min(counts);
    newName = matlab.lang.makeValidName(p + "_is_" + levels(rare));
    T.(newName) = double(T.(p) == levels(rare));
    predictors(predictors == p) = newName;
    fprintf('encoded %s -> %s (%d of %d rows)\n', p, newName, ...
        sum(T.(newName)), height(T));
end

isTrain = T.split == "train";
fprintf('\ntrain: %d rows, %d days\n', sum(isTrain), ...
    numel(unique(T.garmin_calendar_date(isTrain))));

%% Drop near-constant predictors, judged on TRAIN only
keep = strings(0);
dropped = strings(0);
for p = predictors'
    x = T.(p)(isTrain);
    if all(isnan(x)) || std(x, 'omitnan') == 0
        dropped(end+1) = p + " (no variation)"; continue %#ok<AGROW>
    end
    levels = unique(x(~isnan(x)));
    if numel(levels) <= 5
        share = max(arrayfun(@(L) mean(x == L), levels));
        if share >= NEAR_CONSTANT
            dropped(end+1) = p + sprintf(" (%.0f%% one value)", share * 100); %#ok<AGROW>
            continue
        end
    end
    keep(end+1) = p; %#ok<AGROW>
end
fprintf('predictors: %d -> %d after dropping near-constant\n', numel(predictors), numel(keep));
for d = dropped; fprintf('  dropped %s\n', d); end

%% Select, per horizon
selectedAll = table();
curveAll    = table();

for h = 1:size(HORIZONS, 1)
    name = string(HORIZONS{h, 1});
    targetCol = "target_bb_" + name;
    eligible  = T.("eligible_" + name) == 1;

    rows = isTrain & eligible & ~isnan(T.(targetCol));
    y    = T.(targetCol)(rows);
    days = T.garmin_calendar_date(rows);
    X    = table2array(T(rows, cellstr(keep)));

    [dayIdx, dayList] = findgroups(days);
    nDays = numel(dayList);
    fprintf('\n=== %s | train rows %d | days %d ===\n', name, numel(y), nDays);
    if nDays < 6
        fprintf('  too few days to cross-validate -- skipped\n'); continue
    end

    % --- rank by within-day correlation, averaged over days ---------------
    score = zeros(numel(keep), 1);
    for j = 1:numel(keep)
        perDay = nan(nDays, 1);
        for d = 1:nDays
            xd = X(dayIdx == d, j); yd = y(dayIdx == d);
            if numel(xd) < 8 || std(xd) == 0; continue; end
            c = corrcoef(xd, yd);
            perDay(d) = abs(c(1, 2));
        end
        score(j) = mean(perDay, 'omitnan');
    end
    score(isnan(score)) = 0;
    [~, order] = sort(score, 'descend');

    % --- greedy add, skipping duplicates ----------------------------------
    chosen = [];
    for j = order'
        if numel(chosen) >= MAX_FEATURES; break; end
        duplicate = false;
        for c = chosen
            r = corrcoef(X(:, j), X(:, c));
            if abs(r(1, 2)) > REDUNDANT_ABS; duplicate = true; break; end
        end
        if ~duplicate; chosen(end+1) = j; end %#ok<AGROW>
    end

    % --- how many to keep: leave-one-day-out, one-standard-error rule -----
    kMax = numel(chosen);
    maeMean = nan(kMax, 1); maeSe = nan(kMax, 1);
    for k = 1:kMax
        cols = chosen(1:k);
        perDay = nan(nDays, 1);
        for d = 1:nDays
            tr = dayIdx ~= d; te = dayIdx == d;
            if sum(te) < 8 || sum(tr) < 50; continue; end
            yhat = ridgePredict(X(tr, cols), y(tr), X(te, cols), RIDGE_LAMBDA);
            perDay(d) = mean(abs(y(te) - yhat));
        end
        maeMean(k) = mean(perDay, 'omitnan');
        maeSe(k)   = std(perDay, 'omitnan') / sqrt(sum(~isnan(perDay)));
    end

    [bestMae, kBest] = min(maeMean);
    threshold = bestMae + maeSe(kBest);
    kChosen = find(maeMean <= threshold, 1, 'first');   % simplest within 1 SE

    fprintf('  best held-out MAE %.2f at k=%d; simplest within 1 SE is k=%d (MAE %.2f)\n', ...
        bestMae, kBest, kChosen, maeMean(kChosen));
    fprintf('  %-34s %10s %10s\n', 'kept predictor', 'day |r|', 'cumulative MAE');
    for i = 1:kChosen
        j = chosen(i);
        fprintf('  %-34s %10.3f %10.2f\n', keep(j), score(j), maeMean(i));
    end

    selectedAll = [selectedAll; table(repmat(name, kChosen, 1), (1:kChosen)', ...
        keep(chosen(1:kChosen))', score(chosen(1:kChosen)), maeMean(1:kChosen), ...
        'VariableNames', {'horizon', 'rank', 'predictor', 'day_abs_corr', 'cumulative_loo_mae'})]; %#ok<AGROW>

    curveAll = [curveAll; table(repmat(name, kMax, 1), (1:kMax)', maeMean, maeSe, ...
        'VariableNames', {'horizon', 'k', 'loo_mae', 'loo_se'})]; %#ok<AGROW>
end

writetable(selectedAll, fullfile(OUTDIR, 's02_selected_features.csv'));
writetable(curveAll, fullfile(OUTDIR, 's02_selection_curve.csv'));
fprintf('\nwrote %s\n', fullfile(OUTDIR, 's02_selected_features.csv'));

%% Figure: how held-out error moves as predictors are added
figure('Name', 'Feature selection', 'Color', 'w', 'Position', [100 100 940 380]);
names = unique(curveAll.horizon, 'stable');
tiles = numel(names);
for i = 1:tiles
    subplot(1, tiles, i);
    rows = curveAll.horizon == names(i);
    k = curveAll.k(rows); mae = curveAll.loo_mae(rows); se = curveAll.loo_se(rows);
    errorbar(k, mae, se, '-o', 'MarkerSize', 3.5, 'LineWidth', 1.2, ...
        'Color', [0.16 0.42 0.33], 'CapSize', 0);
    hold on;
    [bestMae, kBest] = min(mae);
    kChosen = find(mae <= bestMae + se(kBest), 1, 'first');
    xline(kChosen, '--', sprintf('k=%d', kChosen), 'Color', [0.7 0.3 0.1]);
    hold off; grid on; box off;
    xlabel('predictors kept'); if i == 1; ylabel('leave-one-day-out MAE'); end
    title(names(i));
end
sgtitle('Held-out error by predictor count (train days only)');
pngPath = fullfile(OUTDIR, 's02_features.png');
if exist('exportgraphics', 'file')
    exportgraphics(gcf, pngPath, 'Resolution', 150);
else
    print(gcf, pngPath, '-dpng', '-r150');
end
fprintf('wrote %s\n', pngPath);

%% ---------- local functions ----------

function yhat = ridgePredict(Xtr, ytr, Xte, lambda)
    % Ridge on standardised predictors, standardisation fitted on the training
    % fold only. A probe for comparing feature counts, not a candidate model.
    mu = mean(Xtr, 1);
    sg = std(Xtr, 0, 1);
    sg(sg == 0 | isnan(sg)) = 1;
    Ztr = (Xtr - mu) ./ sg;
    Zte = (Xte - mu) ./ sg;
    yBar = mean(ytr);
    beta = (Ztr' * Ztr + lambda * eye(size(Ztr, 2))) \ (Ztr' * (ytr - yBar));
    yhat = Zte * beta + yBar;
end
