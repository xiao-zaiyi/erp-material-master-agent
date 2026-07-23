from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, computed_field, model_validator


class MaterialStatus(StrEnum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    DISABLED = "disabled"


class MaterialRecord(BaseModel):
    code: str
    name: str
    specification: str = ""
    short_name: str = ""
    english_name: str = ""
    description: str = ""
    status: MaterialStatus
    # 仅用于增量同步，不暴露到对外 API 响应。
    created_at: datetime | None = Field(default=None, exclude=True)
    modified_at: datetime | None = Field(default=None, exclude=True)

    @computed_field
    @property
    def state_label(self) -> str:
        return {
            MaterialStatus.INACTIVE: "未启用",
            MaterialStatus.ACTIVE: "已启用",
            MaterialStatus.DISABLED: "已停用",
        }[self.status]


class MaterialQuery(BaseModel):
    name: str = ""
    specification: str = ""

    @model_validator(mode="after")
    def require_query(self) -> "MaterialQuery":
        if not self.name.strip() and not self.specification.strip():
            raise ValueError("name 和 specification 至少填写一个")
        return self


class Candidate(BaseModel):
    material: MaterialRecord
    match_type: Literal["exact", "synonym", "keyword", "semantic"]
    confidence: Literal["high", "medium", "low"]
    score: float = Field(ge=0, le=1)
    reason: str


class Guidance(BaseModel):
    level: Literal["info", "warning"]
    code: str
    message: str


class SearchResponse(BaseModel):
    items: list[Candidate]
    index_version: str


class ValidateResponse(BaseModel):
    conclusion: Literal[
        "已有可用物料",
        "已有待启用物料",
        "疑似重复，人工确认",
        "未发现重复，可申请新建",
    ]
    confidence: Literal["high", "medium", "low"]
    candidates: list[Candidate]
    guidance: list[Guidance]
    index_version: str


class FeedbackRequest(BaseModel):
    query: MaterialQuery
    candidate_code: str
    decision: Literal["same", "different"]
    confirmed_by: str = Field(min_length=1)
    note: str = ""


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    thread_id: str | None = None
    history: list["ChatHistoryMessage"] = Field(default_factory=list)


class ChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class ChatResponse(BaseModel):
    answer: str
    thread_id: str | None = None


class IndexJobResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed"]


class IndexStatusResponse(BaseModel):
    job_id: str | None = None
    status: Literal["idle", "queued", "running", "succeeded", "failed"]
    indexed_count: int = 0
    error: str | None = None
