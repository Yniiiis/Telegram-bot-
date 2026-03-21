import logging
from collections.abc import AsyncIterator
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import get_current_user_bearer_or_query_token
from app.models.track import Track
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stream"])


def _relay_headers(resp: httpx.Response) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in ("content-type", "content-length", "content-range", "accept-ranges", "etag", "last-modified"):
        v = resp.headers.get(key)
        if v:
            out[key] = v
    return out


@router.get("/stream/{track_id}")
async def stream_track(
    track_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user_bearer_or_query_token),
) -> StreamingResponse:
    track = await db.get(Track, track_id)
    if track is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TRACK_NOT_FOUND", "message": "Track not found"},
        )

    range_hdr = request.headers.get("range") or request.headers.get("Range")
    req_headers = {"User-Agent": "TelegramMusicBot/1.0"}
    if range_hdr:
        req_headers["Range"] = range_hdr

    client = httpx.AsyncClient(
        timeout=httpx.Timeout(120.0, connect=15.0),
        follow_redirects=True,
    )
    stream_cm = client.stream("GET", track.audio_url, headers=req_headers)
    try:
        response = await stream_cm.__aenter__()
    except httpx.HTTPError as exc:
        await client.aclose()
        logger.warning("stream upstream connect failed track_id=%s: %s", track_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "UPSTREAM_UNREACHABLE",
                "message": "Could not reach the audio source. The file may be offline or blocked.",
            },
        ) from exc

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        await stream_cm.__aexit__(None, None, None)
        await client.aclose()
        code = "UPSTREAM_HTTP_ERROR"
        if exc.response.status_code in (403, 404):
            code = "UPSTREAM_NOT_AVAILABLE"
        logger.warning(
            "stream upstream status track_id=%s status=%s",
            track_id,
            exc.response.status_code,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": code,
                "message": "The audio source returned an error. This track may be unavailable.",
                "upstream_status": exc.response.status_code,
            },
        ) from exc

    headers = _relay_headers(response)

    async def body() -> AsyncIterator[bytes]:
        try:
            async for chunk in response.aiter_bytes(65536):
                yield chunk
        except httpx.StreamError as exc:
            logger.warning("stream interrupted track_id=%s: %s", track_id, exc)
            return
        finally:
            await stream_cm.__aexit__(None, None, None)
            await client.aclose()

    media_type = headers.pop("content-type", None) or "application/octet-stream"
    return StreamingResponse(
        body(),
        status_code=response.status_code,
        media_type=media_type,
        headers=headers,
    )
