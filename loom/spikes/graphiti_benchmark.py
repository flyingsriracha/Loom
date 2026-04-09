from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from time import perf_counter
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.settings import load_settings
from graph.graphiti_adapter import AsamProtocol, AutosarModule, ProvenanceEdge, graphiti_search, initialize_graphiti


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Benchmark Graphiti sequential vs bulk episode ingestion for Loom.')
    parser.add_argument('--episodes', type=int, default=6, help='Number of representative episodes to benchmark.')
    parser.add_argument('--query', default='E2E Library deprecated', help='Search query to probe benchmarked groups.')
    parser.add_argument('--delete-existing', action='store_true', help='Rebuild Graphiti indices/constraints before running.')
    return parser.parse_args()


def credentials_available() -> bool:
    azure_ready = all(
        os.getenv(name)
        for name in (
            'AZURE_OPENAI_API_KEY',
            'AZURE_OPENAI_ENDPOINT',
            'AZURE_OPENAI_API_VERSION',
            'AZURE_OPENAI_LLM_DEPLOYMENT',
        )
    )
    return azure_ready or bool(os.getenv('OPENAI_API_KEY'))




def _first_scalar(rows, key: str) -> int:
    if not rows:
        return 0

    def extract(value):
        if isinstance(value, dict):
            if key in value:
                return extract(value[key])
            if len(value) == 1:
                return extract(next(iter(value.values())))
            return 0
        if isinstance(value, (list, tuple)):
            if not value:
                return 0
            return extract(value[0])
        return value

    value = extract(rows[0])
    return int(value or 0)

def sample_episodes(limit: int) -> list[dict[str, object]]:
    now = datetime.now(timezone.utc)
    base = [
        {
            'name': 'autosar_e2e_library_v1',
            'body': json.dumps(
                {
                    'module': 'E2E Library',
                    'spec_type': 'WS',
                    'layer': 'BSW General',
                    'status': 'supported',
                    'source_pipeline': 'virtualECU_text_ingestion',
                    'confidence': 1.0,
                }
            ),
            'source_description': 'AUTOSAR CP module baseline',
            'reference_time': now - timedelta(days=2),
        },
        {
            'name': 'autosar_e2e_library_v2',
            'body': json.dumps(
                {
                    'module': 'E2E Library',
                    'spec_type': 'WS',
                    'layer': 'BSW General',
                    'status': 'deprecated',
                    'source_pipeline': 'cleanup_fix',
                    'confidence': 0.95,
                }
            ),
            'source_description': 'AUTOSAR CP module contradiction update',
            'reference_time': now - timedelta(days=1),
        },
        {
            'name': 'asam_xcp_protocol_v1',
            'body': json.dumps(
                {
                    'protocol': 'XCP',
                    'protocol_type': 'measurement_calibration',
                    'version': '1.5',
                    'source_pipeline': 'mistral_azrouter',
                    'confidence': 1.0,
                }
            ),
            'source_description': 'ASAM XCP protocol baseline',
            'reference_time': now - timedelta(hours=18),
        },
        {
            'name': 'asam_xcp_protocol_v2',
            'body': json.dumps(
                {
                    'protocol': 'XCP',
                    'protocol_type': 'measurement_calibration',
                    'version': '1.6-draft',
                    'source_pipeline': 'docling_kimi25',
                    'confidence': 0.7,
                }
            ),
            'source_description': 'ASAM XCP protocol update',
            'reference_time': now - timedelta(hours=12),
        },
        {
            'name': 'autosar_comm_module',
            'body': json.dumps(
                {
                    'module': 'ComM',
                    'spec_type': 'SWS',
                    'layer': 'Communication Services',
                    'status': 'supported',
                    'source_pipeline': 'virtualECU_text_ingestion',
                    'confidence': 1.0,
                }
            ),
            'source_description': 'AUTOSAR ComM module',
            'reference_time': now - timedelta(hours=6),
        },
        {
            'name': 'asam_xcp_transport',
            'body': json.dumps(
                {
                    'protocol': 'XCP on CAN',
                    'protocol_type': 'transport',
                    'version': '1.0',
                    'source_pipeline': 'docling_kimi25',
                    'confidence': 0.9,
                }
            ),
            'source_description': 'ASAM transport mapping',
            'reference_time': now - timedelta(hours=3),
        },
    ]
    return base[:limit]


async def edge_stats(graphiti, group_id: str) -> dict[str, int]:
    total_rows = await graphiti.driver.execute_query(
        'MATCH ()-[r]->() WHERE r.group_id = $group_id RETURN count(r) AS total_edges',
        group_id=group_id,
    )
    invalidated_rows = await graphiti.driver.execute_query(
        'MATCH ()-[r]->() WHERE r.group_id = $group_id AND (r.invalid_at IS NOT NULL OR r.expired_at IS NOT NULL) RETURN count(r) AS invalidated_edges',
        group_id=group_id,
    )
    valid_at_rows = await graphiti.driver.execute_query(
        'MATCH ()-[r]->() WHERE r.group_id = $group_id AND r.valid_at IS NOT NULL RETURN count(r) AS valid_at_edges',
        group_id=group_id,
    )
    return {
        'total_edges': _first_scalar(total_rows, 'total_edges'),
        'invalidated_edges': _first_scalar(invalidated_rows, 'invalidated_edges'),
        'valid_at_edges': _first_scalar(valid_at_rows, 'valid_at_edges'),
    }


