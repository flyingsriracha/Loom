from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from graph.client import FalkorDBClient


@dataclass(frozen=True)
class ProvenanceRecord:
    source_system: str
    source_pipeline: str | None
    source_file: str | None
    extraction_date: str | None
    confidence: float | None
    page_number: int | None = None
    migration_runs: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            'source_system': self.source_system,
            'source_pipeline': self.source_pipeline,
            'source_file': self.source_file,
            'extraction_date': self.extraction_date,
            'confidence': self.confidence,
            'page_number': self.page_number,
            'migration_runs': list(self.migration_runs),
        }


class ProvenanceResolver:
    def __init__(self, client: FalkorDBClient | None = None) -> None:
        self.client = client or FalkorDBClient()

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        result = self.client.query(
            'MATCH (n {id: $id}) RETURN n.id, labels(n), properties(n) LIMIT 1',
            params={'id': node_id},
            read_only=True,
        )
        if not result.result_set:
            return None
        found_id, labels, props = result.result_set[0]
        return {
            'id': found_id,
            'labels': list(labels),
            'properties': dict(props),
        }

    def resolve(
        self,
        node_id: str,
        *,
        source_system: str | None = None,
        source_pipeline: str | None = None,
        min_confidence: float | None = None,
    ) -> list[dict[str, Any]]:
        result = self.client.query(
            'MATCH (n {id: $id}) '
            'OPTIONAL MATCH (n)-[prov:PROVENANCE]->(d:SourceDocument) '
            'OPTIONAL MATCH (d)-[:EXTRACTED_BY]->(p:SourcePipeline) '
            'OPTIONAL MATCH (d)-[:ORIGINATES_FROM]->(s:SourceSystem) '
            'OPTIONAL MATCH (n)-[:INGESTED_IN]->(nr:MigrationRun) '
            'WITH prov, d, p, s, collect(DISTINCT nr.run_id) AS node_runs '
            'OPTIONAL MATCH (d)-[:MIGRATED_IN]->(dr:MigrationRun) '
            'RETURN properties(prov), properties(d), properties(p), properties(s), node_runs, collect(DISTINCT dr.run_id)',
            params={'id': node_id},
        )

        records: list[ProvenanceRecord] = []
        seen: set[tuple[Any, ...]] = set()
        for prov_props, doc_props, pipeline_props, system_props, node_runs, doc_runs in result.result_set:
            doc_props = dict(doc_props or {})
            pipeline_props = dict(pipeline_props or {})
            system_props = dict(system_props or {})
            prov_props = dict(prov_props or {})
            record = ProvenanceRecord(
                source_system=str(system_props.get('name') or doc_props.get('source_system') or ''),
                source_pipeline=str(prov_props.get('source_pipeline')) if prov_props.get('source_pipeline') is not None else (str(pipeline_props.get('name')) if pipeline_props.get('name') is not None else None),
                source_file=str(doc_props.get('source_file')) if doc_props.get('source_file') is not None else None,
                extraction_date=str(prov_props.get('extraction_date')) if prov_props.get('extraction_date') is not None else None,
                confidence=float(prov_props.get('confidence')) if prov_props.get('confidence') is not None else None,
                page_number=int(prov_props.get('page_number')) if prov_props.get('page_number') is not None else None,
                migration_runs=tuple(dict.fromkeys(run_id for run_id in [*(node_runs or []), *(doc_runs or [])] if run_id not in (None, ''))),
            )
            if not record.source_system and not record.source_file:
                continue
            if source_system is not None and record.source_system != source_system:
                continue
            if source_pipeline is not None and record.source_pipeline != source_pipeline:
                continue
            if min_confidence is not None and (record.confidence is None or record.confidence < min_confidence):
                continue
            key = (
                record.source_system,
                record.source_pipeline,
                record.source_file,
                record.extraction_date,
                record.confidence,
                record.page_number,
                record.migration_runs,
            )
            if key in seen:
                continue
            seen.add(key)
            records.append(record)

        records.sort(
            key=lambda item: (
                item.confidence is not None,
                item.confidence if item.confidence is not None else -1.0,
                item.source_file or '',
            ),
            reverse=True,
        )
        return [record.to_dict() for record in records]

    def search_nodes(
        self,
        query: str,
        *,
        label: str | None = None,
        source_system: str | None = None,
        source_pipeline: str | None = None,
        min_confidence: float | None = None,
        limit: int = 10,
        include_text_chunks: bool = False,
    ) -> list[dict[str, Any]]:
        predicates = [
            '(exists(n.name) AND toLower(n.name) CONTAINS $query_lower)',
            '(exists(n.title) AND toLower(n.title) CONTAINS $query_lower)',
            '(exists(n.description) AND toLower(n.description) CONTAINS $query_lower)',
            '(exists(n.summary) AND toLower(n.summary) CONTAINS $query_lower)',
            '(exists(n.content) AND toLower(n.content) CONTAINS $query_lower)',
            '(exists(n.note_type) AND toLower(n.note_type) CONTAINS $query_lower)',
            '(exists(n.source_file) AND toLower(n.source_file) CONTAINS $query_lower)',
        ]
        if include_text_chunks:
            predicates.extend(
                [
                    '(exists(n.document_preview) AND toLower(n.document_preview) CONTAINS $query_lower)',
                    '(exists(n.content) AND toLower(n.content) CONTAINS $query_lower)',
                ]
            )

        cypher = (
            'MATCH (n) '
            'WHERE (' + ' OR '.join(predicates) + ') '
            'AND NOT ("MigrationRun" IN labels(n) OR "AuditEvent" IN labels(n)) '
            'AND coalesce(n.superseded_at, "") = "" '
        )
        params: dict[str, Any] = {
            'query_lower': query.lower(),
            'candidate_limit': max(limit * 5, limit),
        }
        if label is not None:
            cypher += 'AND $label IN labels(n) '
            params['label'] = label
        cypher += 'RETURN n.id, labels(n), properties(n) LIMIT $candidate_limit'

        result = self.client.query(cypher, params=params, read_only=True)
        matches: list[dict[str, Any]] = []
        for node_id, labels, props in result.result_set:
            provenance = self.resolve(
                str(node_id),
                source_system=source_system,
                source_pipeline=source_pipeline,
                min_confidence=min_confidence,
            )
            if any(filter_value is not None for filter_value in (source_system, source_pipeline, min_confidence)) and not provenance:
                continue
            matches.append(
                {
                    'id': str(node_id),
                    'labels': list(labels),
                    'properties': dict(props),
                    'provenance_preview': provenance[:3],
                }
            )
            if len(matches) >= limit:
                break
        return matches
