from __future__ import annotations

import string
import unittest

from hypothesis import given, strategies as st

from graph.identities import stable_id
from ingestion.loader import IngestionLoader
from orchestrator.classifier import classify_request
from retrieval.reranker import MMRReranker


class PropertyTests(unittest.TestCase):
    @given(st.lists(st.text(min_size=0, max_size=20), min_size=1, max_size=5))
    def test_stable_id_is_deterministic_and_hex(self, parts: list[str]) -> None:
        first = stable_id(*parts)
        second = stable_id(*parts)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 24)
        self.assertTrue(all(ch in string.hexdigits.lower() + string.hexdigits.upper() for ch in first))

    @given(st.text(min_size=1, max_size=4000), st.integers(min_value=50, max_value=400), st.integers(min_value=0, max_value=49))
    def test_chunk_text_produces_nonempty_bounded_chunks(self, text: str, chunk_chars: int, overlap: int) -> None:
        loader = IngestionLoader()
        chunks = loader._chunk_text(text, chunk_chars=chunk_chars, chunk_overlap=overlap)
        self.assertGreaterEqual(len(chunks), 1)
        self.assertTrue(all(chunk for chunk in chunks))
        self.assertTrue(all(len(chunk) <= chunk_chars for chunk in chunks))

    @given(st.sampled_from(['XCP', 'AUTOSAR', 'FMI', 'FIBEX']))
    def test_domain_keywords_do_not_route_to_general(self, keyword: str) -> None:
        result = classify_request(f'Explain {keyword} behavior')
        self.assertNotEqual(result.route, 'general')

    @given(st.integers(min_value=1, max_value=10))
    def test_mmr_reranker_never_returns_duplicates(self, top_k: int) -> None:
        reranker = MMRReranker()
        candidates = [
            {'id': f'c{i}', 'score': 1.0 - i * 0.05, 'embedding': [1.0 if i == 0 else 0.5, float(i)]}
            for i in range(10)
        ]
        ranked = reranker.rerank(candidates, query_embedding=[1.0, 0.0], top_k=top_k)
        ids = [item['id'] for item in ranked]
        self.assertLessEqual(len(ids), top_k)
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == '__main__':
    unittest.main()
