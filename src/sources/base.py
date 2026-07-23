from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol

from materials.models import MaterialRecord


class MaterialSource(Protocol):
    def get_by_id(self, material_id: str) -> MaterialRecord | None: ...

    def fetch_materials(self, modified_since: datetime | None = None) -> Iterable[MaterialRecord]: ...

    def fetch_codes(self) -> Iterable[str]: ...
