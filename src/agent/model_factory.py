from __future__ import annotations

from langchain.chat_models import init_chat_model


def create_local_chat_model(*, model: str, base_url: str, api_key: str = "local"):
    """创建 OpenAI-compatible 的本地 LangChain 模型。"""
    return init_chat_model(
        model=model,
        model_provider="openai",
        base_url=base_url,
        api_key=api_key,
    )
