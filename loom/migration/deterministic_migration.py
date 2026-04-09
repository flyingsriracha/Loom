from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any

from graph.client import FalkorDBClient
from graph.identities import (
    id_audit_event,
    id_migration_run,
    id_protocol,
    id_source_document,
    id_source_pipeline,
    id_source_row,
    id_source_system,
    id_standard,
)
from migration.report import MigrationReport
from migration.sources import CuratedSource

RAW_CORPUS_NOTE = 'curated seed only; supplementary raw predecessor corpora remain future incremental ingestion scope'
COVERAGE_SCOPE = 'curated seed only'


@dataclass(frozen=True)
class TableMapping:
    source_system: str
    table_name: str
    node_label: str
    key_column: str
    category: str = 'structured'
    standard_name: str | None = None
    standard_field: str | None = None
    protocol_name: str | None = None
    protocol_field: str | None = None
    protocol_type: str | None = None
    module_type: str | None = None
    interface_type: str | None = None
    concept_type: str | None = None
    parameter_subtype: str | None = None
    name_fields: tuple[str, ...] = ()
    title_fields: tuple[str, ...] = ()


STRUCTURED_MAPPINGS: tuple[TableMapping, ...] = (
    TableMapping('ASAMKnowledgeDB', 'xcp_commands', 'Command', 'id', standard_name='ASAM XCP', protocol_name='XCP', name_fields=('command',)),
    TableMapping('ASAMKnowledgeDB', 'xcp_errors', 'ErrorCode', 'id', standard_name='ASAM XCP', protocol_name='XCP', name_fields=('error_name',)),
    TableMapping('ASAMKnowledgeDB', 'xcp_events', 'Concept', 'id', standard_name='ASAM XCP', protocol_name='XCP', concept_type='xcp_event', name_fields=('event_name',)),
    TableMapping('ASAMKnowledgeDB', 'protocol_parameters', 'Parameter', 'id', standard_name='ASAM XCP', protocol_field='protocol', parameter_subtype='protocol_parameter', name_fields=('param_name',)),
    TableMapping('ASAMKnowledgeDB', 'mdf_block_types', 'Parameter', 'id', standard_name='ASAM MDF', parameter_subtype='mdf_block', name_fields=('block_name',)),
    TableMapping('ASAMKnowledgeDB', 'mdf_channel_types', 'Parameter', 'id', standard_name='ASAM MDF', parameter_subtype='mdf_channel', name_fields=('type_name',)),
    TableMapping('ASAMKnowledgeDB', 'mdf_conversion_types', 'Parameter', 'id', standard_name='ASAM MDF', parameter_subtype='mdf_conversion', name_fields=('type_name',)),
    TableMapping('ASAMKnowledgeDB', 'odx_compu_categories', 'Parameter', 'id', standard_name='ASAM ODX', parameter_subtype='odx_compu_category', name_fields=('category',)),
    TableMapping('ASAMKnowledgeDB', 'odx_file_types', 'Parameter', 'id', standard_name='ASAM ODX', parameter_subtype='odx_file_type', name_fields=('extension',)),
    TableMapping('ASAMKnowledgeDB', 'domain_glossary', 'Concept', 'id', standard_name='ASAM', concept_type='domain_glossary', name_fields=('term',)),
    TableMapping('autosar-fusion', 'autosar_cp_modules', 'Module', 'id', standard_name='AUTOSAR CP', name_fields=('module_name',)),
    TableMapping('autosar-fusion', 'autosar_cp_interfaces', 'Interface', 'id', standard_name='AUTOSAR CP', name_fields=('interface_type',)),
    TableMapping('autosar-fusion', 'fibex_elements', 'Concept', 'id', standard_name='ASAM FIBEX', concept_type='fibex_element', name_fields=('name', 'element_type')),
    TableMapping('autosar-fusion', 'dcp_concepts', 'Concept', 'id', standard_name='DCP', concept_type='dcp', name_fields=('concept',)),
    TableMapping('autosar-fusion', 'autosar_cp_layers', 'Protocol', 'id', standard_name='AUTOSAR CP', protocol_type='autosar_layer', name_fields=('layer',)),
    TableMapping('autosar-fusion', 'autosar_cp_swc_types', 'Module', 'id', standard_name='AUTOSAR CP', module_type='swc', name_fields=('swc_type',)),
    TableMapping('autosar-fusion', 'fibex_bus_types', 'Protocol', 'id', standard_name='ASAM FIBEX', protocol_type='bus', name_fields=('bus_type',)),
    TableMapping('autosar-fusion', 'fmi_interface_types', 'Interface', 'id', standard_name='FMI', interface_type='fmi', name_fields=('name',)),
    TableMapping('autosar-fusion', 'fmi_variables', 'Parameter', 'id', standard_name='FMI', parameter_subtype='fmi_variable', name_fields=('name',)),
    TableMapping('autosar-fusion', 'mcd3mc_concepts', 'Concept', 'id', standard_name='ASAM MCD-3 MC', concept_type='mcd3mc', name_fields=('concept',)),
    TableMapping('autosar-fusion', 'ssp_system_elements', 'Concept', 'id', standard_name='SSP', concept_type='ssp_element', name_fields=('name', 'element_type')),
    TableMapping('autosar-fusion', 'vecu_levels', 'Concept', 'id', standard_name='virtualECU', concept_type='vecu_level', name_fields=('name', 'level')),
    TableMapping('autosar-fusion', 'xil_ports', 'Interface', 'id', standard_name='ASAM XIL', interface_type='xil_port', name_fields=('port_type',)),
    TableMapping('autosar-fusion', 'xil_test_concepts', 'Concept', 'id', standard_name='ASAM XIL', concept_type='xil_test', name_fields=('concept',)),
    TableMapping('autosar-fusion', 'cosim_concepts', 'Concept', 'id', standard_field='standard', standard_name='Co-Simulation', concept_type='cosim', name_fields=('concept',)),
)

