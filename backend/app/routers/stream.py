import logging
from collections.abc import AsyncIterator
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from starlette.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.deps import get_current_user_bearer_or_query_token
from app.models.track import Track
from app.models.user import User
from app.services.playback_media import PlaybackResolveError, resolve_playback_media
from app.services.stream_disk_cache import try_file_cache_response

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stream"])

_STREAM_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def _relay_headers(resp: httpx.Response) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in ("content-type", "content-length", "content-range", "accept-ranges", "etag", "last-modified"):
        v = resp.headers.get(key)
        if v:
            out[key] = v
    return out


def _playback_resolve_http(exc: PlaybackResolveError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={"code": exc.code, "message": exc.message},
    )


@router.get("/stream/{track_id}", response_model=None)
async def stream_track(
    track_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user_bearer_or_query_token),
) -> FileResponse | StreamingResponse:
    track = await db.get(Track, track_id)
    if track is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TRACK_NOT_FOUND", "message": "Track not found"},
        )

    cached = try_file_cache_response(track_id, settings.stream_cache_dir)
    if cached is not None:
        return cached

    range_hdr = request.headers.get("range") or request.headers.get("Range")
    catalog_http: httpx.AsyncClient = request.app.state.http_client
    stream_http: httpx.AsyncClient = getattr(
        request.app.state, "stream_http_client", catalog_http
    )

    try:
        media_url, upstream_extras, _ = await resolve_playback_media(db, track, catalog_http)
    except PlaybackResolveError as exc:
        raise _playback_resolve_http(exc) from exc

    req_headers: dict[str, str] = dict(upstream_extras)
    req_headers.setdefault("User-Agent", _STREAM_BROWSER_UA)
    req_headers.setdefault("Accept", "*/*")

    if range_hdr:
        req_headers["Range"] = range_hdr

    # Dedicated stream pool (separate from catalog) — keep-alive + bounded concurrency; avoids per-request client cost.
    client = stream_http
    stream_cm = client.stream("GET", media_url, headers=req_headers)
    try:
        response = await stream_cm.__aenter__()
    except httpx.HTTPError as exc:
        logger.warning("stream upstream connect failed track_id=%s: %s", track_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "UPSTREAM_UNREACHABLE",
                "message": "Could not reach the audio source.",
            },
        ) from exc

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        await stream_cm.__aexit__(None, None, None)
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

    media_type = (headers.pop("content-type", None) or "").split(";")[0].strip().lower()
    if not media_type or media_type in ("application/octet-stream", "binary/octet-stream"):
        if track.source == "hitmotop":
            media_type = "audio/mpeg"
        else:
            media_type = "application/octet-stream"
    elif track.source == "hitmotop" and not media_type.startswith("audio/"):
        # Telegram WebView often rejects non-audio MIME even for .mp3 bytes.
        media_type = "audio/mpeg"

    return StreamingResponse(
        body(),
        status_code=response.status_code,
        media_type=media_type,
        headers=headers,
    )
