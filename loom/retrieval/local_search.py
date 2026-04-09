from __future__ import annotations

from typing import Any

from graph.client import FalkorDBClient
from graph.provenance import ProvenanceResolver
from graph.temporal import TemporalStateManager
from retrieval.embeddings import cosine_similarity, encode_text


class LocalSearchService:
    def __init__(self, client: FalkorDBClient | None = None) -> None:
        self.client = client or FalkorDBClient()
        self.provenance = ProvenanceResolver(client=self.client)
        self.temporal = TemporalStateManager(client=self.client)

    def search(
        self,
        query: str,
        *,
        community_hints: list[dict[str, Any]] | None = None,
        valid_at: str | None = None,
        source_system: str | None = None,
        source_pipeline: str | None = None,
        min_confidence: float | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        embedding = encode_text(query)
        allowed_sources = {source_system} if source_system else set()
        for hint in community_hints or []:
            allowed_sources.update(hint.get('source_systems') or [])
        allowed_sources = {item for item in allowed_sources if item}

        candidates: dict[str, dict[str, Any]] = {}

        graph_hits = self.provenance.search_nodes(
            query,
            source_system=source_system,
            source_pipeline=source_pipeline,
            min_confidence=min_confidence,
            limit=max(limit * 4, limit),
            include_text_chunks=False,
        )
        for hit in graph_hits:
            snippet = self._snippet_from_properties(hit['properties'])
            candidate = {
                'id': hit['id'],
                'labels': hit['labels'],
                'properties': hit['properties'],
                'score': self._lexical_score(query, hit['properties']),
                'snippet': snippet,
                'provenance_preview': hit['provenance_preview'],
                'candidate_type': 'graph',
                'embedding': None,
            }
            candidates[hit['id']] = self._best_candidate(candidates.get(hit['id']), candidate)

        if valid_at:
            temporal_hits = self.temporal.query_as_of(
                valid_at=valid_at,
                source_system=source_system,
                query_text=query,
                limit=max(limit * 4, limit),
            )
            for hit in temporal_hits:
                entity_props = dict(hit['entity_properties'])
                state_props = dict(hit['state_properties'])
                provenance_preview = self.provenance.resolve(
                    hit['entity_id'],
                    source_system=source_system,
                    source_pipeline=source_pipeline,
                    min_confidence=min_confidence,
                )
                if any(filter_value is not None for filter_value in (source_system, source_pipeline, min_confidence)) and not provenance_preview:
                    continue
                snippet = self._snippet_from_properties({**entity_props, **state_props})
                candidate = {
                    'id': hit['entity_id'],
                    'labels': hit['entity_labels'],
                    'properties': {**entity_props, 'temporal_state': state_props},
                    'score': self._lexical_score(query, {**entity_props, **state_props}) + 0.05,
                    'snippet': snippet,
                    'provenance_preview': provenance_preview[:3],
                    'candidate_type': 'temporal',
                    'embedding': None,
                }
                candidates[hit['entity_id']] = self._best_candidate(candidates.get(hit['entity_id']), candidate)

        if len(candidates) < min(limit, 3):
            chunk_hits = self._text_chunk_hits(
                query,
                embedding,
                allowed_sources=allowed_sources,
                source_pipeline=source_pipeline,
                limit=max(limit * 10, limit),
            )
            for hit in chunk_hits:
                provenance_preview = self.provenance.resolve(
                    hit['id'],
                    source_system=source_system,
                    source_pipeline=source_pipeline,
                    min_confidence=min_confidence,
                )
                if any(filter_value is not None for filter_value in (source_system, source_pipeline, min_confidence)) and not provenance_preview:
                    continue
                candidate = {
                    'id': hit['id'],
                    'labels': ['TextChunk'],
                    'properties': hit['properties'],
                    'score': hit['score'],
                    'snippet': hit['properties'].get('document_preview') or hit['properties'].get('content') or '',
                    'provenance_preview': provenance_preview[:3],
                    'candidate_type': 'vector',
                    'embedding': hit['properties'].get('embedding'),
                }
                candidates[hit['id']] = self._best_candidate(candidates.get(hit['id']), candidate)

        ranked = sorted(candidates.values(), key=lambda item: item['score'], reverse=True)
        return ranked[:limit]

    def _text_chunk_hits(
        self,
        query: str,
        query_embedding: list[float],
        *,
        allowed_sources: set[str],
        source_pipeline: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        rows = self.client.query(
            'MATCH (n:TextChunk {mapping_category:"vector"}) '
            'WHERE ($allowed_sources_empty OR n.source_system IN $allowed_sources) '
            'AND ($source_pipeline IS NULL OR n.source_pipeline = $source_pipeline) '
            'AND coalesce(n.superseded_at, "") = "" '
            'AND ('
            '  toLower(coalesce(n.document_preview, "")) CONTAINS $query_lower OR '
            '  toLower(coalesce(n.content, "")) CONTAINS $query_lower OR '
            '  toLower(coalesce(n.source_file, "")) CONTAINS $query_lower'
            ') '
            'RETURN n.id, properties(n) LIMIT $limit',
            params={
                'allowed_sources_empty': not bool(allowed_sources),
                'allowed_sources': list(allowed_sources),
                'source_pipeline': source_pipeline,
                'query_lower': query.lower(),
                'limit': limit,
            },
        ).result_set
        hits: list[dict[str, Any]] = []
        for node_id, props in rows:
            props = dict(props)
            emb = list(props.get('embedding') or [])
            hits.append(
                {
                    'id': str(node_id),
                    'score': cosine_similarity(query_embedding, emb) + 0.1 * self._lexical_score(query, props),
                    'properties': props,
                }
            )
        hits.sort(key=lambda item: item['score'], reverse=True)
        return hits[:limit]

    def _lexical_score(self, query: str, props: dict[str, Any]) -> float:
        query_lower = query.lower()
        haystack = ' '.join(
            str(value)
            for value in [
                props.get('name'),
                props.get('title'),
                props.get('description'),
                props.get('summary'),
                props.get('source_file'),
                props.get('document_preview'),
            ]
            if value not in (None, '')
        ).lower()
        if not haystack:
            return 0.0
        score = 0.0
        for token in query_lower.split():
            if token in haystack:
                score += 1.0
        return score / max(len(query_lower.split()), 1)

    def _snippet_from_properties(self, props: dict[str, Any]) -> str:
        for key in ('description', 'summary', 'content', 'title', 'name'):
            value = props.get(key)
            if value not in (None, ''):
                return str(value)
        return ''

    def _best_candidate(self, existing: dict[str, Any] | None, candidate: dict[str, Any]) -> dict[str, Any]:
        if existing is None or candidate['score'] > existing['score']:
            return candidate
        return existing
