from __future__ import annotations

from collections.abc import Callable
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from materials.matcher import MaterialMatcher
from materials.models import Candidate, Guidance, MaterialQuery, MaterialStatus, ValidateResponse
from materials.reranker import CandidateReranker


class ValidationState(TypedDict, total=False):
    query: MaterialQuery
    candidates: list[Candidate]
    guidance: list[Guidance]
    result: ValidateResponse


def build_validation_graph(
    index_version: Callable[[], str],
    matcher: MaterialMatcher,
    reranker: CandidateReranker | None = None,
):
    def retrieve(state: ValidationState) -> dict:
        return {"candidates": matcher.search(state["query"])}

    def advise(state: ValidationState) -> dict:
        query = state["query"]
        candidates = state.get("candidates", [])
        guidance: list[Guidance] = []
        if not query.name.strip():
            guidance.append(Guidance(level="warning", code="NAME_REQUIRED", message="建议补充规范物料名称"))
        if not query.specification.strip():
            guidance.append(Guidance(level="warning", code="SPEC_REQUIRED", message="建议补充规格型号，避免仅凭名称误判"))
        if candidates:
            guidance.append(Guidance(level="info", code="REVIEW_CANDIDATES", message="请核对候选物料的规格、状态和使用范围"))
        if not guidance:
            guidance.append(Guidance(level="info", code="BASIC_VALIDATION", message="未发现明显格式问题"))
        return {"guidance": guidance}

    def decide(state: ValidationState) -> dict:
        candidates = state.get("candidates", [])
        if reranker and candidates:
            candidates = reranker.rerank(state["query"], candidates)
        top = candidates[0] if candidates else None
        if top and top.confidence == "high":
            status = top.material.status
            conclusion = {
                MaterialStatus.INACTIVE: "已有待启用物料",
                MaterialStatus.ACTIVE: "已有可用物料",
                MaterialStatus.DISABLED: "疑似重复，人工确认",
            }[status]
        elif candidates:
            conclusion = "疑似重复，人工确认"
        else:
            conclusion = "未发现重复，可申请新建"
        confidence = top.confidence if top else "low"
        return {"result": ValidateResponse(conclusion=conclusion, confidence=confidence, candidates=candidates, guidance=state.get("guidance", []), index_version=index_version())}

    graph = StateGraph(ValidationState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("advise", advise)
    graph.add_node("decide", decide)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "advise")
    graph.add_edge("advise", "decide")
    graph.add_edge("decide", END)
    return graph.compile()
