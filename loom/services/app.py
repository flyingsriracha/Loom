from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from common.auth import APIRequestContext, build_api_auth_dependency
from common.observability import MetricsRegistry, instrument_request, metrics_response
from common.settings import load_settings
from graph.client import FalkorDBClient, falkordb_health
from graph.corrections import CorrectionStore
from graph.provenance import ProvenanceResolver
from graph.schema import bootstrap_schema
from graph.temporal import TemporalStateManager
from ingestion.community import IngestionCommunityRefresher
from ingestion.graph_loader import IncrementalGraphLoader
from ingestion.loader import IngestionLoader
from ingestion.validation import IngestionValidator
from migration.curated_scanner import CuratedSourceScanner
from migration.deterministic_migration import DeterministicMigrator
from migration.sources import curated_sources
from migration.vector_import import VectorContextImporter
from retrieval.community import CACHE_PATH
from retrieval.embeddings import encode_text
from retrieval.pipeline import RetrievalPipeline

app = FastAPI(title='Loom Services', version='0.1.0')
settings = load_settings()
metrics_registry = MetricsRegistry('loom-services')


@app.on_event('startup')
async def startup_warmup() -> None:
    try:
        encode_text('loom startup warmup')
    except Exception:
        # Warmup is best-effort; health endpoints should still come up even if the local embedder is unavailable.
        return None


@app.middleware('http')
async def metrics_middleware(request, call_next):
    return await instrument_request(request, call_next, registry=metrics_registry)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, description='Natural-language query')
    source_system: str | None = Field(default=None, description='Optional provenance source system filter')
    source_pipeline: str | None = Field(default=None, description='Optional provenance pipeline filter')
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    valid_at: str | None = Field(default=None, description='ISO timestamp for temporal query slicing')
    limit: int = Field(default=10, ge=1, le=100)
    refresh_communities: bool = Field(default=False, description='Regenerate community summaries before search')


class ArtifactContextRequest(SearchRequest):
    artifact_type: str = Field(description='requirements, design, tasks, or another artifact flavor')


class IngestRequest(BaseModel):
    source_path: str = Field(description='Absolute or repo-relative path to a PDF, text, markdown, JSON, YAML, or CSV file')
    source_kind: str | None = Field(default=None, description='Optional explicit source kind override')
    source_system: str | None = Field(default=None, description='Optional explicit source system name')
    source_pipeline: str | None = Field(default=None, description='Optional explicit pipeline name')
    chunk_chars: int = Field(default=1200, ge=200, le=8000)
    chunk_overlap: int = Field(default=150, ge=0, le=1000)
    refresh_communities: bool = Field(default=True, description='Refresh community summaries after ingest')


class TemporalQueryRequest(BaseModel):
    valid_at: str = Field(description='ISO timestamp to query active state at')
    tx_at: str | None = Field(default=None, description='Optional transaction time boundary')
    entity_label: str | None = Field(default=None, description='Optional entity label filter')
    source_system: str | None = Field(default=None)
    query: str | None = Field(default=None, description='Optional lexical filter over entity/state text')
    limit: int = Field(default=25, ge=1, le=200)


class TemporalUpsertRequest(BaseModel):
    entity_label: str = Field(description='Standard, Protocol, Module, or Requirement')
    entity_id: str = Field(description='Stable identity node id')
    state_properties: dict = Field(description='Mutable state properties to upsert')
    valid_at: str | None = Field(default=None)
    tx_at: str | None = Field(default=None)


async def _read_context(
    x_api_key: str | None = Header(default=None, alias='X-API-Key'),
    x_engineer_id: str | None = Header(default=None, alias='X-Engineer-Id'),
    x_session_id: str | None = Header(default=None, alias='X-Session-Id'),
    x_objective_id: str | None = Header(default=None, alias='X-Objective-Id'),
    x_project_id: str | None = Header(default=None, alias='X-Project-Id'),
) -> APIRequestContext:
    dependency = build_api_auth_dependency(settings, admin_only=False)
    return await dependency(
        x_api_key=x_api_key,
        x_engineer_id=x_engineer_id,
        x_session_id=x_session_id,
        x_objective_id=x_objective_id,
        x_project_id=x_project_id,
    )


