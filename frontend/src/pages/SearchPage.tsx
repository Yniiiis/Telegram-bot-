import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import type { Track } from "../types";

import { SearchBar } from "../components/SearchBar";
import { TrackListSkeleton } from "../components/Skeleton";
import { TrackList } from "../components/TrackList";
import {
  addFavorite,
  addTrackToPlaylist,
  getFavorites,
  removeFavorite,
  searchTracksPage,
} from "../lib/api";
import { useAuthStore } from "../store/authStore";
import { usePlayerStore } from "../store/playerStore";

const PAGE_SIZE = 20;

export function SearchPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const initialQ = params.get("q") ?? "";
  const addToPlaylistId = params.get("addTo");

  const token = useAuthStore((s) => s.token);
  const [q, setQ] = useState(initialQ);
  const [results, setResults] = useState<Track[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [nextOffset, setNextOffset] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const setQueue = usePlayerStore((s) => s.setQueue);
  const activeId = usePlayerStore((s) => s.queue[s.index]?.id ?? null);
  const [favoriteIds, setFavoriteIds] = useState<Set<string>>(() => new Set());
  const loadMoreRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!token || addToPlaylistId) return;
    void getFavorites(token)
      .then((tracks) => setFavoriteIds(new Set(tracks.map((t) => t.id))))
      .catch(() => {});
  }, [token, addToPlaylistId]);

  const fetchPage = useCallback(
    async (query: string, offset: number, append: boolean, pageLimit: number = PAGE_SIZE) => {
      const t = query.trim();
      if (!token || !t) {
        if (!append) {
          setResults([]);
          setHasMore(false);
        }
        return;
      }
      const page = await searchTracksPage(token, t, offset, pageLimit);
      if (append) {
        setResults((prev) => [...prev, ...page.tracks]);
      } else {
        setResults(page.tracks);
      }
      setNextOffset(page.offset + page.tracks.length);
      setHasMore(page.has_more);
    },
    [token],
  );

  const runSearch = useCallback(
    async (query: string, reset: boolean) => {
      const t = query.trim();
      if (!token || !t) {
        setResults([]);
        setHasMore(false);
        return;
      }
      if (reset) {
        setLoading(true);
        setErr(null);
        try {
          const lim = addToPlaylistId ? 50 : PAGE_SIZE;
          await fetchPage(t, 0, false, lim);
        } catch (e) {
          setErr(e instanceof Error ? e.message : "Search failed");
          setResults([]);
          setHasMore(false);
        } finally {
          setLoading(false);
        }
      }
    },
    [token, fetchPage, addToPlaylistId],
  );

  const loadMore = useCallback(async () => {
    const t = q.trim();
    if (!token || !t || !hasMore || loadingMore || loading || addToPlaylistId) return;
    setLoadingMore(true);
    setErr(null);
    try {
      await fetchPage(t, nextOffset, true, PAGE_SIZE);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not load more");
    } finally {
      setLoadingMore(false);
    }
  }, [token, q, hasMore, loadingMore, loading, nextOffset, fetchPage, addToPlaylistId]);

  useEffect(() => {
    setQ(initialQ);
    if (initialQ) void runSearch(initialQ, true);
    else {
      setResults([]);
      setHasMore(false);
      setLoading(false);
    }
  }, [initialQ, runSearch]);

  useEffect(() => {
    const el = loadMoreRef.current;
    if (!el || addToPlaylistId || !hasMore) return;
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) void loadMore();
      },
      { rootMargin: "72px" },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [loadMore, hasMore, addToPlaylistId, results.length]);

  const title = useMemo(
    () => (addToPlaylistId ? "Add to playlist" : "Search"),
    [addToPlaylistId],
  );

  async function toggleFavorite(track: Track) {
    if (!token || addToPlaylistId) return;
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
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-bold text-white">{title}</h1>
        {addToPlaylistId && (
          <p className="mt-1 text-sm text-spotify-muted">Tap a track to add it to your playlist.</p>
        )}
      </header>

      <SearchBar
        value={q}
        onChange={setQ}
        onSubmit={() => {
          const t = q.trim();
          const sp = new URLSearchParams();
          if (t) sp.set("q", t);
          if (addToPlaylistId) sp.set("addTo", addToPlaylistId);
          const qs = sp.toString();
          navigate(qs ? `/search?${qs}` : "/search");
          if (t) void runSearch(t, true);
        }}
        autoFocus
      />

      {loading && q.trim() && <TrackListSkeleton rows={8} />}
      {err && <p className="text-sm text-red-400">{err}</p>}

      {!loading && (
        <TrackList
          tracks={results}
          activeId={activeId}
          favoriteIds={addToPlaylistId ? undefined : favoriteIds}
          onToggleFavorite={addToPlaylistId ? undefined : toggleFavorite}
          onPlay={async (track, index) => {
            if (addToPlaylistId && token) {
              try {
                await addTrackToPlaylist(token, addToPlaylistId, track.id);
                navigate(`/playlists/${addToPlaylistId}`);
              } catch (e) {
                setErr(e instanceof Error ? e.message : "Could not add track");
              }
              return;
            }
            setQueue(results, index);
          }}
          emptyLabel={q.trim() ? "No results" : "Type to search the catalog"}
        />
      )}

      {!addToPlaylistId && hasMore && !loading && (
        <div ref={loadMoreRef} className="flex justify-center py-4">
          {loadingMore ? (
            <span className="text-sm text-spotify-muted">Loading more…</span>
          ) : (
            <button
              type="button"
              onClick={() => void loadMore()}
              className="text-sm font-medium text-spotify-accent hover:underline"
            >
              Load more
            </button>
          )}
        </div>
      )}
    </div>
  );
}
