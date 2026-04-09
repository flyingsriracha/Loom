from __future__ import annotations

import re

from orchestrator.models import ClassificationResult

DOMAIN_TERMS = {
    'asam', 'autosar', 'xcp', 'odx', 'mdf', 'fmi', 'ssp', 'fibex', 'dcp', 'xil', 'vecu', 'ecu', 'protocol', 'standard'
}
SPEC_TERMS = {'requirements', 'design', 'tasks', 'spec', 'artifact', 'traceability'}
CODE_TERMS = {'function', 'class', 'module', 'file', 'call', 'caller', 'impact', 'trace', 'codebase', 'repo', 'search code'}
CODING_TERMS = {'implement', 'build', 'add', 'update', 'refactor', 'fix', 'change', 'handler', 'workflow'}
MEMORY_TERMS = {'memory', 'resume', 'recall', 'what did we decide', 'decision', 'progress', 'session', 'where did we leave off', 'pick up where', 'continue from last session', 'continue this objective'}


def classify_request(query: str, *, artifact_type: str | None = None) -> ClassificationResult:
    q = query.strip().lower()
    reasons: list[str] = []

    if artifact_type or any(term in q for term in SPEC_TERMS):
        reasons.append('spec-session language detected')
        return ClassificationResult(
            route='spec_session',
            reasons=tuple(reasons),
            consult_loom=True,
            consult_memory=True,
            consult_cmm=False,
            artifact_type=artifact_type,
        )

    if any(term in q for term in MEMORY_TERMS):
        reasons.append('memory/resume language detected')
        return ClassificationResult(route='memory', reasons=tuple(reasons), consult_memory=True)

    if re.search(r'(what calls|who calls|where is|trace|call path|impact)', q) or any(term in q for term in CODE_TERMS):
        reasons.append('code-structure language detected')
        return ClassificationResult(route='code', reasons=tuple(reasons), consult_cmm=True)

    if any(term in q for term in CODING_TERMS):
        reasons.append('implementation language detected')
        return ClassificationResult(
            route='coding_task',
            reasons=tuple(reasons),
            consult_loom=any(term in q for term in DOMAIN_TERMS) or True,
            consult_memory=True,
            consult_cmm=True,
        )

    if any(term in q for term in DOMAIN_TERMS):
        reasons.append('domain terminology detected')
        return ClassificationResult(route='domain', reasons=tuple(reasons), consult_loom=True, consult_memory=True)

    reasons.append('no specialized pattern detected')
    return ClassificationResult(route='general', reasons=tuple(reasons))
