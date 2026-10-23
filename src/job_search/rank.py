"""Embedding pre-filter: rank postings by cosine similarity to the profile, keep the top k.

Runs a local multilingual model (fastembed/ONNX), so German and English postings are compared on
meaning, not vocabulary, and nothing is sent to an API.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np

from job_search.config import DATA_DIR
from job_search.models import Posting

Embedder = Callable[[Sequence[str]], np.ndarray]


def fastembed_embedder(model_name: str) -> Embedder:
    from fastembed import TextEmbedding

    model = TextEmbedding(model_name=model_name, cache_dir=str(DATA_DIR / "models"))
    e5 = "e5" in model_name.lower()

    def embed(texts: Sequence[str], *, query: bool = False) -> np.ndarray:
        if e5:
            texts = [("query: " if query else "passage: ") + t for t in texts]
        return np.array(list(model.embed(list(texts))))

    return embed


_WINDOW, _STRIDE, _MAX_SCAN = 500, 400, 6000
TITLE_WEIGHT = 0.5


def _windows(description: str) -> list[str]:
    """Overlapping windows over the description: small models read only ~128 tokens, and postings
    often open with company boilerplate, so the role-specific part must get its own window."""
    text = description[:_MAX_SCAN]
    return [text[i:i + _WINDOW] for i in range(0, max(len(text), 1), _STRIDE)] or [""]


def _cosine(docs: np.ndarray, query: np.ndarray) -> np.ndarray:
    return docs @ query / (np.linalg.norm(docs, axis=1) * np.linalg.norm(query) + 1e-12)


def rank(profile: str, postings: list[Posting], top_k: int, embed: Embedder) -> list[tuple[Posting, float]]:
    """Return up to `top_k` (posting, similarity) pairs, most similar first.

    similarity = TITLE_WEIGHT * cos(title, profile) + (1 - TITLE_WEIGHT) * max over description
    windows of cos(window, profile). Ranking on title + best window (live run 2026-10-23) put
    6 of 7 known-good postings in the top 25, versus 3 of 7 for title + first 2,000 characters.
    """
    if not postings:
        return []
    try:
        query = embed([profile], query=True)[0]
    except TypeError:  # simple embedders in tests take no keyword
        query = embed([profile])[0]
    title_sims = _cosine(embed([p.title for p in postings]), query)
    windows = [_windows(p.description) for p in postings]
    flat = _cosine(embed([w for ws in windows for w in ws]), query)
    best, i = [], 0
    for ws in windows:
        best.append(flat[i:i + len(ws)].max())
        i += len(ws)
    sims = TITLE_WEIGHT * title_sims + (1 - TITLE_WEIGHT) * np.array(best)
    order = np.argsort(-sims, kind="stable")[:top_k]
    return [(postings[j], float(sims[j])) for j in order]
