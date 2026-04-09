from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any

import chromadb

from graph.client import FalkorDBClient
from graph.identities import (
    id_migration_run,
    id_source_document,
    id_source_pipeline,
    id_source_row,
    id_source_system,
)
from migration.sources import CuratedSource


class VectorContextImporter:
    def __init__(self, client: FalkorDBClient | None = None) -> None:
        self.client = client or FalkorDBClient()

    def import_vectors(
        self,
        source: CuratedSource,
        *,
        dry_run: bool = True,
        limit: int | None = None,
        batch_size: int = 1000,
    ) -> dict[str, Any]:
        if not source.vector_sqlite_path.exists():
            raise FileNotFoundError(f'Vector sqlite not found: {source.vector_sqlite_path}')

        graph = self.client.select_graph()
        run_id = self._start_run(graph, source.name, dry_run=dry_run, limit=limit)
        started_at = datetime.now(timezone.utc).isoformat()
        collection_info = self._collection_info(source.vector_sqlite_path)
        collection = self._open_collection(source.vector_sqlite_path.parent, collection_info.get('name'))

        total_embeddings = int(collection.count())
        target = min(total_embeddings, limit) if isinstance(limit, int) else total_embeddings

        rows_processed = 0
        nodes_upserted = 0
        edges_created = 0
        rows_failed = 0
        vectors_indexed = 0
        sample_errors: list[str] = []
        offset = 0

        try:
            while rows_processed < target:
                remaining = target - rows_processed
                chunk = min(batch_size, remaining)
                batch = collection.get(limit=chunk, offset=offset, include=['embeddings', 'metadatas', 'documents'])
                rows = self._batch_rows(batch)
                if not rows:
                    break

                created_at_map = self._created_at_for_ids(
                    source.vector_sqlite_path,
                    [str(row['embedding_id']) for row in rows],
                )
                prepared = [
                    self._prepare_row(source.name, collection_info, row, created_at_map.get(str(row['embedding_id'])))
                    for row in rows
                ]

                if not dry_run:
                    try:
                        batch_result = self._write_batch(graph, source.name, run_id, collection_info, prepared)
                        nodes_upserted += batch_result['nodes_upserted']
                        vectors_indexed += batch_result['vectors_indexed']
                        edges_created += batch_result['edges_created']
                    except Exception as exc:  # pragma: no cover - runtime safeguard
                        if len(sample_errors) < 20:
                            sample_errors.append(f'batch_offset={offset} fallback=per_row err={exc}')
                        for item in prepared:
                            try:
                                self._upsert_text_chunk(graph, node_id=item['node_id'], props=item['props'])
                                edges_created += self._link_provenance(graph, node_id=item['node_id'], props=item['props'])
                                edges_created += self._link_migration_run(graph, node_id=item['node_id'], run_id=run_id)
                                nodes_upserted += 1
                                if 'embedding' in item['props']:
                                    vectors_indexed += 1
                            except Exception as exc2:
                                rows_failed += 1
                                if len(sample_errors) < 20:
                                    sample_errors.append(f"id={item['embedding_id']} err={exc2}")

                rows_processed += len(rows)
                offset += len(rows)

            status = 'dry_run_completed' if dry_run else 'completed'
            self._finish_run(graph, run_id=run_id, status=status)
            return {
                'run_id': run_id,
                'status': status,
                'started_at': started_at,
                'finished_at': datetime.now(timezone.utc).isoformat(),
                'collection': collection_info,
                'source_system': source.name,
                'total_embeddings': total_embeddings,
                'target_embeddings': target,
                'rows_processed': rows_processed,
                'nodes_upserted': nodes_upserted,
                'vectors_indexed': vectors_indexed,
                'edges_created': edges_created,
                'dry_run': dry_run,
                'rows_failed': rows_failed,
                'sample_errors': sample_errors,
            }
        except Exception:
            self._finish_run(graph, run_id=run_id, status='failed')
            raise

    def _prepare_row(
        self,
        source_system: str,
        collection: dict[str, Any],
        row: dict[str, Any],
        created_at: str | None,
    ) -> dict[str, Any]:
        props = self._chunk_props(source_system, collection, row, created_at)
        node_id = id_source_row(source_system, 'vector_context', str(row['embedding_id']))
        doc_id = id_source_document(source_system, str(props.get('source_file') or 'vector_context'))
        pipeline_name = props.get('source_pipeline')
        pipeline_id = None
        if pipeline_name not in (None, '', 'None'):
            pipeline_id = id_source_pipeline(source_system, str(pipeline_name))
        return {
            'embedding_id': str(row['embedding_id']),
            'node_id': node_id,
            'doc_id': doc_id,
            'pipeline_id': pipeline_id,
            'pipeline_name': str(pipeline_name) if pipeline_name not in (None, '', 'None') else None,
            'props': props,
        }

    def _write_batch(
        self,
        graph: Any,
        source_system: str,
        run_id: str,
        collection: dict[str, Any],
        prepared: list[dict[str, Any]],
    ) -> dict[str, int]:
        if not prepared:
            return {'nodes_upserted': 0, 'vectors_indexed': 0, 'edges_created': 0}

        source_system_id = id_source_system(source_system)
        graph.query(
            'MERGE (s:SourceSystem {id: $source_system_id}) '
            'SET s.name = $source_system',
            params={'source_system_id': source_system_id, 'source_system': source_system},
        )

        ids = [item['node_id'] for item in prepared]
        props_list = [item['props'] for item in prepared]
        graph.query(
            'UNWIND range(0, size($ids)-1) AS i '
            'MERGE (n:TextChunk {id: $ids[i]}) '
            'SET n.source_system = $source_system, '
            "    n.source_table = 'vector_context', "
            "    n.mapping_category = 'vector', "
            '    n.embedding_id = $embedding_ids[i], '
            '    n.created_at = $created_ats[i], '
            '    n.source_file = $source_files[i], '
            '    n.collection_name = $collection_name, '
            '    n.collection_dimension = $collection_dimension, '
            '    n.source_pipeline = $source_pipelines[i], '
            '    n.content_type = $content_types[i], '
            '    n.page_number = $page_numbers[i], '
            '    n.chunk_index = $chunk_indexes[i], '
            '    n.content = $contents[i], '
            '    n.ai_summary = $ai_summaries[i], '
            '    n.document_preview = $document_previews[i], '
            '    n.embedding = $embeddings[i], '
            '    n.updated_at = timestamp()',
            params={
                'ids': ids,
                'source_system': source_system,
                'embedding_ids': [str(props.get('embedding_id')) for props in props_list],
                'created_ats': [props.get('created_at') for props in props_list],
                'source_files': [str(props.get('source_file') or 'vector_context') for props in props_list],
                'collection_name': collection.get('name'),
                'collection_dimension': collection.get('dimension'),
                'source_pipelines': [props.get('source_pipeline') for props in props_list],
                'content_types': [props.get('content_type') for props in props_list],
                'page_numbers': [props.get('page_number') for props in props_list],
                'chunk_indexes': [props.get('chunk_index') for props in props_list],
                'contents': [props.get('content') for props in props_list],
                'ai_summaries': [props.get('ai_summary') for props in props_list],
                'document_previews': [props.get('document_preview') for props in props_list],
                'embeddings': [props.get('embedding') for props in props_list],
            },
        )

        docs = {}
        pipelines = {}
        doc_pipeline_rows = []
        for item in prepared:
            docs[item['doc_id']] = str(item['props'].get('source_file') or 'vector_context')
            if item['pipeline_id'] and item['pipeline_name']:
                pipelines[item['pipeline_id']] = item['pipeline_name']
                doc_pipeline_rows.append((item['doc_id'], item['pipeline_id']))

        if docs:
            doc_ids = list(docs.keys())
            doc_files = [docs[doc_id] for doc_id in doc_ids]
            graph.query(
                'UNWIND range(0, size($doc_ids)-1) AS i '
                'MERGE (d:SourceDocument {id: $doc_ids[i]}) '
                'SET d.source_file = $doc_files[i], d.source_system = $source_system',
                params={'doc_ids': doc_ids, 'doc_files': doc_files, 'source_system': source_system},
            )
            graph.query(
                'UNWIND $doc_ids AS doc_id '
                'MATCH (d:SourceDocument {id: doc_id}), (s:SourceSystem {id: $source_system_id}) '
                'MERGE (d)-[:ORIGINATES_FROM]->(s)',
                params={'doc_ids': doc_ids, 'source_system_id': source_system_id},
            )

        if pipelines:
            pipeline_ids = list(pipelines.keys())
            pipeline_names = [pipelines[pipeline_id] for pipeline_id in pipeline_ids]
            graph.query(
                'UNWIND range(0, size($pipeline_ids)-1) AS i '
                'MERGE (p:SourcePipeline {id: $pipeline_ids[i]}) '
                'SET p.name = $pipeline_names[i], p.parent_system = $source_system',
                params={
                    'pipeline_ids': pipeline_ids,
                    'pipeline_names': pipeline_names,
                    'source_system': source_system,
                },
            )
            graph.query(
                'UNWIND $pipeline_ids AS pipeline_id '
                'MATCH (p:SourcePipeline {id: pipeline_id}), (s:SourceSystem {id: $source_system_id}) '
                'MERGE (p)-[:BELONGS_TO]->(s)',
                params={'pipeline_ids': pipeline_ids, 'source_system_id': source_system_id},
            )

        graph.query(
            'UNWIND range(0, size($ids)-1) AS i '
            'MATCH (n:TextChunk {id: $ids[i]}), (d:SourceDocument {id: $doc_ids[i]}) '
            'MERGE (n)-[:DERIVED_FROM]->(d)',
            params={'ids': ids, 'doc_ids': [item['doc_id'] for item in prepared]},
        )
        graph.query(
            'UNWIND range(0, size($ids)-1) AS i '
            'MATCH (n:TextChunk {id: $ids[i]}), (d:SourceDocument {id: $doc_ids[i]}) '
            'MERGE (n)-[r:PROVENANCE]->(d) '
            'SET r.page_number = $page_numbers[i], r.extraction_date = $created_ats[i]',
            params={
                'ids': ids,
                'doc_ids': [item['doc_id'] for item in prepared],
                'page_numbers': [item['props'].get('page_number') for item in prepared],
                'created_ats': [item['props'].get('created_at') for item in prepared],
            },
        )

        if doc_pipeline_rows:
            graph.query(
                'UNWIND range(0, size($doc_ids)-1) AS i '
                'MATCH (d:SourceDocument {id: $doc_ids[i]}), (p:SourcePipeline {id: $pipeline_ids[i]}) '
                'MERGE (d)-[:EXTRACTED_BY]->(p)',
                params={
                    'doc_ids': [row[0] for row in doc_pipeline_rows],
                    'pipeline_ids': [row[1] for row in doc_pipeline_rows],
                },
            )

        graph.query(
            'UNWIND $ids AS node_id '
            'MATCH (n:TextChunk {id: node_id}), (r:MigrationRun {id: $run_id}) '
            'MERGE (n)-[:INGESTED_IN]->(r)',
            params={'ids': ids, 'run_id': run_id},
        )
        if docs:
            graph.query(
                'UNWIND $doc_ids AS doc_id '
                'MATCH (d:SourceDocument {id: doc_id}), (r:MigrationRun {id: $run_id}) '
                'MERGE (d)-[:MIGRATED_IN]->(r)',
                params={'doc_ids': list(docs.keys()), 'run_id': run_id},
            )

        edges_created = (len(ids) * 4) + len(docs)
        if pipelines:
            edges_created += len(pipelines)
        if doc_pipeline_rows:
            edges_created += len(doc_pipeline_rows)

        return {
            'nodes_upserted': len(ids),
            'vectors_indexed': len(ids),
            'edges_created': edges_created,
        }

    def _open_collection(self, store_path: Path, collection_name: str | None):
        client = chromadb.PersistentClient(path=str(store_path))
        if collection_name:
            return client.get_collection(collection_name)
        collections = client.list_collections()
        if not collections:
            raise RuntimeError(f'No Chroma collections found in {store_path}')
        return client.get_collection(collections[0].name)

    def _collection_info(self, sqlite_path: Path) -> dict[str, Any]:
        with sqlite3.connect(f'file:{sqlite_path}?mode=ro', uri=True) as conn:
            row = conn.execute('SELECT id, name, dimension FROM collections LIMIT 1').fetchone()
            if not row:
                return {'id': None, 'name': None, 'dimension': None}
            return {'id': row[0], 'name': row[1], 'dimension': row[2]}

    def _batch_rows(self, batch: dict[str, Any]) -> list[dict[str, Any]]:
        ids_raw = batch.get('ids')
        embeddings_raw = batch.get('embeddings')
        metadatas_raw = batch.get('metadatas')
        documents_raw = batch.get('documents')
        ids = list(ids_raw) if ids_raw is not None else []
        embeddings = list(embeddings_raw) if embeddings_raw is not None else []
        metadatas = list(metadatas_raw) if metadatas_raw is not None else []
        documents = list(documents_raw) if documents_raw is not None else []
        rows: list[dict[str, Any]] = []
        for idx, embedding_id in enumerate(ids):
            rows.append(
                {
                    'embedding_id': str(embedding_id),
                    'embedding': self._normalize_embedding(embeddings[idx] if idx < len(embeddings) else None),
                    'metadata': metadatas[idx] if idx < len(metadatas) and metadatas[idx] is not None else {},
                    'document': documents[idx] if idx < len(documents) and documents[idx] is not None else '',
                }
            )
        return rows

    def _created_at_for_ids(self, sqlite_path: Path, embedding_ids: list[str]) -> dict[str, str]:
        if not embedding_ids:
            return {}
        placeholders = ','.join('?' for _ in embedding_ids)
        query = f'SELECT embedding_id, created_at FROM embeddings WHERE embedding_id IN ({placeholders})'
        with sqlite3.connect(f'file:{sqlite_path}?mode=ro', uri=True) as conn:
            rows = conn.execute(query, embedding_ids).fetchall()
            return {str(row[0]): str(row[1]) for row in rows}

    def _chunk_props(
        self,
        source_system: str,
        collection: dict[str, Any],
        row: dict[str, Any],
        created_at: str | None,
    ) -> dict[str, Any]:
        metadata = row.get('metadata') or {}
        source_file = str(metadata.get('source_file') or metadata.get('chunk_id') or row.get('embedding_id') or 'vector_context')
        content = self._truncate(str(row.get('document') or ''))
        props: dict[str, Any] = {
            'source_system': source_system,
            'source_table': 'vector_context',
            'mapping_category': 'vector',
            'embedding_id': str(row.get('embedding_id')),
            'created_at': str(created_at) if created_at else None,
            'source_file': source_file,
            'collection_name': collection.get('name'),
            'collection_dimension': collection.get('dimension'),
            'source_pipeline': metadata.get('source_pipeline'),
            'content_type': metadata.get('content_type'),
            'page_number': metadata.get('page_number'),
            'chunk_index': metadata.get('chunk_index'),
            'content': content,
            'ai_summary': self._truncate(str(metadata.get('ai_summary', ''))),
            'document_preview': content,
            'embedding': row.get('embedding'),
        }
        return {k: v for k, v in props.items() if v not in (None, '', 'None')}

    def _normalize_embedding(self, embedding: Any) -> list[float] | None:
        if embedding is None:
            return None
        return [float(v) for v in embedding]

    def _truncate(self, text: str, *, max_len: int = 4000) -> str:
        return text if len(text) <= max_len else text[:max_len] + ' ...<truncated>'

    def _upsert_text_chunk(self, graph: Any, *, node_id: str, props: dict[str, Any]) -> None:
        props = dict(props)
        embedding = props.pop('embedding', None)
        params: dict[str, Any] = {'id': node_id, 'props': props}
        query = (
            'MERGE (n:TextChunk {id: $id}) '
            'SET n += $props '
            'SET n.updated_at = timestamp()'
        )
        if embedding is not None:
            query += ' SET n.embedding = $embedding'
            params['embedding'] = embedding
        graph.query(query, params=params)

    def _link_provenance(self, graph: Any, *, node_id: str, props: dict[str, Any]) -> int:
        source_system = str(props.get('source_system'))
        source_file = str(props.get('source_file') or 'vector_context')
        source_system_id = id_source_system(source_system)
        source_doc_id = id_source_document(source_system, source_file)
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
            'MATCH (n:TextChunk {id: $node_id}), (d:SourceDocument {id: $source_doc_id}) '
            'MERGE (n)-[:DERIVED_FROM]->(d)',
            params={'node_id': node_id, 'source_doc_id': source_doc_id},
        )
        graph.query(
            'MATCH (n:TextChunk {id: $node_id}), (d:SourceDocument {id: $source_doc_id}) '
            'MERGE (n)-[r:PROVENANCE]->(d) '
            'SET r.page_number = $page_number, r.extraction_date = $created_at, r.source_pipeline = $source_pipeline',
            params={
                'node_id': node_id,
                'source_doc_id': source_doc_id,
                'page_number': props.get('page_number'),
                'created_at': props.get('created_at'),
                'source_pipeline': props.get('source_pipeline'),
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

    def _start_run(self, graph: Any, source_system: str, *, dry_run: bool, limit: int | None) -> str:
        ts = datetime.now(timezone.utc).isoformat()
        run_id = id_migration_run(f'{source_system}-vector', ts)
        graph.query(
            'MERGE (r:MigrationRun {id: $run_id}) '
            'SET r.run_id = $run_id, '
            '    r.source_system = $source_system, '
            '    r.started_at = $started_at, '
            '    r.dry_run = $dry_run, '
            '    r.limit_per_table = $limit, '
            "    r.status = 'running', "
            "    r.run_type = 'vector_context'",
            params={
                'run_id': run_id,
                'source_system': source_system,
                'started_at': ts,
                'dry_run': dry_run,
                'limit': limit if limit is not None else -1,
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

    def _link_migration_run(self, graph: Any, *, node_id: str, run_id: str) -> int:
        graph.query(
            'MATCH (n:TextChunk {id: $node_id}), (r:MigrationRun {id: $run_id}) '
            'MERGE (n)-[:INGESTED_IN]->(r)',
            params={'node_id': node_id, 'run_id': run_id},
        )
        graph.query(
            'MATCH (n:TextChunk {id: $node_id})-[:DERIVED_FROM]->(d:SourceDocument), (r:MigrationRun {id: $run_id}) '
            'MERGE (d)-[:MIGRATED_IN]->(r)',
            params={'node_id': node_id, 'run_id': run_id},
        )
        return 2
