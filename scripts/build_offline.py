"""Generate the bundled synthetic replay through production adapters, normalizer, store, and model."""

import asyncio
import json
import tempfile
from pathlib import Path
from datetime import timedelta
from core.config import Settings
from core.runtime import Runtime
from shared.schemas import utcnow, TwinFrame, Provenance
from modeling.explanations import narration_context
from modeling.outlook import daily_outlook
from modeling.engine import simulate
from modeling.recovery import score_prediction
from shared.schemas import RecoveryPrediction
from narration.service import template
from ingestion.normalizer import METRICS


async def main():
    with tempfile.TemporaryDirectory() as directory:
        runtime = Runtime(Settings(_env_file=None, database_url=f"sqlite:///{directory}/golden.db"))
        await runtime.start()
        for task in runtime.tasks:
            task.cancel()
        await asyncio.gather(*runtime.tasks, return_exceptions=True)
        states = []
        now = utcnow()
        for i in range(12):
            frame = TwinFrame(
                user_id="demo",
                event_time=now - timedelta(seconds=12 - i),
                provenance=Provenance.SYNTHETIC,
                heart_rate_bpm=66 + i * 0.4,
                respiration_brpm=14 + i * 0.1,
                activity_level=0.04,
            )
            await runtime.ingest(frame)
            states.append(runtime.states["demo"].model_dump(mode="json"))
        state = runtime.states["demo"]
        plan = await runtime.get_plan(runtime.store.user("demo"))
        history = runtime.history("demo")
        metrics = {}
        for metric in METRICS:
            metrics[metric] = {
                "series": [
                    {
                        "time": f.event_time.isoformat(),
                        "value": getattr(f, metric).model_dump(mode="json")
                        if metric == "sleep"
                        else getattr(f, metric),
                        "provenance": f.provenance.value,
                        "confidence": f.confidence,
                    }
                    for f in history
                    if getattr(f, metric) is not None
                ]
            }
        context = narration_context(state, plan)
        payload = {
            "simulations": {scenario: simulate(scenario, state, now).model_dump(mode="json") for scenario in ["rest", "light", "exercise"]},
            "outlook": daily_outlook(state, runtime.store.user("demo")["profile"], now).model_dump(
                mode="json"
            ),
            "generated_at": now.isoformat(),
            "states": states,
            "plan": plan.model_dump(mode="json"),
            "metrics": {k: v for k, v in metrics.items() if k != "sleep"},
            "sleep": metrics["sleep"],
            "predictions": [
                score_prediction(RecoveryPrediction.model_validate(p), history).model_dump(mode="json")
                for _, p in runtime.store.docs("demo", "prediction")
            ],
            "readiness": [p for _, p in sorted(runtime.store.docs("demo", "readiness"))],
            "answers": {
                key: template(question, context)
                for key, question in {
                    "readiness": "Why am I tired?",
                    "recovery": "How is my recovery?",
                    "sleep": "How was my sleep?",
                    "plan": "What is my plan?",
                }.items()
            },
        }
        destination = Path(__file__).resolve().parents[1] / "frontend/public/offline.json"
        destination.write_text(json.dumps(payload, separators=(",", ":")))
        (destination.parents[2] / "fixtures/golden/twin-state.json").write_text(
            json.dumps(states[0], indent=2) + "\n"
        )
        await runtime.close()
        print(
            f"Generated {len(states)} states through production pipeline; {destination.stat().st_size} bytes"
        )


if __name__ == "__main__":
    asyncio.run(main())
