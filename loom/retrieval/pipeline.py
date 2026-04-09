from __future__ import annotations

from copy import deepcopy
import json
from threading import Event, Lock
from time import time
from typing import Any

from graph.client import FalkorDBClient
from retrieval.community import CommunityBuilder
from retrieval.embeddings import encode_text
from retrieval.global_search import GlobalSearchService
from retrieval.local_search import LocalSearchService
from retrieval.reranker import MMRReranker

_CACHE_TTL_SECONDS = 120.0
_QUERY_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_QUERY_INFLIGHT: dict[str, Event] = {}
_QUERY_LOCK = Lock()


class RetrievalPipeline:
    def __init__(self, client: FalkorDBClient | None = None) -> None:
        self.client = client or FalkorDBClient()
        self.community_builder = CommunityBuilder(client=self.client)
        self.global_search = GlobalSearchService(client=self.client)
        self.local_search = LocalSearchService(client=self.client)
        self.reranker = MMRReranker()

    def ensure_communities(self, *, refresh: bool = False) -> dict[str, Any]:
        if refresh:
            return self.community_builder.refresh()
        count = self.client.query('MATCH (c:CommunitySummary) RETURN count(c)').result_set[0][0]
        if int(count) == 0:
            return self.community_builder.refresh()
        return {'communities_created': 0, 'skipped': True}

    def _cache_key(self, mode: str, **kwargs: Any) -> str:
        return json.dumps({'mode': mode, **kwargs}, sort_keys=True, default=str)

    def _get_cached(self, key: str) -> dict[str, Any] | None:
        with _QUERY_LOCK:
            payload = _QUERY_CACHE.get(key)
            if payload is None:
                return None
            cached_at, value = payload
            if time() - cached_at > _CACHE_TTL_SECONDS:
                _QUERY_CACHE.pop(key, None)
                return None
            return deepcopy(value)

    def _store_cached(self, key: str, value: dict[str, Any]) -> None:
        with _QUERY_LOCK:
            _QUERY_CACHE[key] = (time(), deepcopy(value))
            waiter = _QUERY_INFLIGHT.pop(key, None)
            if waiter is not None:
                waiter.set()

    def _fail_inflight(self, key: str) -> None:
        with _QUERY_LOCK:
            waiter = _QUERY_INFLIGHT.pop(key, None)
            if waiter is not None:
                waiter.set()

    def _await_inflight(self, key: str) -> dict[str, Any] | None:
        with _QUERY_LOCK:
            waiter = _QUERY_INFLIGHT.get(key)
            if waiter is None:
                return None
        waiter.wait(timeout=180)
        return self._get_cached(key)

    def _begin_or_wait(self, key: str) -> tuple[bool, dict[str, Any] | None]:
        cached = self._get_cached(key)
        if cached is not None:
            return False, cached
        with _QUERY_LOCK:
            waiter = _QUERY_INFLIGHT.get(key)
            if waiter is None:
                _QUERY_INFLIGHT[key] = Event()
                return True, None
        waited = self._await_inflight(key)
        return False, waited

    def search(
        self,
        query: str,
        *,
        valid_at: str | None = None,
        source_system: str | None = None,
        source_pipeline: str | None = None,
        min_confidence: float | None = None,
        limit: int = 10,
        refresh_communities: bool = False,
    ) -> dict[str, Any]:
        cache_key = self._cache_key(
            'search',
            query=query,
            valid_at=valid_at,
            source_system=source_system,
            source_pipeline=source_pipeline,
            min_confidence=min_confidence,
            limit=limit,
            refresh_communities=refresh_communities,
        )
        should_compute, cached = self._begin_or_wait(cache_key)
        if not should_compute:
            if cached is not None:
                return cached
            should_compute = True

        try:
            community_status = self.ensure_communities(refresh=refresh_communities)
            communities = self.global_search.search(query, top_k=5, source_system=source_system)
            candidates = self.local_search.search(
                query,
                community_hints=communities,
                valid_at=valid_at,
                source_system=source_system,
                source_pipeline=source_pipeline,
                min_confidence=min_confidence,
                limit=max(limit * 4, limit),
            )
            reranked = self.reranker.rerank(
                candidates,
                query_embedding=encode_text(query),
                top_k=limit,
            )
            payload = {
                'ok': True,
                'query': query,
                'communities': communities,
                'community_status': community_status,
                'results': reranked,
                'no_results': len(reranked) == 0,
            }
            self._store_cached(cache_key, payload)
            return payload
        except Exception:
            self._fail_inflight(cache_key)
            raise

    def query(
        self,
        query: str,
        *,
        valid_at: str | None = None,
        source_system: str | None = None,
        source_pipeline: str | None = None,
        min_confidence: float | None = None,
        limit: int = 8,
        refresh_communities: bool = False,
    ) -> dict[str, Any]:
        cache_key = self._cache_key(
            'query',
            query=query,
            valid_at=valid_at,
            source_system=source_system,
            source_pipeline=source_pipeline,
            min_confidence=min_confidence,
            limit=limit,
            refresh_communities=refresh_communities,
        )
        should_compute, cached = self._begin_or_wait(cache_key)
        if not should_compute:
            if cached is not None:
                return cached
            should_compute = True

        try:
            payload = self.search(
                query,
                valid_at=valid_at,
                source_system=source_system,
                source_pipeline=source_pipeline,
                min_confidence=min_confidence,
                limit=limit,
                refresh_communities=refresh_communities,
            )
            warnings: list[str] = []
            assembled: list[dict[str, Any]] = []
            for item in payload['results']:
                provenance = list(item.get('provenance_preview') or [])
                item_warnings: list[str] = []
                if not provenance:
                    item_warnings.append('unverified: missing provenance')
                if provenance and any(record.get('confidence') is None for record in provenance):
                    item_warnings.append('warning: incomplete confidence metadata')
                assembled.append(
                    {
                        'id': item['id'],
                        'labels': item.get('labels', []),
                        'score': round(float(item.get('score', 0.0)), 4),
                        'snippet': item.get('snippet', ''),
                        'candidate_type': item.get('candidate_type'),
                        'properties': item.get('properties', {}),
                        'evidence_chain': provenance,
                        'warnings': item_warnings,
                    }
                )
                warnings.extend(item_warnings)
            response = {
                'ok': True,
                'query_mode': 'graphrag_baseline',
                'query': query,
                'valid_at': valid_at,
                'communities': payload.get('communities', []),
                'results': assembled,
                'warnings': list(dict.fromkeys(warnings)),
                'no_results': len(assembled) == 0,
            }
            self._store_cached(cache_key, response)
            return response
        except Exception:
            self._fail_inflight(cache_key)
            raise
