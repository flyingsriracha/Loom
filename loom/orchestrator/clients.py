from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Literal

import httpx
from hindsight_client import Hindsight

from common.auth import APIRequestContext
from common.health import http_check
from common.langsmith_support import traceable
from common.settings import Settings, load_settings
from orchestrator.models import OrchestratorError
from orchestrator.resume_context import DEFAULT_RESUME_TOKEN_BUDGET, allocate_token_budget, build_resume_snapshot
from orchestrator.seed_context import build_seed_bundle

TagMatch = Literal['any', 'all', 'any_strict', 'all_strict']


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / '.kiro').exists():
            return candidate
    return Path(__file__).resolve().parents[1]


def _running_in_container() -> bool:
    return Path('/.dockerenv').exists()


def _truncate(text: str, limit: int = 240) -> str:
    compact = ' '.join(text.split())
    if len(compact) <= limit:
        return compact
    clipped = compact[: max(limit - 3, 1)].rsplit(' ', 1)[0].strip()
    return f'{clipped or compact[: max(limit - 3, 1)]}...'


class LoomServiceClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()

    def _headers(self, context: APIRequestContext) -> dict[str, str]:
        headers = {'Content-Type': 'application/json'}
        api_key = self.settings.loom_admin_api_key or self.settings.loom_api_key
        if api_key:
            headers['X-API-Key'] = api_key
        if context.engineer_id:
            headers['X-Engineer-Id'] = context.engineer_id
        if context.session_id:
            headers['X-Session-Id'] = context.session_id
        if context.objective_id:
            headers['X-Objective-Id'] = context.objective_id
        if context.project_id:
            headers['X-Project-Id'] = context.project_id
        return headers

    def post(self, path: str, payload: dict[str, Any], *, context: APIRequestContext) -> dict[str, Any]:
        try:
            with httpx.Client(base_url=self.settings.loom_service_url, timeout=60.0) as client:
                response = client.post(path, json=payload, headers=self._headers(context))
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            raise OrchestratorError('loom_request_failed', f'Loom service call failed for {path}', 502, {'path': path, 'error': str(exc)})

    @traceable(name='LoomServiceClient.query', run_type='tool')
    def query(self, query: str, *, context: APIRequestContext) -> dict[str, Any]:
        return self.post('/api/v1/query', {'query': query, 'limit': 5}, context=context)

    @traceable(name='LoomServiceClient.search', run_type='tool')
    def search(self, query: str, *, context: APIRequestContext) -> dict[str, Any]:
        return self.post('/api/v1/search', {'query': query, 'limit': 10}, context=context)

    @traceable(name='LoomServiceClient.artifact_context', run_type='tool')
    def artifact_context(self, query: str, artifact_type: str, *, context: APIRequestContext) -> dict[str, Any]:
        return self.post('/api/v1/artifact/context', {'query': query, 'artifact_type': artifact_type, 'limit': 5}, context=context)

    @traceable(name='LoomServiceClient.diagnostics', run_type='tool')
    def diagnostics(self, *, context: APIRequestContext) -> dict[str, Any]:
        try:
            with httpx.Client(base_url=self.settings.loom_service_url, timeout=30.0) as client:
                response = client.get('/api/v1/diagnostics', headers=self._headers(context))
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            raise OrchestratorError('loom_diagnostics_failed', 'Unable to fetch Loom diagnostics', 502, {'error': str(exc)})

    @traceable(name='LoomServiceClient.submit_correction', run_type='tool')
    def submit_correction(self, payload: dict[str, Any], *, context: APIRequestContext) -> dict[str, Any]:
        return self.post('/api/v1/corrections', payload, context=context)


class CMMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()

    def _binary(self) -> str | None:
        candidate = self.settings.cmm_binary_path
        if not candidate:
            return None
        if Path(candidate).exists() or shutil.which(candidate):
            return candidate
        return None

    def _unavailable_error(self) -> OrchestratorError:
        details = {'binary': self.settings.cmm_binary_path}
        if _running_in_container():
            details.update({
                'scope': 'host_native_only',
                'hint': 'Use host-native codebase-memory-mcp or extend the container image with a Linux binary and index state.',
            })
            return OrchestratorError(
                'cmm_host_native_only',
                'CMM is only available in the host-native environment for this container image',
                503,
                details,
            )
        return OrchestratorError('cmm_unavailable', 'CMM binary is not available in this environment', 503, details)

    def _resolve_project(self) -> str:
        if self.settings.cmm_project:
            return self.settings.cmm_project
        projects = self._run('list_projects', {})
        available = projects.get('projects', [])
        if len(available) == 1:
            return str(available[0]['name'])
        raise OrchestratorError('cmm_project_required', 'CMM project could not be resolved automatically', 503, {'projects': available})

    def _run(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        binary = self._binary()
        if binary is None:
            raise self._unavailable_error()
        command = [binary, 'cli', tool_name, json.dumps(payload)]
        try:
            proc = subprocess.run(command, capture_output=True, text=True, check=True, timeout=60)
        except Exception as exc:
            raise OrchestratorError('cmm_call_failed', f'CMM tool {tool_name} failed', 502, {'tool': tool_name, 'error': str(exc)})
        return self._parse_output(proc.stdout)

    def _parse_output(self, stdout: str) -> dict[str, Any]:
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        for line in reversed(lines):
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if isinstance(payload, dict) and 'content' in payload:
                for item in payload.get('content', []):
                    if isinstance(item, dict) and item.get('type') == 'text':
                        try:
                            return json.loads(item.get('text', '{}'))
                        except Exception:
                            return {'raw_text': item.get('text')}
            if isinstance(payload, dict):
                return payload
        raise OrchestratorError('cmm_parse_failed', 'Unable to parse CMM CLI output', 502, {'stdout': stdout[-2000:]})

    @traceable(name='CMMClient.status', run_type='tool')
    def status(self) -> dict[str, Any]:
        binary = self._binary()
        if binary is None:
            exc = self._unavailable_error()
            return {'available': False, 'reason': exc.code, 'details': exc.details}
        try:
            project = self._resolve_project()
            index_status = self._run('index_status', {'project': project})
            return {'available': True, 'project': project, 'index_status': index_status}
        except OrchestratorError as exc:
            return {'available': False, 'reason': exc.code, 'details': exc.details}

    @traceable(name='CMMClient.search_code', run_type='tool')
    def search_code(self, query: str) -> dict[str, Any]:
        project = self._resolve_project()
        return self._run('search_code', {'project': project, 'pattern': query, 'mode': 'compact', 'limit': 10})

    @traceable(name='CMMClient.trace_call_path', run_type='tool')
    def trace_call_path(self, function_name: str) -> dict[str, Any]:
        project = self._resolve_project()
        return self._run('trace_call_path', {'project': project, 'function_name': function_name, 'direction': 'both', 'depth': 3})

    @traceable(name='CMMClient.get_architecture', run_type='tool')
    def get_architecture(self) -> dict[str, Any]:
        project = self._resolve_project()
        return self._run('get_architecture', {'project': project, 'aspects': ['packages', 'services', 'dependencies']})

    @traceable(name='CMMClient.detect_changes', run_type='tool')
    def detect_changes(self, *, scope: str = 'working_tree', depth: int = 2, since: str | None = None) -> dict[str, Any]:
        project = self._resolve_project()
        payload: dict[str, Any] = {
            'project': project,
            'scope': scope,
            'depth': depth,
            'base_branch': self.settings.cmm_base_branch,
        }
        if since is not None:
            payload['since'] = since
        return self._run('detect_changes', payload)


class AMSClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()

    def _base_url(self) -> str:
        return self.settings.hindsight_api_url

    def _scope_identifier(self, context: APIRequestContext) -> str:
        return context.objective_id or context.project_id or context.engineer_id or 'default'

    def _bank_id(self, context: APIRequestContext) -> str:
        if context.objective_id:
            return f'{self.settings.hindsight_bank_prefix}::objective::{context.objective_id}'
        if context.project_id:
            return f'{self.settings.hindsight_bank_prefix}::project::{context.project_id}'
        if context.engineer_id:
            return f'{self.settings.hindsight_bank_prefix}::engineer::{context.engineer_id}'
        return f'{self.settings.hindsight_bank_prefix}::default'

    def _seed_document_id(self, context: APIRequestContext) -> str:
        return f'project-seed::{self._scope_identifier(context)}'

    def _context_string(self, context: APIRequestContext) -> str:
        return ';'.join([
            f'engineer={context.engineer_id}',
            f'project={context.project_id}',
            f'session={context.session_id}',
            f'objective={context.objective_id}',
        ])

    def _client(self) -> Hindsight:
        return Hindsight(base_url=self._base_url(), api_key=self.settings.hindsight_api_key)

    def _run_coro(self, coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()

    def _close_client(self, client: Hindsight) -> None:
        if hasattr(client, 'aclose'):
            self._run_coro(client.aclose())
        elif hasattr(client, 'close'):
            client.close()

    def _serialize(self, obj: Any) -> dict[str, Any]:
        if hasattr(obj, 'model_dump'):
            return obj.model_dump()
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()
        if isinstance(obj, dict):
            return obj
        return {'raw': str(obj)}

    def _normalize_tags(self, tags: list[str] | None, *, transcript_ref: str | None = None) -> list[str] | None:
        normalized = list(dict.fromkeys(tags or []))
        if transcript_ref and 'transcript-reference' not in normalized:
            normalized.append('transcript-reference')
        return normalized or None

    def _normalize_metadata(
        self,
        context: APIRequestContext,
        metadata: dict[str, str] | None,
        *,
        transcript_ref: str | None = None,
        transcript_excerpt: str | None = None,
    ) -> dict[str, str] | None:
        normalized = dict(metadata or {})
        if context.project_id:
            normalized.setdefault('project_id', context.project_id)
        if context.session_id:
            normalized.setdefault('session_id', context.session_id)
        if context.objective_id:
            normalized.setdefault('objective_id', context.objective_id)
        if transcript_ref:
            normalized['transcript_ref'] = transcript_ref
        if transcript_excerpt:
            normalized['transcript_excerpt'] = _truncate(transcript_excerpt, 220)
        return normalized or None

    def _with_transcript_reference(self, text: str, *, transcript_ref: str | None = None, transcript_excerpt: str | None = None) -> str:
        parts = [text.strip()]
        if transcript_ref:
            parts.append(f'Transcript reference: {transcript_ref}')
        if transcript_excerpt:
            parts.append(f'Transcript excerpt: {_truncate(transcript_excerpt, 220)}')
        return '\n\n'.join(part for part in parts if part)

    @traceable(name='AMSClient.status', run_type='tool')
    def status(self) -> dict[str, Any]:
        ok, detail = http_check(f"{self._base_url()}/health", timeout=3.0)
        return {'available': ok, 'detail': detail, 'phase': 'phase2_live'}

    @traceable(name='AMSClient.retain', run_type='tool')
    def retain(
        self,
        text: str,
        *,
        context: APIRequestContext,
        tags: list[str] | None = None,
        metadata: dict[str, str] | None = None,
        document_id: str | None = None,
        transcript_ref: str | None = None,
        transcript_excerpt: str | None = None,
    ) -> dict[str, Any]:
        client = self._client()
        try:
            bank_id = self._bank_id(context)
            normalized_tags = self._normalize_tags(tags, transcript_ref=transcript_ref)
            normalized_metadata = self._normalize_metadata(
                context,
                metadata,
                transcript_ref=transcript_ref,
                transcript_excerpt=transcript_excerpt,
            )
            content = self._with_transcript_reference(text, transcript_ref=transcript_ref, transcript_excerpt=transcript_excerpt)
            result = self._run_coro(client.aretain(
                bank_id=bank_id,
                content=content,
                context=self._context_string(context),
                document_id=document_id,
                metadata=normalized_metadata,
                tags=normalized_tags,
            ))
            payload = {'ok': True, 'bank_id': bank_id, 'result': self._serialize(result), 'request_context': context.to_dict()}
            if document_id:
                payload['document_id'] = document_id
            return payload
        except Exception as exc:
            return {'ok': False, 'available': False, 'detail': str(exc), 'request_context': context.to_dict()}
        finally:
            self._close_client(client)

    @traceable(name='AMSClient.recall', run_type='tool')
    def recall(
        self,
        query: str,
        *,
        context: APIRequestContext,
        max_tokens: int = 4096,
        tags: list[str] | None = None,
        tags_match: TagMatch = 'any',
    ) -> dict[str, Any]:
        client = self._client()
        try:
            bank_id = self._bank_id(context)
            result = self._run_coro(
                client.arecall(
                    bank_id=bank_id,
                    query=query,
                    include_chunks=True,
                    trace=True,
                    max_tokens=max_tokens,
                    tags=tags,
                    tags_match=tags_match,
                )
            )
            return {'ok': True, 'bank_id': bank_id, 'result': self._serialize(result), 'request_context': context.to_dict(), 'available': True}
        except Exception as exc:
            return {'ok': False, 'available': False, 'detail': str(exc), 'query': query, 'request_context': context.to_dict()}
        finally:
            self._close_client(client)

    @traceable(name='AMSClient.reflect', run_type='tool')
    def reflect(self, question: str, *, context: APIRequestContext) -> dict[str, Any]:
        client = self._client()
        try:
            bank_id = self._bank_id(context)
            result = self._run_coro(client.areflect(bank_id=bank_id, query=question, include_facts=True))
            return {'ok': True, 'bank_id': bank_id, 'result': self._serialize(result), 'request_context': context.to_dict(), 'available': True}
        except Exception as exc:
            return {'ok': False, 'available': False, 'detail': str(exc), 'query': question, 'request_context': context.to_dict()}
        finally:
            self._close_client(client)

    @traceable(name='AMSClient.resume', run_type='tool')
    def resume(self, *, context: APIRequestContext, token_budget: int = DEFAULT_RESUME_TOKEN_BUDGET) -> dict[str, Any]:
        allocations = allocate_token_budget(token_budget)
        section_queries = {
            'steering': 'Active steering commands, hard rules, and seeded project context for this objective.',
            'open_threads': 'Open threads, unresolved questions, and next steps for this objective.',
            'recent_decisions': 'Recent decisions, implementation status, and continuity notes for this objective.',
            'transcript_refs': 'Transcript references or transcript-linked notes for this objective.',
        }
        section_payloads = {
            'steering': self.recall(
                section_queries['steering'],
                context=context,
                max_tokens=allocations['steering'],
                tags=['steering', 'project-seed'],
                tags_match='any_strict',
            ),
            'open_threads': self.recall(
                section_queries['open_threads'],
                context=context,
                max_tokens=allocations['open_threads'],
                tags=['open-thread', 'next-step', 'question'],
                tags_match='any_strict',
            ),
            'recent_decisions': self.recall(
                section_queries['recent_decisions'],
                context=context,
                max_tokens=allocations['recent_decisions'],
                tags=['decision', 'status'],
                tags_match='any_strict',
            ),
            'transcript_refs': self.recall(
                section_queries['transcript_refs'],
                context=context,
                max_tokens=allocations['transcript_refs'],
                tags=['transcript-reference'],
                tags_match='any_strict',
            ),
        }
        snapshot = build_resume_snapshot(section_payloads, token_budget=token_budget)
        warnings: list[str] = []
        if snapshot['truncated_sections']:
            warnings.append(f"resume_truncated:{','.join(snapshot['truncated_sections'])}")
        if snapshot['missing_sections']:
            warnings.append(f"resume_missing:{','.join(snapshot['missing_sections'])}")
        available = all(payload.get('available', True) for payload in section_payloads.values())
        return {
            'ok': available,
            'available': available,
            'bank_id': self._bank_id(context),
            'request_context': context.to_dict(),
            'resume_query': 'budgeted_session_snapshot',
            'token_budget': token_budget,
            'section_queries': section_queries,
            'warnings': warnings,
            'result': snapshot,
        }

    @traceable(name='AMSClient.seed_from_project', run_type='tool')
    def seed_from_project(self, *, steering_paths: list[str], progress_path: str | None, context: APIRequestContext) -> dict[str, Any]:
        ordered_paths: list[Path] = []
        seen: set[str] = set()
        raw_paths = [*(steering_paths or []), progress_path] if progress_path else list(steering_paths or [])
        for raw_path in raw_paths:
            if not raw_path:
                continue
            path = Path(raw_path)
            if not path.is_absolute():
                path = (_repo_root() / path).resolve()
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            ordered_paths.append(path)

        bundle = build_seed_bundle(ordered_paths)
        if not bundle.sources:
            return {
                'ok': False,
                'retained': [],
                'warnings': bundle.warnings or ['no_seed_sources_found'],
                'seed_mode': 'bundled_summary',
                'request_context': context.to_dict(),
            }

        document_id = self._seed_document_id(context)
        payload = self.retain(
            bundle.text,
            context=context,
            tags=['steering', 'project-seed'],
            metadata={
                'seed_mode': 'bundled_summary',
                'source_count': str(len(bundle.sources)),
                'source_paths': json.dumps([source.source_path for source in bundle.sources]),
            },
            document_id=document_id,
        )
        ok = payload.get('ok', False)
        retained = [
            {
                'source_path': source.source_path,
                'summary_chars': source.summary_chars,
                'ok': ok,
            }
            for source in bundle.sources
        ]
        response = {
            'ok': ok,
            'retained': retained,
            'warnings': bundle.warnings,
            'seed_mode': 'bundled_summary',
            'bundle_chars': len(bundle.text),
            'document_id': document_id,
            'request_context': context.to_dict(),
        }
        if 'detail' in payload:
            response['detail'] = payload['detail']
        return response
