%% s02_features.m -- does physiology add anything beyond trend and a clock?
%
% Named with a leading letter because MATLAB script names must be valid
% identifiers.
%
% A first version of this script ranked predictors by their correlation with the
% target. At six hours it chose twelve sleep features and stalled at MAE ~23; the
% error only fell, to 10.53, once hour-of-day entered -- and a clock alone scores
% 7.37 on validation. Correlation ranking cannot separate a physiological signal
% from a proxy for the time of day, and the model it produced would have lost to
% the clock it was unknowingly imitating.
%
% So four predictors are FORCED IN and never selected:
%
%     bb_current_measured     where Body Battery is now
%     bb_current_change_1h    which way it is moving
%     hour_sin, hour_cos      what time it is
%
% Together these reproduce the trend+clock baseline from Stage 1, the strongest
% rule at every horizon. Every other predictor is then ranked by how much it
% reduces leave-one-DAY-out error when ADDED to that control model. That is the
% only question worth asking of it.
%
% The verdict is a PAIRED comparison. Both models are scored on the same held-out
% days, so what matters is the spread of the per-day difference, not the spread of
% either model's own error -- comparing a gain against one model's standard error
% throws the pairing away.
%
% TRAIN ONLY, grouped by calendar day throughout. Twenty-three days carry the
% information here, not 4491 rows.
%
% The ridge regression is a probe that compares feature sets on equal terms, not a
% candidate model. Stage 3 chooses the model.
%
% Requires base MATLAB only. Takes a minute or two.
%
% Usage:   run('matlab/s02_features.m')
% Outputs: matlab/results/s02_selected_features.csv
%          matlab/results/s02_selection_curve.csv
%          matlab/results/s02_verdict.csv
%          matlab/results/s02_features.png

clear; clc;

HORIZONS      = {'30m', 30; '1h', 60; '3h', 180; '6h', 360};
CONTROLS      = {'bb_current_measured', 'bb_current_change_1h', 'hour_sin', 'hour_cos'};
MAX_ADDED     = 12;     % candidates added beyond the controls
REDUNDANT_ABS = 0.90;   % |r| above this counts as a duplicate predictor
NEAR_CONSTANT = 0.99;   % a level holding this share of TRAIN rows is constant
RIDGE_LAMBDA  = 1.0;    % mild, on standardised predictors

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
% gaps were filled by short causal forward-fill and TRAIN-only medians, so no
% validation or test information reaches the predictors.

%% Encode the binary text predictors against their rarer level
for p = predictors'
    if ~isstring(T.(p)); continue; end
    levels = unique(T.(p));
    counts = arrayfun(@(L) sum(T.(p) == L), levels);
    [~, rare] = min(counts);
    newName = matlab.lang.makeValidName(p + "_is_" + levels(rare));
    T.(newName) = double(T.(p) == levels(rare));
    predictors(predictors == p) = newName;
    fprintf('encoded %s -> %s (%d of %d rows)\n', p, newName, sum(T.(newName)), height(T));
end

isTrain = T.split == "train";
fprintf('\ntrain: %d rows, %d days\n', sum(isTrain), ...
    numel(unique(T.garmin_calendar_date(isTrain))));
for c = CONTROLS
    assert(any(predictors == string(c{1})), 'control %s is not a manifest predictor', c{1});
end

%% Drop near-constant candidates, judged on TRAIN. Controls are exempt: they are
%% forced in for what they represent, not for their spread.
keep = string(CONTROLS);
dropped = strings(0);
for p = predictors'
    if any(keep == p); continue; end
    x = T.(p)(isTrain);
    if std(x, 'omitnan') == 0
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
fprintf('predictors: %d -> %d (%d controls + %d candidates)\n', ...
    numel(predictors), numel(keep), numel(CONTROLS), numel(keep) - numel(CONTROLS));
for d = dropped; fprintf('  dropped %s\n', d); end

%% Forward selection, per horizon
selectedAll = table(); curveAll = table(); verdictAll = table();

