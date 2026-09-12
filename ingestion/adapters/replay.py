import asyncio
from datetime import timedelta
from shared.schemas import TwinFrame, Provenance, utcnow


class ReplayAdapter:
    provenance = Provenance.REPLAY

    def __init__(self, records, speed=1):
        if not 0.1 <= speed <= 100:
            raise ValueError("Replay speed must be between 0.1 and 100")
        self.records = records
        self.speed = speed

    async def authorize(self, user_id):
        return {"status": "local", "provenance": self.provenance}

    async def health(self):
        return {"status": "available", "records": len(self.records)}

    async def backfill(self, user_id, since):
        for raw in self.records:
            frame = TwinFrame.model_validate({**raw, "user_id": user_id, "provenance": self.provenance})
            if frame.event_time >= since:
                yield frame

    async def stream(self, user_id):
        records = sorted(
            [
                TwinFrame.model_validate({**r, "user_id": user_id, "provenance": self.provenance})
                for r in self.records
            ],
            key=lambda f: f.event_time,
        )
        if not records:
            return
        anchor, previous = utcnow(), 0
        for frame in records:
            offset = (frame.event_time - records[0].event_time).total_seconds() / self.speed
            await asyncio.sleep(max(0, offset - previous))
            yield frame.model_copy(
                update={"event_time": anchor + timedelta(seconds=offset), "ingest_time": utcnow()}
            )
            previous = offset
