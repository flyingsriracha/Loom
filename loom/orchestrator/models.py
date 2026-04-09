from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from common.auth import APIRequestContext

RouteType = Literal['domain', 'memory', 'code', 'coding_task', 'spec_session', 'general']


@dataclass(frozen=True)
class ClassificationResult:
    route: RouteType
    reasons: tuple[str, ...] = ()
    consult_loom: bool = False
    consult_memory: bool = False
    consult_cmm: bool = False
    artifact_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            'route': self.route,
            'reasons': list(self.reasons),
            'consult_loom': self.consult_loom,
            'consult_memory': self.consult_memory,
            'consult_cmm': self.consult_cmm,
            'artifact_type': self.artifact_type,
        }


@dataclass
class OrchestratorResponse:
    ok: bool
    route: RouteType
    status: str
    summary: str
    request_context: dict[str, Any]
    classification: dict[str, Any]
    knowledge: dict[str, Any] | None = None
    memory: dict[str, Any] | None = None
    code: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    audit_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            'ok': self.ok,
            'route': self.route,
            'status': self.status,
            'summary': self.summary,
            'request_context': self.request_context,
            'classification': self.classification,
            'knowledge': self.knowledge,
            'memory': self.memory,
            'code': self.code,
            'warnings': self.warnings,
            'citations': self.citations,
            'audit_id': self.audit_id,
        }


@dataclass
class AskRequest:
    query: str
    artifact_type: str | None = None


@dataclass
class OrchestratorError(Exception):
    code: str
    message: str
    status_code: int = 400
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'error': {
                'code': self.code,
                'message': self.message,
                'details': self.details,
            }
        }


@dataclass
class WorkflowState:
    query: str
    context: APIRequestContext
    artifact_type: str | None = None
    classification: ClassificationResult | None = None
    knowledge: dict[str, Any] | None = None
    memory: dict[str, Any] | None = None
    code: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    status: str = 'running'
    summary: str = ''
    citations: list[dict[str, Any]] = field(default_factory=list)
