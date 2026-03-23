"""Blend relevance order with popularity (listeners) and novelty (released_ts) + stable variety per query page."""

from __future__ import annotations

import hashlib
import math
import random
import time

from app.services.catalog.relevance import relevance_score
from app.services.external_track import ExternalTrack


def diversify_search_results(
    tracks: list[ExternalTrack],
    query: str,
    *,
    offset: int = 0,
) -> list[ExternalTrack]:
    if len(tracks) < 2:
        return tracks

    now = time.time()
    q = query.strip()

    def novelty_score(t: ExternalTrack) -> float:
        ts = t.released_ts
        if not ts or ts <= 0:
            return 0.35
        age_days = max(0.0, (now - ts) / 86400.0)
        return max(0.0, 1.0 - min(380.0, age_days) / 380.0)

    def pop_score(t: ExternalTrack) -> float:
        lst = t.listeners or 0
        return min(1.0, math.log1p(max(0, lst)) / 14.0)

    seed = int(hashlib.sha256(f"{q}\0{offset}".encode()).hexdigest()[:12], 16)
    rng = random.Random(seed)

    scored: list[tuple[float, int, ExternalTrack]] = []
    for i, t in enumerate(tracks):
        rel = relevance_score(q, t.title, t.artist)
        mix = 0.48 * rel + 0.28 * pop_score(t) + 0.24 * novelty_score(t)
        jitter = rng.random() * 0.06
        scored.append((mix + jitter, i, t))

    scored.sort(key=lambda x: (-x[0], x[1]))
    return [t for _, __, t in scored]
