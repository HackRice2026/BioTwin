from typing import Protocol, AsyncIterator
from datetime import datetime
from shared.schemas import Provenance, TwinFrame


class SourceAdapter(Protocol):
    provenance: Provenance

    async def authorize(self, user_id: str) -> dict | str: ...

    def backfill(self, user_id: str, since: datetime) -> AsyncIterator[TwinFrame]: ...

    def stream(self, user_id: str) -> AsyncIterator[TwinFrame]: ...

    async def health(self) -> dict: ...
