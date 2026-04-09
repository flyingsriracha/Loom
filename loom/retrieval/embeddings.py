from __future__ import annotations

from functools import lru_cache
from typing import Iterable

import numpy as np
from sentence_transformers import SentenceTransformer

DEFAULT_EMBEDDING_MODEL = 'sentence-transformers/all-MiniLM-L6-v2'


@lru_cache(maxsize=1)
def get_embedder(model_name: str = DEFAULT_EMBEDDING_MODEL) -> SentenceTransformer:
    return SentenceTransformer(model_name)


def encode_texts(texts: Iterable[str], *, model_name: str = DEFAULT_EMBEDDING_MODEL) -> list[list[float]]:
    values = list(texts)
    if not values:
        return []
    matrix = get_embedder(model_name).encode(values, normalize_embeddings=True)
    return [[float(v) for v in row] for row in matrix]


def encode_text(text: str, *, model_name: str = DEFAULT_EMBEDDING_MODEL) -> list[float]:
    rows = encode_texts([text], model_name=model_name)
    return rows[0] if rows else []


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    arr_a = np.asarray(a, dtype=np.float32)
    arr_b = np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(arr_a) * np.linalg.norm(arr_b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(arr_a, arr_b) / denom)
