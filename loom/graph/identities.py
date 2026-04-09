from __future__ import annotations

import hashlib


def stable_id(*parts: str) -> str:
    payload = '::'.join(parts)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]


def id_standard(name: str) -> str:
    return stable_id('standard', name)


def id_protocol(name: str) -> str:
    return stable_id('protocol', name)


def id_module(name: str) -> str:
    return stable_id('module', name)


def id_source_system(source_system: str) -> str:
    return stable_id('source_system', source_system)


def id_source_pipeline(source_system: str, pipeline_name: str) -> str:
    return stable_id('source_pipeline', source_system, pipeline_name)


def id_source_document(source_system: str, source_file: str) -> str:
    return stable_id('source_document', source_system, source_file)




def id_artifact(artifact_type: str, artifact_path: str) -> str:
    return stable_id('artifact', artifact_type, artifact_path)


def id_artifact_revision(artifact_type: str, revision_key: str) -> str:
    return stable_id('artifact_revision', artifact_type, revision_key)


def id_migration_run(source_system: str, started_at: str) -> str:
    return stable_id('migration_run', source_system, started_at)


def id_audit_event(run_id: str, table_name: str, status: str, count: int) -> str:
    return stable_id('audit_event', run_id, table_name, status, str(count))


def id_source_row(source_system: str, table_name: str, row_id: str) -> str:
    # Keep compatibility with already-migrated IDs generated before typed helpers.
    return stable_id(source_system, table_name, row_id)


def id_correction_item(engineer_id: str, scope_id: str, title: str, created_at: str) -> str:
    return stable_id('correction_item', engineer_id, scope_id, title, created_at)


def id_practical_note(title: str, scope_id: str) -> str:
    return stable_id('practical_note', title, scope_id)
