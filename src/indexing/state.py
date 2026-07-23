from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine, text


class PostgresIndexState:
    """保存增量同步状态，不写入 ERP。"""

    def __init__(self, url: str):
        self.engine = create_engine(url, pool_pre_ping=True, future=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS material_index_state (
                        code TEXT PRIMARY KEY,
                        modified_at TIMESTAMP NULL,
                        indexed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS material_sync_checkpoint (
                        name TEXT PRIMARY KEY,
                        last_modified TIMESTAMP NULL
                    )
                    """
                )
            )

    def checkpoint(self) -> datetime | None:
        with self.engine.connect() as connection:
            return connection.execute(
                text("SELECT last_modified FROM material_sync_checkpoint WHERE name = 'materials'")
            ).scalar_one_or_none()

    def modified_times(self) -> dict[str, datetime | None]:
        with self.engine.connect() as connection:
            rows = connection.execute(text("SELECT code, modified_at FROM material_index_state"))
            return {str(code): modified_at for code, modified_at in rows}

    def indexed_codes(self) -> set[str]:
        with self.engine.connect() as connection:
            rows = connection.execute(text("SELECT code FROM material_index_state"))
            return {str(code) for (code,) in rows}

    def save(self, records: list[tuple[str, datetime | None]], checkpoint: datetime | None) -> None:
        with self.engine.begin() as connection:
            for code, modified_at in records:
                connection.execute(
                    text(
                        """
                        INSERT INTO material_index_state (code, modified_at)
                        VALUES (:code, :modified_at)
                        ON CONFLICT (code) DO UPDATE SET
                            modified_at = EXCLUDED.modified_at,
                            indexed_at = NOW()
                        """
                    ),
                    {"code": code, "modified_at": modified_at},
                )
            if checkpoint is not None:
                connection.execute(
                    text(
                        """
                        INSERT INTO material_sync_checkpoint (name, last_modified)
                        VALUES ('materials', :last_modified)
                        ON CONFLICT (name) DO UPDATE SET last_modified = EXCLUDED.last_modified
                        """
                    ),
                    {"last_modified": checkpoint},
                )

    def remove(self, codes: set[str]) -> None:
        if not codes:
            return
        with self.engine.begin() as connection:
            for code in codes:
                connection.execute(text("DELETE FROM material_index_state WHERE code = :code"), {"code": code})
