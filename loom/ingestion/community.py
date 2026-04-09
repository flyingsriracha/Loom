from __future__ import annotations

from typing import Any

from graph.client import FalkorDBClient
from retrieval.pipeline import RetrievalPipeline


class IngestionCommunityRefresher:
    def __init__(self, client: FalkorDBClient | None = None) -> None:
        self.client = client or FalkorDBClient()

    def refresh(self) -> dict[str, Any]:
        pipeline = RetrievalPipeline(client=self.client)
        return pipeline.ensure_communities(refresh=True)
