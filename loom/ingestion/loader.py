from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from pypdf import PdfReader
import yaml


@dataclass(frozen=True)
class IngestionChunk:
    content: str
    chunk_index: int
    page_number: int | None = None


@dataclass(frozen=True)
class IngestionTable:
    caption: str
    markdown_content: str
    json_content: str
    row_count: int
    col_count: int
    table_index: int
    page_number: int | None = None


@dataclass(frozen=True)
class LoadedIngestionDocument:
    source_path: Path
    source_kind: str
    source_system: str
    source_pipeline: str
    source_file: str
    title: str
    checksum: str
    extracted_at: str
    chunks: list[IngestionChunk] = field(default_factory=list)
    tables: list[IngestionTable] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class IngestionLoader:
    SUPPORTED_KINDS = {'pdf', 'text', 'markdown', 'json', 'yaml', 'csv'}

    def load(
        self,
        *,
        source_path: str,
        source_kind: str | None = None,
        source_system: str | None = None,
        source_pipeline: str | None = None,
        chunk_chars: int = 1200,
        chunk_overlap: int = 150,
    ) -> LoadedIngestionDocument:
        path = Path(source_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f'Ingestion source not found: {path}')
        kind = self._infer_kind(path, source_kind)
        if kind not in self.SUPPORTED_KINDS:
            raise ValueError(f'Unsupported source kind: {kind}')
        system = source_system or self._infer_source_system(path)
        pipeline = source_pipeline or self._default_pipeline(kind, system)
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        extracted_at = datetime.now(timezone.utc).isoformat()
        source_file = self._relative_or_absolute(path)
        title = path.stem
        warnings: list[str] = []

        if kind == 'pdf':
            chunks, metadata, pdf_warnings = self._load_pdf(path, chunk_chars=chunk_chars, chunk_overlap=chunk_overlap)
            warnings.extend(pdf_warnings)
            return LoadedIngestionDocument(
                source_path=path,
                source_kind=kind,
                source_system=system,
                source_pipeline=pipeline,
                source_file=source_file,
                title=title,
                checksum=checksum,
                extracted_at=extracted_at,
                chunks=chunks,
                metadata=metadata,
                warnings=warnings,
            )

        if kind in {'text', 'markdown'}:
            text = path.read_text(encoding='utf-8', errors='ignore')
            chunks = [IngestionChunk(content=chunk, chunk_index=idx) for idx, chunk in enumerate(self._chunk_text(text, chunk_chars, chunk_overlap))]
            metadata = {'char_count': len(text), 'line_count': len(text.splitlines())}
            return LoadedIngestionDocument(
                source_path=path,
                source_kind=kind,
                source_system=system,
                source_pipeline=pipeline,
                source_file=source_file,
                title=title,
                checksum=checksum,
                extracted_at=extracted_at,
                chunks=chunks,
                metadata=metadata,
                warnings=warnings,
            )

        tables, chunks, metadata = self._load_structured(path, kind, chunk_chars=chunk_chars, chunk_overlap=chunk_overlap)
        return LoadedIngestionDocument(
            source_path=path,
            source_kind=kind,
            source_system=system,
            source_pipeline=pipeline,
            source_file=source_file,
            title=title,
            checksum=checksum,
            extracted_at=extracted_at,
            chunks=chunks,
            tables=tables,
            metadata=metadata,
            warnings=warnings,
        )

    def _infer_kind(self, path: Path, requested: str | None) -> str:
        if requested:
            return requested.lower().strip()
        suffix = path.suffix.lower()
        return {
            '.pdf': 'pdf',
            '.md': 'markdown',
            '.txt': 'text',
            '.rst': 'text',
            '.json': 'json',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.csv': 'csv',
        }.get(suffix, 'text')

    def _infer_source_system(self, path: Path) -> str:
        lowered = str(path).lower()
        if 'autosar' in lowered:
            return 'autosar-supplementary'
        if 'asam' in lowered:
            return 'asam-supplementary'
        return 'user-supplementary'

    def _default_pipeline(self, kind: str, source_system: str) -> str:
        if kind == 'pdf':
            if source_system.startswith('autosar'):
                return 'supplementary_autosar_pdf_ingest'
            return 'incremental_pdf_loader'
        if kind in {'json', 'yaml', 'csv'}:
            return 'incremental_structured_loader'
        return 'incremental_text_loader'

    def _load_pdf(self, path: Path, *, chunk_chars: int, chunk_overlap: int) -> tuple[list[IngestionChunk], dict[str, Any], list[str]]:
        reader = PdfReader(str(path))
        chunks: list[IngestionChunk] = []
        warnings: list[str] = []
        blank_pages = 0
        for page_index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ''
            if not text.strip():
                blank_pages += 1
                continue
            for idx, chunk in enumerate(self._chunk_text(text, chunk_chars, chunk_overlap)):
                chunks.append(IngestionChunk(content=chunk, chunk_index=len(chunks), page_number=page_index))
        if blank_pages:
            warnings.append(f'blank_pages_skipped:{blank_pages}')
        metadata = {'page_count': len(reader.pages), 'blank_pages': blank_pages}
        return chunks, metadata, warnings

    def _load_structured(self, path: Path, kind: str, *, chunk_chars: int, chunk_overlap: int) -> tuple[list[IngestionTable], list[IngestionChunk], dict[str, Any]]:
        if kind == 'json':
            payload = json.loads(path.read_text(encoding='utf-8'))
        elif kind == 'yaml':
            payload = yaml.safe_load(path.read_text(encoding='utf-8'))
        elif kind == 'csv':
            with path.open('r', encoding='utf-8', errors='ignore', newline='') as handle:
                reader = csv.DictReader(handle)
                payload = list(reader)
        else:
            raise ValueError(f'Unsupported structured kind: {kind}')

        serialized = json.dumps(payload, indent=2, ensure_ascii=False)
        table = self._table_from_payload(payload, path.name, table_index=0)
        chunks = [IngestionChunk(content=chunk, chunk_index=idx) for idx, chunk in enumerate(self._chunk_text(serialized, chunk_chars, chunk_overlap))]
        metadata = {
            'structured_kind': kind,
            'root_type': type(payload).__name__,
            'table_count': 1,
        }
        return [table], chunks, metadata

    def _table_from_payload(self, payload: Any, caption: str, *, table_index: int) -> IngestionTable:
        rows: list[dict[str, Any]] = []
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    rows.append(item)
                else:
                    rows.append({'value': item})
        elif isinstance(payload, dict):
            rows = [{'key': key, 'value': value} for key, value in payload.items()]
        else:
            rows = [{'value': payload}]

        columns = list(rows[0].keys()) if rows else ['value']
        header = '| ' + ' | '.join(columns) + ' |'
        divider = '| ' + ' | '.join('---' for _ in columns) + ' |'
        body_rows = []
        for row in rows[:100]:
            body_rows.append('| ' + ' | '.join(str(row.get(col, '')) for col in columns) + ' |')
        markdown_content = '\n'.join([header, divider, *body_rows])
        json_content = json.dumps(payload, ensure_ascii=False)
        return IngestionTable(
            caption=caption,
            markdown_content=markdown_content,
            json_content=json_content,
            row_count=len(rows),
            col_count=len(columns),
            table_index=table_index,
        )

    def _chunk_text(self, text: str, chunk_chars: int, chunk_overlap: int) -> list[str]:
        normalized = text.strip()
        if not normalized:
            return []
        chunks: list[str] = []
        start = 0
        length = len(normalized)
        while start < length:
            end = min(length, start + chunk_chars)
            chunk = normalized[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= length:
                break
            start = max(end - chunk_overlap, start + 1)
        return chunks

    def _relative_or_absolute(self, path: Path) -> str:
        repo_root = next((candidate for candidate in path.parents if (candidate / '.kiro').exists()), None)
        if repo_root is not None:
            try:
                return str(path.relative_to(repo_root))
            except ValueError:
                pass
        return str(path)
