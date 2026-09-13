# Fitness Harness Branch Context

Branch: `fitness-model-harness`

Base: `origin/dev`

## Goal

Build on Aditya's existing readiness, recovery, daily outlook, planner, and what-if simulation math by making the fitness harness visible and structured. Gemini should receive domain decisions from the harness, not invent coaching constraints from a prompt.

## What changed

- Added shared `FitnessHarnessResult` contracts:
  - `HarnessMetric`
  - `HarnessDecision`
  - `HarnessScenario`
  - `FitnessHarnessResult`
- Added `modeling/harness.py`, which derives:
  - current user-state metrics
  - forecast summary from `DayOutlook`
  - training policy decisions
  - plan evaluation checks
  - scenario impact checks when a simulation is supplied
  - next recommended action
- Added `/api/harness` for the frontend.
- Added the harness into `NarrationContext`, so Gemini receives it alongside readiness, baseline, plan, prediction, facts, provenance, and quality.
- Added harness facts to deterministic/template narration context.
- Added a Daily Plan harness panel showing policy, forecast, checks, and confidence.
- Added a What-if Lab scenario impact card showing start, peak, and ending heart-rate trajectory for the selected scenario.
- Regenerated shared schema and frontend contracts.
- Added tests for deterministic harness construction and API exposure.
- Promoted the source-of-truth shape to:
  - `state`
  - `forecast`
  - `policy_decisions`
  - `plan`
  - `scenarios`
  - `evidence`
  - `confidence`
  - `allowed_actions`
- Added hard validators/tests:
  - Gemini narration is rejected when cited harness/plan timing evidence is contradicted.
  - Harness plan checks reject proposals that overlap busy calendar windows.
  - Scenario summaries are derived from the actual simulated curve start/peak/end values.
- Reworded the visible Daily Plan panel from developer-facing harness language to judge-facing "Forecast / Decision / Adaptation" language.

## Remaining work

1. Make the planner directly consume `FitnessHarnessResult.policy_decisions` instead of recomputing similar rules inside `planning.py`.
2. Add pending calendar/action intent validation so Gemini can request actions and the harness can approve or reject them.
3. Add richer scenario comparisons: train now vs best window, not just rest/light/exercise single-path simulations.
4. Store harness snapshots with conversations for later evaluation.
5. Add browser verification screenshots for the new Daily Plan and What-if UI.

## Guardrail

Keep the LLM as the explainer and semantic-action chooser. Keep training policy, forecast, calendar fit, and simulation checks deterministic and inspectable.