async def _admin_context(
    x_api_key: str | None = Header(default=None, alias='X-API-Key'),
    x_engineer_id: str | None = Header(default=None, alias='X-Engineer-Id'),
    x_session_id: str | None = Header(default=None, alias='X-Session-Id'),
    x_objective_id: str | None = Header(default=None, alias='X-Objective-Id'),
    x_project_id: str | None = Header(default=None, alias='X-Project-Id'),
) -> APIRequestContext:
    dependency = build_api_auth_dependency(settings, admin_only=True)
    return await dependency(
        x_api_key=x_api_key,
        x_engineer_id=x_engineer_id,
        x_session_id=x_session_id,
        x_objective_id=x_objective_id,
        x_project_id=x_project_id,
    )


def _with_context(payload: dict, context: APIRequestContext) -> dict:
    return {**payload, 'request_context': context.to_dict()}


def _artifact_guidance(artifact_type: str) -> dict[str, object]:
    normalized = artifact_type.lower().strip()
    if normalized == 'requirements':
        return {
            'focus': ['constraints', 'obligations', 'protocol rules', 'confidence and provenance'],
            'preferred_labels': ['Requirement', 'Protocol', 'Parameter', 'Table'],
        }
    if normalized == 'design':
        return {
            'focus': ['modules', 'interfaces', 'protocol structure', 'temporal behavior'],
            'preferred_labels': ['Module', 'Interface', 'Protocol', 'Concept', 'Table'],
        }
    if normalized == 'tasks':
        return {
            'focus': ['implementation sequence', 'affected modules', 'supporting evidence'],
            'preferred_labels': ['Module', 'Protocol', 'Concept', 'Table', 'TextChunk'],
        }
    return {
        'focus': ['general standards grounding', 'supporting evidence'],
        'preferred_labels': ['Protocol', 'Module', 'Concept', 'Table', 'TextChunk'],
    }


def _ingestion_document_summary(doc) -> dict[str, object]:
    return {
        'source_path': str(doc.source_path),
        'source_kind': doc.source_kind,
        'source_system': doc.source_system,
        'source_pipeline': doc.source_pipeline,
        'source_file': doc.source_file,
        'title': doc.title,
        'checksum': doc.checksum,
        'chunk_count': len(doc.chunks),
        'table_count': len(doc.tables),
        'metadata': doc.metadata,
        'warnings': doc.warnings,
    }


@app.get('/metrics')
@app.get('/api/v1/metrics')
async def metrics():
    return metrics_response(metrics_registry)


@app.get('/health')
@app.get('/api/v1/health')
async def health() -> dict:
    falkordb = falkordb_health(settings)
    return {
        'service': 'loom-services',
        'status': 'ok' if falkordb.ok else 'degraded',
        'graphiti_enabled': True,
        'temporal_backend': 'graphiti_ready_falkordb_state',
        'retrieval_backend': 'local_minilm_graphrag',
        'falkordb': {
            **falkordb.to_dict(),
            'group_id': settings.graphiti_group_id,
        },
    }


@app.get('/health/falkordb')
@app.get('/api/v1/health/falkordb')
async def health_falkordb() -> dict:
    return falkordb_health(settings).to_dict()


@app.get('/api/v1/diagnostics')
async def api_diagnostics(context: APIRequestContext = Depends(_read_context)) -> dict:
    client = FalkorDBClient(settings=settings)
    try:
        falkordb = falkordb_health(settings)
        counts = {
            'mapped_nodes': client.query('MATCH (n) WHERE n.mapping_category IN ["structured","reference","audit"] RETURN count(n)').result_set[0][0],
            'vector_nodes': client.query('MATCH (n:TextChunk {mapping_category:"vector"}) RETURN count(n)').result_set[0][0],
            'state_edges': client.query('MATCH ()-[r:HAS_STATE]->() RETURN count(r)').result_set[0][0],
            'provenance_edges': client.query('MATCH ()-[r:PROVENANCE]->() RETURN count(r)').result_set[0][0],
            'source_pipelines': client.query('MATCH (n:SourcePipeline) RETURN count(n)').result_set[0][0],
            'community_nodes': client.query('MATCH (n:Community) RETURN count(n)').result_set[0][0],
            'practical_notes': client.query('MATCH (n:PracticalNote) RETURN count(n)').result_set[0][0],
            'corrections': client.query('MATCH (n:CorrectionItem) RETURN count(n)').result_set[0][0],
        }
        cache_info = {
            'path': str(CACHE_PATH),
            'exists': CACHE_PATH.exists(),
            'size_bytes': CACHE_PATH.stat().st_size if CACHE_PATH.exists() else 0,
        }
        return _with_context(
            {
                'ok': True,
                'service': 'loom-services',
                'falkordb': falkordb.to_dict(),
                'counts': counts,
                'community_cache': cache_info,
                'auth': {
                    'loom_api_key_configured': bool(settings.loom_api_key),
                    'loom_admin_api_key_configured': bool(settings.loom_admin_api_key),
                    'allow_local_dev_bypass': settings.allow_local_dev_bypass,
                    'deployment_environment': settings.deployment_environment,
                },
                'graphiti_provider': {
                    'azure_configured': bool(settings.azure_openai_api_key and settings.azure_openai_endpoint),
                },
            },
            context,
        )
    finally:
        client.close()


