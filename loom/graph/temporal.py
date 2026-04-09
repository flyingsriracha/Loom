from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from graph.client import FalkorDBClient
from graph.identities import stable_id

STATE_LABELS = {
    'Standard': 'StandardState',
    'Protocol': 'ProtocolState',
    'Module': 'ModuleState',
    'Requirement': 'RequirementState',
}

STATE_FIELDS = {
    'Standard': ('organization', 'version', 'source_system'),
    'Protocol': ('protocol_type', 'version', 'standard_name', 'description', 'source_system'),
    'Module': (
        'module_type',
        'spec_type',
        'description',
        'source_system',
        'source_pipeline',
        'source_file',
        'confidence',
        'standard_name',
    ),
    'Requirement': (
        'identifier',
        'title',
        'description',
        'source_system',
        'source_pipeline',
        'source_file',
        'confidence',
        'standard_name',
    ),
}


@dataclass(frozen=True)
class TemporalStateRecord:
    entity_id: str
    entity_labels: list[str]
    entity_properties: dict[str, Any]
    state_label: str
    state_properties: dict[str, Any]
    valid_from: str | None
    valid_to: str | None
    tx_from: str | None
    tx_to: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            'entity_id': self.entity_id,
            'entity_labels': self.entity_labels,
            'entity_properties': self.entity_properties,
            'state_label': self.state_label,
            'state_properties': self.state_properties,
            'valid_from': self.valid_from,
            'valid_to': self.valid_to,
            'tx_from': self.tx_from,
            'tx_to': self.tx_to,
        }


