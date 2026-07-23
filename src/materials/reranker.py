from __future__ import annotations

from typing import Literal, Protocol

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from materials.models import Candidate, MaterialQuery


class RerankDecision(BaseModel):
    same_material: bool
    confidence: Literal["high", "medium", "low"]
    reason: str


class CandidateReranker(Protocol):
    def rerank(self, query: MaterialQuery, candidates: list[Candidate]) -> list[Candidate]: ...


class LangChainCandidateReranker:
    """使用 LangChain 结构化输出做候选精排；不负责全库检索。"""

    def __init__(self, model: BaseChatModel):
        self._model = model.with_structured_output(RerankDecision)

    def rerank(self, query: MaterialQuery, candidates: list[Candidate]) -> list[Candidate]:
        if not candidates:
            return []
        prompt = (
            "你是 ERP 物料主数据审核助手。只能根据给定名称和规格判断候选是否同一物料。"
            "规格缺失时不得擅自断言确定重复。\n"
            f"待建物料：名称={query.name!r}，规格={query.specification!r}\n"
            "候选：\n"
            + "\n".join(
                f"- code={item.material.code}, name={item.material.name}, spec={item.material.specification}"
                for item in candidates
            )
        )
        decision = self._model.invoke(prompt)
        if not isinstance(decision, RerankDecision):
            return candidates
        if decision.same_material:
            candidates[0] = candidates[0].model_copy(update={"confidence": decision.confidence, "reason": decision.reason})
        return candidates
