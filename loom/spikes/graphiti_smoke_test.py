from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from pprint import pprint

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.settings import load_settings
from graph.client import falkordb_reachable
from graph.graphiti_adapter import initialize_graphiti, smoke_episode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Validate Loom Graphiti/FalkorDB adapter assumptions.')
    parser.add_argument('--with-episode', action='store_true', help='Run a JSON episode ingestion smoke test.')
    parser.add_argument('--delete-existing', action='store_true', help='Rebuild Graphiti indices with delete_existing=True.')
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    settings = load_settings()
    reachable, detail = falkordb_reachable()
    if not reachable:
        raise SystemExit(f'FalkorDB is not reachable at {settings.falkordb_host}:{settings.falkordb_port}: {detail}')

    if not args.with_episode and not (os.getenv('OPENAI_API_KEY') or os.getenv('AZURE_OPENAI_API_KEY')):
        os.environ['OPENAI_API_KEY'] = 'dummy'

    graphiti = await initialize_graphiti(settings, delete_existing=args.delete_existing)
    result = {
        'connected': True,
        'database': settings.falkordb_database,
        'group_id': settings.graphiti_group_id,
        'indices_built': True,
    }
    if args.with_episode:
        if not (os.getenv('OPENAI_API_KEY') or os.getenv('AZURE_OPENAI_API_KEY')):
            raise SystemExit('Set OPENAI_API_KEY or AZURE_OPENAI_API_KEY before using --with-episode.')
        result['episode'] = await smoke_episode(graphiti, group_id=settings.graphiti_group_id)
    pprint(result)
    close = getattr(graphiti, 'close', None)
    if callable(close):
        maybe_awaitable = close()
        if maybe_awaitable is not None:
            await maybe_awaitable


if __name__ == '__main__':
    asyncio.run(main())