@app.post('/api/v1/search')
async def api_search(request: SearchRequest, context: APIRequestContext = Depends(_read_context)) -> dict:
    client = FalkorDBClient(settings=settings)
    pipeline = RetrievalPipeline(client=client)
    try:
        payload = pipeline.search(
            request.query,
            valid_at=request.valid_at,
            source_system=request.source_system,
            source_pipeline=request.source_pipeline,
            min_confidence=request.min_confidence,
            limit=request.limit,
            refresh_communities=request.refresh_communities,
        )
        return _with_context(payload, context)
    finally:
        client.close()


@app.post('/api/v1/query')
async def api_query(request: SearchRequest, context: APIRequestContext = Depends(_read_context)) -> dict:
    client = FalkorDBClient(settings=settings)
    pipeline = RetrievalPipeline(client=client)
    try:
        payload = pipeline.query(
            request.query,
            valid_at=request.valid_at,
            source_system=request.source_system,
            source_pipeline=request.source_pipeline,
            min_confidence=request.min_confidence,
            limit=request.limit,
            refresh_communities=request.refresh_communities,
        )
        return _with_context(payload, context)
    finally:
        client.close()


@app.post('/api/v1/artifact/context')
async def api_artifact_context(request: ArtifactContextRequest, context: APIRequestContext = Depends(_read_context)) -> dict:
    client = FalkorDBClient(settings=settings)
    pipeline = RetrievalPipeline(client=client)
    try:
        guidance = _artifact_guidance(request.artifact_type)
        payload = pipeline.query(
            request.query,
            valid_at=request.valid_at,
            source_system=request.source_system,
            source_pipeline=request.source_pipeline,
            min_confidence=request.min_confidence,
            limit=request.limit,
            refresh_communities=request.refresh_communities,
        )
        payload.update(
            {
                'artifact_type': request.artifact_type,
                'artifact_guidance': guidance,
            }
        )
        return _with_context(payload, context)
    finally:
        client.close()


@app.post('/api/v1/ingest/validate')
async def api_ingest_validate(request: IngestRequest, context: APIRequestContext = Depends(_admin_context)) -> dict:
    loader = IngestionLoader()
    validator = IngestionValidator()
    doc = loader.load(**request.model_dump(exclude={'refresh_communities'}))
    validation = validator.validate(doc)
    return _with_context(
        {
            'ok': validation.accepted,
            'document': _ingestion_document_summary(doc),
            'validation': validation.to_dict(),
        },
        context,
    )


@app.post('/api/v1/ingest')
async def api_ingest(request: IngestRequest, context: APIRequestContext = Depends(_admin_context)) -> dict:
    loader = IngestionLoader()
    validator = IngestionValidator()
    doc = loader.load(**request.model_dump(exclude={'refresh_communities'}))
    validation = validator.validate(doc)
    if not validation.accepted:
        raise HTTPException(status_code=400, detail={'validation': validation.to_dict()})

    client = FalkorDBClient(settings=settings)
    try:
        graph_loader = IncrementalGraphLoader(client=client)
        ingest_result = graph_loader.ingest(doc)
        community_refresh = None
        warnings = list(validation.warnings)
        if request.refresh_communities:
            try:
                community_refresh = IngestionCommunityRefresher(client=client).refresh()
            except Exception as exc:
                warnings.append(f'community_refresh_failed:{exc}')
        return _with_context(
            {
                'ok': True,
                'document': _ingestion_document_summary(doc),
                'validation': validation.to_dict(),
                'ingest_result': ingest_result,
                'community_refresh': community_refresh,
                'warnings': warnings,
            },
            context,
        )
    finally:
        client.close()


