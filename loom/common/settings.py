from __future__ import annotations

from dataclasses import dataclass
import os

from common.runtime_env import load_runtime_env


def _bool_env(name: str, default: bool = False) -> bool:
    return _get(name, str(default)).strip().lower() in {'1', 'true', 'yes', 'on'}


def _default_service_host(container_host: str) -> str:
    if os.path.exists('/.dockerenv'):
        return container_host
    return 'localhost'


RUNTIME_ENV = load_runtime_env()


def _get(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, RUNTIME_ENV.get(name, default))


@dataclass(frozen=True)
class Settings:
    falkordb_host: str
    falkordb_port: int
    falkordb_database: str
    falkordb_username: str | None
    falkordb_password: str | None
    graphiti_group_id: str
    graphiti_delete_existing: bool
    loom_service_host: str
    loom_service_port: int
    orchestrator_host: str
    orchestrator_port: int
    loom_service_url: str
    cmm_binary_path: str
    cmm_project: str | None
    cmm_base_branch: str
    hindsight_host: str
    hindsight_api_port: int
    hindsight_mcp_port: int
    hindsight_api_key: str | None
    hindsight_bank_prefix: str
    hindsight_api_url: str
    loom_api_key: str | None
    loom_admin_api_key: str | None
    deployment_environment: str
    allow_local_dev_bypass: bool
    audit_export_dir: str
    azure_openai_api_key: str | None
    azure_openai_endpoint: str | None
    azure_openai_api_version: str | None
    azure_openai_llm_deployment: str | None
    azure_openai_llm_model_name: str | None
    azure_openai_embedding_deployment: str | None
    azure_openai_embedding_model_name: str | None
    azure_openai_embedding_api_version: str | None
    azure_openai_router_deployment: str | None
    azure_openai_router_model_name: str | None
    azure_openai_router_api_version: str | None


def load_settings() -> Settings:
    hindsight_host = _get('HINDSIGHT_HOST', _default_service_host('hindsight')) or _default_service_host('hindsight')
    hindsight_api_port = int(_get('HINDSIGHT_API_PORT', '8888') or '8888')
    return Settings(
        falkordb_host=_get('FALKORDB_HOST', 'localhost') or 'localhost',
        falkordb_port=int(_get('FALKORDB_PORT', '6379') or '6379'),
        falkordb_database=_get('FALKORDB_DATABASE', 'loom_knowledge') or 'loom_knowledge',
        falkordb_username=_get('FALKORDB_USERNAME') or None,
        falkordb_password=_get('FALKORDB_PASSWORD') or None,
        graphiti_group_id=_get('GRAPHITI_GROUP_ID', 'loom_knowledge') or 'loom_knowledge',
        graphiti_delete_existing=_bool_env('GRAPHITI_DELETE_EXISTING', False),
        loom_service_host=_get('LOOM_SERVICE_HOST', '0.0.0.0') or '0.0.0.0',
        loom_service_port=int(_get('LOOM_SERVICE_PORT', '8090') or '8090'),
        orchestrator_host=_get('ORCHESTRATOR_HOST', '0.0.0.0') or '0.0.0.0',
        orchestrator_port=int(_get('ORCHESTRATOR_PORT', '8080') or '8080'),
        loom_service_url=_get('LOOM_SERVICE_URL', 'http://localhost:8090') or 'http://localhost:8090',
        cmm_binary_path=_get('CMM_BINARY_PATH', 'codebase-memory-mcp') or 'codebase-memory-mcp',
        cmm_project=_get('CMM_PROJECT') or None,
        cmm_base_branch=_get('CMM_BASE_BRANCH', 'main') or 'main',
        hindsight_host=hindsight_host,
        hindsight_api_port=hindsight_api_port,
        hindsight_mcp_port=int(_get('HINDSIGHT_MCP_PORT', '9999') or '9999'),
        hindsight_api_key=_get('HINDSIGHT_API_TENANT_API_KEY') or None,
        hindsight_bank_prefix=_get('HINDSIGHT_BANK_PREFIX', 'loom') or 'loom',
        hindsight_api_url=_get('HINDSIGHT_API_URL', f'http://{hindsight_host}:{hindsight_api_port}') or f'http://{hindsight_host}:{hindsight_api_port}',
        loom_api_key=_get('LOOM_API_KEY') or None,
        loom_admin_api_key=_get('LOOM_ADMIN_API_KEY') or None,
        deployment_environment=_get('LOOM_DEPLOYMENT_ENV', 'development') or 'development',
        allow_local_dev_bypass=_bool_env('LOOM_ALLOW_LOCAL_DEV_BYPASS', True),
        audit_export_dir=_get('LOOM_AUDIT_EXPORT_DIR', '/app/artifacts/exports') or '/app/artifacts/exports',
        azure_openai_api_key=_get('AZURE_OPENAI_API_KEY') or None,
        azure_openai_endpoint=_get('AZURE_OPENAI_ENDPOINT') or None,
        azure_openai_api_version=_get('AZURE_OPENAI_API_VERSION') or None,
        azure_openai_llm_deployment=_get('AZURE_OPENAI_LLM_DEPLOYMENT') or None,
        azure_openai_llm_model_name=_get('AZURE_OPENAI_LLM_MODEL_NAME') or None,
        azure_openai_embedding_deployment=_get('AZURE_OPENAI_EMBEDDING_DEPLOYMENT') or None,
        azure_openai_embedding_model_name=_get('AZURE_OPENAI_EMBEDDING_MODEL_NAME') or None,
        azure_openai_embedding_api_version=_get('AZURE_OPENAI_EMBEDDING_API_VERSION') or None,
        azure_openai_router_deployment=_get('AZURE_OPENAI_ROUTER_DEPLOYMENT') or None,
        azure_openai_router_model_name=_get('AZURE_OPENAI_ROUTER_MODEL_NAME') or None,
        azure_openai_router_api_version=_get('AZURE_OPENAI_ROUTER_API_VERSION') or None,
    )
