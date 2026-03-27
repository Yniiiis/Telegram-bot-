import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import type { Track } from "../types";

import { SearchBar } from "../components/SearchBar";
import { TrackListSkeleton } from "../components/Skeleton";
import { TrackList } from "../components/TrackList";
import { usePrefetchCovers } from "../hooks/usePrefetchCovers";
import {
  addFavorite,
  addTrackToPlaylist,
  getFavorites,
  removeFavorite,
  searchHitmotopFeedPage,
  searchTracksPage,
  warmTrackPlaybackBatch,
  type SearchPageResult,
} from "../lib/api";
import { useAuthStore } from "../store/authStore";
import { usePlayerStore } from "../store/playerStore";

const PAGE_SIZE = 20;

function buildSearchParams(
  q: string,
  addTo: string | null,
  artistMode: boolean,
): URLSearchParams {
  const sp = new URLSearchParams();
  const t = q.trim();
  if (t) sp.set("q", t);
  if (addTo) sp.set("addTo", addTo);
  if (artistMode) sp.set("artist", "1");
  return sp;
}

export function SearchPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const initialQ = params.get("q") ?? "";
  const addToPlaylistId = params.get("addTo");
  const artistMode = params.get("artist") === "1";

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
  const prefetchBuf = useRef<{
    mode: "feed" | "search";
    q: string;
    offset: number;
    fk: string;
    page: SearchPageResult;
  } | null>(null);

  const prefetchKey = useMemo(() => (artistMode ? "a1" : "a0"), [artistMode]);

  const openArtist = useCallback(
    (artist: string) => {
      const t = artist.trim();
      if (t) navigate(`/artist?name=${encodeURIComponent(t)}`);
    },
    [navigate],
  );

  usePrefetchCovers(results, 20);

  useEffect(() => {
    if (!token || results.length === 0) return;
    warmTrackPlaybackBatch(
      token,
      results.map((t) => t.id),
      15,
    );
  }, [token, results]);

  useEffect(() => {
    if (!token || addToPlaylistId) return;
    void getFavorites(token)
      .then((tracks) => setFavoriteIds(new Set(tracks.map((t) => t.id))))
      .catch(() => {});
  }, [token, addToPlaylistId]);

  const fetchPage = useCallback(
    async (
      query: string,
      offset: number,
      append: boolean,
      pageLimit: number = PAGE_SIZE,
    ) => {
      if (!token) return;
      const t = query.trim();
      if (!t) {
        const page = await searchHitmotopFeedPage(token, offset, pageLimit);
        if (append) {
          setResults((prev) => [...prev, ...page.tracks]);
        } else {
          setResults(page.tracks);
        }
        setNextOffset(page.offset + page.tracks.length);
        setHasMore(page.has_more);
        return;
      }
      const page = await searchTracksPage(token, t, offset, pageLimit, undefined, {
        artistFocus: artistMode,
      });
      if (append) {
        setResults((prev) => [...prev, ...page.tracks]);
      } else {
        setResults(page.tracks);
      }
      setNextOffset(page.offset + page.tracks.length);
      setHasMore(page.has_more);
    },
    [token, artistMode],
  );

  const runSearch = useCallback(
    async (query: string, reset: boolean) => {
      if (!token) return;
      const t = query.trim();
      if (reset) {
        prefetchBuf.current = null;
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
    if (!token || !hasMore || loadingMore || loading || addToPlaylistId) return;
    const t = q.trim();
    const mode: "feed" | "search" = t ? "search" : "feed";
    const buf = prefetchBuf.current;
    if (
      buf &&
      buf.mode === mode &&
      buf.q === t &&
      buf.offset === nextOffset &&
      buf.fk === prefetchKey
    ) {
      prefetchBuf.current = null;
      setLoadingMore(true);
      setErr(null);
      try {
        setResults((prev) => [...prev, ...buf.page.tracks]);
        setNextOffset(buf.page.offset + buf.page.tracks.length);
        setHasMore(buf.page.has_more);
      } finally {
        setLoadingMore(false);
      }
      return;
    }
    setLoadingMore(true);
    setErr(null);
    try {
      await fetchPage(t, nextOffset, true, PAGE_SIZE);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not load more");
    } finally {
      setLoadingMore(false);
    }
  }, [
    token,
    q,
    hasMore,
    loadingMore,
    loading,
    nextOffset,
    fetchPage,
    addToPlaylistId,
    prefetchKey,
  ]);

  useEffect(() => {
    if (!token || !hasMore || loading || loadingMore || addToPlaylistId) return;
    const t = q.trim();
    const off = nextOffset;
    let cancelled = false;
    void (async () => {
      try {
        const page = t
          ? await searchTracksPage(token, t, off, PAGE_SIZE, undefined, {
              artistFocus: artistMode,
            })
          : await searchHitmotopFeedPage(token, off, PAGE_SIZE);
        if (cancelled) return;
        prefetchBuf.current = {
          mode: t ? "search" : "feed",
          q: t,
          offset: off,
          fk: prefetchKey,
          page,
        };
      } catch {
        if (!cancelled) prefetchBuf.current = null;
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    token,
    q,
    hasMore,
    nextOffset,
    loading,
    loadingMore,
    addToPlaylistId,
    artistMode,
    prefetchKey,
  ]);

  useEffect(() => {
    setQ(initialQ);
    void runSearch(initialQ, true);
  }, [initialQ, artistMode, runSearch]);

  useEffect(() => {
    const el = loadMoreRef.current;
    if (!el || addToPlaylistId || !hasMore) return;
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) void loadMore();
      },
      { rootMargin: "520px" },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [loadMore, hasMore, addToPlaylistId, results.length]);

  const title = useMemo(
    () => (addToPlaylistId ? "Add to playlist" : "Поиск Hitmotop"),
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

  const showSkeleton = loading && (q.trim() || results.length === 0);

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-bold text-white">{title}</h1>
        {addToPlaylistId && (
          <p className="mt-1 text-sm text-spotify-muted">Tap a track to add it to your playlist.</p>
        )}
        {!addToPlaylistId && (
          <p className="mt-1 text-xs text-spotify-muted">
            Каталог: rus.hitmotop.com · без запроса показывается страница /2026
          </p>
        )}
      </header>

      <SearchBar
        value={q}
        onChange={setQ}
        onSubmit={() => {
          const t = q.trim();
          const sp = buildSearchParams(q, addToPlaylistId, artistMode);
          const qs = sp.toString();
          navigate(qs ? `/search?${qs}` : "/search");
          void runSearch(t, true);
        }}
        autoFocus
      />

      {!addToPlaylistId && (
        <label className="flex cursor-pointer items-center gap-2 text-xs text-white">
          <input
            type="checkbox"
            checked={artistMode}
            onChange={() => {
              const sp = buildSearchParams(q, addToPlaylistId, !artistMode);
              const qs = sp.toString();
              navigate(qs ? `/search?${qs}` : "/search");
            }}
            className="rounded border-spotify-muted"
          />
          Упор на исполнителя (быстрее при длинном запросе)
        </label>
      )}

      {showSkeleton && <TrackListSkeleton rows={8} />}
      {err && <p className="text-sm text-red-400">{err}</p>}

      {!loading && (
        <TrackList
          tracks={results}
          activeId={activeId}
          favoriteIds={addToPlaylistId ? undefined : favoriteIds}
          onToggleFavorite={addToPlaylistId ? undefined : toggleFavorite}
          onArtistClick={addToPlaylistId ? undefined : openArtist}
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
          emptyLabel={
            q.trim() ? "Ничего не найдено" : "Пусто — проверьте доступ к rus.hitmotop.com с сервера"
          }
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