for h = 1:size(HORIZONS, 1)
    name = string(HORIZONS{h, 1});
    targetCol = "target_bb_" + name;
    rows = isTrain & T.("eligible_" + name) == 1 & ~isnan(T.(targetCol));

    y    = T.(targetCol)(rows);
    days = T.garmin_calendar_date(rows);
    X    = table2array(T(rows, cellstr(keep)));

    [dayIdx, dayList] = findgroups(days);
    nDays = numel(dayList);
    fprintf('\n=== %s | train rows %d | days %d ===\n', name, numel(y), nDays);
    if nDays < 6
        fprintf('  too few days to cross-validate -- skipped\n'); continue
    end

    % Folds: one per day, skipping any too small to score.
    folds = {};
    for d = 1:nDays
        te = find(dayIdx == d); tr = find(dayIdx ~= d);
        if numel(te) >= 8 && numel(tr) >= 50; folds{end+1} = {tr, te}; end %#ok<AGROW>
    end

    controlCols = arrayfun(@(c) find(keep == c), string(CONTROLS));
    basePerDay  = looDayMae(X, y, folds, controlCols, RIDGE_LAMBDA);
    baseMae     = mean(basePerDay);
    baseSe      = std(basePerDay) / sqrt(numel(basePerDay));
    fprintf('  control model (current BB + change + hour sin/cos): MAE %.2f +/- %.2f\n', ...
        baseMae, baseSe);

    curveAll = [curveAll; table(name, 0, "(controls only)", baseMae, baseSe, 0, ...
        'VariableNames', {'horizon', 'step', 'added', 'loo_mae', 'loo_se', 'gain'})]; %#ok<AGROW>

    chosen = controlCols; chosenNames = strings(0);
    perDayByStep = {basePerDay};
    candidates = setdiff(1:numel(keep), controlCols);
    currentMae = baseMae;

    fprintf('  %-5s %-34s %8s %8s\n', 'step', 'added predictor', 'MAE', 'gain');
    for step = 1:MAX_ADDED
        bestMaeStep = inf; bestJ = 0; bestPerDay = [];
        for j = candidates
            % skip anything that duplicates a predictor already in the model
            duplicate = false;
            for c = chosen
                rr = corrcoef(X(:, j), X(:, c));
                if abs(rr(1, 2)) > REDUNDANT_ABS; duplicate = true; break; end
            end
            if duplicate; continue; end
            perDay = looDayMae(X, y, folds, [chosen j], RIDGE_LAMBDA);
            if mean(perDay) < bestMaeStep
                bestMaeStep = mean(perDay); bestJ = j; bestPerDay = perDay;
            end
        end
        if bestJ == 0; break; end
        gain = currentMae - bestMaeStep;
        chosen(end+1) = bestJ; %#ok<AGROW>
        chosenNames(end+1) = keep(bestJ); %#ok<AGROW>
        candidates = setdiff(candidates, bestJ);
        perDayByStep{end+1} = bestPerDay; %#ok<AGROW>
        fprintf('  %-5d %-34s %8.2f %+8.2f\n', step, keep(bestJ), bestMaeStep, gain);
        curveAll = [curveAll; table(name, step, keep(bestJ), bestMaeStep, ...
            std(bestPerDay) / sqrt(numel(bestPerDay)), gain, ...
            'VariableNames', {'horizon', 'step', 'added', 'loo_mae', 'loo_se', 'gain'})]; %#ok<AGROW>
        currentMae = bestMaeStep;
    end

    % How many additions the evidence justifies: one standard error from the best.
    theseRows  = curveAll(curveAll.horizon == name, :);
    [bestMae, bestIdx] = min(theseRows.loo_mae);
    threshold  = bestMae + theseRows.loo_se(bestIdx);
    chosenStep = theseRows.step(find(theseRows.loo_mae <= threshold, 1, 'first'));

    % Paired verdict: same held-out days for both models, so the per-day
    % difference is what carries the evidence.
    bestPerDay = perDayByStep{bestIdx};
    diffs   = basePerDay - bestPerDay;
    meanDiff = mean(diffs);
    seDiff   = std(diffs) / sqrt(numel(diffs));
    ratio    = meanDiff / max(seDiff, eps);
    wins     = sum(diffs > 0);
    if ratio >= 2;      verdict = "clear";
    elseif ratio >= 1;  verdict = "suggestive";
    else;               verdict = "not demonstrated";
    end

    fprintf('  best MAE %.2f at step %d; simplest within 1 SE is step %d\n', ...
        bestMae, theseRows.step(bestIdx), chosenStep);
    fprintf(['  physiology beyond trend+clock: %+.2f +/- %.2f MAE paired over %d days ' ...
             '(%.1f SE), better on %d/%d days -> %s\n'], ...
        meanDiff, seDiff, numel(diffs), ratio, wins, numel(diffs), upper(verdict));

    verdictAll = [verdictAll; table(name, baseMae, baseSe, bestMae, ...
        theseRows.step(bestIdx), chosenStep, baseMae - bestMae, meanDiff, seDiff, ...
        ratio, string(sprintf('%d/%d', wins, numel(diffs))), verdict, ...
        'VariableNames', {'horizon', 'control_mae', 'control_se', 'best_mae', ...
            'best_step', 'chosen_step', 'improvement', 'paired_mean_diff', ...
            'paired_se_diff', 'paired_se_ratio', 'days_improved', 'verdict'})]; %#ok<AGROW>

    for i = 1:min(chosenStep, numel(chosenNames))
        selectedAll = [selectedAll; table(name, i, chosenNames(i), "added", ...
            'VariableNames', {'horizon', 'rank', 'predictor', 'role'})]; %#ok<AGROW>
    end
    for c = string(CONTROLS)
        selectedAll = [selectedAll; table(name, 0, c, "control", ...
            'VariableNames', {'horizon', 'rank', 'predictor', 'role'})]; %#ok<AGROW>
    end
