from __future__ import annotations

from dataclasses import asdict, dataclass
from time import sleep
from typing import Any

from falkordb import FalkorDB

from common.settings import Settings, load_settings


@dataclass(frozen=True)
class FalkorDBHealth:
    ok: bool
    detail: str
    database: str
    graphs: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FalkorDBClient:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        max_retries: int = 3,
        connect_timeout: float = 2.0,
        socket_timeout: float = 30.0,
    ) -> None:
        self.settings = settings or load_settings()
        self.max_retries = max_retries
        self.connect_timeout = connect_timeout
        self.socket_timeout = socket_timeout
        self._client: FalkorDB | None = None

    def connect(self) -> FalkorDB:
        if self._client is not None:
            return self._client

        delays = [0.2, 0.5, 1.0]
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                self._client = FalkorDB(
                    host=self.settings.falkordb_host,
                    port=self.settings.falkordb_port,
                    username=self.settings.falkordb_username,
                    password=self.settings.falkordb_password,
                    socket_connect_timeout=self.connect_timeout,
                    socket_timeout=self.socket_timeout,
                )
                self._client.execute_command('PING')
                return self._client
            except Exception as exc:  # pragma: no cover - runtime/network protection
                last_error = exc
                self._client = None
                if attempt < self.max_retries - 1:
                    sleep(delays[min(attempt, len(delays) - 1)])
        raise RuntimeError(f'Unable to connect to FalkorDB: {last_error}')

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def list_graphs(self) -> list[str]:
        return list(self.connect().list_graphs())

    def select_graph(self, graph_name: str | None = None):
        graph_name = graph_name or self.settings.falkordb_database
        return self.connect().select_graph(graph_name)

    def query(
        self,
        cypher: str,
        params: dict[str, object] | None = None,
        timeout: int | None = None,
        *,
        read_only: bool = False,
    ):
        graph = self.select_graph()
        if read_only:
            return graph.ro_query(cypher, params=params, timeout=timeout)
        return graph.query(cypher, params=params, timeout=timeout)

    def health(self) -> FalkorDBHealth:
        try:
            client = self.connect()
            ping_ok = bool(client.execute_command('PING'))
            graphs = self.list_graphs()
            return FalkorDBHealth(
                ok=ping_ok,
                detail='ok',
                database=self.settings.falkordb_database,
                graphs=graphs,
            )
        except Exception as exc:  # pragma: no cover - runtime/network protection
            return FalkorDBHealth(
                ok=False,
                detail=str(exc),
                database=self.settings.falkordb_database,
                graphs=[],
            )


def falkordb_health(settings: Settings | None = None) -> FalkorDBHealth:
    client = FalkorDBClient(settings=settings)
    try:
        return client.health()
    finally:
        client.close()
