from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common.auth import APIRequestContext
from orchestrator.models import OrchestratorError

def _discover_repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / '.kiro').exists():
            return candidate
    return Path(__file__).resolve().parents[1]


REPO_ROOT = _discover_repo_root()
STEERING_CANDIDATES = [
    REPO_ROOT / '.kiro' / 'steering' / 'loom-core.md',
    REPO_ROOT / '.kiro' / 'steering' / 'loom-progress.md',
]
DEFAULT_ARTIFACT_PATHS = {
    'requirements': REPO_ROOT / '.kiro' / 'specs' / 'aaems-system-architecture' / 'requirements.generated.md',
    'design': REPO_ROOT / '.kiro' / 'specs' / 'aaems-system-architecture' / 'design.generated.md',
    'tasks': REPO_ROOT / '.kiro' / 'specs' / 'aaems-system-architecture' / 'tasks.generated.md',
}


def resolve_target_path(artifact_type: str, target_path: str | None) -> Path:
    if target_path:
        candidate = Path(target_path)
        return candidate if candidate.is_absolute() else (REPO_ROOT / candidate).resolve()
    return DEFAULT_ARTIFACT_PATHS.get(artifact_type, REPO_ROOT / '.kiro' / 'specs' / f'{artifact_type}.generated.md')


def steering_paths() -> list[str]:
    return [str(path.relative_to(REPO_ROOT)) for path in STEERING_CANDIDATES if path.exists()]


def extract_unresolved_items(content: str) -> list[str]:
    lines = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        lowered = line.lower()
        if line.startswith('- [ ]') or 'todo' in lowered or 'open question' in lowered or 'unresolved' in lowered:
            lines.append(line)
    return lines[:20]


