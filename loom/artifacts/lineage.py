from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from graph.client import FalkorDBClient
from graph.identities import id_artifact, id_artifact_revision


@dataclass(frozen=True)
class ArtifactRevisionLink:
    artifact_type: str
    artifact_path: str
    objective_id: str | None
    session_id: str | None


class ArtifactLineageStore:
    def __init__(self, client: FalkorDBClient | None = None) -> None:
        self.client = client or FalkorDBClient()

    def record_revision(
        self,
        *,
        artifact_type: str,
        artifact_path: str,
        content: str,
        objective_id: str | None,
        session_id: str | None,
        engineer_id: str | None,
        prompt: str,
        operation: str,
        request_context: dict[str, Any],
        citations: list[dict[str, Any]],
        supporting_node_ids: list[str],
        steering_paths: list[str],
        unresolved_items: list[str],
        traceability_ok: bool,
        change_request: str | None = None,
    ) -> dict[str, Any]:
        graph = self.client.select_graph()
        artifact_id = id_artifact(artifact_type, artifact_path)
        rows = graph.query(
            'MATCH (a:Artifact {id: $artifact_id})-[:HAS_REVISION]->(r:ArtifactRevision) '
            'RETURN coalesce(max(r.revision_number), 0), '
            '       head([rev IN collect(r) | rev.id])',
            params={'artifact_id': artifact_id},
        ).result_set
        last_revision_number = int(rows[0][0]) if rows else 0
        previous_revision_id = rows[0][1] if rows and rows[0][1] is not None else None
        revision_number = last_revision_number + 1
        revision_key = f'{artifact_path}:{revision_number}'
        revision_id = id_artifact_revision(artifact_type, revision_key)
        created_at = datetime.now(timezone.utc).isoformat()
        content_sha = hashlib.sha256(content.encode('utf-8')).hexdigest()

        graph.query(
            'MERGE (a:Artifact {id: $artifact_id}) '
            'SET a.artifact_type = $artifact_type, '
            '    a.path = $artifact_path, '
            '    a.objective_id = $objective_id',
            params={
                'artifact_id': artifact_id,
                'artifact_type': artifact_type,
                'artifact_path': artifact_path,
                'objective_id': objective_id,
            },
        )
        graph.query(
            'MERGE (r:ArtifactRevision {id: $revision_id}) '
            'SET r.revision_id = $revision_id, '
            '    r.artifact_id = $artifact_id, '
            '    r.revision_number = $revision_number, '
            '    r.session_id = $session_id, '
            '    r.engineer_id = $engineer_id, '
            '    r.objective_id = $objective_id, '
            '    r.artifact_type = $artifact_type, '
            '    r.path = $artifact_path, '
            '    r.prompt = $prompt, '
            '    r.operation = $operation, '
            '    r.change_request = $change_request, '
            '    r.created_at = $created_at, '
            '    r.content_sha256 = $content_sha256, '
            '    r.content_preview = $content_preview, '
            '    r.traceability_ok = $traceability_ok, '
            '    r.citation_count = $citation_count, '
            '    r.request_context_json = $request_context_json, '
            '    r.citations_json = $citations_json, '
            '    r.steering_paths_json = $steering_paths_json, '
            '    r.unresolved_items_json = $unresolved_items_json',
            params={
                'revision_id': revision_id,
                'artifact_id': artifact_id,
                'revision_number': revision_number,
                'session_id': session_id,
                'engineer_id': engineer_id,
                'objective_id': objective_id,
                'artifact_type': artifact_type,
                'artifact_path': artifact_path,
                'prompt': prompt,
                'operation': operation,
                'change_request': change_request,
                'created_at': created_at,
                'content_sha256': content_sha,
                'content_preview': content[:4000],
                'traceability_ok': traceability_ok,
                'citation_count': len(citations),
                'request_context_json': json.dumps(request_context),
                'citations_json': json.dumps(citations),
                'steering_paths_json': json.dumps(steering_paths),
                'unresolved_items_json': json.dumps(unresolved_items),
            },
        )
        graph.query(
            'MATCH (a:Artifact {id: $artifact_id}), (r:ArtifactRevision {id: $revision_id}) '
            'MERGE (a)-[:HAS_REVISION]->(r)',
            params={'artifact_id': artifact_id, 'revision_id': revision_id},
        )
        if previous_revision_id:
            graph.query(
                'MATCH (prev:ArtifactRevision {id: $prev}), (curr:ArtifactRevision {id: $curr}) '
                'MERGE (curr)-[:REVISED_FROM]->(prev)',
                params={'prev': previous_revision_id, 'curr': revision_id},
            )
        for node_id in supporting_node_ids:
            graph.query(
                'MATCH (r:ArtifactRevision {id: $revision_id}), (n {id: $node_id}) '
                'MERGE (r)-[:SUPPORTED_BY]->(n)',
                params={'revision_id': revision_id, 'node_id': node_id},
            )

        return {
            'artifact_id': artifact_id,
            'revision_id': revision_id,
            'revision_number': revision_number,
            'previous_revision_id': previous_revision_id,
            'created_at': created_at,
            'citation_count': len(citations),
            'traceability_ok': traceability_ok,
            'unresolved_items': unresolved_items,
        }

    def get_audit(self, *, artifact_type: str, artifact_path: str) -> dict[str, Any]:
        artifact_id = id_artifact(artifact_type, artifact_path)
        graph = self.client.select_graph()
        artifact_rows = graph.query(
            'MATCH (a:Artifact {id: $artifact_id}) RETURN properties(a) LIMIT 1',
            params={'artifact_id': artifact_id},
        ).result_set
        if not artifact_rows:
            return {'found': False, 'artifact': None, 'revisions': []}
        revision_rows = graph.query(
            'MATCH (a:Artifact {id: $artifact_id})-[:HAS_REVISION]->(r:ArtifactRevision) '
            'OPTIONAL MATCH (r)-[:REVISED_FROM]->(prev:ArtifactRevision) '
            'RETURN properties(r), prev.id '
            'ORDER BY r.revision_number DESC',
            params={'artifact_id': artifact_id},
        ).result_set
        revisions: list[dict[str, Any]] = []
        for revision_props, previous_revision_id in revision_rows:
            revision = dict(revision_props)
            revision['previous_revision_id'] = previous_revision_id
            revision['supported_by'] = [
                {
                    'id': node_id,
                    'labels': list(labels),
                    'properties': dict(props),
                }
                for node_id, labels, props in graph.query(
                    'MATCH (r:ArtifactRevision {id: $revision_id})-[:SUPPORTED_BY]->(n) '
                    'RETURN n.id, labels(n), properties(n)',
                    params={'revision_id': revision['id']},
                ).result_set
            ]
            revisions.append(revision)
        return {'found': True, 'artifact': dict(artifact_rows[0][0]), 'revisions': revisions}
