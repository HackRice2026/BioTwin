# Simulate My Day

This branch adds a reproducible what-if engine for the Battery Forecast modal.

The source of truth is still the MATLAB-exported Body Battery trajectory in `modeling.forecast.trajectory`. The new `/api/simulate/day` endpoint builds scenario overlays on top of that baseline so the UI can compare futures without asking Gemini to invent numbers.

Implemented scenarios:
- Current plan baseline.
- Train now.
- Train at the best planned window.
- Add 0-10,000 extra steps.
- Take a 10-60 minute recovery break.

Important modeling boundary: step/workout/recovery effects are deterministic scenario estimates for coaching and planning, not proven causal physiology. The UI says this plainly while still making the interaction feel like moving the day and watching the forecast respond.

Frontend entry point: the existing Battery Forecast modal now includes the `Simulate My Day` section with scenario buttons, a steps slider, decision cards, and a coach-style explanation.
