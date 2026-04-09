from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Literal

from common.auth import APIRequestContext
from graph.client import FalkorDBClient
from graph.identities import (
    id_correction_item,
    id_practical_note,
    id_source_document,
    id_source_pipeline,
    id_source_system,
)
from retrieval.embeddings import encode_text

CorrectionType = Literal['data_quality', 'retrieval_quality', 'practical_knowledge']
ReviewDecision = Literal['approved', 'rejected']

AMS_SOURCE_SYSTEM = 'loom_ams'
AMS_SOURCE_PIPELINE = 'ams_promotion'
FEDERATION_EXPORT_PATH = Path(__file__).resolve().parents[1] / 'artifacts' / 'federation_export.json'


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(text: str, limit: int = 240) -> str:
    compact = ' '.join(text.split())
    if len(compact) <= limit:
        return compact
    clipped = compact[: max(limit - 3, 1)].rsplit(' ', 1)[0].strip()
    return f'{clipped or compact[: max(limit - 3, 1)]}...'


def _clean_props(values: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in values.items():
        if value is None:
            continue
        cleaned[key] = value
    return cleaned


class CorrectionStore:
    def __init__(self, client: FalkorDBClient | None = None) -> None:
        self.client = client or FalkorDBClient()

    def submit_correction(
        self,
        *,
        correction_type: CorrectionType,
        title: str,
        content: str,
        context: APIRequestContext,
        target_node_id: str | None = None,
        priority: str = 'medium',
        source: str = 'manual',
        transcript_ref: str | None = None,
        transcript_excerpt: str | None = None,
    ) -> dict[str, Any]:
        created_at = _utcnow()
        correction_id = id_correction_item(
            context.engineer_id or 'anon',
            context.objective_id or context.project_id or 'global',
            title,
            created_at,
        )
        props = {
            'id': correction_id,
            'title': title,
            'content': content,
            'summary': _truncate(content, 220),
            'correction_type': correction_type,
            'priority': priority,
            'source': source,
            'status': 'submitted',
            'created_at': created_at,
            'engineer_id': context.engineer_id,
            'project_id': context.project_id,
            'session_id': context.session_id,
            'objective_id': context.objective_id,
            'target_node_id': target_node_id,
            'transcript_ref': transcript_ref,
            'transcript_excerpt': _truncate(transcript_excerpt, 220) if transcript_excerpt else None,
            'mapping_category': 'audit',
            'reviewed_at': None,
            'reviewed_by': None,
            'resolution_note': None,
            'practical_note_id': None,
            'federated': False,
            'federated_at': None,
        }
        self.client.query(
            'CREATE (c:CorrectionItem) '
            'SET c += $props '
            'WITH c '
            'OPTIONAL MATCH (t {id: $target_node_id}) '
            'FOREACH (_ IN CASE WHEN t IS NULL THEN [] ELSE [1] END | MERGE (c)-[:TARGETS]->(t))',
            params={'props': _clean_props(props), 'target_node_id': target_node_id},
        )
        return props

    def list_corrections(
        self,
        *,
        status: str | None = None,
        correction_type: str | None = None,
        engineer_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        rows = self.client.query(
            'MATCH (c:CorrectionItem) '
            'WHERE ($status IS NULL OR c.status = $status) '
            'AND ($correction_type IS NULL OR c.correction_type = $correction_type) '
            'AND ($engineer_id IS NULL OR c.engineer_id = $engineer_id) '
            'RETURN properties(c) ORDER BY c.created_at DESC LIMIT $limit',
            params={
                'status': status,
                'correction_type': correction_type,
                'engineer_id': engineer_id,
                'limit': limit,
            },
            read_only=True,
        ).result_set
        return [dict(props) for (props,) in rows]

    def get_correction(self, correction_id: str) -> dict[str, Any] | None:
        rows = self.client.query(
            'MATCH (c:CorrectionItem {id: $id}) RETURN properties(c) LIMIT 1',
            params={'id': correction_id},
            read_only=True,
        ).result_set
        if not rows:
            return None
        return dict(rows[0][0])

    def create_practical_note(
        self,
        *,
        note_type: str,
        title: str,
        content: str,
        context: APIRequestContext,
        correction_id: str | None = None,
        target_node_id: str | None = None,
        transcript_ref: str | None = None,
        transcript_excerpt: str | None = None,
        approved_by: str | None = None,
        federate: bool = False,
    ) -> dict[str, Any]:
        created_at = _utcnow()
        note_id = id_practical_note(title, context.project_id or context.objective_id or created_at)
        summary = _truncate(content, 220)
        document_ref = transcript_ref or correction_id or note_id
        source_system_id = id_source_system(AMS_SOURCE_SYSTEM)
        source_pipeline_id = id_source_pipeline(AMS_SOURCE_SYSTEM, AMS_SOURCE_PIPELINE)
        source_document_id = id_source_document(AMS_SOURCE_SYSTEM, document_ref)
        note_props = {
            'id': note_id,
            'title': title,
            'name': title,
            'note_type': note_type,
            'content': content,
            'summary': summary,
            'description': summary,
            'engineer_id': context.engineer_id,
            'project_id': context.project_id,
            'session_id': context.session_id,
            'objective_id': context.objective_id,
            'correction_id': correction_id,
            'transcript_ref': transcript_ref,
            'transcript_excerpt': _truncate(transcript_excerpt, 220) if transcript_excerpt else None,
            'approved_by': approved_by,
            'created_at': created_at,
            'federated': federate,
            'federated_at': created_at if federate else None,
            'mapping_category': 'practical',
            'embedding': encode_text(f'{title}\n\n{content}'),
        }
        doc_props = {
            'id': source_document_id,
            'source_file': document_ref,
            'filename': document_ref,
            'source_system': AMS_SOURCE_SYSTEM,
            'created_at': created_at,
        }
        pipeline_props = {
            'id': source_pipeline_id,
            'name': AMS_SOURCE_PIPELINE,
            'parent_system': AMS_SOURCE_SYSTEM,
        }
        system_props = {
            'id': source_system_id,
            'name': AMS_SOURCE_SYSTEM,
            'path': 'loom/orchestrator/ams',
            'source_kind': 'local_memory',
        }
        self.client.query(
            'MERGE (s:SourceSystem {id: $source_system_id}) SET s += $source_system '
            'MERGE (p:SourcePipeline {id: $source_pipeline_id}) SET p += $source_pipeline '
            'MERGE (d:SourceDocument {id: $source_document_id}) SET d += $source_document '
            'MERGE (p)-[:BELONGS_TO]->(s) '
            'MERGE (d)-[:EXTRACTED_BY]->(p) '
            'MERGE (d)-[:ORIGINATES_FROM]->(s) '
            'MERGE (n:PracticalNote {id: $note_id}) SET n += $note '
            'MERGE (n)-[prov:PROVENANCE]->(d) '
            'SET prov.confidence = 1.0, prov.extraction_date = $created_at, prov.source_pipeline = $source_pipeline_name '
            'WITH n '
            'OPTIONAL MATCH (t {id: $target_node_id}) '
            'FOREACH (_ IN CASE WHEN t IS NULL THEN [] ELSE [1] END | MERGE (n)-[:TARGETS]->(t))',
            params={
                'note_id': note_id,
                'note': _clean_props(note_props),
                'source_document_id': source_document_id,
                'source_document': _clean_props(doc_props),
                'source_pipeline_id': source_pipeline_id,
                'source_pipeline_name': pipeline_props['name'],
                'source_pipeline': _clean_props(pipeline_props),
                'source_system_id': source_system_id,
                'source_system': _clean_props(system_props),
                'target_node_id': target_node_id,
                'created_at': created_at,
            },
        )
        return note_props

    def list_practical_notes(
        self,
        *,
        note_type: str | None = None,
        federated_only: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        rows = self.client.query(
            'MATCH (n:PracticalNote) '
            'WHERE ($note_type IS NULL OR n.note_type = $note_type) '
            'AND ($federated_only = false OR coalesce(n.federated, false) = true) '
            'RETURN properties(n) ORDER BY n.created_at DESC LIMIT $limit',
            params={
                'note_type': note_type,
                'federated_only': federated_only,
                'limit': limit,
            },
            read_only=True,
        ).result_set
        return [dict(props) for (props,) in rows]

    def review_correction(
        self,
        correction_id: str,
        *,
        decision: ReviewDecision,
        context: APIRequestContext,
        resolution_note: str | None = None,
        publish_practical_note: bool = True,
        federate: bool = False,
    ) -> dict[str, Any]:
        correction = self.get_correction(correction_id)
        if correction is None:
            raise ValueError(f'unknown correction_id: {correction_id}')

        reviewed_at = _utcnow()
        practical_note = None
        if decision == 'approved' and publish_practical_note:
            practical_note = self.create_practical_note(
                note_type=correction['correction_type'],
                title=correction['title'],
                content=correction['content'],
                context=APIRequestContext(
                    role=context.role,
                    auth_mode=context.auth_mode,
                    engineer_id=correction.get('engineer_id'),
                    session_id=correction.get('session_id'),
                    objective_id=correction.get('objective_id'),
                    project_id=correction.get('project_id'),
                ),
                correction_id=correction_id,
                target_node_id=correction.get('target_node_id'),
                transcript_ref=correction.get('transcript_ref'),
                transcript_excerpt=correction.get('transcript_excerpt'),
                approved_by=context.engineer_id,
                federate=federate,
            )

        self.client.query(
            'MATCH (c:CorrectionItem {id: $correction_id}) '
            'SET c.status = $decision, '
            '    c.reviewed_at = $reviewed_at, '
            '    c.reviewed_by = $reviewed_by, '
            '    c.resolution_note = $resolution_note, '
            '    c.practical_note_id = $practical_note_id, '
            '    c.federated = $federated, '
            '    c.federated_at = $federated_at '
            'WITH c '
            'OPTIONAL MATCH (n:PracticalNote {id: $practical_note_id}) '
            'FOREACH (_ IN CASE WHEN n IS NULL THEN [] ELSE [1] END | MERGE (c)-[:PROMOTED_TO]->(n))',
            params={
                'correction_id': correction_id,
                'decision': decision,
                'reviewed_at': reviewed_at,
                'reviewed_by': context.engineer_id,
                'resolution_note': resolution_note,
                'practical_note_id': practical_note['id'] if practical_note else None,
                'federated': federate,
                'federated_at': reviewed_at if federate else None,
            },
        )
        updated = self.get_correction(correction_id) or {}
        return {'correction': updated, 'practical_note': practical_note}

    def export_federated_notes(
        self,
        *,
        note_ids: list[str] | None = None,
        limit: int = 100,
        output_path: Path | None = None,
    ) -> dict[str, Any]:
        notes = self.list_practical_notes(federated_only=not bool(note_ids), limit=limit)
        if note_ids:
            note_set = set(note_ids)
            notes = [note for note in notes if note.get('id') in note_set]
        export_path = output_path or FEDERATION_EXPORT_PATH
        export_payload = {
            'exported_at': _utcnow(),
            'source_system': AMS_SOURCE_SYSTEM,
            'source_pipeline': AMS_SOURCE_PIPELINE,
            'count': len(notes),
            'notes': notes,
        }
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(json.dumps(export_payload, indent=2))
        return {'ok': True, 'count': len(notes), 'path': str(export_path)}
