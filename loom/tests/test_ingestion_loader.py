from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ingestion.loader import IngestionLoader


class _FakePage:
    def __init__(self, text: str):
        self._text = text

    def extract_text(self):
        return self._text


class _FakePdfReader:
    def __init__(self, path: str):
        self.pages = [_FakePage('AUTOSAR E2E Library page one'), _FakePage('AUTOSAR E2E Library page two')]


class IngestionLoaderTests(unittest.TestCase):
    def test_load_json_infers_supplementary_autosar(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'autosar_extra.json'
            path.write_text('{"name": "E2E Library", "type": "module"}')
            loader = IngestionLoader()

            doc = loader.load(source_path=str(path))

            self.assertEqual(doc.source_kind, 'json')
            self.assertEqual(doc.source_system, 'autosar-supplementary')
            self.assertEqual(len(doc.tables), 1)
            self.assertGreaterEqual(len(doc.chunks), 1)

    def test_load_text_chunks_content(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'notes.txt'
            path.write_text('hello world\n' * 200)
            loader = IngestionLoader()

            doc = loader.load(source_path=str(path), chunk_chars=100, chunk_overlap=10)

            self.assertEqual(doc.source_kind, 'text')
            self.assertGreater(len(doc.chunks), 1)

    def test_load_pdf_uses_pdf_reader(self) -> None:
        with TemporaryDirectory() as tmp, patch('ingestion.loader.PdfReader', _FakePdfReader):
            path = Path(tmp) / 'asam_doc.pdf'
            path.write_bytes(b'%PDF-1.4 fake')
            loader = IngestionLoader()

            doc = loader.load(source_path=str(path), source_kind='pdf')

            self.assertEqual(doc.source_kind, 'pdf')
            self.assertEqual(doc.source_system, 'asam-supplementary')
            self.assertEqual(len(doc.chunks), 2)
            self.assertEqual(doc.metadata['page_count'], 2)


if __name__ == '__main__':
    unittest.main()
