from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MigrationReport:
    source_system: str
    source_structured_rows: int
    source_vectors: int
    run_id: str | None = None
    run_started_at: str | None = None
    run_finished_at: str | None = None
    run_status: str = 'pending'
    mappings_applied: int = 0
    source_rows_processed: int = 0
    nodes_created: int = 0
    edges_created: int = 0
    vectors_indexed: int = 0
    audit_events_recorded: int = 0
    upstream_pipeline_counts: dict[str, int] = field(default_factory=dict)
    records_skipped: list[dict] = field(default_factory=list)
    provenance_coverage: float = 0.0
    reconciliation: list[dict[str, int | str]] = field(default_factory=list)
    row_count_match: bool = False
    raw_corpus_note: str = 'curated seed only; supplementary raw predecessor corpora remain future incremental ingestion scope'
    coverage_scope: str = 'curated seed only'
