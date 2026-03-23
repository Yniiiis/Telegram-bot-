import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ActivityPicksWave } from "../components/ActivityPicksWave";
import { SearchBar } from "../components/SearchBar";
import { TrackListSkeleton } from "../components/Skeleton";
import { TrackList } from "../components/TrackList";
import {
  addFavorite,
  getDiscoveryMeta,
  getDiscoveryPicks,
  getFavorites,
  getNewReleases,
  getRecentTracks,
  removeFavorite,
  searchTracks,
} from "../lib/api";
import { useAuthStore } from "../store/authStore";
import { usePlayerStore } from "../store/playerStore";
import type { DailyContextMeta, Track } from "../types";

export function HomePage() {
  const navigate = useNavigate();
  const openArtist = (artist: string) => {
    const t = artist.trim();
    if (t) navigate(`/artist?name=${encodeURIComponent(t)}`);
  };
  const token = useAuthStore((s) => s.token);
  const setQueue = usePlayerStore((s) => s.setQueue);
  const [q, setQ] = useState("");
  const [recs, setRecs] = useState<Track[]>([]);
  const [recent, setRecent] = useState<Track[]>([]);
  const [newTracks, setNewTracks] = useState<Track[]>([]);
  const [contexts, setContexts] = useState<DailyContextMeta[]>([]);
  const [weekdayHint, setWeekdayHint] = useState("");
  const [picksTracks, setPicksTracks] = useState<Track[]>([]);
  const [picksLabel, setPicksLabel] = useState("");
  const [activeContextId, setActiveContextId] = useState<string | null>(null);
  const [loadingRecs, setLoadingRecs] = useState(true);
  const [loadingRecent, setLoadingRecent] = useState(true);
  const [loadingNew, setLoadingNew] = useState(true);
  const [loadingPicks, setLoadingPicks] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [favoriteIds, setFavoriteIds] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    if (!token) return;
    void getFavorites(token)
      .then((tracks) => setFavoriteIds(new Set(tracks.map((t) => t.id))))
      .catch(() => {});
  }, [token]);

  const loadRecent = useCallback(async () => {
    if (!token) return;
    setLoadingRecent(true);
    try {
      const tracks = await getRecentTracks(token, 15);
      setRecent(tracks);
    } catch {
      setRecent([]);
    } finally {
      setLoadingRecent(false);
    }
  }, [token]);

  const loadRecs = useCallback(async () => {
    if (!token) return;
    setLoadingRecs(true);
    setErr(null);
    try {
      const tracks = await searchTracks(token, "pop", 12);
      setRecs(tracks);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoadingRecs(false);
    }
  }, [token]);

  const loadNew = useCallback(async () => {
    if (!token) return;
    setLoadingNew(true);
    try {
      const tracks = await getNewReleases(token, 18);
      setNewTracks(tracks);
    } catch {
      setNewTracks([]);
    } finally {
      setLoadingNew(false);
    }
  }, [token]);

  const loadMetaAndPicks = useCallback(async () => {
    if (!token) return;
    setLoadingPicks(true);
    try {
      const meta = await getDiscoveryMeta(token);
      setContexts(meta.contexts);
      setWeekdayHint(meta.weekday_mood_query);
      const picks = await getDiscoveryPicks(token, { mode: "weekday" });
      setPicksTracks(picks.tracks);
      setPicksLabel(picks.used_query);
      setActiveContextId(null);
    } catch {
      setContexts([]);
      setPicksTracks([]);
      setPicksLabel("");
    } finally {
      setLoadingPicks(false);
    }
  }, [token]);

  const loadContextPicks = useCallback(async (ctx: DailyContextMeta) => {
    if (!token) return;
    setLoadingPicks(true);
    setActiveContextId(ctx.id);
    try {
      const picks = await getDiscoveryPicks(token, { mode: "context", context: ctx.id });
      setPicksTracks(picks.tracks);
      setPicksLabel(ctx.label);
    } catch {
      setPicksTracks([]);
    } finally {
      setLoadingPicks(false);
    }
  }, [token]);

  useEffect(() => {
    void loadRecs();
  }, [loadRecs]);

  useEffect(() => {
    void loadRecent();
  }, [loadRecent]);

  useEffect(() => {
    void loadNew();
  }, [loadNew]);

  useEffect(() => {
    void loadMetaAndPicks();
  }, [loadMetaAndPicks]);

  const activeId = usePlayerStore((s) => s.queue[s.index]?.id ?? null);

  async function toggleFavorite(track: Track) {
    if (!token) return;
    const isFav = favoriteIds.has(track.id);
    try {
      if (isFav) {
        await removeFavorite(token, track.id);
        setFavoriteIds((prev) => {
          const next = new Set(prev);
          next.delete(track.id);
          return next;
        });
      } else {
        await addFavorite(token, track.id);
        setFavoriteIds((prev) => new Set(prev).add(track.id));
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not update favorite");
    }
  }

  return (
    <div className="space-y-8">
      <header className="space-y-1">
        <p className="text-xs font-medium uppercase tracking-widest text-spotify-muted">Good listening</p>
        <h1 className="text-2xl font-bold text-white">Home</h1>
      </header>

      <SearchBar
        value={q}
        onChange={setQ}
        onSubmit={() => {
          const t = q.trim();
          if (t) navigate(`/search?q=${encodeURIComponent(t)}`);
          else navigate("/search");
        }}
        placeholder="What do you want to hear?"
      />

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">New Hype</h2>
          <button
            type="button"
            onClick={() => void loadNew()}
            className="text-xs font-medium text-spotify-accent hover:underline"
          >
            Обновить
          </button>
        </div>
        {loadingNew && <TrackListSkeleton rows={4} />}
        {!loadingNew && newTracks.length === 0 && (
          <p className="text-sm text-spotify-muted">Пока пусто — подождите фоновое обновление или откройте поиск.</p>
        )}
        {!loadingNew && newTracks.length > 0 && (
          <TrackList
            tracks={newTracks}
            activeId={activeId}
            favoriteIds={favoriteIds}
            onToggleFavorite={toggleFavorite}
            onArtistClick={openArtist}
            onPlay={(_t, index) => setQueue(newTracks, index)}
            emptyLabel=""
          />
        )}
      </section>

      <section>
        <div className="mb-2">
          <h2 className="text-lg font-semibold text-white">Сегодня под настроение и дела</h2>
          <p className="mt-1 text-xs text-spotify-muted">
            День недели: <span className="text-spotify-accent">{weekdayHint}</span>
          </p>
        </div>
        <div className="mb-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void loadMetaAndPicks()}
            className={`rounded-full px-3 py-1.5 text-xs font-medium ${
              activeContextId === null
                ? "bg-spotify-accent text-black"
                : "bg-spotify-elevated text-white hover:bg-white/10"
            }`}
          >
            День недели
          </button>
          {contexts.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => void loadContextPicks(c)}
              className={`rounded-full px-3 py-1.5 text-xs font-medium ${
                activeContextId === c.id
                  ? "bg-spotify-accent text-black"
                  : "bg-spotify-elevated text-white hover:bg-white/10"
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
        {loadingPicks && <TrackListSkeleton rows={5} />}
        {!loadingPicks && picksTracks.length > 0 && (
          <>
            <p className="mb-3 text-xs text-spotify-muted">Подборка: {picksLabel}</p>
            <ActivityPicksWave
              tracks={picksTracks}
              activeId={activeId}
              favoriteIds={favoriteIds}
              onToggleFavorite={toggleFavorite}
              onPlay={(_t, index) => setQueue(picksTracks, index)}
            />
          </>
        )}
        {!loadingPicks && picksTracks.length === 0 && (
          <p className="text-sm text-spotify-muted">Нет треков для этой подборки.</p>
        )}
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Recently played</h2>
          <button
            type="button"
            onClick={() => void loadRecent()}
            className="text-xs font-medium text-spotify-accent hover:underline"
          >
            Refresh
          </button>
        </div>
        {loadingRecent && <TrackListSkeleton rows={4} />}
        {!loadingRecent && recent.length === 0 && (
          <p className="text-sm text-spotify-muted">Play something — it will show up here.</p>
        )}
        {!loadingRecent && recent.length > 0 && (
          <TrackList
            tracks={recent}
            activeId={activeId}
            favoriteIds={favoriteIds}
            onToggleFavorite={toggleFavorite}
            onArtistClick={openArtist}
            onPlay={(_t, index) => setQueue(recent, index)}
            emptyLabel=""
          />
        )}
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Made for you</h2>
          <button
            type="button"
            onClick={() => void loadRecs()}
            className="text-xs font-medium text-spotify-accent hover:underline"
          >
            Refresh
          </button>
        </div>
        {loadingRecs && <TrackListSkeleton rows={6} />}
        {err && <p className="text-sm text-red-400">{err}</p>}
        {!loadingRecs && !err && (
          <TrackList
            tracks={recs}
            activeId={activeId}
            favoriteIds={favoriteIds}
            onToggleFavorite={toggleFavorite}
            onArtistClick={openArtist}
            onPlay={(_t, index) => setQueue(recs, index)}
            emptyLabel="Search something to get started"
          />
        )}
      </section>
    </div>
  );
}
