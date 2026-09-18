"""Session store. In-memory for the MVP; the interface is what Supabase/Postgres
will implement later (sessions + turns + ledger_events tables)."""
from __future__ import annotations

from typing import Protocol

from .models import Session


class SessionStore(Protocol):
    async def get(self, session_id: str) -> Session | None: ...
    async def save(self, session: Session) -> None: ...


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    async def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    async def save(self, session: Session) -> None:
        self._sessions[session.id] = session


store = InMemorySessionStore()
