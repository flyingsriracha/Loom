from __future__ import annotations

from typing import Any

from retrieval.embeddings import cosine_similarity


class MMRReranker:
    def rerank(
        self,
        candidates: list[dict[str, Any]],
        *,
        query_embedding: list[float] | None,
        top_k: int,
        lambda_mult: float = 0.7,
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []
        if not query_embedding:
            return sorted(candidates, key=lambda item: item.get('score', 0.0), reverse=True)[:top_k]

        embedded = [candidate for candidate in candidates if candidate.get('embedding')]
        non_embedded = [candidate for candidate in candidates if not candidate.get('embedding')]
        if not embedded:
            return sorted(candidates, key=lambda item: item.get('score', 0.0), reverse=True)[:top_k]

        selected: list[dict[str, Any]] = []
        pool = embedded[:]
        while pool and len(selected) < top_k:
            best_candidate = None
            best_score = None
            for candidate in pool:
                candidate_embedding = candidate.get('embedding') or []
                relevance = cosine_similarity(query_embedding, candidate_embedding)
                diversity_penalty = 0.0
                if selected:
                    diversity_penalty = max(
                        cosine_similarity(candidate_embedding, selected_candidate.get('embedding') or [])
                        for selected_candidate in selected
                    )
                mmr_score = lambda_mult * relevance - (1 - lambda_mult) * diversity_penalty
                tie_break = float(candidate.get('score', 0.0))
                if best_score is None or mmr_score > best_score or (mmr_score == best_score and best_candidate is not None and tie_break > float(best_candidate.get('score', 0.0))):
                    best_score = mmr_score
                    best_candidate = candidate
            assert best_candidate is not None
            selected.append(best_candidate)
            pool.remove(best_candidate)

        if len(selected) < top_k:
            remaining = sorted(non_embedded, key=lambda item: item.get('score', 0.0), reverse=True)
            selected.extend(remaining[: top_k - len(selected)])
        return selected[:top_k]
