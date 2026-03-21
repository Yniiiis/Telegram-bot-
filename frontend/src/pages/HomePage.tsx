import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { SearchBar } from "../components/SearchBar";
import { TrackListSkeleton } from "../components/Skeleton";
import { TrackList } from "../components/TrackList";
import {
  addFavorite,
  getFavorites,
  getRecentTracks,
  removeFavorite,
  searchTracks,
} from "../lib/api";
import { useAuthStore } from "../store/authStore";
import { usePlayerStore } from "../store/playerStore";
import type { Track } from "../types";

export function HomePage() {
  const navigate = useNavigate();
  const token = useAuthStore((s) => s.token);
  const setQueue = usePlayerStore((s) => s.setQueue);
  const [q, setQ] = useState("");
  const [recs, setRecs] = useState<Track[]>([]);
  const [recent, setRecent] = useState<Track[]>([]);
  const [loadingRecs, setLoadingRecs] = useState(true);
  const [loadingRecent, setLoadingRecent] = useState(true);
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

  useEffect(() => {
    void loadRecs();
  }, [loadRecs]);

  useEffect(() => {
    void loadRecent();
  }, [loadRecent]);

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
            onPlay={(_t, index) => setQueue(recs, index)}
            emptyLabel="Search something to get started"
          />
        )}
      </section>
    </div>
  );
}