async def search_snapshot(graphiti, *, query: str, group_id: str) -> dict[str, int]:
    search_results = await graphiti_search(graphiti, query, group_id=group_id, num_results=5)
    rich_results = await graphiti.search_(query=query, group_ids=[group_id])
    return {
        'search_results': len(search_results or []),
        'search__edge_results': len(getattr(rich_results, 'edges', []) or []),
        'search__node_results': len(getattr(rich_results, 'nodes', []) or []),
        'search__episode_results': len(getattr(rich_results, 'episodes', []) or []),
    }


async def run() -> None:
    args = parse_args()
    settings = load_settings()
    if not credentials_available():
        print(
            json.dumps(
                {
                    'ok': False,
                    'blocked': 'No OpenAI/Azure OpenAI credential available in environment.',
                    'benchmark_script': str(Path(__file__).name),
                    'latest_graphiti_core': '0.28.2',
                    'notes': [
                        'Sequential add_episode still exercises contradiction/invalidation logic.',
                        'Bulk add_episode_bulk is benchmarked for ingestion throughput, but upstream docs note invalidation/date extraction are not part of the bulk path.',
                    ],
                },
                indent=2,
            )
        )
        return

    graphiti = await initialize_graphiti(settings, delete_existing=args.delete_existing)
    _, _, EpisodeType, *_ = __import__('graph.graphiti_adapter', fromlist=['_load_graphiti_modules'])._load_graphiti_modules()
    from graphiti_core.utils.bulk_utils import RawEpisode

    episode_defs = sample_episodes(args.episodes)
    suffix = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    seq_group = f'{settings.graphiti_group_id}_benchmark_seq_{suffix}'
    bulk_group = f'{settings.graphiti_group_id}_benchmark_bulk_{suffix}'

    seq_start = perf_counter()
    seq_results = []
    for episode in episode_defs:
        started = perf_counter()
        result = await graphiti.add_episode(
            name=str(episode['name']),
            episode_body=str(episode['body']),
            source_description=str(episode['source_description']),
            reference_time=episode['reference_time'],
            source=EpisodeType.json,
            group_id=seq_group,
            entity_types={'AutosarModule': AutosarModule, 'AsamProtocol': AsamProtocol},
            edge_types={'ProvenanceEdge': ProvenanceEdge},
        )
        seq_results.append(
            {
                'name': episode['name'],
                'elapsed_ms': round((perf_counter() - started) * 1000, 2),
                'nodes': len(result.nodes),
                'edges': len(result.edges),
                'communities': len(result.communities),
            }
        )
    seq_elapsed_ms = round((perf_counter() - seq_start) * 1000, 2)

    raw_episodes = [
        RawEpisode(
            name=str(episode['name']),
            uuid=None,
            content=str(episode['body']),
            source_description=str(episode['source_description']),
            source=EpisodeType.json,
            reference_time=episode['reference_time'],
        )
        for episode in episode_defs
    ]
    bulk_elapsed_ms = None
    bulk_payload = None
    bulk_error = None
    bulk_start = perf_counter()
    try:
        bulk_result = await graphiti.add_episode_bulk(
            raw_episodes,
            group_id=bulk_group,
            entity_types={'AutosarModule': AutosarModule, 'AsamProtocol': AsamProtocol},
            edge_types={'ProvenanceEdge': ProvenanceEdge},
        )
        bulk_elapsed_ms = round((perf_counter() - bulk_start) * 1000, 2)
        bulk_payload = {
            'elapsed_ms': bulk_elapsed_ms,
            'episodes_created': len(bulk_result.episodes),
            'nodes': len(bulk_result.nodes),
            'edges': len(bulk_result.edges),
            'communities': len(bulk_result.communities),
            'edge_stats': await edge_stats(graphiti, bulk_group),
            'search_snapshot': await search_snapshot(graphiti, query=args.query, group_id=bulk_group),
        }
    except Exception as exc:
        bulk_elapsed_ms = round((perf_counter() - bulk_start) * 1000, 2)
        bulk_error = {'type': type(exc).__name__, 'message': str(exc), 'elapsed_ms': bulk_elapsed_ms}

    payload = {
        'ok': True,
        'graphiti_version': '0.28.2',
        'provider': 'azure' if os.getenv('AZURE_OPENAI_API_KEY') else 'openai',
        'local_embedder_fallback': bool(os.getenv('AZURE_OPENAI_API_KEY') and not os.getenv('AZURE_OPENAI_EMBEDDING_DEPLOYMENT')), 
        'episodes_benchmarked': len(episode_defs),
        'groups': {'sequential': seq_group, 'bulk': bulk_group},
        'sequential': {
            'elapsed_ms': seq_elapsed_ms,
            'per_episode': seq_results,
            'edge_stats': await edge_stats(graphiti, seq_group),
            'search_snapshot': await search_snapshot(graphiti, query=args.query, group_id=seq_group),
        },
        'bulk': bulk_payload,
        'bulk_error': bulk_error,
        'interpretation': {
            'bulk_expected_behavior': 'bulk is expected to improve ingestion throughput but may not invalidate prior facts/date extract the same way as sequential add_episode.',
            'recommended_seed_strategy': 'keep deterministic curated-source migration and direct Chroma imports for seed data; reserve Graphiti episodes for temporal/incremental updates.',
        },
    }
    print(json.dumps(payload, indent=2, default=str))

    close = getattr(graphiti, 'close', None)
    if callable(close):
        maybe_awaitable = close()
        if maybe_awaitable is not None:
            await maybe_awaitable


if __name__ == '__main__':
    asyncio.run(run())
