from __future__ import annotations

from datetime import datetime
from typing import Any

import pyodbc
from sqlalchemy.engine import make_url

from materials.models import MaterialRecord, MaterialStatus


MATERIAL_QUERY = """
    SELECT code, name, materialspec, materialshortname,
           ename, memo, enablestate, creationtime, modifiedtime
    FROM bd_material_v
    """

MATERIAL_CHANGED_QUERY = MATERIAL_QUERY + " WHERE modifiedtime >= ? OR modifiedtime IS NULL"
MATERIAL_CODES_QUERY = "SELECT code FROM bd_material_v"


class NccMaterialSource:
    """用友 NCC 物料数据源 Adapter；ERP 连接严格只读。"""

    def __init__(self, connection_string: str):
        self._connection_string = connection_string

    @classmethod
    def from_url(cls, url: str) -> "NccMaterialSource":
        parsed = make_url(url)
        query = dict(parsed.query)
        driver = query.pop("driver", "ODBC Driver 18 for SQL Server")
        server = parsed.host or "localhost"
        if parsed.port:
            server = f"{server},{parsed.port}"
        parts = [
            f"DRIVER={{{driver}}}",
            f"SERVER={server}",
            f"DATABASE={parsed.database or ''}",
            f"UID={parsed.username or ''}",
            f"PWD={parsed.password or ''}",
        ]
        parts.extend(f"{key}={value}" for key, value in query.items())
        return cls(";".join(parts))

    def fetch_materials(self, modified_since: datetime | None = None) -> list[MaterialRecord]:
        with pyodbc.connect(self._connection_string, timeout=10) as connection:
            cursor = connection.cursor()
            if modified_since is None:
                cursor.execute(MATERIAL_QUERY)
            else:
                cursor.execute(MATERIAL_CHANGED_QUERY, modified_since)
            columns = [column[0] for column in cursor.description]
            return [self._to_record(dict(zip(columns, row, strict=True))) for row in cursor.fetchall()]

    def fetch_codes(self) -> list[str]:
        with pyodbc.connect(self._connection_string, timeout=10) as connection:
            cursor = connection.cursor()
            cursor.execute(MATERIAL_CODES_QUERY)
            return [str(row[0]) for row in cursor.fetchall() if row[0] is not None]

    @staticmethod
    def _to_record(row: Any) -> MaterialRecord:
        status_value = int(row.get("enablestate") or 3)
        status = {
            1: MaterialStatus.INACTIVE,
            2: MaterialStatus.ACTIVE,
            3: MaterialStatus.DISABLED,
        }.get(status_value, MaterialStatus.DISABLED)
        return MaterialRecord(
            code=str(row.get("code") or ""),
            name=str(row.get("name") or ""),
            specification=str(row.get("materialspec") or ""),
            short_name=str(row.get("materialshortname") or ""),
            english_name=str(row.get("ename") or ""),
            description=str(row.get("memo") or ""),
            status=status,
            created_at=row.get("creationtime"),
            modified_at=row.get("modifiedtime"),
        )
