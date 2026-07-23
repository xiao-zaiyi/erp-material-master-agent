from __future__ import annotations

from materials.feedback import FeedbackRepository
from materials.matcher import MaterialMatcher
from materials.models import FeedbackRequest, MaterialQuery, MaterialRecord, SearchResponse, ValidateResponse
from materials.reranker import CandidateReranker
from materials.validation_graph import build_validation_graph
from materials.vector_matcher import VectorMaterialMatcher
from sources.base import MaterialSource


class MaterialService:
    def __init__(
        self,
        source: MaterialSource | None = None,
        reranker: CandidateReranker | None = None,
        vector_store=None,
        feedback_repository: FeedbackRepository | None = None,
    ):
        self.source = source
        if vector_store is not None:
            self.matcher = VectorMaterialMatcher(vector_store)
            self._index_version = self.matcher.index_version
        elif source is not None:
            self.matcher = MaterialMatcher(list(source.fetch_materials()))
            self._index_version = lambda: "source"
        else:
            raise ValueError("必须配置 PGVector 或物料数据源")
        self.feedback_repository = feedback_repository
        if self.feedback_repository is None and source is not None and hasattr(source, "record_feedback"):
            self.feedback_repository = source
        self.validation_graph = build_validation_graph(self._index_version, self.matcher, reranker)

    def search(self, query: MaterialQuery) -> SearchResponse:
        items = self.matcher.search(query)
        return SearchResponse(items=items, index_version=self._index_version())

    def get_by_id(self, material_id: str) -> MaterialRecord | None:
        if self.source is None:
            raise RuntimeError("未配置 ERP 物料数据源")
        return self.source.get_by_id(material_id)

    def validate(self, query: MaterialQuery) -> ValidateResponse:
        state = self.validation_graph.invoke({"query": query})
        return state["result"]

    def feedback(self, request: FeedbackRequest) -> None:
        if self.feedback_repository is None:
            raise RuntimeError("未配置 PostgreSQL 反馈仓储")
        self.feedback_repository.record_feedback(request.model_dump())