@app.post('/api/v1/temporal/query')
async def api_temporal_query(request: TemporalQueryRequest, context: APIRequestContext = Depends(_read_context)) -> dict:
    client = FalkorDBClient(settings=settings)
    manager = TemporalStateManager(client=client)
    try:
        results = manager.query_as_of(
            valid_at=request.valid_at,
            tx_at=request.tx_at,
            entity_label=request.entity_label,
            source_system=request.source_system,
            query_text=request.query,
            limit=request.limit,
        )
        return _with_context(
            {
                'ok': True,
                'valid_at': request.valid_at,
                'tx_at': request.tx_at or request.valid_at,
                'entity_label': request.entity_label,
                'source_system': request.source_system,
                'results': results,
                'no_results': len(results) == 0,
            },
            context,
        )
    finally:
        client.close()


@app.get('/api/v1/node/{node_id}')
async def api_node(node_id: str, context: APIRequestContext = Depends(_read_context)) -> dict:
    client = FalkorDBClient(settings=settings)
    resolver = ProvenanceResolver(client=client)
    try:
        node = resolver.get_node(node_id)
        if node is None:
            raise HTTPException(status_code=404, detail=f'unknown node id: {node_id}')
        return _with_context({'ok': True, 'node': node}, context)
    finally:
        client.close()


@app.get('/api/v1/node/{node_id}/provenance')
async def api_node_provenance(
    node_id: str,
    source_system: str | None = Query(None),
    source_pipeline: str | None = Query(None),
    min_confidence: float | None = Query(None, ge=0.0, le=1.0),
    context: APIRequestContext = Depends(_read_context),
) -> dict:
    client = FalkorDBClient(settings=settings)
    resolver = ProvenanceResolver(client=client)
    try:
        node = resolver.get_node(node_id)
        if node is None:
            raise HTTPException(status_code=404, detail=f'unknown node id: {node_id}')
        provenance = resolver.resolve(
            node_id,
            source_system=source_system,
            source_pipeline=source_pipeline,
            min_confidence=min_confidence,
        )
        return _with_context({'ok': True, 'node': node, 'provenance': provenance}, context)
    finally:
        client.close()


@app.post('/admin/bootstrap/schema')
async def admin_bootstrap_schema(context: APIRequestContext = Depends(_admin_context)) -> dict:
    client = FalkorDBClient(settings=settings)
    try:
        result = bootstrap_schema(client=client)
        return _with_context(
            {
                'ok': True,
                'database': settings.falkordb_database,
                **result.to_dict(),
            },
            context,
        )
    finally:
        client.close()


@app.post('/admin/temporal/bootstrap')
async def admin_temporal_bootstrap(
    source_system: str | None = Query(None),
    context: APIRequestContext = Depends(_admin_context),
) -> dict:
    client = FalkorDBClient(settings=settings)
    manager = TemporalStateManager(client=client)
    try:
        return _with_context({'ok': True, **manager.seed_from_existing(source_system=source_system)}, context)
    finally:
        client.close()


@app.post('/admin/temporal/upsert')
async def admin_temporal_upsert(
    request: TemporalUpsertRequest,
    context: APIRequestContext = Depends(_admin_context),
) -> dict:
    client = FalkorDBClient(settings=settings)
    manager = TemporalStateManager(client=client)
    try:
        return _with_context({'ok': True, **manager.upsert_state(**request.model_dump())}, context)
    finally:
        client.close()


@app.post('/admin/retrieval/communities/refresh')
async def admin_refresh_communities(context: APIRequestContext = Depends(_admin_context)) -> dict:
    client = FalkorDBClient(settings=settings)
    pipeline = RetrievalPipeline(client=client)
    try:
        return _with_context({'ok': True, **pipeline.ensure_communities(refresh=True)}, context)
    finally:
        client.close()