class TemporalStateManager:
    def __init__(self, client: FalkorDBClient | None = None) -> None:
        self.client = client or FalkorDBClient()

    def seed_from_existing(self, *, source_system: str | None = None) -> dict[str, Any]:
        graph = self.client.select_graph()
        now = datetime.now(timezone.utc).isoformat()
        states_created = 0
        states_skipped = 0
        per_label: dict[str, int] = {}

        for entity_label, state_label in STATE_LABELS.items():
            rows = graph.ro_query(
                f'MATCH (e:{entity_label}) '
                'WHERE ($source_system IS NULL OR e.source_system = $source_system) '
                'RETURN e.id, properties(e)',
                params={'source_system': source_system},
            ).result_set
            label_created = 0
            for entity_id, entity_props in rows:
                current = self._current_state(graph, entity_label=entity_label, entity_id=str(entity_id))
                next_state = self._extract_state_properties(entity_label, dict(entity_props))
                if current and self._normalize_state(current.state_properties) == self._normalize_state(next_state):
                    states_skipped += 1
                    continue
                if current is None:
                    self._create_state(graph, entity_label, str(entity_id), next_state, valid_at=now, tx_at=now)
                    states_created += 1
                    label_created += 1
            per_label[entity_label] = label_created

        return {
            'created': states_created,
            'skipped': states_skipped,
            'source_system': source_system,
            'per_label': per_label,
            'backend': 'graphiti_ready_falkordb_state',
        }

    def upsert_state(
        self,
        *,
        entity_label: str,
        entity_id: str,
        state_properties: dict[str, Any],
        valid_at: str | None = None,
        tx_at: str | None = None,
    ) -> dict[str, Any]:
        if entity_label not in STATE_LABELS:
            raise ValueError(f'unsupported temporal entity label: {entity_label}')
        graph = self.client.select_graph()
        valid_at = valid_at or datetime.now(timezone.utc).isoformat()
        tx_at = tx_at or valid_at
        entity_result = graph.ro_query(
            f'MATCH (e:{entity_label} {{id: $entity_id}}) RETURN properties(e) LIMIT 1',
            params={'entity_id': entity_id},
        )
        if not entity_result.result_set:
            raise ValueError(f'unknown {entity_label} id: {entity_id}')

        current = self._current_state(graph, entity_label=entity_label, entity_id=entity_id)
        next_state = self._normalize_state(state_properties)
        if current and self._normalize_state(current.state_properties) == next_state:
            return {'created': False, 'entity_id': entity_id, 'entity_label': entity_label, 'state': current.to_dict()}

        if current is not None:
            graph.query(
                f'MATCH (e:{entity_label} {{id: $entity_id}})-[r:HAS_STATE]->(s:{current.state_label}) '
                'WHERE r.txTo IS NULL AND r.validTo IS NULL '
                'SET r.validTo = $valid_to, r.txTo = $tx_to, s.state_status = "historical"',
                params={'entity_id': entity_id, 'valid_to': valid_at, 'tx_to': tx_at},
            )

        state = self._create_state(graph, entity_label, entity_id, next_state, valid_at=valid_at, tx_at=tx_at)
        return {'created': True, 'entity_id': entity_id, 'entity_label': entity_label, 'state': state.to_dict()}

    def query_as_of(
        self,
        *,
        valid_at: str,
        tx_at: str | None = None,
        entity_label: str | None = None,
        source_system: str | None = None,
        query_text: str | None = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        tx_at = tx_at or valid_at
        graph = self.client.select_graph()
        rows = graph.ro_query(
            'MATCH (e)-[r:HAS_STATE]->(s) '
            'WHERE ($source_system IS NULL OR e.source_system = $source_system) '
            '  AND r.validFrom <= $valid_at '
            '  AND (r.validTo IS NULL OR r.validTo > $valid_at) '
            '  AND r.txFrom <= $tx_at '
            '  AND (r.txTo IS NULL OR r.txTo > $tx_at) '
            'RETURN e.id, labels(e), properties(e), labels(s), properties(s), r.validFrom, r.validTo, r.txFrom, r.txTo',
            params={
                'source_system': source_system,
                'valid_at': valid_at,
                'tx_at': tx_at,
            },
        ).result_set

        out: list[dict[str, Any]] = []
        query_lower = query_text.lower() if query_text else None
        for entity_id, entity_labels, entity_props, state_labels, state_props, valid_from, valid_to, edge_tx_from, edge_tx_to in rows:
            entity_labels = list(entity_labels)
            if entity_label and entity_label not in entity_labels:
                continue
            record = TemporalStateRecord(
                entity_id=str(entity_id),
                entity_labels=entity_labels,
                entity_properties=dict(entity_props),
                state_label=state_labels[0] if state_labels else 'State',
                state_properties=dict(state_props),
                valid_from=valid_from,
                valid_to=valid_to,
                tx_from=edge_tx_from,
                tx_to=edge_tx_to,
            )
            if query_lower:
                haystack = ' '.join(
                    str(value)
                    for value in [
                        record.entity_properties.get('name'),
                        record.entity_properties.get('title'),
                        record.entity_properties.get('description'),
                        record.state_properties.get('description'),
                        record.state_properties.get('status'),
                        record.state_properties.get('version'),
                        record.state_properties.get('module_type'),
                        record.state_properties.get('protocol_type'),
                    ]
                    if value not in (None, '')
                ).lower()
                if query_lower not in haystack:
                    continue
            out.append(record.to_dict())
            if len(out) >= limit:
                break
        return out

    def _create_state(
        self,
        graph: Any,
        entity_label: str,
        entity_id: str,
        state_properties: dict[str, Any],
        *,
        valid_at: str,
        tx_at: str,
    ) -> TemporalStateRecord:
        state_label = STATE_LABELS[entity_label]
        state_id = stable_id('state', entity_label, entity_id, tx_at)
        props = {
            **state_properties,
            'id': state_id,
            'entity_id': entity_id,
            'state_status': state_properties.get('status', 'current'),
            'created_at': tx_at,
            'updated_at': tx_at,
        }
        graph.query(
            f'MATCH (e:{entity_label} {{id: $entity_id}}) '
            f'MERGE (s:{state_label} {{id: $state_id}}) '
            'SET s += $props '
            'MERGE (e)-[r:HAS_STATE]->(s) '
            'SET r.validFrom = $valid_from, r.validTo = NULL, r.txFrom = $tx_from, r.txTo = NULL',
            params={
                'entity_id': entity_id,
                'state_id': state_id,
                'props': props,
                'valid_from': valid_at,
                'tx_from': tx_at,
            },
        )
        return TemporalStateRecord(
            entity_id=entity_id,
            entity_labels=[entity_label],
            entity_properties={},
            state_label=state_label,
            state_properties=props,
            valid_from=valid_at,
            valid_to=None,
            tx_from=tx_at,
            tx_to=None,
        )

    def _current_state(self, graph: Any, *, entity_label: str, entity_id: str) -> TemporalStateRecord | None:
        state_label = STATE_LABELS[entity_label]
        rows = graph.ro_query(
            f'MATCH (e:{entity_label} {{id: $entity_id}})-[r:HAS_STATE]->(s:{state_label}) '
            'WHERE r.validTo IS NULL AND r.txTo IS NULL '
            'RETURN e.id, labels(e), properties(e), labels(s), properties(s), r.validFrom, r.validTo, r.txFrom, r.txTo '
            'LIMIT 1',
            params={'entity_id': entity_id},
        ).result_set
        if not rows:
            return None
        entity_id, entity_labels, entity_props, state_labels, state_props, valid_from, valid_to, tx_from, tx_to = rows[0]
        return TemporalStateRecord(
            entity_id=str(entity_id),
            entity_labels=list(entity_labels),
            entity_properties=dict(entity_props),
            state_label=state_labels[0] if state_labels else state_label,
            state_properties=dict(state_props),
            valid_from=valid_from,
            valid_to=valid_to,
            tx_from=tx_from,
            tx_to=tx_to,
        )

    def _extract_state_properties(self, entity_label: str, entity_props: dict[str, Any]) -> dict[str, Any]:
        state_props: dict[str, Any] = {}
        for field in STATE_FIELDS[entity_label]:
            value = entity_props.get(field)
            if value not in (None, '', []):
                state_props[field] = value
        if 'description' not in state_props and entity_props.get('description') not in (None, ''):
            state_props['description'] = entity_props['description']
        if 'status' not in state_props:
            state_props['status'] = 'current'
        return state_props

    def _normalize_state(self, state_props: dict[str, Any]) -> dict[str, Any]:
        ignored = {'id', 'entity_id', 'created_at', 'updated_at', 'state_status'}
        return {key: value for key, value in state_props.items() if key not in ignored}
