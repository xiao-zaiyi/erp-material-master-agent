from typing import Protocol

from sqlalchemy import create_engine, text


class FeedbackRepository(Protocol):
    def record_feedback(self, payload: dict) -> None: ...


class PostgresFeedbackRepository:
    def __init__(self, url: str):
        self.engine = create_engine(url, pool_pre_ping=True, future=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        statement = text(
            """
            CREATE TABLE IF NOT EXISTS material_feedback (
                id BIGSERIAL PRIMARY KEY,
                query_name TEXT NOT NULL DEFAULT '',
                query_specification TEXT NOT NULL DEFAULT '',
                candidate_code TEXT NOT NULL,
                decision TEXT NOT NULL CHECK (decision IN ('same', 'different')),
                confirmed_by TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        with self.engine.begin() as connection:
            connection.execute(statement)

    def record_feedback(self, payload: dict) -> None:
        query = payload.get("query", {})
        statement = text(
            """
            INSERT INTO material_feedback (
                query_name, query_specification, candidate_code, decision, confirmed_by, note
            ) VALUES (
                :query_name, :query_specification, :candidate_code, :decision, :confirmed_by, :note
            )
            """
        )
        params = {
            "query_name": query.get("name", ""),
            "query_specification": query.get("specification", ""),
            "candidate_code": payload["candidate_code"],
            "decision": payload["decision"],
            "confirmed_by": payload["confirmed_by"],
            "note": payload.get("note", ""),
        }
        with self.engine.begin() as connection:
            connection.execute(statement, params)
