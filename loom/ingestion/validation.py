from __future__ import annotations

from dataclasses import dataclass, field

from ingestion.loader import LoadedIngestionDocument


@dataclass(frozen=True)
class IngestionValidationResult:
    accepted: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommended_stack: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            'accepted': self.accepted,
            'errors': self.errors,
            'warnings': self.warnings,
            'recommended_stack': self.recommended_stack,
            'notes': self.notes,
        }


class IngestionValidator:
    def validate(self, doc: LoadedIngestionDocument) -> IngestionValidationResult:
        errors: list[str] = []
        warnings = list(doc.warnings)
        notes: list[str] = []

        if not doc.chunks and not doc.tables:
            errors.append('no_extractable_content')
        if doc.source_kind == 'pdf' and not doc.chunks:
            errors.append('pdf_text_extraction_empty')
        if doc.source_kind in {'json', 'yaml', 'csv'} and not doc.tables:
            errors.append('structured_payload_empty')
        if doc.source_kind in {'json', 'yaml', 'csv'} and doc.tables and doc.tables[0].row_count == 0:
            warnings.append('structured_table_has_zero_rows')
        if doc.source_system.startswith('autosar-supplementary'):
            notes.append('supplementary_AUTOSAR_flow_enabled')
        if doc.source_kind == 'pdf':
            notes.append('docling_kimi25_reuse_recommended_when_high-fidelity extraction is required')
        if doc.source_kind in {'json', 'yaml', 'csv'}:
            notes.append('structured payload is loaded as reference/context and vectorized text chunks')

        return IngestionValidationResult(
            accepted=not errors,
            errors=errors,
            warnings=warnings,
            recommended_stack=self._recommended_stack(doc.source_kind),
            notes=notes,
        )

    def _recommended_stack(self, source_kind: str) -> list[str]:
        if source_kind == 'pdf':
            return ['pypdf-baseline-loader', 'docling', 'kimi-guided-validation']
        if source_kind in {'json', 'yaml', 'csv'}:
            return ['native-structured-parser', 'kimi-guided-validation']
        return ['native-text-loader']
