"""Optional local file cache for /stream (serve pre-downloaded `{track_id}.audio`; supports Range via Starlette)."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from starlette.responses import FileResponse

logger = logging.getLogger(__name__)


def try_file_cache_response(track_id: UUID, cache_dir: str | None) -> FileResponse | None:
    """
    If `STREAM_CACHE_DIR` is set and `cache_dir / f"{track_id}.audio"` exists, serve it.
    Populate the folder externally or with a future prefetch job; no full-buffer download in-request.
    """
    if not cache_dir or not cache_dir.strip():
        return None
    root = Path(cache_dir).expanduser().resolve()
    path = root / f"{track_id}.audio"
    try:
        if not path.is_file():
            return None
        size = path.stat().st_size
    except OSError as exc:
        logger.debug("stream cache stat failed: %s", exc)
        return None
    if size < 4096:
        return None
    return FileResponse(
        str(path),
        media_type="audio/mpeg",
        headers={"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=86400"},
    )
