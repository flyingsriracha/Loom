from __future__ import annotations

from collections import Counter
from typing import Any

from common.auth import APIRequestContext
from common.langsmith_support import traceable
from common.settings import Settings, load_settings
from orchestrator.audit import OrchestratorAuditLogger
from orchestrator.clients import AMSClient, CMMClient, LoomServiceClient
from orchestrator.models import OrchestratorError, OrchestratorResponse
from orchestrator.portal_links import build_integration_links
from orchestrator.workflow import OrchestratorWorkflow

_SKIP_ACTIONS = {'dashboard_overview', 'dashboard_journey', 'integration_links'}


class PortalAggregationService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        loom_client: LoomServiceClient | None = None,
        cmm_client: CMMClient | None = None,
        ams_client: AMSClient | None = None,
        audit_logger: OrchestratorAuditLogger | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.loom = loom_client or LoomServiceClient(settings=self.settings)
        self.cmm = cmm_client or CMMClient(settings=self.settings)
        self.ams = ams_client or AMSClient(settings=self.settings)
        self.audit_logger = audit_logger or OrchestratorAuditLogger()

    @traceable(name='PortalAggregationService.trace_explain', run_type='chain')
    def trace_explain(
        self,
        *,
        query: str,
        context: APIRequestContext,
        artifact_type: str | None = None,
        include_change_impact: bool = False,
        change_scope: str = 'working_tree',
        change_depth: int = 2,
        orchestrator_base_url: str | None = None,
    ) -> dict[str, Any]:
        response = OrchestratorWorkflow(loom_client=self.loom, cmm_client=self.cmm, ams_client=self.ams).run(
            query=query,
            context=context,
            artifact_type=artifact_type,
        )
        extra_change_impact = self._safe_change_impact(scope=change_scope, depth=change_depth) if include_change_impact else None
        availability = self._availability(response, extra_change_impact)
        node_id = self._first_node_id(response)
        transcript_ref = self._first_transcript_ref(response.memory)
        code_trace = self._code_trace(response.code)
        if extra_change_impact is not None:
            code_trace.append({'kind': 'change_impact', 'payload': extra_change_impact})
        return {
            'ok': response.ok,
            'route': response.route,
            'status': response.status,
            'answer_summary': response.summary,
            'request_context': response.request_context,
            'classification': response.classification,
            'knowledge_trace': self._knowledge_trace(response.knowledge),
            'memory_trace': self._memory_trace(response.memory),
            'code_trace': code_trace,
            'workflow_trace': self._workflow_trace(response, availability, extra_change_impact is not None),
            'audit': {'source_audit_id': response.audit_id},
            'citations': response.citations,
            'warnings': response.warnings,
            'deep_links': build_integration_links(
                self.settings,
                context=context,
                query=query,
                node_id=node_id,
                transcript_ref=transcript_ref,
                orchestrator_base_url=orchestrator_base_url,
            ),
            'availability': availability,
        }

    @traceable(name='PortalAggregationService.dashboard_overview', run_type='chain')
    def dashboard_overview(
        self,
        *,
        context: APIRequestContext,
        audit_limit: int = 25,
        change_scope: str = 'working_tree',
        change_depth: int = 2,
        orchestrator_base_url: str | None = None,
    ) -> dict[str, Any]:
        diagnostics = self._safe_diagnostics(context)
        resume = self.ams.resume(context=context, token_budget=1200)
        change_impact = self._safe_change_impact(scope=change_scope, depth=change_depth)
        records = self.audit_logger.list_records(
            limit=max(audit_limit * 2, audit_limit),
            engineer_id=context.engineer_id,
            project_id=context.project_id,
            objective_id=context.objective_id,
            session_id=context.session_id,
        )
        events = [event for event in (self._record_to_event(record) for record in records) if event][:audit_limit]
        counts = Counter(event['event_type'] for event in events)
        progress = self._progress_counts(records, events)
        return {
            'ok': True,
            'request_context': context.to_dict(),
            'objective': {
                'summary': ((resume.get('result') or {}).get('summary')),
                'sections': ((resume.get('result') or {}).get('sections') or {}),
                'warnings': resume.get('warnings', []),
                'token_budget': resume.get('token_budget'),
                'available': resume.get('available', False),
            },
            'services': {
                'loom': diagnostics,
                'ams': self.ams.status(),
                'cmm': self.cmm.status(),
            },
            'progress': {
                'recent_event_count': len(events),
                'knowledge_queries': progress['knowledge_queries'],
                'memory_events': progress['memory_events'],
                'artifact_revisions': progress['artifact_revisions'],
                'code_events': progress['code_events'],
                'hitl_checkpoints': progress['hitl_checkpoints'],
            },
            'recent_events': events[:5],
            'change_impact': change_impact,
            'deep_links': build_integration_links(self.settings, context=context, orchestrator_base_url=orchestrator_base_url),
        }

    @traceable(name='PortalAggregationService.dashboard_journey', run_type='chain')
    def dashboard_journey(self, *, context: APIRequestContext, limit: int = 50) -> dict[str, Any]:
        records = self.audit_logger.list_records(
            limit=limit + len(_SKIP_ACTIONS),
            engineer_id=context.engineer_id,
            project_id=context.project_id,
            objective_id=context.objective_id,
            session_id=context.session_id,
        )
        events = [event for event in (self._record_to_event(record) for record in records) if event][:limit]
        return {
            'ok': True,
            'request_context': context.to_dict(),
            'events': events,
            'counts': dict(Counter(event['event_type'] for event in events)),
        }

    @traceable(name='PortalAggregationService.integration_links', run_type='chain')
    def integration_links(
        self,
        *,
        context: APIRequestContext,
        query: str | None = None,
        node_id: str | None = None,
        audit_id: str | None = None,
        transcript_ref: str | None = None,
        orchestrator_base_url: str | None = None,
    ) -> dict[str, Any]:
        return {
            'ok': True,
            'request_context': context.to_dict(),
            'links': build_integration_links(
                self.settings,
                context=context,
                query=query,
                node_id=node_id,
                audit_id=audit_id,
                transcript_ref=transcript_ref,
                orchestrator_base_url=orchestrator_base_url,
            ),
        }

    def _safe_diagnostics(self, context: APIRequestContext) -> dict[str, Any]:
        try:
            return self.loom.diagnostics(context=context)
        except OrchestratorError as exc:
            return {'ok': False, 'error': exc.to_dict()['error']}

    def _safe_change_impact(self, *, scope: str, depth: int) -> dict[str, Any]:
        try:
            return {'ok': True, 'impact': self.cmm.detect_changes(scope=scope, depth=depth)}
        except OrchestratorError as exc:
            return {'ok': False, 'error': exc.to_dict()['error']}

    def _availability(self, response: OrchestratorResponse, extra_change_impact: dict[str, Any] | None) -> dict[str, str]:
        classification = response.classification
        return {
            'knowledge': 'used' if response.knowledge else ('not_used' if not classification.get('consult_loom') else 'unavailable'),
            'memory': 'used' if response.memory else ('not_used' if not classification.get('consult_memory') else 'unavailable'),
            'code': 'used' if (response.code or extra_change_impact) else ('not_used' if not classification.get('consult_cmm') else 'unavailable'),
            'workflow': 'used',
        }

    def _knowledge_trace(self, payload: dict[str, Any] | None) -> list[dict[str, Any]]:
        results = (payload or {}).get('results', [])
        return [
            {
                'id': item.get('id'),
                'labels': item.get('labels', []),
                'summary': item.get('snippet') or item.get('summary') or (item.get('properties') or {}).get('name'),
                'candidate_type': item.get('candidate_type'),
                'evidence': item.get('evidence_chain') or item.get('provenance_preview') or [],
            }
            for item in results[:8]
        ]

    def _memory_trace(self, payload: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not payload:
            return []
        result = payload.get('result') or {}
        if result.get('sections'):
            return [{'kind': 'resume_section', 'name': name, 'items': items} for name, items in result.get('sections', {}).items()]
        return [
            {'kind': 'recall_result', 'text': record.get('text'), 'metadata': record.get('metadata', {})}
            for record in result.get('results', [])[:8]
            if isinstance(record, dict)
        ]

    def _code_trace(self, payload: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not payload:
            return []
        if 'search' in payload:
            return [
                {'kind': 'code_search', 'payload': payload.get('search')},
                {'kind': 'architecture', 'payload': payload.get('architecture')},
                {'kind': 'status', 'payload': payload.get('status')},
            ]
        return [{'kind': 'code_payload', 'payload': payload}]

    def _workflow_trace(self, response: OrchestratorResponse, availability: dict[str, str], has_extra_change_impact: bool) -> list[dict[str, Any]]:
        return [
            {'step': 'classify', 'status': 'used', 'details': response.classification},
            {'step': 'knowledge', 'status': availability['knowledge'], 'count': len((response.knowledge or {}).get('results', []))},
            {'step': 'memory', 'status': availability['memory'], 'mode': 'resume' if (response.memory or {}).get('resume_query') else 'recall'},
            {'step': 'code', 'status': availability['code'], 'has_extra_change_impact': has_extra_change_impact},
            {'step': 'verify', 'status': response.status, 'warnings': response.warnings},
        ]

    def _progress_counts(self, records: list[dict[str, Any]], events: list[dict[str, Any]]) -> dict[str, int]:
        counts = {
            'knowledge_queries': 0,
            'memory_events': 0,
            'artifact_revisions': 0,
            'code_events': 0,
            'hitl_checkpoints': 0,
        }
        for record in records:
            action = record.get('action')
            result = record.get('result') or {}
            availability = result.get('availability') or {}
            code_trace = result.get('code_trace') or []
            if action in {'search_knowledge', 'ask', 'trace_explain'}:
                counts['knowledge_queries'] += 1
            if action in {'memory_retain', 'memory_recall', 'memory_reflect', 'resume_session'}:
                counts['memory_events'] += 1
            elif action == 'trace_explain' and availability.get('memory') == 'used':
                counts['memory_events'] += 1
            if action in {'generate_spec_artifact', 'update_spec_artifact', 'audit_spec_artifact'}:
                counts['artifact_revisions'] += 1
            if action in {'search_code', 'search_code_impact'}:
                counts['code_events'] += 1
            elif action == 'trace_explain' and any((item or {}).get('kind') == 'change_impact' for item in code_trace):
                counts['code_events'] += 1
            if result.get('status') == 'needs_human':
                counts['hitl_checkpoints'] += 1
        return counts

    def _record_to_event(self, record: dict[str, Any]) -> dict[str, Any] | None:
        action = record.get('action')
        if action in _SKIP_ACTIONS:
            return None
        event_type = {
            'resume_session': 'session_resumed',
            'search_knowledge': 'knowledge_query',
            'ask': 'knowledge_query',
            'trace_explain': 'knowledge_query',
            'memory_retain': 'memory_retain',
            'memory_recall': 'memory_recall',
            'memory_reflect': 'memory_reflect',
            'search_code': 'code_impact',
            'search_code_impact': 'code_impact',
            'generate_spec_artifact': 'artifact_revision',
            'update_spec_artifact': 'artifact_revision',
            'audit_spec_artifact': 'artifact_revision',
            'export_audit_log': 'audit_export',
        }.get(action)
        if not event_type:
            return None
        ctx = record.get('request_context') or {}
        result = record.get('result') or {}
        summary = result.get('summary') or result.get('detail') or result.get('operation') or action.replace('_', ' ')
        if result.get('status') == 'needs_human':
            event_type = 'hitl_checkpoint'
        related_ids = {'audit_id': record.get('audit_id')}
        revision = result.get('revision') or {}
        if revision.get('revision_id'):
            related_ids['artifact_revision_id'] = revision['revision_id']
        if ctx.get('project_id'):
            related_ids['project_id'] = ctx['project_id']
        if ctx.get('objective_id'):
            related_ids['objective_id'] = ctx['objective_id']
        if ctx.get('session_id'):
            related_ids['session_id'] = ctx['session_id']
        return {
            'event_id': record.get('audit_id'),
            'event_type': event_type,
            'timestamp': record.get('timestamp'),
            'engineer_id': ctx.get('engineer_id'),
            'project_id': ctx.get('project_id'),
            'objective_id': ctx.get('objective_id'),
            'session_id': ctx.get('session_id'),
            'audit_id': record.get('audit_id'),
            'title': action.replace('_', ' ').title(),
            'summary': str(summary),
            'related_ids': {key: value for key, value in related_ids.items() if value},
        }

    def _first_node_id(self, response: OrchestratorResponse) -> str | None:
        results = (response.knowledge or {}).get('results', [])
        for item in results:
            if item.get('id'):
                return str(item['id'])
        return None

    def _first_transcript_ref(self, memory_payload: dict[str, Any] | None) -> str | None:
        result = (memory_payload or {}).get('result') or {}
        for record in result.get('results', []):
            metadata = (record or {}).get('metadata') or {}
            if metadata.get('transcript_ref'):
                return str(metadata['transcript_ref'])
        return None
