from __future__ import annotations

from datetime import datetime, timezone
import inspect
import os
from typing import Any, Iterable

from openai import AsyncAzureOpenAI
from graphiti_core.embedder.client import EmbedderClient
from pydantic import BaseModel, Field

from common.settings import Settings, load_settings
from common.langsmith_support import wrap_openai_client
from retrieval.embeddings import encode_text, encode_texts


class AutosarModule(BaseModel):
    spec_type: str | None = Field(default=None, description='AUTOSAR spec type')
    layer: str | None = Field(default=None, description='AUTOSAR layer')
    source_pipeline: str | None = Field(default=None, description='Source pipeline identifier')
    confidence: float = Field(default=1.0, description='Confidence score')


class AsamProtocol(BaseModel):
    protocol_type: str | None = Field(default=None, description='ASAM protocol type')
    version: str | None = Field(default=None, description='ASAM protocol version')
    source_pipeline: str | None = Field(default=None, description='Source pipeline identifier')
    confidence: float = Field(default=1.0, description='Confidence score')


class ProvenanceEdge(BaseModel):
    source_system: str = Field(description='Curated source system')
    source_file: str | None = Field(default=None, description='Original source file')
    extraction_date: str | None = Field(default=None, description='Extraction or cleanup date')
    confidence: float = Field(default=1.0, description='Confidence score')


class LocalSentenceTransformerEmbedder(EmbedderClient):
    async def create(self, input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]]) -> list[float]:
        if isinstance(input_data, str):
            return encode_text(input_data)
        if isinstance(input_data, list) and input_data and all(isinstance(item, str) for item in input_data):
            return encode_text(input_data[0])
        return []

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        return encode_texts(input_data_list)


def _load_graphiti_modules():
    from graphiti_core import Graphiti
    from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.embedder.azure_openai import AzureOpenAIEmbedderClient
    from graphiti_core.llm_client.azure_openai_client import AzureOpenAILLMClient
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.nodes import EpisodeType

    return (
        Graphiti,
        FalkorDriver,
        EpisodeType,
        AzureOpenAILLMClient,
        AzureOpenAIEmbedderClient,
        OpenAIRerankerClient,
        LLMConfig,
    )


class LoomAzureOpenAILLMClient:
    def __new__(
        cls,
        base_cls,
        *,
        azure_client: AsyncAzureOpenAI,
        config,
        reasoning_model_name: str | None,
    ):
        class _Client(base_cls):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._loom_reasoning_model_name = reasoning_model_name or (config.model if config else None)

            def _supports_reasoning_features(self, model: str) -> bool:  # type: ignore[override]
                effective_name = (self._loom_reasoning_model_name or model or '').lower()
                return effective_name.startswith(('o1', 'o3', 'gpt-5'))

            def _handle_structured_response(self, response):  # type: ignore[override]
                if hasattr(response, 'choices') and response.choices:
                    message = response.choices[0].message
                    input_tokens = 0
                    output_tokens = 0
                    if hasattr(response, 'usage') and response.usage:
                        input_tokens = getattr(response.usage, 'prompt_tokens', 0) or 0
                        output_tokens = getattr(response.usage, 'completion_tokens', 0) or 0
                    if hasattr(message, 'parsed') and message.parsed:
                        return message.parsed.model_dump(), input_tokens, output_tokens
                    if hasattr(message, 'refusal') and message.refusal:
                        raise Exception(message.refusal)
                    raise Exception(f'Invalid response from LLM: {response}')

                if hasattr(response, 'output_text'):
                    input_tokens = 0
                    output_tokens = 0
                    if hasattr(response, 'usage') and response.usage:
                        input_tokens = getattr(response.usage, 'input_tokens', 0) or 0
                        output_tokens = getattr(response.usage, 'output_tokens', 0) or 0
                    if response.output_text:
                        import json

                        return json.loads(response.output_text), input_tokens, output_tokens
                    if hasattr(response, 'refusal') and response.refusal:
                        raise Exception(response.refusal)
                raise Exception(f'Unknown response format: {type(response)}')

            async def _create_completion(self, model, messages, temperature, max_tokens, response_model=None, reasoning=None, verbosity=None):  # type: ignore[override]
                if self._supports_reasoning_features(model):
                    request_kwargs = {
                        'model': model,
                        'messages': messages,
                        'max_completion_tokens': max_tokens,
                        'response_format': {'type': 'json_object'},
                    }
                    return await self.client.chat.completions.create(**request_kwargs)
                return await super()._create_completion(model, messages, temperature, max_tokens, response_model=response_model, reasoning=reasoning, verbosity=verbosity)


        return _Client(azure_client=azure_client, config=config)


