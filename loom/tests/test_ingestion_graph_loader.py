from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from ingestion.graph_loader import IncrementalGraphLoader
from ingestion.loader import IngestionChunk, IngestionTable, LoadedIngestionDocument


class _FakeResult:
    def __init__(self, rows):
        self.result_set = rows


class _FakeGraph:
    def __init__(self):
        self.calls = []

    def query(self, cypher: str, params: dict | None = None, timeout=None):
        self.calls.append((cypher, params))
        if 'RETURN count(n)' in cypher:
            return _FakeResult([[0]])
        return _FakeResult([])


class _FakeClient:
    def __init__(self):
        self.graph = _FakeGraph()

    def select_graph(self):
        return self.graph


class IncrementalGraphLoaderTests(unittest.TestCase):
    def test_ingest_returns_counts(self) -> None:
        doc = LoadedIngestionDocument(
            source_path=Path('/tmp/autosar.json'),
            source_kind='json',
            source_system='autosar-supplementary',
            source_pipeline='incremental_structured_loader',
            source_file='tmp/autosar.json',
            title='autosar',
            checksum='abc123',
            extracted_at='2026-04-07T00:00:00Z',
            chunks=[IngestionChunk(content='hello', chunk_index=0)],
            tables=[IngestionTable(caption='autosar', markdown_content='|a|\n|---|', json_content='{}', row_count=1, col_count=1, table_index=0)],
        )
        loader = IncrementalGraphLoader(client=_FakeClient())
        with patch('ingestion.graph_loader.encode_texts', return_value=[[0.1, 0.2], [0.3, 0.4]]):
            result = loader.ingest(doc)

        self.assertEqual(result['text_chunks_created'], 1)
        self.assertEqual(result['table_nodes_created'], 1)
        self.assertEqual(result['vector_dimensions'], 2)


if __name__ == '__main__':
    unittest.main()