end

writetable(selectedAll, fullfile(OUTDIR, 's02_selected_features.csv'));
writetable(curveAll,    fullfile(OUTDIR, 's02_selection_curve.csv'));
writetable(verdictAll,  fullfile(OUTDIR, 's02_verdict.csv'));
fprintf('\nwrote %s\n', fullfile(OUTDIR, 's02_verdict.csv'));

%% Figure: error against the control line, as predictors are added
figure('Name', 'What physiology adds', 'Color', 'w', 'Position', [100 100 980 380]);
names = unique(curveAll.horizon, 'stable');
for i = 1:numel(names)
    subplot(1, numel(names), i);
    rows = curveAll.horizon == names(i);
    step = curveAll.step(rows); mae = curveAll.loo_mae(rows); se = curveAll.loo_se(rows);
    errorbar(step, mae, se, '-o', 'MarkerSize', 3.5, 'LineWidth', 1.3, ...
        'Color', [0.16 0.42 0.33], 'CapSize', 0);
    hold on;
    yline(mae(step == 0), '--', 'trend+clock', 'Color', [0.45 0.45 0.45], ...
        'LabelVerticalAlignment', 'bottom');
    v = verdictAll(verdictAll.horizon == names(i), :);
    if ~isempty(v)
        xline(v.chosen_step(1), ':', sprintf('%s', v.verdict(1)), ...
            'Color', [0.7 0.3 0.1]);
    end
    hold off; grid on; box off;
    xlabel('predictors added'); if i == 1; ylabel('leave-one-day-out MAE'); end
    title(names(i));
end
sgtitle('Error as predictors are added to the control model (train days only)');
pngPath = fullfile(OUTDIR, 's02_features.png');
if exist('exportgraphics', 'file')
    exportgraphics(gcf, pngPath, 'Resolution', 150);
else
    print(gcf, pngPath, '-dpng', '-r150');
end
fprintf('wrote %s\n', pngPath);

%% ---------- local functions ----------

function perDay = looDayMae(X, y, folds, cols, lambda)
    % Leave-one-day-out error, returned per day so its spread can be reported
    % and so two feature sets can be compared on the same days.
    perDay = zeros(numel(folds), 1);
    for f = 1:numel(folds)
        tr = folds{f}{1}; te = folds{f}{2};
        yhat = ridgePredict(X(tr, cols), y(tr), X(te, cols), lambda);
        perDay(f) = mean(abs(y(te) - yhat));
    end
end

function yhat = ridgePredict(Xtr, ytr, Xte, lambda)
    % Ridge on standardised predictors, standardisation fitted on the training
    % fold only. A probe for comparing feature sets, not a candidate model.
    mu = mean(Xtr, 1);
    sg = std(Xtr, 0, 1);
    sg(sg == 0 | isnan(sg)) = 1;
    Ztr = (Xtr - mu) ./ sg;
    Zte = (Xte - mu) ./ sg;
    yBar = mean(ytr);
    beta = (Ztr' * Ztr + lambda * eye(size(Ztr, 2))) \ (Ztr' * (ytr - yBar));
    yhat = Zte * beta + yBar;
end
