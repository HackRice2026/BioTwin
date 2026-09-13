# BioTwin 2.0 — central plan

Authorized by Shivendra on 2026-09-12. This records the user's full redesign
request and subsequent authorization to implement it. Work on `biotwin2.0`,
branched from `dev`; make multiple logical commits as Shivendra. Maintain
`AGENTS.md` throughout. Keep secrets and personal data out of git.

## Product and scope

Rebuild the BioTwin frontend entirely. Preserve the existing backend and
pipeline: Gemini via Vertex AI, ElevenLabs, transcription, readiness and
recovery modeling, persistence, live wearable data, and avatar animation.
Change backend endpoints or shapes only when required by the new frontend.
Remove the old UI after the replacement passes end-to-end verification.

Build two real responsive layouts sharing five sections: Overview, Signals,
Daily plan, What-if lab, Connections. Mobile uses a bottom tab bar; desktop
uses persistent navigation and a dashboard suited to its wider screen.

Use a dark, modern, glassy health-app design with neutral surfaces and white
type. Use red for heart rate, blue for sleep/calm, amber for energy expenditure,
and green for activity and positive states. Avoid debug labels and internal
engineering status in the product UI. Retain meaningful measurement origins,
missing-data states, and honest labels for estimates and scenarios.

## Required experiences

- Persistent Body Battery top bar on every page: a 0–100 energy reserve
  estimate derived from sleep, HRV, recovery and rest, styled as an iOS-like
  filling battery with percentage. Clearly distinguish BioTwin's estimate
  from Garmin's reported battery measurement.
- Overview: digital twin hero first, with current state and listening,
  thinking, speaking or idle status. Below: compact heart rate, sleep,
  calories burned and steps cards, readiness score and recovery chart.
- Detect the topic of the user's question immediately, before Gemini answers.
  Both typed and genuinely transcribed questions can open heart rate, sleep,
  calories, steps, plan or what-if panels across the lower screen. Display
  actual charts/data and captions synchronized to the answer's audio. Keep
  the twin's speaking indicator visible. A back button dismisses the panel;
  completed speech automatically returns to the normal Overview. Text-only
  and failed-audio answers remain accessible with a clear state.
- Preserve calendar sync, availability, proposal confirmation and booking,
  event reminders, transcript history/replay, What-if Lab, all connections
  and import/live paths, preferences, authentication, export/deletion,
  readiness/recovery explanations and recalibration, and avatar states,
  gestures, viewing controls and reduced motion.
- Preserve PWA installability, manifest, service worker, offline behavior
  and iOS icon support. Never cache private health API responses.

## Implementation checklist

- [x] Inventory existing features and create branch from dev.
- [x] Record authorized central plan and commit workflow.
- [x] Add timestamped speech and question-topic lifecycle with regression tests.
- [x] Build distinct mobile/desktop layouts and all five sections.
- [x] Wire Body Battery, live charts, twin hero and topic takeovers.
- [x] Rebuild Connections and transcript UI; preserve every existing action.
- [x] Verify real recorded question → transcription → Vertex → ElevenLabs →
  captions/audio → Overview; test missing/failed provider states too.
- [x] Verify mobile/desktop navigation, calendar actions, simulations, history,
  account isolation, PWA manifest/icons/service worker and offline behavior.
- [x] Remove the old UI after verification and finish local checks.
- [ ] Push the logical commits and verify the remote branch.

## Verification baseline

Before redesign: Python suite 64 passed / 3 skipped; frontend production build
passes (existing large Three.js chunk warning). New dev updates include face
and EMAGE body services; retain both integrations. Existing untracked PWA icon
assets must be preserved. Human microphone hardware verification must be
distinguished from automated testing with a spoken audio recording.
