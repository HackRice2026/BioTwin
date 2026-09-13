"""Export what the app needs to draw a Body Battery trajectory at 1h, 3h and 6h.

One model does not win at every horizon, and pretending otherwise would put the
worse predictor on a chart. Stage 1 and Stage 3 measured which wins where, and
this exports exactly those:

    1 hour   the ridge model          1.91 MAE, against 2.35 for the best rule
    3 hours  trend + clock            5.20 MAE, against 6.32 for the ridge
    6 hours  time of day alone        7.37 MAE, against 9.21 for the ridge

Trend + clock averages a linear extrapolation of the current level with the
hour-of-day climatology. Both of the latter two need that climatology -- the mean
Body Battery this person reaches at each hour of the day -- so it is computed
here on the TRAIN split only and written out as 24 numbers per horizon.

The 1-hour entry is exported too, even though the ridge wins there. It is the
fallback for when the current Body Battery reading is too old for the ridge to
use: the hour-of-day rhythm needs nothing but the clock, so it can still answer
when the model cannot, at its own honestly worse error.

Every MAE is recomputed on the validation split rather than copied from the
stage tables, so a number in the shipped file cannot drift from the data.

    ./.venv/bin/python -m matlab.export_trajectory_params
"""

import csv
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAINING = ROOT / "processed_data" / "garmin_5min_training.csv"
OUT = ROOT / "matlab" / "params_trajectory.json"
HORIZONS = [("1h", 60), ("3h", 180), ("6h", 360)]
BB_MIN, BB_MAX = 0.0, 100.0


def number(raw):
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return None if value != value else value


def clip(value):
    return max(BB_MIN, min(BB_MAX, value))


def rows():
    with TRAINING.open() as handle:
        for row in csv.DictReader(handle):
            yield row


def target_hour(row, minutes):
    stamp = datetime.fromisoformat(row["local_timestamp"].replace("Z", "+00:00"))
    return (stamp.hour + (stamp.minute + minutes) // 60) % 24


def main():
    data = list(rows())
    export = {
        "source": "processed_data/garmin_5min_training.csv",
        "note": (
            "Per-horizon predictors chosen by measured validation error, not by "
            "preferring one model. The ridge in params_forecast.json wins at 1 "
            "hour; beyond it this person's own hour-of-day rhythm wins."
        ),
        "horizons": {},
    }

    for name, minutes in HORIZONS:
        target = "target_bb_" + name
        usable = [
            r for r in data
            if r.get("eligible_" + name) in ("1", "1.0", "True", "true")
            and number(r[target]) is not None
            and number(r["bb_current_measured"]) is not None
        ]
        train = [r for r in usable if r["split"] == "train"]
        validation = [r for r in usable if r["split"] == "validation"]

        # Climatology of the TARGET hour, the way Stage 1 built it: what this
        # person's Body Battery averages at the hour being predicted.
        overall = sum(number(r[target]) for r in train) / len(train)
        climatology = []
        for hour in range(24):
            at_hour = [number(r[target]) for r in train if target_hour(r, minutes) == hour]
            climatology.append(round(sum(at_hour) / len(at_hour) if at_hour else overall, 4))

        def predict(row, method):
            current = number(row["bb_current_measured"])
            clock = climatology[target_hour(row, minutes)]
            if method == "time_of_day":
                return clock
            change = number(row["bb_current_change_1h"]) or 0.0
            extrapolated = clip(current + change / 60 * minutes)
            return clip((extrapolated + clock) / 2)

        scores = {}
        for method in ("trend_plus_clock", "time_of_day"):
            errors = [abs(number(r[target]) - predict(r, method)) for r in validation]
            scores[method] = round(sum(errors) / len(errors), 4)
        chosen = min(scores, key=scores.get)

        export["horizons"][name] = {
            "minutes": minutes,
            "method": chosen,
            "validation_mae": scores[chosen],
            "alternatives": scores,
            "climatology_by_target_hour": climatology,
            "fitted_on": {"rows": len(train), "days": len({r["garmin_calendar_date"] for r in train})},
            "validated_on": {"rows": len(validation), "days": len({r["garmin_calendar_date"] for r in validation})},
        }
        print(f"{name}: {chosen} wins, validation MAE {scores[chosen]}  (alternatives {scores})")

    OUT.write_text(json.dumps(export, indent=2) + "\n")
    print(f"\nwrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
