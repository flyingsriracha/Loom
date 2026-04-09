from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

_MAX_GENERIC_SUMMARY_CHARS = 220
_MAX_SEED_SOURCES = 4
_LIST_PREFIX_RE = re.compile(r'^(?:[-*]\s+|\d+\.\s+)')


@dataclass(frozen=True)
class SeedSource:
    source_path: str
    source_name: str
    summary: str
    summary_chars: int


@dataclass(frozen=True)
class SeedBundle:
    text: str
    sources: list[SeedSource]
    warnings: list[str]


def _truncate(text: str, limit: int) -> str:
    normalized = ' '.join(text.split())
    if len(normalized) <= limit:
        return normalized
    clipped = normalized[: max(limit - 3, 1)].rsplit(' ', 1)[0].strip()
    return f'{clipped or normalized[: max(limit - 3, 1)]}...'


def _strip_frontmatter(text: str) -> list[str]:
    lines = text.splitlines()
    if len(lines) > 1 and lines[0].strip() == '---':
        for idx in range(1, len(lines)):
            if lines[idx].strip() == '---':
                return lines[idx + 1 :]
    return lines


def _parse_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    buffer: list[str] = []
    for line in lines:
        if line.startswith('## '):
            if current is not None:
                sections[current] = buffer
            current = line[3:].strip()
            buffer = []
            continue
        if current is not None:
            buffer.append(line.rstrip())
    if current is not None:
        sections[current] = buffer
    return sections


def _paragraph_summary(lines: list[str], *, limit: int) -> str:
    parts: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if parts:
                break
            continue
        if _LIST_PREFIX_RE.match(stripped):
            if parts:
                break
            continue
        parts.append(stripped)
    if not parts:
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            parts.append(_LIST_PREFIX_RE.sub('', stripped))
            if len(parts) >= 2:
                break
    return _truncate(' '.join(parts), limit) if parts else ''


def _list_summary(lines: list[str], *, max_items: int, limit: int) -> str:
    items: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if not _LIST_PREFIX_RE.match(stripped):
            continue
        items.append(_LIST_PREFIX_RE.sub('', stripped))
        if len(items) >= max_items:
            break
    return _truncate('; '.join(items), limit) if items else ''


def _loom_core_summary(sections: dict[str, list[str]]) -> str:
    identity_intro = _paragraph_summary(sections.get('Identity', []), limit=48).removesuffix(' Four modules:').removesuffix(' Modules:').rstrip(': ')
    modules = _list_summary(sections.get('Identity', []), max_items=4, limit=140)
    rules = _list_summary(sections.get('Hard Rules', []), max_items=3, limit=110)
    parts: list[str] = []
    if identity_intro or modules:
        combined = identity_intro
        if modules:
            combined = f'{combined} Modules: {modules}'.strip()
        parts.append(f'Identity: {_truncate(combined, 180)}')
    if rules:
        parts.append(f'Rules: {rules}')
    return ' '.join(parts)


def _loom_progress_summary(sections: dict[str, list[str]]) -> str:
    task = _paragraph_summary(sections.get('Current Task', []), limit=120)
    blockers = _list_summary(sections.get('Blockers', []), max_items=2, limit=100)
    next_steps = _list_summary(sections.get('Next Steps', []), max_items=2, limit=100)
    parts: list[str] = []
    if task:
        parts.append(f'Current task: {task}')
    if blockers:
        parts.append(f'Blockers: {blockers}')
    if next_steps:
        parts.append(f'Next steps: {next_steps}')
    return ' '.join(parts)


def _default_summary(sections: dict[str, list[str]], lines: list[str]) -> str:
    for title, body in sections.items():
        paragraph = _paragraph_summary(body, limit=150)
        if paragraph:
            return f'{title}: {paragraph}'
        bullets = _list_summary(body, max_items=2, limit=150)
        if bullets:
            return f'{title}: {bullets}'
    plain = ' '.join(line.strip() for line in lines if line.strip())
    return _truncate(plain, _MAX_GENERIC_SUMMARY_CHARS)


def build_seed_source(path: Path) -> SeedSource:
    lines = _strip_frontmatter(path.read_text())
    sections = _parse_sections(lines)
    if path.name == 'loom-core.md':
        summary = _loom_core_summary(sections)
    elif path.name == 'loom-progress.md':
        summary = _loom_progress_summary(sections)
    else:
        summary = _default_summary(sections, lines)
    if not summary:
        summary = _default_summary({}, lines)
    return SeedSource(
        source_path=str(path),
        source_name=path.name,
        summary=summary,
        summary_chars=len(summary),
    )


def build_seed_bundle(paths: list[Path]) -> SeedBundle:
    warnings: list[str] = []
    unique_paths: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique_paths.append(path)
    if len(unique_paths) > _MAX_SEED_SOURCES:
        warnings.append(f'additional_paths_skipped:{len(unique_paths) - _MAX_SEED_SOURCES}')
        unique_paths = unique_paths[:_MAX_SEED_SOURCES]

    sources: list[SeedSource] = []
    for path in unique_paths:
        if not path.exists():
            warnings.append(f'missing:{path}')
            continue
        sources.append(build_seed_source(path))

    lines = ['Project continuity seed for Loom.']
    for source in sources:
        lines.append(f'Source path: {source.source_name}')
        lines.append(source.summary)
    return SeedBundle(text='\n\n'.join(lines), sources=sources, warnings=warnings)