@app.get('/admin/migration/curated-sources/scan')
async def admin_scan_curated_sources(context: APIRequestContext = Depends(_admin_context)) -> dict:
    scanner = CuratedSourceScanner()
    sources = curated_sources()
    scans = []
    for source in sources:
        scan = scanner.scan(source)
        report = scanner.seed_report(source, scan)
        scans.append(
            {
                **scan.to_dict(),
                'seed_report': {
                    'source_structured_rows': report.source_structured_rows,
                    'source_vectors': report.source_vectors,
                    'upstream_pipeline_counts': report.upstream_pipeline_counts,
                },
            }
        )
    return _with_context({'ok': True, 'sources': scans}, context)


@app.get('/admin/migration/structured/plan')
async def admin_migration_structured_plan(context: APIRequestContext = Depends(_admin_context)) -> dict:
    migrator = DeterministicMigrator()
    plans = [migrator.plan(source, include_reference=True, include_audit=True) for source in curated_sources()]
    return _with_context({'ok': True, 'plans': plans}, context)


@app.post('/admin/migration/structured/run')
async def admin_migration_structured_run(
    source_system: str = Query(..., description='ASAMKnowledgeDB or autosar-fusion'),
    dry_run: bool = Query(True, description='Dry run by default'),
    limit_per_table: int | None = Query(None, ge=1, le=10000),
    include_reference: bool = Query(False, description='Include docling reference-table migration'),
    include_audit: bool = Query(False, description='Include fusion audit table migration'),
    include_reconciliation: bool = Query(True, description='Compute row reconciliation after migration'),
    context: APIRequestContext = Depends(_admin_context),
) -> dict:
    source = next((s for s in curated_sources() if s.name == source_system), None)
    if source is None:
        raise HTTPException(status_code=400, detail=f'unknown source_system: {source_system}')

    client = FalkorDBClient(settings=settings)
    migrator = DeterministicMigrator(client=client)
    try:
        report = migrator.migrate(
            source,
            dry_run=dry_run,
            limit_per_table=limit_per_table,
            include_reference=include_reference,
            include_audit=include_audit,
            include_reconciliation=include_reconciliation,
        )
        return _with_context(
            {
                'ok': True,
                'source_system': source_system,
                'dry_run': dry_run,
                'limit_per_table': limit_per_table,
                'include_reference': include_reference,
                'include_audit': include_audit,
                'include_reconciliation': include_reconciliation,
                'report': {
                    'run_id': report.run_id,
                    'run_started_at': report.run_started_at,
                    'run_finished_at': report.run_finished_at,
                    'run_status': report.run_status,
                    'source_structured_rows': report.source_structured_rows,
                    'source_vectors': report.source_vectors,
                    'mappings_applied': report.mappings_applied,
                    'source_rows_processed': report.source_rows_processed,
                    'nodes_created': report.nodes_created,
                    'edges_created': report.edges_created,
                    'vectors_indexed': report.vectors_indexed,
                    'audit_events_recorded': report.audit_events_recorded,
                    'upstream_pipeline_counts': report.upstream_pipeline_counts,
                    'records_skipped': report.records_skipped,
                    'provenance_coverage': report.provenance_coverage,
                    'reconciliation': report.reconciliation,
                    'row_count_match': report.row_count_match,
                    'raw_corpus_note': report.raw_corpus_note,
                    'coverage_scope': report.coverage_scope,
                },
            },
            context,
        )
    finally:
        client.close()


@app.post('/admin/migration/vector/run')
async def admin_migration_vector_run(
    source_system: str = Query(..., description='ASAMKnowledgeDB or autosar-fusion'),
    dry_run: bool = Query(True, description='Dry run by default'),
    limit: int | None = Query(None, ge=1),
    batch_size: int = Query(1000, ge=100, le=5000),
    context: APIRequestContext = Depends(_admin_context),
) -> dict:
    source = next((s for s in curated_sources() if s.name == source_system), None)
    if source is None:
        raise HTTPException(status_code=400, detail=f'unknown source_system: {source_system}')

    client = FalkorDBClient(settings=settings)
    importer = VectorContextImporter(client=client)
    try:
        result = importer.import_vectors(
            source,
            dry_run=dry_run,
            limit=limit,
            batch_size=batch_size,
        )
        return _with_context({'ok': True, **result}, context)
    finally:
        client.close()


