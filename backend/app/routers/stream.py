import asyncio
import logging
from collections.abc import AsyncIterator
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.deps import get_current_user_bearer_or_query_token
from app.models.track import Track
from app.models.user import User
from app.services.catalog.soundcloud_source import soundcloud_refresh_play_url
from app.services.catalog.zaycev_client import get_zaycev_access_token, zaycev_play_url
from app.services.youtube_audio import extract_youtube_audio_url

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stream"])

# Many CDNs (Zaycev, Hitmotop MP3, etc.) reject non-browser User-Agent on direct file URLs.
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

    if track.source == "youtube_music":
        resolved = await asyncio.to_thread(extract_youtube_audio_url, track.audio_url)
        if not resolved:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "YOUTUBE_EXTRACT_FAILED",
                    "message": "Could not resolve YouTube audio. Install yt-dlp or try another track.",
                },
            )
        media_url, upstream_headers = resolved
        req_headers = dict(upstream_headers)
        if not req_headers.get("User-Agent"):
            req_headers["User-Agent"] = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
        if range_hdr:
            req_headers["Range"] = range_hdr

        client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                settings.stream_read_timeout_sec,
                connect=settings.stream_connect_timeout_sec,
            ),
            follow_redirects=True,
        )
        stream_cm = client.stream("GET", media_url, headers=req_headers)
        try:
            response = await stream_cm.__aenter__()
        except httpx.HTTPError as exc:
            await client.aclose()
            logger.warning("youtube stream connect failed track_id=%s: %s", track_id, exc)
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
            await client.aclose()
            logger.warning(
                "youtube stream http track_id=%s status=%s",
                track_id,
                exc.response.status_code,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "UPSTREAM_NOT_AVAILABLE",
                    "message": "The audio source returned an error.",
                    "upstream_status": exc.response.status_code,
                },
            ) from exc

        headers = _relay_headers(response)

        async def body_yt() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.aiter_bytes(65536):
                    yield chunk
            except httpx.StreamError as exc:
                logger.warning("youtube stream interrupted track_id=%s: %s", track_id, exc)
                return
            finally:
                await stream_cm.__aexit__(None, None, None)
                await client.aclose()

        media_type = headers.pop("content-type", None) or "application/octet-stream"
        return StreamingResponse(
            body_yt(),
            status_code=response.status_code,
            media_type=media_type,
            headers=headers,
        )

    media_url = track.audio_url
    if track.source == "soundcloud":
        api = request.app.state.http_client
        sc_cid = (settings.soundcloud_client_id or "").strip()
        if not sc_cid:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "SOUNDCLOUD_NO_CLIENT_ID",
                    "message": "SoundCloud client_id is not configured.",
                },
            )
        fresh = await soundcloud_refresh_play_url(api, track.external_id, sc_cid)
        if not fresh:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "SOUNDCLOUD_RESOLVE_FAILED",
                    "message": "Could not resolve SoundCloud stream for this track.",
                },
            )
        if fresh != track.audio_url:
            track.audio_url = fresh
            await db.commit()
        media_url = fresh

    if track.source == "zaycev":
        api = request.app.state.http_client
        ztok = await get_zaycev_access_token(api)
        if not ztok:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "ZAYCEV_AUTH",
                    "message": "Could not obtain Zaycev access token.",
                },
            )
        try:
            zid = int(track.external_id)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "ZAYCEV_BAD_ID", "message": "Invalid Zaycev track id."},
            ) from exc
        fresh = await zaycev_play_url(api, ztok, zid)
        if not fresh:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "ZAYCEV_PLAY",
                    "message": "Zaycev did not return a play URL for this track.",
                },
            )
        if fresh != track.audio_url:
            track.audio_url = fresh
            await db.commit()
        media_url = fresh

    req_headers = {"User-Agent": _STREAM_BROWSER_UA, "Accept": "*/*"}
    if range_hdr:
        req_headers["Range"] = range_hdr

    client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            settings.stream_read_timeout_sec,
            connect=settings.stream_connect_timeout_sec,
        ),
        follow_redirects=True,
    )
    stream_cm = client.stream("GET", media_url, headers=req_headers)
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
