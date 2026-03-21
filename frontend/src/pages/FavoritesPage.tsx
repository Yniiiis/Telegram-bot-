import { useCallback, useEffect, useMemo, useState } from "react";

import { TrackListSkeleton } from "../components/Skeleton";
import { TrackList } from "../components/TrackList";
import { addFavorite, getFavorites, removeFavorite } from "../lib/api";
import { useAuthStore } from "../store/authStore";
import { usePlayerStore } from "../store/playerStore";
import type { Track } from "../types";

export function FavoritesPage() {
  const token = useAuthStore((s) => s.token);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const setQueue = usePlayerStore((s) => s.setQueue);
  const activeId = usePlayerStore((s) => s.queue[s.index]?.id ?? null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setErr(null);
    try {
      const list = await getFavorites(token);
      setTracks(list);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load favorites");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  const favoriteIds = useMemo(() => new Set(tracks.map((t) => t.id)), [tracks]);

  async function toggleFavorite(track: Track) {
    if (!token) return;
    const isFav = favoriteIds.has(track.id);
    try {
      if (isFav) {
        await removeFavorite(token, track.id);
        setTracks((prev) => prev.filter((x) => x.id !== track.id));
      } else {
        await addFavorite(token, track.id);
        setTracks((prev) => [track, ...prev]);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Update failed");
    }
  }

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-bold text-white">Liked songs</h1>
        <p className="mt-1 text-sm text-spotify-muted">{tracks.length} saved tracks</p>
      </header>

      {loading && <TrackListSkeleton rows={8} />}
      {err && <p className="text-sm text-red-400">{err}</p>}

      {!loading && (
      <TrackList
        tracks={tracks}
        activeId={activeId}
        favoriteIds={favoriteIds}
        onPlay={(_t, index) => setQueue(tracks, index)}
        onToggleFavorite={toggleFavorite}
        emptyLabel="Save tracks you love — they’ll show up here."
      />
      )}
    </div>
  );
}
