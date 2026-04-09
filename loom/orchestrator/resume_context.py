from __future__ import annotations

from typing import Any

DEFAULT_RESUME_TOKEN_BUDGET = 2000
_RESUME_SECTIONS = [
    ('steering', 'Active steering and project seed context', 0.4),
    ('open_threads', 'Open threads and next steps', 0.3),
    ('recent_decisions', 'Recent decisions and status', 0.2),
    ('transcript_refs', 'Transcript references for audit/debug', 0.1),
]


def allocate_token_budget(token_budget: int) -> dict[str, int]:
    total = max(token_budget, 400)
    remaining = total
    allocations: dict[str, int] = {}
    for idx, (name, _, weight) in enumerate(_RESUME_SECTIONS):
        if idx == len(_RESUME_SECTIONS) - 1:
            allocations[name] = remaining
            break
        allocated = max(120, int(total * weight))
        allocations[name] = allocated
        remaining -= allocated
    return allocations


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _truncate(text: str, limit: int = 280) -> str:
    compact = ' '.join(text.split())
    if len(compact) <= limit:
        return compact
    clipped = compact[: max(limit - 3, 1)].rsplit(' ', 1)[0].strip()
    return f'{clipped or compact[: max(limit - 3, 1)]}...'


def _result_items(payload: dict[str, Any]) -> list[str]:
    result = payload.get('result', {}) if isinstance(payload, dict) else {}
    items: list[str] = []
    for record in result.get('results', []) or []:
        if not isinstance(record, dict):
            continue
        text = str(record.get('text') or '').strip()
        metadata = record.get('metadata') or {}
        if metadata.get('transcript_ref'):
            text = f"{text} [transcript_ref: {metadata['transcript_ref']}]" if text else f"transcript_ref: {metadata['transcript_ref']}"
        if text:
            items.append(_truncate(text))
    if items:
        return items
    chunks = result.get('chunks', {}) if isinstance(result, dict) else {}
    for chunk in (chunks or {}).values():
        if not isinstance(chunk, dict):
            continue
        text = str(chunk.get('text') or '').strip()
        if text:
            items.append(_truncate(text))
    return items


def build_resume_snapshot(section_payloads: dict[str, dict[str, Any]], *, token_budget: int) -> dict[str, Any]:
    used_tokens = 0
    sections: dict[str, list[str]] = {}
    truncated_sections: list[str] = []
    missing_sections: list[str] = []
    text_parts: list[str] = []

    for section_name, section_title, _ in _RESUME_SECTIONS:
        items = _result_items(section_payloads.get(section_name, {}))
        if not items:
            sections[section_name] = []
            missing_sections.append(section_name)
            continue

        kept: list[str] = []
        for item in items:
            item_tokens = _approx_tokens(item)
            if used_tokens + item_tokens > token_budget:
                remaining_chars = max((token_budget - used_tokens) * 4, 0)
                if remaining_chars >= 80:
                    clipped = _truncate(item, remaining_chars)
                    kept.append(clipped)
                    used_tokens += _approx_tokens(clipped)
                truncated_sections.append(section_name)
                break
            kept.append(item)
            used_tokens += item_tokens

        sections[section_name] = kept
        if kept:
            text_parts.append(f'{section_title}:')
            text_parts.extend(f'- {item}' for item in kept)
        if used_tokens >= token_budget:
            break

    return {
        'summary': '\n'.join(text_parts).strip(),
        'sections': sections,
        'token_budget': token_budget,
        'approx_tokens': used_tokens,
        'truncated_sections': list(dict.fromkeys(truncated_sections)),
        'missing_sections': missing_sections,
    }
