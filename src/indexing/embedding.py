from __future__ import annotations

import httpx
from langchain_core.embeddings import Embeddings


class E5Embeddings(Embeddings):
    def __init__(self, *, api_url: str, model: str, api_key: str = "local", timeout: float = 20.0):
        self.api_url = api_url
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = httpx.post(
            self.api_url,
            json={"input": texts, "model": self.model},
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json().get("data", [])
        return [item["embedding"] for item in sorted(data, key=lambda item: item.get("index", 0))]

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])
        if not vectors:
            raise RuntimeError("Embedding 服务没有返回向量")
        return vectors[0]
