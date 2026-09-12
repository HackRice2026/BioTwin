import json
from pathlib import Path
from pydantic import create_model
from shared.schemas import (
    TwinState,
    TwinFrame,
    Baseline,
    Readiness,
    RecoveryPrediction,
    DailyPlan,
    NarrationContext,
    NarrationResponse,
    SimulationOverlay,
    DayOutlook,
)

root = Path(__file__).resolve().parents[2]
Package = create_model(
    "BioTwinContracts",
    **{
        model.__name__: (model, ...)
        for model in [
            TwinState,
            TwinFrame,
            Baseline,
            Readiness,
            RecoveryPrediction,
            DailyPlan,
            NarrationContext,
            NarrationResponse,
            SimulationOverlay,
            DayOutlook,
        ]
    },
)
(root / "shared/schemas/schema.json").write_text(json.dumps(Package.model_json_schema(), indent=2) + "\n")
