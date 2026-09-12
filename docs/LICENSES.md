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

The avatar has no external textures or animation downloads. Its GLB is about 400 KB with 13,212 triangles. System fonts are used; there are no font-CDN requests. Dependency versions are locked in `uv.lock` and `frontend/package-lock.json`.
