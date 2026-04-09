from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from graph.client import FalkorDBClient

DEFAULT_TEXT_CHUNK_EMBEDDING_DIMENSIONS = 384
DEFAULT_COMMUNITY_SUMMARY_EMBEDDING_DIMENSIONS = 384

DOMAIN_NODE_TYPES = (
    'Standard',
    'Protocol',
    'Requirement',
    'Module',
    'Interface',
    'Concept',
    'Command',
    'ErrorCode',
    'Event',
    'Element',
    'Parameter',
    'Table',
    'TextChunk',
    'CommunitySummary',
    'PracticalNote',
)

AUDIT_NODE_TYPES = (
    'SourceSystem',
    'SourcePipeline',
    'SourceDocument',
    'FusionAssessment',
    'MigrationRun',
    'Artifact',
    'ArtifactRevision',
    'AuditEvent',
    'CorrectionItem',
)


@dataclass
class SchemaBootstrapResult:
    statements_applied: int = 0
    statements_skipped: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            'statements_applied': self.statements_applied,
            'statements_skipped': self.statements_skipped,
            'warnings': self.warnings,
        }


class GraphSchemaBootstrap:
    def __init__(self, client: FalkorDBClient | None = None) -> None:
        self.client = client or FalkorDBClient()

    def run(
        self,
        *,
        embedding_dimensions: int | None = None,
        text_chunk_embedding_dimensions: int | None = None,
        community_summary_embedding_dimensions: int | None = None,
    ) -> SchemaBootstrapResult:
        graph = self.client.select_graph()
        result = SchemaBootstrapResult()

        text_chunk_dims = text_chunk_embedding_dimensions or embedding_dimensions or DEFAULT_TEXT_CHUNK_EMBEDDING_DIMENSIONS
        community_dims = community_summary_embedding_dimensions or embedding_dimensions or DEFAULT_COMMUNITY_SUMMARY_EMBEDDING_DIMENSIONS

        for label in DOMAIN_NODE_TYPES + AUDIT_NODE_TYPES:
            self._apply(
                result,
                f'node range index on {label}.id',
                lambda label=label: graph.create_node_range_index(label, 'id'),
            )

        self._apply(
            result,
            'node range index on SourceDocument.source_file',
            lambda: graph.create_node_range_index('SourceDocument', 'source_file'),
        )
        self._apply(
            result,
            'node range index on MigrationRun.run_id',
            lambda: graph.create_node_range_index('MigrationRun', 'run_id'),
        )
        self._apply(
            result,
            'node range index on ArtifactRevision.revision_id',
            lambda: graph.create_node_range_index('ArtifactRevision', 'revision_id'),
        )

        for label in DOMAIN_NODE_TYPES + AUDIT_NODE_TYPES:
            self._apply(
                result,
                f'node unique constraint on {label}.id',
                lambda label=label: graph.create_node_unique_constraint(label, 'id'),
            )

        self._apply(
            result,
            f'node vector index on TextChunk.embedding ({text_chunk_dims})',
            lambda: graph.create_node_vector_index('TextChunk', 'embedding', dim=text_chunk_dims, similarity_function='cosine'),
        )
        self._apply(
            result,
            f'node vector index on CommunitySummary.embedding ({community_dims})',
            lambda: graph.create_node_vector_index('CommunitySummary', 'embedding', dim=community_dims, similarity_function='cosine'),
        )
        self._apply(
            result,
            f'node vector index on PracticalNote.embedding ({text_chunk_dims})',
            lambda: graph.create_node_vector_index('PracticalNote', 'embedding', dim=text_chunk_dims, similarity_function='cosine'),
        )
        self._apply(
            result,
            'node range index on CorrectionItem.status',
            lambda: graph.create_node_range_index('CorrectionItem', 'status'),
        )

        return result

    def _apply(
        self,
        result: SchemaBootstrapResult,
        operation_name: str,
        operation: Callable[[], object],
    ) -> None:
        try:
            operation()
            result.statements_applied += 1
        except Exception as exc:  # pragma: no cover - runtime compatibility handling
            if self._is_skip_error(str(exc)):
                result.statements_skipped += 1
                result.warnings.append(f'skipped: {operation_name} ({exc})')
                return
            result.warnings.append(f'failed: {operation_name} ({exc})')
            raise

    def _is_skip_error(self, message: str) -> bool:
        lowered = message.lower()
        return any(
            fragment in lowered
            for fragment in (
                'already indexed',
                'already exists',
                'constraint already exists',
                'already constrained',
            )
        )


def bootstrap_schema(
    client: FalkorDBClient | None = None,
    *,
    embedding_dimensions: int | None = None,
    text_chunk_embedding_dimensions: int | None = None,
    community_summary_embedding_dimensions: int | None = None,
) -> SchemaBootstrapResult:
    manager = GraphSchemaBootstrap(client=client)
    return manager.run(
        embedding_dimensions=embedding_dimensions,
        text_chunk_embedding_dimensions=text_chunk_embedding_dimensions,
        community_summary_embedding_dimensions=community_summary_embedding_dimensions,
    )
