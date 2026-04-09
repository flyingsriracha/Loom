from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from graph.client import FalkorDBClient
from graph.identities import (
    id_migration_run,
    id_source_document,
    id_source_pipeline,
    id_source_system,
    stable_id,
)
from ingestion.loader import IngestionChunk, IngestionTable, LoadedIngestionDocument
from retrieval.embeddings import encode_text, encode_texts


class IncrementalGraphLoader:
    def __init__(self, client: FalkorDBClient | None = None) -> None:
        self.client = client or FalkorDBClient()

    def ingest(self, doc: LoadedIngestionDocument) -> dict[str, Any]:
        graph = self.client.select_graph()
        source_system_id = id_source_system(doc.source_system)
        pipeline_id = id_source_pipeline(doc.source_system, doc.source_pipeline)
        document_id = id_source_document(doc.source_system, doc.source_file)
        run_started_at = datetime.now(timezone.utc).isoformat()
        run_id = id_migration_run(f'{doc.source_system}-incremental-ingest', run_started_at)

        self._start_run(graph, run_id=run_id, doc=doc, started_at=run_started_at)
        self._upsert_source_nodes(graph, source_system_id=source_system_id, pipeline_id=pipeline_id, document_id=document_id, doc=doc)
        superseded = self._supersede_previous_incremental_nodes(graph, doc=doc, run_id=run_id, superseded_at=run_started_at)

        chunk_embeddings = encode_texts([chunk.content for chunk in doc.chunks]) if doc.chunks else []
        table_embeddings = encode_texts([table.markdown_content for table in doc.tables]) if doc.tables else []

        chunk_count = 0
        table_count = 0
        for idx, chunk in enumerate(doc.chunks):
            embedding = chunk_embeddings[idx] if idx < len(chunk_embeddings) else []
            self._upsert_text_chunk(graph, doc=doc, document_id=document_id, pipeline_id=pipeline_id, run_id=run_id, chunk=chunk, embedding=embedding)
            chunk_count += 1

        for idx, table in enumerate(doc.tables):
            embedding = table_embeddings[idx] if idx < len(table_embeddings) else []
            self._upsert_table_node(graph, doc=doc, document_id=document_id, pipeline_id=pipeline_id, run_id=run_id, table=table, embedding=embedding)
            table_count += 1

        self._finish_run(graph, run_id=run_id, finished_at=datetime.now(timezone.utc).isoformat())
        return {
            'run_id': run_id,
            'source_system': doc.source_system,
            'source_kind': doc.source_kind,
            'source_file': doc.source_file,
            'checksum': doc.checksum,
            'text_chunks_created': chunk_count,
            'table_nodes_created': table_count,
            'superseded_nodes': superseded,
            'vector_dimensions': len(chunk_embeddings[0]) if chunk_embeddings else 0,
        }

    def _start_run(self, graph: Any, *, run_id: str, doc: LoadedIngestionDocument, started_at: str) -> None:
        graph.query(
            'MERGE (r:MigrationRun {id: $run_id}) '
            'SET r.run_id = $run_id, '
            '    r.source_system = $source_system, '
            '    r.source_kind = $source_kind, '
            '    r.source_file = $source_file, '
            '    r.started_at = $started_at, '
            "    r.status = 'running', "
            "    r.run_type = 'incremental_ingest'",
            params={
                'run_id': run_id,
                'source_system': doc.source_system,
                'source_kind': doc.source_kind,
                'source_file': doc.source_file,
                'started_at': started_at,
            },
        )

    def _finish_run(self, graph: Any, *, run_id: str, finished_at: str) -> None:
        graph.query(
            'MATCH (r:MigrationRun {id: $run_id}) SET r.status = "completed", r.finished_at = $finished_at',
            params={'run_id': run_id, 'finished_at': finished_at},
        )

    def _upsert_source_nodes(self, graph: Any, *, source_system_id: str, pipeline_id: str, document_id: str, doc: LoadedIngestionDocument) -> None:
        graph.query(
            'MERGE (s:SourceSystem {id: $source_system_id}) '
            'SET s.name = $source_system, s.source_kind = $source_kind',
            params={'source_system_id': source_system_id, 'source_system': doc.source_system, 'source_kind': doc.source_kind},
        )
        graph.query(
            'MERGE (p:SourcePipeline {id: $pipeline_id}) '
            'SET p.name = $pipeline_name, p.parent_system = $source_system',
            params={'pipeline_id': pipeline_id, 'pipeline_name': doc.source_pipeline, 'source_system': doc.source_system},
        )
        graph.query(
            'MERGE (d:SourceDocument {id: $document_id}) '
            'SET d.source_file = $source_file, d.source_system = $source_system, d.title = $title, d.checksum = $checksum, d.source_kind = $source_kind',
            params={
                'document_id': document_id,
                'source_file': doc.source_file,
                'source_system': doc.source_system,
                'title': doc.title,
                'checksum': doc.checksum,
                'source_kind': doc.source_kind,
            },
        )
        graph.query(
            'MATCH (d:SourceDocument {id: $document_id}), (p:SourcePipeline {id: $pipeline_id}) MERGE (d)-[:EXTRACTED_BY]->(p)',
            params={'document_id': document_id, 'pipeline_id': pipeline_id},
        )
        graph.query(
            'MATCH (p:SourcePipeline {id: $pipeline_id}), (s:SourceSystem {id: $source_system_id}) MERGE (p)-[:BELONGS_TO]->(s)',
            params={'pipeline_id': pipeline_id, 'source_system_id': source_system_id},
        )
        graph.query(
            'MATCH (d:SourceDocument {id: $document_id}), (s:SourceSystem {id: $source_system_id}) MERGE (d)-[:ORIGINATES_FROM]->(s)',
            params={'document_id': document_id, 'source_system_id': source_system_id},
        )

    def _supersede_previous_incremental_nodes(self, graph: Any, *, doc: LoadedIngestionDocument, run_id: str, superseded_at: str) -> int:
        result = graph.query(
            'MATCH (n {source_system: $source_system, source_file: $source_file}) '
            'WHERE n.source_table IN ["incremental_context", "incremental_structured_input"] '
            '  AND coalesce(n.superseded_at, "") = "" '
            '  AND n.checksum <> $checksum '
            'SET n.superseded_at = $superseded_at, n.superseded_by_run = $run_id '
            'RETURN count(n)',
            params={
                'source_system': doc.source_system,
                'source_file': doc.source_file,
                'checksum': doc.checksum,
                'superseded_at': superseded_at,
                'run_id': run_id,
            },
        )
        return int(result.result_set[0][0]) if result.result_set else 0

    def _upsert_text_chunk(
        self,
        graph: Any,
        *,
        doc: LoadedIngestionDocument,
        document_id: str,
        pipeline_id: str,
        run_id: str,
        chunk: IngestionChunk,
        embedding: list[float],
    ) -> None:
        node_id = stable_id('ingest_chunk', doc.source_system, doc.source_file, doc.checksum, str(chunk.chunk_index))
        props = {
            'source_system': doc.source_system,
            'source_table': 'incremental_context',
            'mapping_category': 'vector',
            'source_file': doc.source_file,
            'source_pipeline': doc.source_pipeline,
            'source_kind': doc.source_kind,
            'checksum': doc.checksum,
            'title': doc.title,
            'content': chunk.content,
            'document_preview': chunk.content[:4000],
            'chunk_index': chunk.chunk_index,
            'page_number': chunk.page_number,
            'created_at': doc.extracted_at,
            'collection_name': 'incremental_ingestion',
            'collection_dimension': len(embedding),
        }
        params = {'id': node_id, 'props': props, 'embedding': embedding}
        graph.query(
            'MERGE (n:TextChunk {id: $id}) '
            'SET n += $props '
            'SET n.embedding = $embedding '
            'SET n.updated_at = timestamp()',
            params=params,
        )
        self._link_standard_context(graph, node_id=node_id, source_system=doc.source_system)
        self._link_provenance(graph, node_id=node_id, label='TextChunk', document_id=document_id, pipeline_id=pipeline_id, run_id=run_id, doc=doc, page_number=chunk.page_number, confidence=1.0)

    def _upsert_table_node(
        self,
        graph: Any,
        *,
        doc: LoadedIngestionDocument,
        document_id: str,
        pipeline_id: str,
        run_id: str,
        table: IngestionTable,
        embedding: list[float],
    ) -> None:
        node_id = stable_id('ingest_table', doc.source_system, doc.source_file, doc.checksum, str(table.table_index))
        props = {
            'source_system': doc.source_system,
            'source_table': 'incremental_structured_input',
            'mapping_category': 'reference',
            'is_reference_layer': True,
            'source_file': doc.source_file,
            'source_pipeline': doc.source_pipeline,
            'source_kind': doc.source_kind,
            'checksum': doc.checksum,
            'caption': table.caption,
            'title': table.caption,
            'name': table.caption,
            'markdown_content': table.markdown_content[:12000],
            'json_content': table.json_content[:12000],
            'row_count': table.row_count,
            'col_count': table.col_count,
            'page_number': table.page_number,
            'created_at': doc.extracted_at,
        }
        params = {'id': node_id, 'props': props, 'embedding': embedding}
        graph.query(
            'MERGE (n:Table {id: $id}) '
            'SET n += $props '
            'SET n.embedding = $embedding '
            'SET n.updated_at = timestamp()',
            params=params,
        )
        self._link_standard_context(graph, node_id=node_id, source_system=doc.source_system)
        self._link_provenance(graph, node_id=node_id, label='Table', document_id=document_id, pipeline_id=pipeline_id, run_id=run_id, doc=doc, page_number=table.page_number, confidence=1.0)

    def _link_standard_context(self, graph: Any, *, node_id: str, source_system: str) -> None:
        standard_name = None
        lowered = source_system.lower()
        if 'autosar' in lowered:
            standard_name = 'AUTOSAR'
        elif 'asam' in lowered:
            standard_name = 'ASAM'
        if not standard_name:
            return
        standard_id = stable_id('standard', standard_name)
        graph.query(
            'MERGE (s:Standard {id: $standard_id}) SET s.name = $standard_name, s.organization = $organization',
            params={'standard_id': standard_id, 'standard_name': standard_name, 'organization': standard_name},
        )
        graph.query(
            'MATCH (n {id: $node_id}), (s:Standard {id: $standard_id}) MERGE (n)-[:PART_OF]->(s)',
            params={'node_id': node_id, 'standard_id': standard_id},
        )

    def _link_provenance(
        self,
        graph: Any,
        *,
        node_id: str,
        label: str,
        document_id: str,
        pipeline_id: str,
        run_id: str,
        doc: LoadedIngestionDocument,
        page_number: int | None,
        confidence: float,
    ) -> None:
        graph.query(
            f'MATCH (n:{label} {{id: $node_id}}), (d:SourceDocument {{id: $document_id}}) MERGE (n)-[:DERIVED_FROM]->(d)',
            params={'node_id': node_id, 'document_id': document_id},
        )
        graph.query(
            f'MATCH (n:{label} {{id: $node_id}}), (d:SourceDocument {{id: $document_id}}) '
            'MERGE (n)-[r:PROVENANCE]->(d) '
            'SET r.confidence = $confidence, r.extraction_date = $extraction_date, r.page_number = $page_number, r.source_pipeline = $source_pipeline',
            params={
                'node_id': node_id,
                'document_id': document_id,
                'confidence': confidence,
                'extraction_date': doc.extracted_at,
                'page_number': page_number,
                'source_pipeline': doc.source_pipeline,
            },
        )
        graph.query(
            f'MATCH (n:{label} {{id: $node_id}}), (r:MigrationRun {{id: $run_id}}) MERGE (n)-[:INGESTED_IN]->(r)',
            params={'node_id': node_id, 'run_id': run_id},
        )
        graph.query(
            'MATCH (d:SourceDocument {id: $document_id}), (r:MigrationRun {id: $run_id}) MERGE (d)-[:MIGRATED_IN]->(r)',
            params={'document_id': document_id, 'run_id': run_id},
        )
