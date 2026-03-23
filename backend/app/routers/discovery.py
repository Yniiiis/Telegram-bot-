import asyncio
import logging
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.deps import get_current_user
from app.models.featured_new_release import FeaturedNewRelease
from app.models.track import Track
from app.models.user import User
from app.schemas.discovery import (
    DailyContextOut,
    DiscoveryMetaResponse,
    DiscoveryPicksResponse,
    TrackListResponse,
)
from app.schemas.track import TrackOut
from app.services.discovery import (
    CONTEXT_QUERY_BATCHES,
    DAILY_CONTEXTS,
    catalog_source_ids,
    collect_discovery_picks,
    weekday_mood_query,
)
from app.services.track_availability import filter_tracks_by_availability
from app.services.track_upsert import upsert_external_tracks

logger = logging.getLogger(__name__)

router = APIRouter(tags=["discovery"])

_last_new_releases_touch = 0.0
_nr_touch_lock = asyncio.Lock()


@router.get("/discovery/meta", response_model=DiscoveryMetaResponse)
async def discovery_meta(_user: User = Depends(get_current_user)) -> DiscoveryMetaResponse:
    return DiscoveryMetaResponse(
        contexts=[DailyContextOut(**c) for c in DAILY_CONTEXTS],
        catalog_sources=catalog_source_ids(),
        weekday_mood_query=weekday_mood_query(),
    )


@router.get("/discovery/new-releases", response_model=TrackListResponse)
async def discovery_new_releases(
    request: Request,
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> TrackListResponse:
    client: httpx.AsyncClient = request.app.state.http_client
    from app.services.discovery import collect_new_release_candidates, refresh_featured_new_releases

    global _last_new_releases_touch
    do_refresh = False
    async with _nr_touch_lock:
        now = time.monotonic()
        if now - _last_new_releases_touch >= settings.new_releases_user_touch_sec:
            _last_new_releases_touch = now
            do_refresh = True
    if do_refresh:
        try:
            await asyncio.wait_for(refresh_featured_new_releases(db, client), timeout=14.0)
        except Exception as exc:
            logger.warning("new-releases user-touch refresh failed: %s", exc)

    fetch_n = limit
    if settings.track_availability_enabled:
        fetch_n = min(60, max(limit * 2, limit + 14))
    stmt = (
        select(Track)
        .join(FeaturedNewRelease, FeaturedNewRelease.track_id == Track.id)
        .order_by(FeaturedNewRelease.position)
        .limit(fetch_n)
    )
    res = await db.execute(stmt)
    rows = list(res.scalars().all())
    if rows:
        rows = await filter_tracks_by_availability(client, rows)
        return TrackListResponse(tracks=[TrackOut.model_validate(t) for t in rows[:limit]])

    # Cold start: no rows yet — populate once.
    try:
        candidates = await collect_new_release_candidates(client)
        if candidates:
            tracks = await upsert_external_tracks(db, candidates[: settings.new_releases_store_limit])
            tracks = await filter_tracks_by_availability(client, tracks)
            await db.execute(delete(FeaturedNewRelease))
            for i, tr in enumerate(tracks):
                db.add(FeaturedNewRelease(track_id=tr.id, position=i))
            await db.commit()
            return TrackListResponse(
                tracks=[TrackOut.model_validate(t) for t in tracks[:limit]],
            )
    except Exception as exc:
        logger.warning("inline new-releases fallback failed: %s", exc)

    return TrackListResponse(tracks=[])


@router.get("/discovery/picks", response_model=DiscoveryPicksResponse)
async def discovery_picks(
    request: Request,
    context: str | None = Query(None, description="id from /discovery/meta contexts"),
    mode: str = Query("weekday", description="weekday | context"),
    limit: int = Query(18, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> DiscoveryPicksResponse:
    client: httpx.AsyncClient = request.app.state.http_client
    m = (mode or "weekday").strip().lower()
    if m == "context" and not (context and context.strip()):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="context is required when mode=context",
        )
    if m == "context" and context and context.strip() not in CONTEXT_QUERY_BATCHES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown context")

    pick_limit = limit
    if settings.track_availability_enabled:
        pick_limit = min(50, max(limit * 2, limit + 12))

    try:
        external, display_name, ctx_id = await collect_discovery_picks(
            client,
            mode=m,
            context=context.strip() if context else None,
            limit=pick_limit,
        )
    except ValueError as exc:
        if str(exc) == "context_required":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="context is required when mode=context",
            ) from exc
        if str(exc) == "unknown_context":
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown context") from exc
        raise

    tracks = await upsert_external_tracks(db, external)
    tracks = await filter_tracks_by_availability(client, tracks)
    tracks = tracks[:limit]
    return DiscoveryPicksResponse(
        tracks=[TrackOut.model_validate(t) for t in tracks],
        used_query=display_name,
        context_id=ctx_id,
        mode="context" if m == "context" else "weekday",
    )
