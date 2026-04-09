from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from common.auth import APIRequestContext
from orchestrator.classifier import classify_request
from orchestrator.clients import AMSClient, CMMClient, LoomServiceClient
from orchestrator.models import ClassificationResult, OrchestratorError, OrchestratorResponse
from orchestrator.spec_session import fallback_queries

_RESUME_QUERY_TERMS = (
    'resume',
    'where did we leave off',
    'pick up where',
    'continue this objective',
    'continue from last session',
)


class WorkflowState(TypedDict, total=False):
    query: str
    artifact_type: str | None
    context: APIRequestContext
    classification: ClassificationResult
    knowledge: dict[str, Any]
    memory: dict[str, Any]
    code: dict[str, Any]
    warnings: list[str]
    status: str
    summary: str
    citations: list[dict[str, Any]]


class OrchestratorWorkflow:
    def __init__(
        self,
        *,
        loom_client: LoomServiceClient | None = None,
        cmm_client: CMMClient | None = None,
        ams_client: AMSClient | None = None,
    ) -> None:
        self.loom = loom_client or LoomServiceClient()
        self.cmm = cmm_client or CMMClient()
        self.ams = ams_client or AMSClient()
        self.graph = self._build_graph().compile()

    def run(self, *, query: str, context: APIRequestContext, artifact_type: str | None = None) -> OrchestratorResponse:
        initial: WorkflowState = {
            'query': query,
            'artifact_type': artifact_type,
            'context': context,
            'warnings': [],
            'status': 'running',
            'citations': [],
        }
        state = self.graph.invoke(initial)
        classification = state['classification']
        return OrchestratorResponse(
            ok=state.get('status') not in {'error'},
            route=classification.route,
            status=state.get('status', 'ok'),
            summary=state.get('summary', ''),
            request_context=context.to_dict(),
            classification=classification.to_dict(),
            knowledge=state.get('knowledge'),
            memory=state.get('memory'),
            code=state.get('code'),
            warnings=state.get('warnings', []),
            citations=state.get('citations', []),
        )

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(WorkflowState)
        graph.add_node('classify', self._classify)
        graph.add_node('research', self._research)
        graph.add_node('memory', self._memory)
        graph.add_node('code', self._code)
        graph.add_node('draft', self._draft)
        graph.add_node('verify', self._verify)
        graph.add_edge(START, 'classify')
        graph.add_conditional_edges('classify', self._next_after_classify)
        graph.add_conditional_edges('research', self._next_after_research)
        graph.add_conditional_edges('memory', self._next_after_memory)
        graph.add_edge('code', 'draft')
        graph.add_edge('draft', 'verify')
        graph.add_edge('verify', END)
        return graph

    def _classify(self, state: WorkflowState) -> WorkflowState:
        classification = classify_request(state['query'], artifact_type=state.get('artifact_type'))
        return {'classification': classification}

    def _next_after_classify(self, state: WorkflowState) -> str:
        route = state['classification'].route
        if route in {'domain', 'coding_task', 'spec_session'}:
            return 'research'
        if route == 'memory':
            return 'memory'
        if route == 'code':
            return 'code'
        return 'draft'

    def _research(self, state: WorkflowState) -> WorkflowState:
        classification = state['classification']
        context = state['context']
        query = state['query']
        warnings = list(state.get('warnings', []))
        if classification.route == 'spec_session':
            artifact_type = classification.artifact_type or state.get('artifact_type') or 'design'
            knowledge = self.loom.artifact_context(query, artifact_type, context=context)
            if knowledge.get('no_results') is True or not knowledge.get('results'):
                for fallback in fallback_queries(query):
                    knowledge = self.loom.search(fallback, context=context)
                    if knowledge.get('results'):
                        warnings.append(f'artifact_context_fell_back_to_search:{fallback}')
                        break
        else:
            knowledge = self.loom.query(query, context=context)
            if knowledge.get('no_results') is True or not knowledge.get('results'):
                for fallback in fallback_queries(query):
                    knowledge = self.loom.search(fallback, context=context)
                    if knowledge.get('results'):
                        warnings.append(f'query_fell_back_to_search:{fallback}')
                        break
        return {'knowledge': knowledge, 'warnings': warnings}

    def _next_after_research(self, state: WorkflowState) -> str:
        if state['classification'].consult_memory:
            return 'memory'
        if state['classification'].consult_cmm:
            return 'code'
        return 'draft'

    def _should_use_resume_context(self, state: WorkflowState) -> bool:
        route = state['classification'].route
        query = state['query'].strip().lower()
        if route in {'coding_task', 'spec_session'}:
            return True
        return any(term in query for term in _RESUME_QUERY_TERMS)

    def _memory(self, state: WorkflowState) -> WorkflowState:
        if self._should_use_resume_context(state):
            memory = self.ams.resume(context=state['context'])
        else:
            memory = self.ams.recall(state['query'], context=state['context'])
        return {'memory': memory}

    def _next_after_memory(self, state: WorkflowState) -> str:
        if state['classification'].consult_cmm:
            return 'code'
        return 'draft'

    def _code(self, state: WorkflowState) -> WorkflowState:
        query = state['query']
        lower = query.lower()
        try:
            if 'what calls' in lower or 'who calls' in lower or 'call path' in lower or 'trace' in lower:
                target = self._extract_symbol(query)
                code = self.cmm.trace_call_path(target) if target else self.cmm.search_code(query)
            elif state['classification'].route == 'coding_task':
                code = {
                    'search': self.cmm.search_code(query),
                    'architecture': self.cmm.get_architecture(),
                    'status': self.cmm.status(),
                }
                if any(term in lower for term in ('change', 'update', 'fix', 'refactor', 'modify')):
                    code['change_impact'] = self.cmm.detect_changes(scope='working_tree', depth=3)
            else:
                code = self.cmm.search_code(query)
            return {'code': code}
        except OrchestratorError as exc:
            warnings = list(state.get('warnings', []))
            warnings.append(f'cmm_unavailable:{exc.code}')
            return {'code': {'ok': False, 'error': exc.to_dict()['error']}, 'warnings': warnings}

    def _draft(self, state: WorkflowState) -> WorkflowState:
        classification = state['classification']
        route = classification.route
        warnings = list(state.get('warnings', []))
        knowledge = state.get('knowledge') or {}
        memory = state.get('memory') or {}
        citations = self._citations_from_knowledge(knowledge)

        if route == 'domain':
            summary = 'Standards-grounded response prepared from Loom retrieval.'
        elif route == 'coding_task':
            summary = 'Coding-task guidance assembled from Loom research, AMS resumption context, and CMM code/change-impact context.'
        elif route == 'spec_session':
            summary = 'Spec-session context package assembled with standards citations, AMS resumption context, and artifact guidance.'
        elif route == 'code':
            summary = 'Code-structure context prepared from CMM.'
        elif route == 'memory':
            summary = 'Memory/status response prepared from AMS continuity context.'
        else:
            summary = 'No specialized route matched; returning guarded general response.'
            warnings.append('general_route_no_specialized_grounding')

        if memory and not memory.get('available', True):
            warnings.append('memory_unavailable_phase2_pending')

        return {
            'summary': summary,
            'warnings': list(dict.fromkeys(warnings)),
            'citations': citations,
        }

    def _verify(self, state: WorkflowState) -> WorkflowState:
        classification = state['classification']
        route = classification.route
        knowledge = state.get('knowledge') or {}
        code = state.get('code') or {}
        warnings = list(state.get('warnings', []))
        status = 'ok'

        if route in {'domain', 'coding_task', 'spec_session'}:
            if knowledge.get('no_results') is True or not knowledge.get('results'):
                warnings.append('needs_human:research_zero_results')
                status = 'needs_human'

        if route == 'coding_task':
            code_ok = code and ('results' in code or 'search' in code or code.get('ok') is True)
            if not code_ok:
                warnings.append('needs_human:cmm_context_missing')
                status = 'needs_human'

        if route == 'spec_session' and not state.get('artifact_type'):
            warnings.append('spec_session_defaulted_artifact_type')

        return {'status': status, 'warnings': list(dict.fromkeys(warnings))}

    def _citations_from_knowledge(self, knowledge: dict[str, Any]) -> list[dict[str, Any]]:
        citations: list[dict[str, Any]] = []
        for item in knowledge.get('results', [])[:5]:
            evidence_list = item.get('evidence_chain') or item.get('provenance_preview') or []
            for evidence in evidence_list[:3]:
                citations.append(evidence)
        return citations

    def _extract_symbol(self, query: str) -> str | None:
        strip_chars = " `\"'"
        tokens = [token.strip(strip_chars) for token in query.split() if token.strip(strip_chars)]
        if not tokens:
            return None
        return tokens[-1]