class CorrectionRequest(BaseModel):
    correction_type: str = Field(description='data_quality, retrieval_quality, or practical_knowledge')
    title: str = Field(min_length=3)
    content: str = Field(min_length=3)
    target_node_id: str | None = None
    priority: str = Field(default='medium')
    source: str = Field(default='manual')
    transcript_ref: str | None = None
    transcript_excerpt: str | None = None


class CorrectionReviewRequest(BaseModel):
    decision: str = Field(description='approved or rejected')
    resolution_note: str | None = None
    publish_practical_note: bool = True
    federate: bool = False


class PracticalNoteRequest(BaseModel):
    note_type: str = Field(default='practical_knowledge')
    title: str = Field(min_length=3)
    content: str = Field(min_length=3)
    target_node_id: str | None = None
    federate: bool = False
    transcript_ref: str | None = None
    transcript_excerpt: str | None = None


class FederationExportRequest(BaseModel):
    note_ids: list[str] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=500)


@app.post('/api/v1/corrections')
async def api_submit_correction(request: CorrectionRequest, context: APIRequestContext = Depends(_read_context)) -> dict:
    client = FalkorDBClient(settings=settings)
    store = CorrectionStore(client=client)
    try:
        correction = store.submit_correction(
            correction_type=request.correction_type,
            title=request.title,
            content=request.content,
            context=context,
            target_node_id=request.target_node_id,
            priority=request.priority,
            source=request.source,
            transcript_ref=request.transcript_ref,
            transcript_excerpt=request.transcript_excerpt,
        )
        return _with_context({'ok': True, 'correction': correction}, context)
    finally:
        client.close()


@app.get('/api/v1/corrections')
async def api_list_corrections(
    status: str | None = Query(None),
    correction_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    context: APIRequestContext = Depends(_read_context),
) -> dict:
    client = FalkorDBClient(settings=settings)
    store = CorrectionStore(client=client)
    try:
        engineer_filter = None if context.role == 'admin' else context.engineer_id
        corrections = store.list_corrections(
            status=status,
            correction_type=correction_type,
            engineer_id=engineer_filter,
            limit=limit,
        )
        return _with_context({'ok': True, 'corrections': corrections, 'count': len(corrections)}, context)
    finally:
        client.close()


@app.post('/admin/corrections/{correction_id}/review')
async def admin_review_correction(
    correction_id: str,
    request: CorrectionReviewRequest,
    context: APIRequestContext = Depends(_admin_context),
) -> dict:
    client = FalkorDBClient(settings=settings)
    store = CorrectionStore(client=client)
    try:
        result = store.review_correction(
            correction_id,
            decision=request.decision,
            context=context,
            resolution_note=request.resolution_note,
            publish_practical_note=request.publish_practical_note,
            federate=request.federate,
        )
        return _with_context({'ok': True, **result}, context)
    finally:
        client.close()


@app.get('/api/v1/practical-notes')
async def api_list_practical_notes(
    note_type: str | None = Query(None),
    federated_only: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    context: APIRequestContext = Depends(_read_context),
) -> dict:
    client = FalkorDBClient(settings=settings)
    store = CorrectionStore(client=client)
    try:
        notes = store.list_practical_notes(note_type=note_type, federated_only=federated_only, limit=limit)
        return _with_context({'ok': True, 'notes': notes, 'count': len(notes)}, context)
    finally:
        client.close()


@app.post('/admin/practical-notes')
async def admin_create_practical_note(
    request: PracticalNoteRequest,
    context: APIRequestContext = Depends(_admin_context),
) -> dict:
    client = FalkorDBClient(settings=settings)
    store = CorrectionStore(client=client)
    try:
        note = store.create_practical_note(
            note_type=request.note_type,
            title=request.title,
            content=request.content,
            context=context,
            target_node_id=request.target_node_id,
            transcript_ref=request.transcript_ref,
            transcript_excerpt=request.transcript_excerpt,
            approved_by=context.engineer_id,
            federate=request.federate,
        )
        return _with_context({'ok': True, 'note': note}, context)
    finally:
        client.close()


@app.post('/admin/federation/export')
async def admin_export_federation(
    request: FederationExportRequest,
    context: APIRequestContext = Depends(_admin_context),
) -> dict:
    client = FalkorDBClient(settings=settings)
    store = CorrectionStore(client=client)
    try:
        payload = store.export_federated_notes(note_ids=request.note_ids or None, limit=request.limit)
        return _with_context(payload, context)
    finally:
        client.close()
