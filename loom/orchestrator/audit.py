from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from common.auth import APIRequestContext
from graph.identities import stable_id

AUDIT_LOG_PATH = Path(__file__).resolve().parents[1] / 'artifacts' / 'orchestrator_audit.jsonl'


class OrchestratorAuditLogger:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or AUDIT_LOG_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, *, action: str, context: APIRequestContext, request: dict, result: dict) -> str:
        timestamp = datetime.now(timezone.utc).isoformat()
        audit_id = stable_id('orchestrator_audit', action, timestamp, context.engineer_id or 'anon')
        payload = {
            'audit_id': audit_id,
            'timestamp': timestamp,
            'action': action,
            'request_context': context.to_dict(),
            'request': request,
            'result': result,
        }
        with self.path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + '\n')
        return audit_id


    def export(self, *, output_dir: str, limit: int | None = None) -> dict[str, object]:
        records = []
        if self.path.exists():
            records = [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]
        if limit is not None:
            records = records[-limit:]
        export_dir = Path(output_dir)
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
        export_path = export_dir / f'orchestrator_audit_export_{timestamp}.json'
        export_path.write_text(json.dumps(records, indent=2, ensure_ascii=True))
        return {'ok': True, 'path': str(export_path), 'count': len(records)}
