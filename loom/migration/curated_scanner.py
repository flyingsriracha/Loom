from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
import sqlite3

from migration.report import MigrationReport
from migration.sources import CuratedSource


@dataclass
class TableProfile:
    table: str
    row_count: int
    has_source_pipeline: bool
    has_confidence: bool
    has_source_file: bool


@dataclass
class CuratedScanResult:
    source_system: str
    database_path: str
    table_profiles: list[TableProfile]
    total_rows: int
    pipeline_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            'source_system': self.source_system,
            'database_path': self.database_path,
            'tables': [
                {
                    'table': t.table,
                    'row_count': t.row_count,
                    'has_source_pipeline': t.has_source_pipeline,
                    'has_confidence': t.has_confidence,
                    'has_source_file': t.has_source_file,
                }
                for t in self.table_profiles
            ],
            'total_rows': self.total_rows,
            'pipeline_counts': self.pipeline_counts,
        }


class CuratedSourceScanner:
    def scan(self, source: CuratedSource) -> CuratedScanResult:
        db_path = Path(source.sqlite_path)
        if not db_path.exists():
            raise FileNotFoundError(f'Curated source DB not found: {db_path}')

        uri = f'file:{db_path}?mode=ro'
        table_profiles: list[TableProfile] = []
        pipelines: Counter[str] = Counter()

        with sqlite3.connect(uri, uri=True) as conn:
            conn.row_factory = sqlite3.Row
            tables = self._list_user_tables(conn)
            for table_name in tables:
                columns = self._column_names(conn, table_name)
                row_count = self._count_table(conn, table_name)
                profile = TableProfile(
                    table=table_name,
                    row_count=row_count,
                    has_source_pipeline='source_pipeline' in columns,
                    has_confidence='confidence' in columns,
                    has_source_file='source_file' in columns,
                )
                table_profiles.append(profile)
                if profile.has_source_pipeline and row_count > 0:
                    pipelines.update(self._pipeline_counts(conn, table_name))

        total_rows = sum(t.row_count for t in table_profiles)
        return CuratedScanResult(
            source_system=source.name,
            database_path=str(db_path),
            table_profiles=table_profiles,
            total_rows=total_rows,
            pipeline_counts=dict(pipelines),
        )

    def seed_report(self, source: CuratedSource, scan: CuratedScanResult) -> MigrationReport:
        return MigrationReport(
            source_system=source.name,
            source_structured_rows=source.expected_structured_rows,
            source_vectors=source.expected_vectors,
            upstream_pipeline_counts=scan.pipeline_counts,
        )

    def _list_user_tables(self, conn: sqlite3.Connection) -> list[str]:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
        return [str(row[0]) for row in rows]

    def _column_names(self, conn: sqlite3.Connection, table_name: str) -> set[str]:
        rows = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
        return {str(row[1]) for row in rows}

    def _count_table(self, conn: sqlite3.Connection, table_name: str) -> int:
        row = conn.execute(f'SELECT COUNT(1) FROM "{table_name}"').fetchone()
        return int(row[0] if row else 0)

    def _pipeline_counts(self, conn: sqlite3.Connection, table_name: str) -> Counter[str]:
        counts: Counter[str] = Counter()
        query = (
            f'SELECT source_pipeline, COUNT(1) FROM "{table_name}" '
            'WHERE source_pipeline IS NOT NULL GROUP BY source_pipeline'
        )
        rows = conn.execute(query).fetchall()
        for pipeline, cnt in rows:
            if pipeline:
                counts[str(pipeline)] += int(cnt)
        return counts
