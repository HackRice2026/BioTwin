"""Issue prequential recovery predictions over imported history.

A prediction is only evidence if it was made before its observations. The demo
workspace gets this from a seed path in Runtime.start; imported real measurements
never do, because `/api/ingest/file` and the bulk importer both ingest with
broadcast=False and the prediction block sits after that early return.

This walks real recovery onsets in time order and, at each one, recomputes the
state using ONLY data up to that instant, issues a forecast stamped at that
instant, and stores it immutably. Later real samples then score it -- a true
out-of-sample error on this account's own measurements.

    uv run python -m scripts.backfill_predictions --email you@example.com
"""

import argparse
import asyncio

from core.config import Settings
from core.runtime import Runtime
from modeling.recovery import issue_prediction, score_prediction, segments


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--limit", type=int, default=40, help="most recent onsets to use")
    ap.add_argument("--replace", action="store_true", help="clear stored predictions first")
    a = ap.parse_args()

    rt = Runtime(Settings())
    await rt.start()
    try:
        user = rt.store.by_email(a.email.lower().strip())
        if not user:
            raise SystemExit(f"no account for {a.email}")
        uid = user["id"]

        if a.replace:
            for key, _ in rt.store.docs(uid, "prediction"):
                rt.store.put(uid, "prediction", {}, key)

        history = rt.history(uid)
        print(f"{len(history)} measurements within the retention window")
        base = rt.compute(uid, refit=True).baseline_summary
        found = segments(history, base.resting_hr.median, absolute=True)
        print(f"{len(found)} recovery segments detected\n")
        onsets = sorted({onset for _t, _y, onset in found})[-a.limit:]
        print(f"issuing at the {len(onsets)} most recent onsets")

        issued = skipped = 0
        for t in onsets:
            state = rt.compute(uid, now=t, refit=True)
            if state.baseline_summary.recovery_tau_s is None:
                skipped += 1        # too little prior history to have had a constant yet
                continue
            pred = issue_prediction(t, state.latest, state.baseline_summary)
            if not pred:
                skipped += 1
                continue
            rt.store.put(uid, "prediction", pred.model_dump(mode="json"), pred.id, immutable=True)
            issued += 1
            print(f"  {t:%Y-%m-%d %H:%M}  tau {state.baseline_summary.recovery_tau_s:>6.1f}s  "
                  f"from {state.baseline_summary.tau_fit_n_sessions} prior sessions  "
                  f"peak {state.latest.heart_rate_bpm:.0f} bpm")

        print(f"\nissued {issued}, skipped {skipped} (no constant fitted from prior data yet)")

        scored = []
        for _, raw in rt.store.docs(uid, "prediction"):
            if not raw:
                continue
            from shared.schemas import RecoveryPrediction
            original = RecoveryPrediction.model_validate(raw)
            result = score_prediction(original, rt.prediction_window(uid, original))
            if result.rmse is not None:
                scored.append(result.rmse)
        if scored:
            scored.sort()
            print(f"\n=== OUT-OF-SAMPLE ERROR ON REAL MEASUREMENTS ===")
            print(f"  scored predictions   {len(scored)}")
            print(f"  median RMSE          {scored[len(scored)//2]:.2f} bpm")
            print(f"  best / worst         {scored[0]:.2f} / {scored[-1]:.2f} bpm")
        else:
            print("\nno prediction has overlapping later observations yet")
        rt.publish(uid, rt.compute(uid, refit=True))
    finally:
        await rt.close()


if __name__ == "__main__":
    asyncio.run(main())
