# Fitness Harness Branch

Branch: `fitness-model-harness`

Base: latest `origin/dev`

## One-line summary

We built a deterministic fitness coaching harness that turns wearable data, calendar context, forecasts, and simulations into grounded decisions Gemini can explain but not invent.

## Why this matters

BioTwin is stronger when it is not just "Gemini answering fitness questions." The durable product is the layer around Gemini: the user's current state, forecast, plan, policy rules, scenario checks, and evidence. This branch makes that layer explicit.

The app now decides from structured data first, then lets Gemini explain that decision in natural coaching language. Gemini can be warm and helpful, but it is constrained by the harness so it cannot casually invent a better workout time, fake plan, or scenario result.

## What the user should feel

The visible experience should feel like:

> Your best window is later today because your calendar opens up and your readiness forecast looks better there.

Not:

> Here is a technical harness object and a pile of metrics.

The UI should stay judge-facing and coach-like: forecast, decision, adaptation, explanation.

## What changed

- Added a canonical `FitnessHarnessResult` contract with:
  - `state`
  - `forecast`
  - `policy_decisions`
  - `plan`
  - `scenarios`
  - `evidence`
  - `confidence`
  - `allowed_actions`
  - `next_actions`
- Added `modeling/harness.py` to derive the source-of-truth coaching object from readiness, outlook, plan, and simulations.
- Added `/api/harness` so the frontend consumes the same coaching result Gemini receives.
- Added the harness into `NarrationContext`, so Gemini gets structured coaching context alongside readiness, baseline, plan, prediction, provenance, and quality.
- Updated Gemini instructions to speak like a coach: practical suggestion first, then 1-2 strongest data-backed reasons, without dumping every metric.
- Updated narration facts to sound natural: "coaching confidence," "coaching guardrail," and "recommended next step," not internal harness jargon.
- Integrated the harness into the latest `dev` UI through `useDashboard` and `DashboardPanels`.
- Added a small Daily Plan "Why this works" block backed by harness forecast and policy decisions.
- Added a What-if Lab scenario impact summary from actual simulated start, peak, and end heart-rate values.

## Guardrails added

1. Narration must not contradict harness or plan timing evidence.
   - If Gemini cites a harness/plan time, the time it says must exist in that cited evidence.

2. Plan duration must fit available calendar windows.
   - Harness validation rejects proposals that overlap busy calendar intervals.

3. Scenario explanations must match actual scenario outputs.
   - Scenario summaries are derived from the real simulated curve, not from an LLM guess.

## Main files

- `modeling/harness.py`
  - Builds the deterministic `FitnessHarnessResult`.

- `shared/schemas/__init__.py`
  - Defines `FitnessHarnessResult`, `HarnessMetric`, `HarnessDecision`, and `HarnessScenario`.

- `core/api.py`
  - Exposes `/api/harness`.
  - Adds outlook-aware harness context to Gemini narration.

- `modeling/explanations.py`
  - Adds coach-facing harness facts to `NarrationContext`.

- `narration/service.py`
  - Strengthens Gemini prompt and grounding validation.

- `frontend/src/useDashboard.ts`
  - Loads `/api/harness` with the dashboard data.

- `frontend/src/DashboardPanels.tsx`
  - Renders the small coach-facing decision explanation and scenario impact.

- `docs/FITNESS_HARNESS_BRANCH_CONTEXT.md`
  - Short handoff note for future agents.

## Verification

Last verified on this branch after rebasing onto latest `origin/dev`:

```bash
uv run pytest -q
npm run test --prefix frontend
npm run build --prefix frontend
git diff --check
```

Results:

- Python: `103 passed, 3 skipped`
- Frontend tests: `21 passed`
- Frontend production build: passed
- Diff whitespace check: clean

## Remaining work

1. Make the planner directly consume `FitnessHarnessResult.policy_decisions` instead of recomputing similar policy logic in `planning.py`.
2. Add action validation so Gemini can request semantic actions and the harness can approve, reject, or defer them.
3. Add richer comparisons such as "train now vs best window" instead of only rest/light/exercise single-path scenarios.
4. Store harness snapshots with conversations so later evaluation can prove what Gemini was allowed to say.
5. Browser-capture the Daily Plan and What-if Lab after latest `dev` UI changes for visual evidence.

## Product line

Foundation models can talk about fitness. The harness is what turns that into a coach that understands the user over time.
