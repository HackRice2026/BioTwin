# Asset and library licenses

| Asset | Origin | Permission |
|---|---|---|
| `frontend/public/assets/twin.glb` | Original geometry and articulated hierarchy created by `scripts/build-avatar.mjs` for this project | Project-owned; no third-party model or animation asset |
| Procedural gestures and activity FSM | Original code in `frontend/src/Avatar.tsx` and `fsm.ts` | Project-owned |
| `frontend/public/icon.svg` | Original BioTwin mark created for this project | Project-owned |
| Offline JSON / golden recovery FIT | Generated from this project's synthetic data generator/test fixture | No real person's health history |
| Interface icons | Lucide (`lucide-react`) | ISC; package license included in installed dependency |
| Three.js / React Three Fiber / Drei | Open-source npm dependencies | MIT; see each locked package's license |
| React / Recharts / Vite | Open-source npm dependencies | MIT; see each locked package's license |

The active avatar is the existing team-supplied `model.glb` (about 15 MB),
not the legacy generated `twin.glb`. Its rig and animation integrations are
preserved by the redesign; see `AVATAR_IMPLEMENTATION_PLAN.md` for their origins.

`frontend/public/assets/studio.hdr` is Greg Zaal’s **Lebombo** HDRI from
[Poly Haven](https://polyhaven.com/a/lebombo), CC0. It is the same lighting asset
Drei’s apartment preset used, now stored locally for offline operation (copied
from pmndrs/drei-assets commit 456060a26bbeb8fdf79326f224b6d99b8bcce736).
DM Sans and Manrope are loaded through Google Fonts, with local system-font
fallbacks when offline. Dependency versions remain locked in `uv.lock` and
`frontend/package-lock.json`.
