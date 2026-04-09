from __future__ import annotations

import json
from typing import Any

from graph.client import FalkorDBClient
from retrieval.community import CommunityBuilder
from retrieval.embeddings import cosine_similarity, encode_text


class GlobalSearchService:
    def __init__(self, client: FalkorDBClient | None = None) -> None:
        self.client = client or FalkorDBClient()
        self.community_builder = CommunityBuilder(client=self.client)

    def search(self, query: str, *, top_k: int = 5, source_system: str | None = None) -> list[dict[str, Any]]:
        graph_rows = self.client.query('MATCH (c:Community) RETURN c.uuid, properties(c)').result_set
        if graph_rows:
            embedding = encode_text(query)
            scored = []
            for community_id, props in graph_rows:
                props = dict(props)
                source_systems = json.loads(props.get('source_systems_json', '[]')) if props.get('source_systems_json') else []
                if source_system is not None and source_system not in source_systems:
                    continue
                scored.append({
                    'id': str(community_id),
                    'score': cosine_similarity(embedding, list(props.get('name_embedding') or [])),
                    'summary': props.get('summary'),
                    'level': props.get('level'),
                    'member_count': props.get('member_count'),
                    'source_systems': source_systems,
                    'standard_names': json.loads(props.get('standard_names_json', '[]')) if props.get('standard_names_json') else [],
                })
            scored.sort(key=lambda item: item['score'], reverse=True)
            return scored[:top_k]

        cache = self.community_builder.load_cache() or {}
        communities = list(cache.get('communities') or [])
        embedding = encode_text(query)
        scored: list[dict[str, Any]] = []
        for community in communities:
            source_systems = list(community.get('source_systems') or [])
            if source_system is not None and source_system not in source_systems:
                continue
            scored.append({
                'id': community['id'],
                'score': cosine_similarity(embedding, list(community.get('embedding') or [])),
                'summary': community.get('summary'),
                'level': community.get('level'),
                'member_count': community.get('member_count'),
                'source_systems': source_systems,
                'standard_names': list(community.get('standard_names') or []),
            })
        scored.sort(key=lambda item: item['score'], reverse=True)
        return scored[:top_k]