def supporting_node_ids(knowledge: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for item in knowledge.get('results', []):
        node_id = item.get('id')
        if node_id:
            ids.append(str(node_id))
    return list(dict.fromkeys(ids))




def fallback_queries(prompt: str) -> list[str]:
    stop_single = {'update', 'preserve', 'add', 'implement', 'review', 'draft', 'create', 'what', 'how', 'why', 'when', 'where', 'which'}
    tokens = [token.strip('.,:;()[]{}') for token in prompt.split() if token.strip('.,:;()[]{}')]
    phrases: list[str] = []
    current: list[str] = []
    for token in tokens:
        keep = any(ch.isupper() for ch in token) or any(ch.isdigit() for ch in token)
        if keep:
            current.append(token)
        else:
            if current:
                phrases.append(' '.join(current))
            current = []
    if current:
        phrases.append(' '.join(current))

    ranked: list[str] = []
    multi = [phrase for phrase in phrases if len(phrase.split()) >= 2]
    single = [phrase for phrase in phrases if len(phrase.split()) == 1 and phrase.lower() not in stop_single]
    ranked.extend(multi)
    ranked.extend(single)
    ranked.append(prompt)
    out = []
    for item in ranked:
        item = item.strip()
        if item and item not in out:
            out.append(item)
    return out[:5]


def citations_from_knowledge(knowledge: dict[str, Any]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for item in knowledge.get('results', []):
        evidence_list = item.get('evidence_chain') or item.get('provenance_preview') or []
        for evidence in evidence_list:
            citations.append(dict(evidence))
    return citations


def verify_traceability(
    *,
    context: APIRequestContext,
    citations: list[dict[str, Any]],
    references: list[str],
    steering_refs: list[str],
) -> None:
    missing = []
    if not context.objective_id:
        missing.append('objective_id')
    if not context.session_id:
        missing.append('session_id')
    if not steering_refs:
        missing.append('steering_context')
    if not citations and not references:
        missing.append('citations_or_references')
    if missing:
        raise OrchestratorError(
            'traceability_verification_failed',
            'Spec artifact output blocked because required lineage/traceability inputs are missing.',
            409,
            {'missing': missing},
        )


def render_artifact(
    *,
    artifact_type: str,
    prompt: str,
    knowledge: dict[str, Any],
    context: APIRequestContext,
    target_path: Path,
    existing_content: str | None = None,
    references: list[str] | None = None,
    operation: str,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    refs = references or []
    steering_refs = steering_paths()
    citations = citations_from_knowledge(knowledge)
    verify_traceability(context=context, citations=citations, references=refs, steering_refs=steering_refs)

    unresolved = extract_unresolved_items(existing_content or '')
    title = {
        'requirements': '# Requirements Draft',
        'design': '# Design Draft',
        'tasks': '# Tasks Draft',
    }.get(artifact_type, f'# {artifact_type.title()} Draft')

    evidence_lines = []
    for idx, item in enumerate(knowledge.get('results', [])[:5], start=1):
        snippet = str(item.get('snippet', '')).strip().replace('\n', ' ')
        snippet = snippet[:300]
        evidence_lines.append(f'- Evidence {idx}: {snippet}')
    if not evidence_lines:
        evidence_lines.append('- No grounded results were available.')

    citation_lines = []
    for idx, citation in enumerate(citations[:8], start=1):
        citation_lines.append(
            f"- Citation {idx}: source_system={citation.get('source_system')} | "
            f"source_pipeline={citation.get('source_pipeline')} | "
            f"source_file={citation.get('source_file')} | confidence={citation.get('confidence')}"
        )
    for idx, ref in enumerate(refs, start=1):
        citation_lines.append(f'- Engineer reference {idx}: {ref}')

    open_items_lines = [f'- {item}' for item in unresolved] if unresolved else ['- None preserved from previous revision.']

    body = [
        title,
        '',
        f'- Artifact type: `{artifact_type}`',
        f'- Operation: `{operation}`',
        f'- Target path: `{target_path}`',
        f'- Objective ID: `{context.objective_id}`',
        f'- Session ID: `{context.session_id}`',
        f'- Engineer ID: `{context.engineer_id or "anonymous-local-dev"}`',
        f'- Generated at: `{now}`',
        '',
        '## Prompt or Change Request',
        prompt,
        '',
        '## Standards-Grounded Evidence Summary',
        *evidence_lines,
        '',
        '## Proposed Content',
    ]

    if artifact_type == 'requirements':
        body.extend([
            '- Capture normative requirements derived from the evidence summary above.',
            '- Preserve explicit assumptions and open issues instead of silently filling gaps.',
            '- Keep downstream traceability intact for later design and task updates.',
        ])
    elif artifact_type == 'design':
        body.extend([
            '- Describe architecture, interfaces, and constraints supported by the cited evidence.',
            '- Record any temporary fallback implementation choices explicitly.',
            '- Keep operational and provenance implications visible for later implementation work.',
        ])
    elif artifact_type == 'tasks':
        body.extend([
            '- Break the work into implementation-ready tasks grounded in the cited evidence.',
            '- Preserve blocked work separately from executable work.',
            '- Keep verification and traceability tasks visible, not implied.',
        ])
    else:
        body.extend(['- Summarize the grounded artifact intent using the evidence above.'])

    steering_lines = [f'- {item}' for item in steering_refs] if steering_refs else ['- None']

    body.extend([
        '',
        '## Traceability and Citations',
        *citation_lines,
        '',
        '## Steering References',
        *steering_lines,
        '',
        '## Preserved Open Items',
        *open_items_lines,
    ])

    if existing_content:
        body.extend([
            '',
            '## Previous Content Snapshot',
            '```markdown',
            existing_content[:8000],
            '```',
        ])

    content = '\n'.join(body).strip() + '\n'
    return {
        'content': content,
        'citations': citations,
        'supporting_node_ids': supporting_node_ids(knowledge),
        'steering_paths': steering_refs,
        'unresolved_items': unresolved,
        'traceability_ok': True,
    }