def build_graphiti(settings: Settings | None = None):
    settings = settings or load_settings()
    (
        Graphiti,
        FalkorDriver,
        _,
        AzureOpenAILLMClient,
        AzureOpenAIEmbedderClient,
        OpenAIRerankerClient,
        LLMConfig,
    ) = _load_graphiti_modules()

    driver = FalkorDriver(
        host=settings.falkordb_host,
        port=settings.falkordb_port,
        username=settings.falkordb_username,
        password=settings.falkordb_password,
        database=settings.falkordb_database,
    )

    azure_llm_ready = all(
        [
            settings.azure_openai_api_key,
            settings.azure_openai_endpoint,
            settings.azure_openai_api_version,
            settings.azure_openai_llm_deployment,
        ]
    )

    if not azure_llm_ready:
        if not os.getenv('OPENAI_API_KEY'):
            raise RuntimeError('Graphiti requires AZURE_OPENAI_* or OPENAI_API_KEY to initialize.')
        return Graphiti(graph_driver=driver)

    azure_client = wrap_openai_client(AsyncAzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    ))
    llm_config = LLMConfig(
        api_key=settings.azure_openai_api_key,
        model=settings.azure_openai_llm_deployment,
        small_model=settings.azure_openai_router_deployment or settings.azure_openai_llm_deployment,
    )
    llm_client = LoomAzureOpenAILLMClient(
        AzureOpenAILLMClient,
        azure_client=azure_client,
        config=llm_config,
        reasoning_model_name=settings.azure_openai_llm_model_name,
    )
    if settings.azure_openai_embedding_deployment:
        embedding_client = wrap_openai_client(AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_embedding_api_version or settings.azure_openai_api_version,
        ))
        embedder = AzureOpenAIEmbedderClient(
            azure_client=embedding_client,
            model=settings.azure_openai_embedding_deployment,
        )
    else:
        embedder = LocalSentenceTransformerEmbedder()
    reranker = OpenAIRerankerClient(client=azure_client, config=llm_config)

    return Graphiti(
        graph_driver=driver,
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=reranker,
    )


async def initialize_graphiti(settings: Settings | None = None, *, delete_existing: bool = False):
    graphiti = build_graphiti(settings)
    await graphiti.build_indices_and_constraints(delete_existing=delete_existing)
    return graphiti


async def graphiti_search(graphiti: Any, query: str, *, group_id: str, num_results: int = 10) -> Any:
    """Use Graphiti search() by default and fallback to search_()."""
    if hasattr(graphiti, 'search'):
        search = graphiti.search
        params = {'query': query, 'num_results': num_results}
        if 'group_ids' in inspect.signature(search).parameters:
            params['group_ids'] = [group_id]
        else:
            params['group_id'] = group_id
        return await search(**params)
    if hasattr(graphiti, 'search_'):
        search = graphiti.search_
        params = {'query': query, 'num_results': num_results}
        if 'group_ids' in inspect.signature(search).parameters:
            params['group_ids'] = [group_id]
        else:
            params['group_id'] = group_id
        return await search(**params)
    raise RuntimeError('Graphiti client does not expose search() or search_()')


async def smoke_episode(graphiti: Any, *, group_id: str, name: str = 'loom_graphiti_smoke_test') -> dict:
    _, _, EpisodeType, *_ = _load_graphiti_modules()
    body = (
        '{'
        '"protocol":"XCP",'
        '"protocol_type":"measurement_calibration",'
        '"version":"1.5",'
        '"source_pipeline":"mistral_azrouter",'
        '"confidence":1.0'
        '}'
    )
    result = await graphiti.add_episode(
        name=name,
        episode_body=body,
        source_description='loom Graphiti smoke test',
        reference_time=datetime.now(timezone.utc),
        source=EpisodeType.json,
        group_id=group_id,
        entity_types={'AsamProtocol': AsamProtocol},
        edge_types={'ProvenanceEdge': ProvenanceEdge},
    )
    return {'episode_uuid': getattr(getattr(result, 'episode', None), 'uuid', None)}