REFERENCE_MAPPINGS: tuple[TableMapping, ...] = (
    TableMapping('ASAMKnowledgeDB', 'docling_tables', 'Table', 'id', category='reference', standard_name='ASAM', name_fields=('caption', 'source_file')),
    TableMapping('autosar-fusion', 'docling_tables', 'Table', 'id', category='reference', standard_name='AUTOSAR', name_fields=('caption', 'source_file')),
    TableMapping('autosar-fusion', 'research_papers', 'Concept', 'id', category='reference', standard_name='AUTOSAR Research', concept_type='research_paper', name_fields=('title',), title_fields=('title',)),
)

AUDIT_MAPPINGS: tuple[TableMapping, ...] = (
    TableMapping('ASAMKnowledgeDB', 'fusion_log', 'FusionAssessment', 'id', category='audit'),
    TableMapping('ASAMKnowledgeDB', 'comparison_report', 'FusionAssessment', 'id', category='audit'),
    TableMapping('autosar-fusion', 'fusion_log', 'FusionAssessment', 'id', category='audit'),
    TableMapping('autosar-fusion', 'comparison_report', 'FusionAssessment', 'id', category='audit'),
)


class DeterministicMigrator:
    def __init__(self, client: FalkorDBClient | None = None) -> None:
        self.client = client or FalkorDBClient()

    def plan(self, source: CuratedSource, *, include_reference: bool = False, include_audit: bool = False) -> dict[str, Any]:
        table_names = set(self._list_tables(source.sqlite_path))
        mappings = self._select_mappings(source.name, include_reference=include_reference, include_audit=include_audit)
        present = [m for m in mappings if m.table_name in table_names]
        missing = [m.table_name for m in mappings if m.table_name not in table_names]
        return {
            'source_system': source.name,
            'mapped_tables': [
                {
                    'table_name': m.table_name,
                    'node_label': m.node_label,
                    'key_column': m.key_column,
                    'category': m.category,
                }
                for m in present
            ],
            'missing_tables': missing,
        }

    def migrate(
        self,
        source: CuratedSource,
        *,
        dry_run: bool = True,
        limit_per_table: int | None = None,
        include_reference: bool = False,
        include_audit: bool = False,
        include_reconciliation: bool = True,
    ) -> MigrationReport:
        report = MigrationReport(
            source_system=source.name,
            source_structured_rows=source.expected_structured_rows,
            source_vectors=source.expected_vectors,
            raw_corpus_note=RAW_CORPUS_NOTE,
            coverage_scope=COVERAGE_SCOPE,
        )

        mappings = self._select_mappings(
            source.name,
            include_reference=include_reference,
            include_audit=include_audit,
        )
        table_names = set(self._list_tables(source.sqlite_path))
        graph = self.client.select_graph()
        pipeline_counts: Counter[str] = Counter()

        run_id = self._start_run(
            graph,
            source.name,
            dry_run=dry_run,
            limit_per_table=limit_per_table,
            include_reference=include_reference,
            include_audit=include_audit,
        )
        report.run_id = run_id
        report.run_started_at = datetime.now(timezone.utc).isoformat()
        report.run_status = 'running'

        try:
            for mapping in mappings:
                report.mappings_applied += 1
                if mapping.table_name not in table_names:
                    report.records_skipped.append({'table': mapping.table_name, 'reason': 'table_missing'})
                    self._record_audit_event(
                        graph,
                        run_id=run_id,
                        source_system=source.name,
                        table_name=mapping.table_name,
                        status='table_missing',
                        count=0,
                        detail='table not found in source sqlite',
                    )
                    report.audit_events_recorded += 1
                    continue

                rows = self._read_rows(source.sqlite_path, mapping.table_name, limit_per_table)
                for row in rows:
                    pipeline = row.get('source_pipeline')
                    if pipeline:
                        pipeline_counts[str(pipeline)] += 1

                if dry_run:
                    report.records_skipped.append(
                        {
                            'table': mapping.table_name,
                            'reason': 'dry_run',
                            'count': len(rows),
                            'category': mapping.category,
                        }
                    )
                    self._record_audit_event(
                        graph,
                        run_id=run_id,
                        source_system=source.name,
                        table_name=mapping.table_name,
                        status='dry_run',
                        count=len(rows),
                        detail=f'no graph writes in dry run mode ({mapping.category})',
                    )
                    report.audit_events_recorded += 1
                    report.source_rows_processed += len(rows)
                    continue

                for row in rows:
                    row_key = str(row.get(mapping.key_column) or '')
                    node_id = id_source_row(source.name, mapping.table_name, row_key)
                    props = self._node_properties(row, source.name, mapping)
                    self._upsert_node(graph, mapping.node_label, node_id, props)
                    report.nodes_created += 1
                    report.edges_created += self._link_provenance(graph, node_id=node_id, props=props)
                    report.edges_created += self._link_domain_context(graph, mapping=mapping, node_id=node_id, props=props, row=row)
                    report.edges_created += self._link_migration_run(graph, node_id=node_id, run_id=run_id)

                self._record_audit_event(
                    graph,
                    run_id=run_id,
                    source_system=source.name,
                    table_name=mapping.table_name,
                    status='completed',
                    count=len(rows),
                    detail=f'deterministic mapping completed ({mapping.category})',
                )
                report.audit_events_recorded += 1
                report.source_rows_processed += len(rows)

            report.upstream_pipeline_counts = dict(pipeline_counts)
            report.provenance_coverage = 1.0 if report.nodes_created > 0 else 0.0
            if include_reconciliation:
                report.reconciliation = self._build_reconciliation(
                    graph,
                    source=source,
                    mappings=mappings,
                    limit_per_table=limit_per_table,
                )
                report.row_count_match = all(int(item.get('delta', 0)) == 0 for item in report.reconciliation)
            report.run_status = 'completed' if not dry_run else 'dry_run_completed'
            self._finish_run(graph, run_id=run_id, status=report.run_status)
            report.run_finished_at = datetime.now(timezone.utc).isoformat()
            return report
        except Exception:
            report.run_status = 'failed'
            self._finish_run(graph, run_id=run_id, status='failed')
            report.run_finished_at = datetime.now(timezone.utc).isoformat()
            raise

    def _select_mappings(self, source_system: str, *, include_reference: bool, include_audit: bool) -> list[TableMapping]:
        selected = [m for m in STRUCTURED_MAPPINGS if m.source_system == source_system]
        if include_reference:
            selected.extend(m for m in REFERENCE_MAPPINGS if m.source_system == source_system)
        if include_audit:
            selected.extend(m for m in AUDIT_MAPPINGS if m.source_system == source_system)
        return selected

    def _build_reconciliation(
        self,
        graph: Any,
        *,
        source: CuratedSource,
        mappings: list[TableMapping],
        limit_per_table: int | None,
    ) -> list[dict[str, int | str]]:
        rows: list[dict[str, int | str]] = []
        for mapping in mappings:
            source_count_full = self._count_rows(source.sqlite_path, mapping.table_name)
            source_count = min(source_count_full, limit_per_table) if isinstance(limit_per_table, int) else source_count_full
            graph_result = graph.query(
                'MATCH (n {source_system: $source_system, source_table: $source_table, mapping_category: $mapping_category}) RETURN count(n)',
                params={
                    'source_system': source.name,
                    'source_table': mapping.table_name,
                    'mapping_category': mapping.category,
                },
            )
            graph_count = int(graph_result.result_set[0][0]) if graph_result.result_set else 0
            rows.append(
                {
                    'table': mapping.table_name,
                    'category': mapping.category,
                    'source_count': int(source_count),
                    'graph_count': graph_count,
                    'delta': graph_count - int(source_count),
                }
            )
        return rows

    def _start_run(
        self,
        graph: Any,
        source_system: str,
        *,
        dry_run: bool,
        limit_per_table: int | None,
        include_reference: bool,
        include_audit: bool,
    ) -> str:
        timestamp = datetime.now(timezone.utc).isoformat()
        run_id = id_migration_run(source_system, timestamp)
        graph.query(
            'MERGE (r:MigrationRun {id: $run_id}) '
            'SET r.run_id = $run_id, '
            '    r.source_system = $source_system, '
            '    r.started_at = $started_at, '
            '    r.dry_run = $dry_run, '
            '    r.limit_per_table = $limit_per_table, '
            '    r.include_reference = $include_reference, '
            '    r.include_audit = $include_audit, '
            "    r.status = 'running'",
            params={
                'run_id': run_id,
                'source_system': source_system,
                'started_at': timestamp,
                'dry_run': dry_run,
                'limit_per_table': limit_per_table if limit_per_table is not None else -1,
                'include_reference': include_reference,
                'include_audit': include_audit,
            },
        )
        return run_id

    def _finish_run(self, graph: Any, *, run_id: str, status: str) -> None:
        graph.query(
            'MATCH (r:MigrationRun {id: $run_id}) '
            'SET r.status = $status, r.finished_at = $finished_at',
            params={
                'run_id': run_id,
                'status': status,
                'finished_at': datetime.now(timezone.utc).isoformat(),
            },
        )

    def _record_audit_event(
        self,
        graph: Any,
        *,
        run_id: str,
        source_system: str,
        table_name: str,
        status: str,
        count: int,
        detail: str,
    ) -> None:
        event_id = id_audit_event(run_id, table_name, status, count)
        graph.query(
            'MERGE (e:AuditEvent {id: $event_id}) '
            'SET e.run_id = $run_id, '
            '    e.source_system = $source_system, '
            '    e.table_name = $table_name, '
            '    e.status = $status, '
            '    e.count = $count, '
            '    e.detail = $detail, '
            '    e.timestamp = $timestamp',
            params={
                'event_id': event_id,
                'run_id': run_id,
                'source_system': source_system,
                'table_name': table_name,
                'status': status,
                'count': count,
                'detail': detail,
                'timestamp': datetime.now(timezone.utc).isoformat(),
            },
        )
        graph.query(
            'MATCH (r:MigrationRun {id: $run_id}), (e:AuditEvent {id: $event_id}) '
            'MERGE (r)-[:HAS_AUDIT_EVENT]->(e)',
            params={
                'run_id': run_id,
                'event_id': event_id,
            },
        )

    def _link_migration_run(self, graph: Any, *, node_id: str, run_id: str) -> int:
        graph.query(
            'MATCH (n {id: $node_id}), (r:MigrationRun {id: $run_id}) '
            'MERGE (n)-[:INGESTED_IN]->(r)',
            params={'node_id': node_id, 'run_id': run_id},
        )
        graph.query(
            'MATCH (n {id: $node_id})-[:DERIVED_FROM]->(d:SourceDocument), (r:MigrationRun {id: $run_id}) '
            'MERGE (d)-[:MIGRATED_IN]->(r)',
            params={'node_id': node_id, 'run_id': run_id},
        )
        return 2

    def _list_tables(self, db_path: Path) -> list[str]:
        uri = f'file:{db_path}?mode=ro'
        with sqlite3.connect(uri, uri=True) as conn:
            rows = conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
            return [str(r[0]) for r in rows]

    def _count_rows(self, db_path: Path, table_name: str) -> int:
        uri = f'file:{db_path}?mode=ro'
        with sqlite3.connect(uri, uri=True) as conn:
            row = conn.execute(f'SELECT COUNT(1) FROM "{table_name}"').fetchone()
            return int(row[0] if row else 0)

    def _read_rows(self, db_path: Path, table_name: str, limit: int | None) -> list[dict[str, Any]]:
        uri = f'file:{db_path}?mode=ro'
        with sqlite3.connect(uri, uri=True) as conn:
            conn.row_factory = sqlite3.Row
            query = f'SELECT * FROM "{table_name}"'
            if isinstance(limit, int) and limit > 0:
                query += f' LIMIT {limit}'
            rows = conn.execute(query).fetchall()
            return [dict(row) for row in rows]

    def _node_properties(self, row: dict[str, Any], source_system: str, mapping: TableMapping) -> dict[str, Any]:
        props: dict[str, Any] = {
            'source_system': source_system,
            'source_table': mapping.table_name,
            'mapping_category': mapping.category,
        }
        if mapping.category == 'reference':
            props['is_reference_layer'] = True
        if mapping.category == 'audit':
            props['is_audit_layer'] = True

        reserved = {'id', 'source_system', 'source_table', 'mapping_category'}
        for key, value in row.items():
            if value is None:
                continue
            target_key = f'raw_{key}' if key in reserved else key
            if isinstance(value, (str, int, float, bool)):
                props[target_key] = self._truncate_if_large(value)
            else:
                props[target_key] = self._truncate_if_large(str(value))

        self._apply_canonical_properties(props, row, mapping)
        return props

    def _apply_canonical_properties(self, props: dict[str, Any], row: dict[str, Any], mapping: TableMapping) -> None:
        name = self._first_non_empty(
            row,
            *mapping.name_fields,
            'name',
            'title',
            'command',
            'error_name',
            'event_name',
            'param_name',
            'block_name',
            'type_name',
            'category',
            'term',
            'module_name',
            'interface_type',
            'concept',
            'layer',
            'swc_type',
            'bus_type',
            'port_type',
            'element_type',
            'level',
        )
        if name is not None:
            props['name'] = self._truncate_if_large(str(name))

        title = self._first_non_empty(row, *mapping.title_fields, 'title', 'caption')
        if title is not None:
            props['title'] = self._truncate_if_large(str(title))

        description = self._first_non_empty(row, 'description', 'definition', 'purpose', 'what_virtualized', 'typical_use')
        if description is not None:
            props['description'] = self._truncate_if_large(str(description))

        source_file = self._first_non_empty(row, 'source_file', 'file_path')
        if source_file is not None:
            props['source_file'] = str(source_file)

        if mapping.module_type:
            props['module_type'] = mapping.module_type
        if mapping.interface_type:
            props['interface_type'] = mapping.interface_type
        if mapping.protocol_type:
            props['protocol_type'] = mapping.protocol_type
        if mapping.concept_type:
            props['concept_type'] = mapping.concept_type
        if mapping.parameter_subtype:
            props['subtype'] = mapping.parameter_subtype

        standard_name = self._resolve_standard_name(mapping, row)
        if standard_name:
            props['standard_name'] = standard_name

        protocol_name = self._resolve_protocol_name(mapping, row)
        if protocol_name:
            props['protocol_name'] = protocol_name

    def _resolve_standard_name(self, mapping: TableMapping, row: dict[str, Any]) -> str | None:
        if mapping.standard_field:
            value = row.get(mapping.standard_field)
            if value not in (None, '', 'None'):
                return str(value)
        if mapping.standard_name:
            return mapping.standard_name
        return None

    def _resolve_protocol_name(self, mapping: TableMapping, row: dict[str, Any]) -> str | None:
        if mapping.protocol_field:
            value = row.get(mapping.protocol_field)
            if value not in (None, '', 'None'):
                return str(value)
        if mapping.protocol_name:
            return mapping.protocol_name
        return None

    def _first_non_empty(self, row: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = row.get(key)
            if value not in (None, '', 'None'):
                return value
        return None

    def _truncate_if_large(self, value: str | int | float | bool) -> str | int | float | bool:
        if not isinstance(value, str):
            return value
        if len(value) <= 4000:
            return value
        return value[:4000] + ' ...<truncated>'

    def _upsert_node(self, graph: Any, label: str, node_id: str, props: dict[str, Any]) -> None:
        query = (
            f'MERGE (n:{label} {{id: $id}}) '
            'SET n += $props '
            'SET n.updated_at = timestamp()'
        )
        graph.query(query, params={'id': node_id, 'props': props})

    def _link_provenance(self, graph: Any, *, node_id: str, props: dict[str, Any]) -> int:
        source_system = str(props.get('source_system'))
        source_file = str(props.get('source_file') or props.get('source_table'))
        source_system_id = id_source_system(source_system)
        source_doc_id = id_source_document(source_system, source_file)
        confidence = props.get('confidence')
        extraction_date = props.get('created_at')
        page_number = props.get('page_number')
        pipeline_name = props.get('source_pipeline')

        graph.query(
            'MERGE (s:SourceSystem {id: $source_system_id}) '
            'SET s.name = $source_system',
            params={'source_system_id': source_system_id, 'source_system': source_system},
        )
        graph.query(
            'MERGE (d:SourceDocument {id: $source_doc_id}) '
            'SET d.source_file = $source_file, d.source_system = $source_system',
            params={'source_doc_id': source_doc_id, 'source_file': source_file, 'source_system': source_system},
        )
        graph.query(
            'MATCH (n {id: $node_id}), (d:SourceDocument {id: $source_doc_id}) '
            'MERGE (n)-[:DERIVED_FROM]->(d)',
            params={'node_id': node_id, 'source_doc_id': source_doc_id},
        )
        graph.query(
            'MATCH (n {id: $node_id}), (d:SourceDocument {id: $source_doc_id}) '
            'MERGE (n)-[r:PROVENANCE]->(d) '
            'SET r.confidence = $confidence, r.extraction_date = $extraction_date, r.page_number = $page_number, '
            '    r.source_pipeline = $source_pipeline',
            params={
                'node_id': node_id,
                'source_doc_id': source_doc_id,
                'confidence': confidence,
                'extraction_date': extraction_date,
                'page_number': page_number,
                'source_pipeline': pipeline_name,
            },
        )
        graph.query(
            'MATCH (d:SourceDocument {id: $source_doc_id}), (s:SourceSystem {id: $source_system_id}) '
            'MERGE (d)-[:ORIGINATES_FROM]->(s)',
            params={'source_doc_id': source_doc_id, 'source_system_id': source_system_id},
        )

        edge_count = 3
        if pipeline_name not in (None, '', 'None'):
            pipeline_name = str(pipeline_name)
            pipeline_id = id_source_pipeline(source_system, pipeline_name)
            graph.query(
                'MERGE (p:SourcePipeline {id: $pipeline_id}) '
                'SET p.name = $pipeline_name, p.parent_system = $source_system',
                params={
                    'pipeline_id': pipeline_id,
                    'pipeline_name': pipeline_name,
                    'source_system': source_system,
                },
            )
            graph.query(
                'MATCH (d:SourceDocument {id: $source_doc_id}), (p:SourcePipeline {id: $pipeline_id}) '
                'MERGE (d)-[:EXTRACTED_BY]->(p)',
                params={'source_doc_id': source_doc_id, 'pipeline_id': pipeline_id},
            )
            graph.query(
                'MATCH (p:SourcePipeline {id: $pipeline_id}), (s:SourceSystem {id: $source_system_id}) '
                'MERGE (p)-[:BELONGS_TO]->(s)',
                params={'pipeline_id': pipeline_id, 'source_system_id': source_system_id},
            )
            edge_count += 2

        return edge_count

    def _link_domain_context(
        self,
        graph: Any,
        *,
        mapping: TableMapping,
        node_id: str,
        props: dict[str, Any],
        row: dict[str, Any],
    ) -> int:
        if mapping.category == 'audit':
            return 0

        standard_name = self._resolve_standard_name(mapping, row)
        protocol_name = self._resolve_protocol_name(mapping, row)
        edge_count = 0
        standard_id: str | None = None

        if standard_name:
            standard_id = id_standard(standard_name)
            graph.query(
                'MERGE (s:Standard {id: $standard_id}) '
                'SET s.name = $standard_name, s.organization = $organization, s.source_system = $source_system',
                params={
                    'standard_id': standard_id,
                    'standard_name': standard_name,
                    'organization': self._standard_organization(standard_name),
                    'source_system': props.get('source_system'),
                },
            )

        protocol_id: str | None = None
        if protocol_name:
            protocol_id = id_protocol(protocol_name)
            graph.query(
                'MERGE (p:Protocol {id: $protocol_id}) '
                'SET p.name = $protocol_name, p.protocol_type = coalesce(p.protocol_type, $protocol_type), '
                '    p.standard_id = $standard_id, p.source_system = $source_system',
                params={
                    'protocol_id': protocol_id,
                    'protocol_name': protocol_name,
                    'protocol_type': mapping.protocol_type,
                    'standard_id': standard_id,
                    'source_system': props.get('source_system'),
                },
            )
            if standard_id:
                graph.query(
                    'MATCH (s:Standard {id: $standard_id}), (p:Protocol {id: $protocol_id}) '
                    'MERGE (s)-[:DEFINES]->(p)',
                    params={'standard_id': standard_id, 'protocol_id': protocol_id},
                )
                edge_count += 1

        if mapping.node_label in {'Command', 'ErrorCode', 'Parameter'} and protocol_id:
            graph.query(
                'MATCH (p:Protocol {id: $protocol_id}), (n {id: $node_id}) '
                'MERGE (p)-[:DEFINES]->(n)',
                params={'protocol_id': protocol_id, 'node_id': node_id},
            )
            edge_count += 1
        elif standard_id:
            if mapping.node_label in {'Module', 'Protocol', 'Requirement'}:
                graph.query(
                    'MATCH (s:Standard {id: $standard_id}), (n {id: $node_id}) '
                    'MERGE (s)-[:DEFINES]->(n)',
                    params={'standard_id': standard_id, 'node_id': node_id},
                )
            else:
                graph.query(
                    'MATCH (n {id: $node_id}), (s:Standard {id: $standard_id}) '
                    'MERGE (n)-[:PART_OF]->(s)',
                    params={'standard_id': standard_id, 'node_id': node_id},
                )
            edge_count += 1

        return edge_count

    def _standard_organization(self, standard_name: str) -> str | None:
        upper = standard_name.upper()
        if upper.startswith('ASAM'):
            return 'ASAM'
        if upper.startswith('AUTOSAR'):
            return 'AUTOSAR'
        if upper.startswith('FMI'):
            return 'FMI'
        if upper.startswith('SSP'):
            return 'SSP'
        if upper.startswith('DCP'):
            return 'DCP'
        return None
