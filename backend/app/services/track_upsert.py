from uuid import uuid4

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.track import Track
from app.services.external_track import ExternalTrack


async def upsert_external_tracks(session: AsyncSession, rows: list[ExternalTrack]) -> list[Track]:
    if not rows:
        return []

    dialect = session.get_bind().dialect.name
    insert_fn = sqlite_insert if dialect == "sqlite" else pg_insert
    conflict_kw: dict = (
        {"index_elements": ["source", "external_id"]}
        if dialect == "sqlite"
        else {"constraint": "uq_tracks_source_external"}
    )

    values = [
        {
            "id": uuid4(),
            "source": row.source,
            "external_id": row.external_id,
            "title": row.title,
            "artist": row.artist,
            "duration_sec": row.duration_sec,
            "audio_url": row.audio_url,
            "cover_url": row.cover_url,
            "license_url": row.license_url,
            "license_short": row.license_short,
        }
        for row in rows
    ]

    ins = insert_fn(Track).values(values)
    stmt = ins.on_conflict_do_update(
        **conflict_kw,
        set_={
            "title": ins.excluded.title,
            "artist": ins.excluded.artist,
            "duration_sec": ins.excluded.duration_sec,
            "audio_url": ins.excluded.audio_url,
            "cover_url": ins.excluded.cover_url,
            "license_url": ins.excluded.license_url,
            "license_short": ins.excluded.license_short,
        },
    ).returning(Track)

    res = await session.execute(stmt, execution_options={"populate_existing": True})
    out = list(res.scalars().all())
    await session.commit()
    return out
