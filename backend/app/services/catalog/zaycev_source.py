import asyncio
import logging
import re

import httpx

from app.services.catalog.protocol import CatalogSource
from app.services.catalog.zaycev_client import get_zaycev_access_token, zaycev_play_url, zaycev_search_raw
from app.services.external_track import ExternalTrack

logger = logging.getLogger(__name__)

_PAGE = 20


def _parse_duration(raw: str | None) -> int | None:
    if not raw:
        return None
    s = str(raw).strip()
    if s.isdigit():
        return int(s)
    m = re.match(r"^(\d{1,3}):(\d{2})$", s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


class ZaycevCatalogSource(CatalogSource):
    """Catalog via Zaycev official `api.zaycev.net/external` (search + per-track play URL)."""

    async def search(
        self,
        client: httpx.AsyncClient,
        query: str,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> list[ExternalTrack]:
        token = await get_zaycev_access_token(client)
        if not token:
            return []

        page_idx = offset // _PAGE + 1
        start = offset % _PAGE
        try:
            data = await zaycev_search_raw(client, token, query.strip(), page=page_idx)
        except Exception as exc:
            logger.warning("zaycev search failed: %s", exc)
            return []

        rows = data.get("tracks") or []
        slice_rows = rows[start : start + min(limit, 50)]

        sem = asyncio.Semaphore(10)

        async def play_for(tid: int) -> str | None:
            async with sem:
                return await zaycev_play_url(client, token, tid)

        prepared: list[tuple[dict, int]] = []
        for item in slice_rows:
            if not isinstance(item, dict):
                continue
            if item.get("block") or item.get("phantom"):
                continue
            tid = item.get("id")
            if tid is None:
                continue
            try:
                tid_int = int(tid)
            except (TypeError, ValueError):
                continue
            prepared.append((item, tid_int))

        audios = await asyncio.gather(*[play_for(tid) for _, tid in prepared])

        out: list[ExternalTrack] = []
        for (item, tid_int), audio in zip(prepared, audios):
            if not audio:
                continue
            title = str(item.get("track") or "Unknown").strip() or "Unknown"
            artist = str(item.get("artistName") or "Unknown").strip() or "Unknown"
            cover = item.get("trackImageUrl") or item.get("artistImageUrlSquare250")
            out.append(
                ExternalTrack(
                    source="zaycev",
                    external_id=str(tid_int),
                    title=title,
                    artist=artist,
                    duration_sec=_parse_duration(item.get("duration")),
                    audio_url=audio,
                    cover_url=str(cover).strip() if cover else None,
                    license_url="https://zaycev.net",
                    license_short="zaycev",
                )
            )
            if len(out) >= limit:
                break

        return out
