from __future__ import annotations

import unittest

from migration.vector_import import VectorContextImporter


class VectorImportTests(unittest.TestCase):
    def test_normalize_embedding_reads_numeric_sequence(self) -> None:
        importer = VectorContextImporter()

        decoded = importer._normalize_embedding([0.1, 0.2, 0.3])

        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(len(decoded), 3)
        self.assertAlmostEqual(decoded[0], 0.1, places=5)
        self.assertAlmostEqual(decoded[2], 0.3, places=5)

    def test_chunk_props_include_embedding_and_content(self) -> None:
        importer = VectorContextImporter()
        row = {
            'embedding_id': 'abc123',
            'created_at': '2026-04-07T00:00:00Z',
            'embedding': [0.1, 0.2],
        }
        metadata = {
            'source_file': 'foo.pdf',
            'source_pipeline': 'virtualECU_text_ingestion',
            'page_number': 3,
        }

        props = importer._chunk_props(
            'autosar-fusion',
            {'name': 'autosar_fused_chunks', 'dimension': 384},
            {'embedding_id': row['embedding_id'], 'embedding': row['embedding'], 'metadata': metadata, 'document': 'Hello world'},
            '2026-04-07T00:00:00Z',
        )

        self.assertEqual(props['mapping_category'], 'vector')
        self.assertEqual(props['source_file'], 'foo.pdf')
        self.assertEqual(props['content'], 'Hello world')
        self.assertEqual(props['collection_dimension'], 384)
        self.assertEqual(len(props['embedding']), 2)


if __name__ == '__main__':
    unittest.main()
