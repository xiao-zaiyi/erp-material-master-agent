from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Protocol

from langchain_core.documents import Document

from indexing.embedding import E5Embeddings
from indexing.vector_store import create_vector_store
from materials.models import MaterialRecord, MaterialStatus
from sources.base import MaterialSource


logger = logging.getLogger("material_agent.sync")


class VectorStorePort(Protocol):
    def add_documents(self, documents: list[Document], **kwargs) -> list[str]: ...

    def delete(self, ids: list[str] | None = None) -> bool | None: ...


def material_text(material: MaterialRecord) -> str:
    """只使用名称、规格和别名等业务文本，不把 code 当作语义特征。"""
    parts = [material.name, material.specification, material.short_name, material.english_name]
    return " ".join(part.strip() for part in parts if part and part.strip())


def material_document(material: MaterialRecord, index_version: str) -> Document:
    return Document(
        page_content=material_text(material),
        metadata={
            "code": material.code,
            "name": material.name,
            "specification": material.specification,
            "short_name": material.short_name,
            "english_name": material.english_name,
            "description": material.description,
            "status": material.status.value,
            "state_label": material.state_label,
            "index_version": index_version,
        },
    )


def sync_material_index(
    source: MaterialSource,
    vector_store: VectorStorePort,
    batch_size: int = 2048,
    state=None,
) -> int:
    if state is None:
        return _sync_full(source, vector_store, batch_size)

    checkpoint = state.checkpoint()
    previous_times = state.modified_times()
    if checkpoint is None:
        materials = list(source.fetch_materials())
        logger.info("首次同步：读取全部物料 %d 条", len(materials))
    else:
        materials = list(source.fetch_materials(checkpoint))
        logger.info("增量同步：检查点=%s，读取变化候选 %d 条", checkpoint, len(materials))

    changed = [
        material
        for material in materials
        if material.code not in previous_times
        or material.modified_at != previous_times[material.code]
    ]
    skipped = len(materials) - len(changed)
    logger.info("增量判断完成：新增/变更 %d 条，未变化跳过 %d 条", len(changed), skipped)

    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    total = _write_batches(changed, vector_store, batch_size, version, state)

    indexed_codes = state.indexed_codes()
    current_codes = set(source.fetch_codes())
    deleted = indexed_codes - current_codes
    if deleted:
        vector_store.delete(ids=sorted(deleted))
        state.remove(deleted)
        logger.info("清理 ERP 已删除物料：%d 条", len(deleted))

    max_modified = max((m.modified_at for m in materials if m.modified_at is not None), default=checkpoint)
    state.save([], max_modified)
    logger.info("增量索引完成：更新 %d 条，跳过 %d 条，删除 %d 条", total, skipped, len(deleted))
    return total


def _sync_full(source: MaterialSource, vector_store: VectorStorePort, batch_size: int) -> int:
    materials = list(source.fetch_materials())
    logger.info("读取物料完成：共 %d 条", len(materials))
    _log_state_distribution(materials)
    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return _write_batches(materials, vector_store, batch_size, version)


def _write_batches(
    materials: list[MaterialRecord],
    vector_store: VectorStorePort,
    batch_size: int,
    version: str,
    state=None,
) -> int:
    total_materials = len(materials)
    total = 0
    for start in range(0, total_materials, batch_size):
        batch = materials[start : start + batch_size]
        batch_no = start // batch_size + 1
        total_batches = (total_materials + batch_size - 1) // batch_size
        logger.info("处理第 %d/%d 批：%d-%d/%d", batch_no, total_batches, start + 1, start + len(batch), total_materials)
        documents = [material_document(material, version) for material in batch]
        vector_store.add_documents(documents, ids=[material.code for material in batch])
        if state is not None:
            state.save([(material.code, material.modified_at) for material in batch], None)
        logger.info("LangChain Embedding + PGVector 写入完成：第 %d 批，文档数=%d", batch_no, len(documents))
        total += len(documents)
        logger.info("写入 PostgreSQL 完成：第 %d 批，累计=%d/%d（%.1f%%）", batch_no, total, total_materials, total / total_materials * 100 if total_materials else 100)
    logger.info("索引写入完成：共写入 %d 条，索引版本=%s", total, version)
    return total


def _log_state_distribution(materials: list[MaterialRecord]) -> None:
    counts = Counter(material.status for material in materials)
    logger.info(
        "物料状态分布：未启用=%d，已启用=%d，已停用=%d，其他=%d",
        counts.get(MaterialStatus.INACTIVE, 0),
        counts.get(MaterialStatus.ACTIVE, 0),
        counts.get(MaterialStatus.DISABLED, 0),
        sum(count for status, count in counts.items() if status not in set(MaterialStatus)),
    )


def sync_from_settings() -> int:
    from config import Settings
    from indexing.state import PostgresIndexState
    from sources.factory import create_material_source

    settings = Settings()
    required = {
        "MATERIAL_SOURCE_URL": settings.source_url,
        "MATERIAL_POSTGRES_URL": settings.postgres_url,
        "MATERIAL_EMBEDDING_API_URL": settings.embedding_api_url,
        "MATERIAL_EMBEDDING_MODEL": settings.embedding_model,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"缺少同步配置：{', '.join(missing)}")

    source = create_material_source(settings)
    embeddings = E5Embeddings(
        api_url=settings.embedding_api_url,
        model=settings.embedding_model,
        api_key=settings.embedding_api_key,
    )
    vector_store = create_vector_store(settings, embeddings)
    state = PostgresIndexState(settings.postgres_url)
    return sync_material_index(source, vector_store, state=state)
