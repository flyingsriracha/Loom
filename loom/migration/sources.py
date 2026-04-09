from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CuratedSource:
    name: str
    sqlite_path: Path
    vector_sqlite_path: Path
    expected_structured_rows: int
    expected_vectors: int


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def curated_sources() -> tuple[CuratedSource, CuratedSource]:
    root = _repo_root()
    asam = CuratedSource(
        name='ASAMKnowledgeDB',
        sqlite_path=root / 'tools' / 'ASAMKnowledgeDB' / 'fused_knowledge.db',
        vector_sqlite_path=root / 'tools' / 'ASAMKnowledgeDB' / 'fused_vector_store' / 'chroma.sqlite3',
        expected_structured_rows=659,
        expected_vectors=74086,
    )
    autosar = CuratedSource(
        name='autosar-fusion',
        sqlite_path=root / 'tools' / 'autosar-fusion' / 'autosar_fused.db',
        vector_sqlite_path=root / 'tools' / 'autosar-fusion' / 'autosar_fused_vectors' / 'chroma.sqlite3',
        expected_structured_rows=1789,
        expected_vectors=310686,
    )
    return asam, autosar
