from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agent.runtime import build_material_agent, stream_agent_events
from indexing.jobs import IndexJobManager
from materials.models import ChatRequest, ChatResponse, FeedbackRequest, IndexJobResponse, IndexStatusResponse, MaterialQuery, SearchResponse, ValidateResponse
from config import Settings
from agent.model_factory import create_local_chat_model
from materials.service import MaterialService


def create_app(service: MaterialService | None = None, agent=None, index_sync=None) -> FastAPI:
    app = FastAPI(title="ERP 物料主数据 Agent", version="0.1.0")
    static_dir = Path(__file__).with_name("static")
    app.mount("/assets", StaticFiles(directory=static_dir), name="assets")
    material_service = service or _build_configured_service()
    material_agent = agent or _build_configured_agent(material_service)
    sync_task = index_sync or _default_index_sync
    index_jobs = IndexJobManager()

    @app.get("/", include_in_schema=False)
    def conversation_page() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/materials/index/rebuild", response_model=IndexJobResponse, status_code=202)
    def rebuild_index(background_tasks: BackgroundTasks) -> IndexJobResponse:
        job_id, status = index_jobs.start(sync_task)
        if status == "queued":
            background_tasks.add_task(index_jobs.run, job_id, sync_task)
        return IndexJobResponse(job_id=job_id, status=status)

    @app.get("/api/v1/materials/index/status", response_model=IndexStatusResponse)
    def index_status() -> IndexStatusResponse:
        return index_jobs.status()

    @app.post("/api/v1/agent/chat", response_model=ChatResponse)
    def chat(request: ChatRequest) -> ChatResponse:
        if material_agent is None:
            raise HTTPException(status_code=503, detail="本地 LangChain Agent 尚未配置模型")
        messages = [item.model_dump() for item in request.history]
        messages.append({"role": "user", "content": request.message})
        result = material_agent.invoke({"messages": messages})
        from agent.runtime import extract_agent_text

        return ChatResponse(answer=extract_agent_text(result), thread_id=request.thread_id)

    @app.post("/api/v1/agent/chat/stream")
    def chat_stream(request: ChatRequest) -> StreamingResponse:
        if material_agent is None:
            raise HTTPException(status_code=503, detail="本地 LangChain Agent 尚未配置模型")
        thread_id = request.thread_id or uuid.uuid4().hex
        messages = [item.model_dump() for item in request.history]
        messages.append({"role": "user", "content": request.message})

        def generate():
            yield _sse("start", {"thread_id": thread_id})
            for event, data in stream_agent_events(material_agent, {"messages": messages}):
                if event == "done":
                    data["thread_id"] = thread_id
                yield _sse(event, data)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/v1/materials/search", response_model=SearchResponse)
    def search(query: MaterialQuery) -> SearchResponse:
        return material_service.search(query)

    @app.post("/api/v1/materials/validate", response_model=ValidateResponse)
    def validate(query: MaterialQuery) -> ValidateResponse:
        return material_service.validate(query)

    @app.post("/api/v1/materials/feedback", status_code=204, response_model=None)
    def feedback(request: FeedbackRequest) -> Response:
        material_service.feedback(request)
        return Response(status_code=204)

    return app


def _default_index_sync() -> int:
    from indexing.sync import sync_from_settings

    return sync_from_settings()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _build_configured_service() -> MaterialService:
    from indexing.embedding import E5Embeddings
    from indexing.vector_store import create_vector_store
    from materials.feedback import PostgresFeedbackRepository
    from sources.factory import create_material_source

    settings = Settings()
    required = {
        "MATERIAL_SOURCE_URL": settings.source_url,
        "MATERIAL_POSTGRES_URL": settings.postgres_url,
        "MATERIAL_EMBEDDING_API_URL": settings.embedding_api_url,
        "MATERIAL_EMBEDDING_MODEL": settings.embedding_model,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"缺少生产配置：{', '.join(missing)}")
    embeddings = E5Embeddings(
        api_url=settings.embedding_api_url,
        model=settings.embedding_model,
        api_key=settings.embedding_api_key,
    )
    source = create_material_source(settings)
    vector_store = create_vector_store(settings, embeddings)
    feedback_repository = PostgresFeedbackRepository(settings.postgres_url)
    return MaterialService(source=source, vector_store=vector_store, feedback_repository=feedback_repository)


def _build_configured_agent(service: MaterialService):
    settings = Settings()
    if not settings.chat_model or not settings.chat_base_url:
        return None
    model = create_local_chat_model(
        model=settings.chat_model,
        base_url=settings.chat_base_url,
        api_key=settings.chat_api_key,
    )
    return build_material_agent(model, service)
