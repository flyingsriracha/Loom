from __future__ import annotations

import asyncio
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import igraph as ig
import leidenalg
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.nodes import CommunityNode

from common.settings import load_settings
from graph.client import FalkorDBClient
from retrieval.embeddings import encode_text

DOMAIN_LABELS = ('Standard', 'Protocol', 'Requirement', 'Module', 'Interface', 'Concept', 'Command', 'ErrorCode', 'Parameter', 'Table')
SEMANTIC_EDGE_TYPES = ('DEFINES', 'PART_OF', 'CONSTRAINS', 'REFERENCES')
CACHE_PATH = Path(__file__).resolve().parents[1] / 'artifacts' / 'community_cache.json'


class CommunityBuilder:
    def __init__(self, client: FalkorDBClient | None = None) -> None:
        self.client = client or FalkorDBClient()
        self.settings = self.client.settings

    def refresh(self) -> dict[str, Any]:
        graph = self.client.select_graph()
        nodes = self._load_nodes(graph)
        edges = self._load_edges(graph)
        communities = self._detect_communities(nodes, edges)
        generated_at = datetime.now(timezone.utc).isoformat()
        root_id = self._community_uuid('root')

        community_payloads: list[dict[str, Any]] = []
        for idx, member_ids in enumerate(communities):
            community_uuid = self._community_uuid('0', str(idx), *sorted(member_ids)[:25])
            community_payloads.append(self._community_props(nodes, member_ids, community_uuid, level=0, generated_at=generated_at))

        root_payload = self._root_props(nodes, communities, root_id=root_id, generated_at=generated_at)
        payload = {
            'generated_at': generated_at,
            'persist_mode': 'graph_and_file_cache',
            'root': root_payload,
            'communities': community_payloads,
        }
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(payload, indent=2))

        self._persist_to_graph(community_payloads, root_payload)

        return {
            'communities_created': len(community_payloads),
            'root_id': root_id,
            'member_nodes': sum(len(members) for members in communities),
            'generated_at': generated_at,
            'persist_mode': 'graph_and_file_cache',
            'cache_path': str(CACHE_PATH),
        }


    def _run_async(self, coro) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()

    def load_cache(self) -> dict[str, Any] | None:
        if not CACHE_PATH.exists():
            return None
        return json.loads(CACHE_PATH.read_text())

    def _persist_to_graph(self, communities: list[dict[str, Any]], root_payload: dict[str, Any]) -> None:
        import asyncio

        async def _run() -> None:
            driver = FalkorDriver(
                host=self.settings.falkordb_host,
                port=self.settings.falkordb_port,
                username=self.settings.falkordb_username,
                password=self.settings.falkordb_password,
                database=self.settings.falkordb_database,
            )
            try:
                await driver.execute_query(
                    'MATCH (c:Community) WHERE c.group_id = $group_id DETACH DELETE c',
                    group_id=self.settings.graphiti_group_id,
                )
                payloads = [*communities, root_payload]
                for item in payloads:
                    node = CommunityNode(
                        uuid=item['id'],
                        name=item['name'],
                        group_id=self.settings.graphiti_group_id,
                        labels=['Community'],
                        created_at=datetime.fromisoformat(item['generated_at']),
                        summary=item['summary'],
                        name_embedding=item['embedding'],
                    )
                    await driver.community_node_ops.save(driver, node)
                    await driver.execute_query(
                        'MATCH (c:Community {uuid: $uuid}) '                        'SET c.level = $level, '                        '    c.member_count = $member_count, '                        '    c.generated_at = $generated_at, '                        '    c.source_systems_json = $source_systems_json, '                        '    c.standard_names_json = $standard_names_json, '                        '    c.member_sample_ids_json = $member_sample_ids_json',
                        uuid=item['id'],
                        level=item['level'],
                        member_count=item['member_count'],
                        generated_at=item['generated_at'],
                        source_systems_json=json.dumps(item['source_systems']),
                        standard_names_json=json.dumps(item['standard_names']),
                        member_sample_ids_json=json.dumps(item['member_sample_ids']),
                    )
                for item in communities:
                    await driver.execute_query(
                        'MATCH (c:Community {uuid: $child}), (root:Community {uuid: $root}) MERGE (c)-[:MEMBER_OF]->(root)',
                        child=item['id'],
                        root=root_payload['id'],
                    )
            finally:
                close = getattr(driver, 'close', None)
                if callable(close):
                    maybe = close()
                    if maybe is not None:
                        await maybe

        self._run_async(_run())

    def _load_nodes(self, graph: Any) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for label in DOMAIN_LABELS:
            rows = graph.query(f'MATCH (n:{label}) WHERE coalesce(n.superseded_at, "") = "" RETURN n.id, labels(n), properties(n)').result_set
            for node_id, labels, props in rows:
                out[str(node_id)] = {'labels': list(labels), 'props': dict(props)}
        return out

    def _load_edges(self, graph: Any) -> list[tuple[str, str]]:
        rows = graph.query(
            'MATCH (a)-[r]->(b) '
            'WHERE type(r) IN $types '
            'RETURN a.id, b.id',
            params={'types': list(SEMANTIC_EDGE_TYPES)},
        ).result_set
        return [(str(a), str(b)) for a, b in rows]

    def _detect_communities(self, nodes: dict[str, dict[str, Any]], edges: list[tuple[str, str]]) -> list[list[str]]:
        node_ids = list(nodes.keys())
        if not node_ids:
            return []
        if not edges:
            return [node_ids]
        id_to_index = {node_id: idx for idx, node_id in enumerate(node_ids)}
        graph = ig.Graph(directed=False)
        graph.add_vertices(len(node_ids))
        graph.add_edges([(id_to_index[a], id_to_index[b]) for a, b in edges if a in id_to_index and b in id_to_index and a != b])
        partition = leidenalg.find_partition(graph, leidenalg.ModularityVertexPartition)
        communities = [[node_ids[idx] for idx in community] for community in partition]
        return communities or [node_ids]

    def _community_props(self, nodes: dict[str, dict[str, Any]], member_ids: list[str], community_id: str, *, level: int, generated_at: str) -> dict[str, Any]:
        labels = Counter()
        source_systems = Counter()
        standards = Counter()
        names: list[str] = []
        descriptions: list[str] = []
        for member_id in member_ids:
            item = nodes[member_id]
            for label in item['labels']:
                labels[label] += 1
            props = item['props']
            if props.get('source_system'):
                source_systems[str(props['source_system'])] += 1
            if props.get('standard_name'):
                standards[str(props['standard_name'])] += 1
            name = props.get('name') or props.get('title')
            if name:
                names.append(str(name))
            description = props.get('description')
            if description:
                descriptions.append(str(description))
        summary = self._render_summary(level, labels, source_systems, standards, names, descriptions)
        return {
            'id': community_id,
            'name': f'community_{community_id[:8]}',
            'level': level,
            'summary': summary,
            'embedding': encode_text(summary),
            'member_count': len(member_ids),
            'member_sample_ids': member_ids[:50],
            'source_systems': list(source_systems.keys()),
            'standard_names': list(standards.keys()),
            'generated_at': generated_at,
            'updated_at': generated_at,
        }

    def _root_props(self, nodes: dict[str, dict[str, Any]], communities: list[list[str]], *, root_id: str, generated_at: str) -> dict[str, Any]:
        all_ids = [member_id for community in communities for member_id in community]
        props = self._community_props(nodes, all_ids, root_id, level=1, generated_at=generated_at)
        props['name'] = 'loom_root_community'
        return props

    def _render_summary(self, level: int, labels: Counter, source_systems: Counter, standards: Counter, names: list[str], descriptions: list[str]) -> str:
        top_labels = ', '.join(f'{label}:{count}' for label, count in labels.most_common(5)) or 'no labels'
        top_sources = ', '.join(source_systems.keys()) or 'unknown source systems'
        top_standards = ', '.join(standard for standard, _ in standards.most_common(5)) or 'mixed standards'
        top_names = ', '.join(names[:8]) or 'unnamed nodes'
        top_desc = ' | '.join(descriptions[:3])
        return (
            f'Community level {level}. '
            f'Sources: {top_sources}. '
            f'Standards: {top_standards}. '
            f'Label mix: {top_labels}. '
            f'Representative nodes: {top_names}. '
            f'Key details: {top_desc}'
        ).strip()

    def _community_uuid(self, *parts: str) -> str:
        from graph.identities import stable_id
        return stable_id('community', *parts)
