from __future__ import annotations

import unittest

from retrieval.reranker import MMRReranker


class RetrievalTests(unittest.TestCase):
    def test_mmr_reranker_prefers_diverse_results(self) -> None:
        reranker = MMRReranker()
        candidates = [
            {'id': 'a', 'score': 0.9, 'embedding': [1.0, 0.0]},
            {'id': 'b', 'score': 0.85, 'embedding': [0.98, 0.02]},
            {'id': 'c', 'score': 0.8, 'embedding': [0.0, 1.0]},
        ]

        ranked = reranker.rerank(candidates, query_embedding=[1.0, 0.0], top_k=2, lambda_mult=0.3)

        self.assertEqual(ranked[0]['id'], 'a')
        self.assertEqual(ranked[1]['id'], 'c')


if __name__ == '__main__':
    unittest.main()
