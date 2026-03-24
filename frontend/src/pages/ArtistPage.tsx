import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { TrackListSkeleton } from "../components/Skeleton";
import { TrackList } from "../components/TrackList";
import { usePrefetchCovers } from "../hooks/usePrefetchCovers";
import {
  addFavorite,
  getFavorites,
  removeFavorite,
  searchTracksPage,
  warmTrackPlaybackBatch,
  type SearchPageResult,
} from "../lib/api";
import { useAuthStore } from "../store/authStore";
import { usePlayerStore } from "../store/playerStore";
import type { Track } from "../types";

const PAGE_SIZE = 24;

export function ArtistPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const name = (params.get("name") ?? "").trim();

  const token = useAuthStore((s) => s.token);
  const [results, setResults] = useState<Track[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [nextOffset, setNextOffset] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const setQueue = usePlayerStore((s) => s.setQueue);
  const activeId = usePlayerStore((s) => s.queue[s.index]?.id ?? null);
  const [favoriteIds, setFavoriteIds] = useState<Set<string>>(() => new Set());
  const loadMoreRef = useRef<HTMLDivElement | null>(null);
  const prefetchBuf = useRef<{
    q: string;
    offset: number;
    page: SearchPageResult;
  } | null>(null);

  usePrefetchCovers(results, 20);

  useEffect(() => {
    if (!token || results.length === 0) return;
    warmTrackPlaybackBatch(
      token,
      results.map((t) => t.id),
      8,
    );
  }, [token, results]);

  useEffect(() => {
    if (!token) return;
    void getFavorites(token)
      .then((tracks) => setFavoriteIds(new Set(tracks.map((t) => t.id))))
      .catch(() => {});
  }, [token]);

  const openArtist = useCallback(
    (artist: string) => {
      const t = artist.trim();
      if (!t) return;
      navigate(`/artist?name=${encodeURIComponent(t)}`);
    },
    [navigate],
  );

  const applyPage = useCallback((page: SearchPageResult, append: boolean) => {
    if (append) {
      setResults((prev) => [...prev, ...page.tracks]);
    } else {
      setResults(page.tracks);
    }
    setNextOffset(page.offset + page.tracks.length);
    setHasMore(page.has_more);
  }, []);

  const loadFirst = useCallback(async () => {
    if (!token || !name) {
      setResults([]);
      setHasMore(false);
      setLoading(false);
      return;
    }
    prefetchBuf.current = null;
    setLoading(true);
    setErr(null);
    try {
      const page = await searchTracksPage(token, name, 0, PAGE_SIZE, undefined, { artistFocus: true });
      applyPage(page, false);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load");
      setResults([]);
      setHasMore(false);
    } finally {
      setLoading(false);
    }
  }, [token, name, applyPage]);

  useEffect(() => {
    void loadFirst();
  }, [loadFirst]);

  const loadMore = useCallback(async () => {
    if (!token || !name || !hasMore || loadingMore || loading) return;
    const buf = prefetchBuf.current;
    if (buf && buf.q === name && buf.offset === nextOffset) {
      prefetchBuf.current = null;
      setLoadingMore(true);
      setErr(null);
      try {
        applyPage(buf.page, true);
      } finally {
        setLoadingMore(false);
      }
      return;
    }
    setLoadingMore(true);
    setErr(null);
    try {
      const page = await searchTracksPage(token, name, nextOffset, PAGE_SIZE, undefined, {
        artistFocus: true,
      });
      applyPage(page, true);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not load more");
    } finally {
      setLoadingMore(false);
    }
  }, [token, name, hasMore, loadingMore, loading, nextOffset, applyPage]);

  useEffect(() => {
    if (!token || !name || !hasMore || loading || loadingMore) return;
    const off = nextOffset;
    let cancelled = false;
    void (async () => {
      try {
        const page = await searchTracksPage(token, name, off, PAGE_SIZE, undefined, { artistFocus: true });
        if (cancelled) return;
        prefetchBuf.current = { q: name, offset: off, page };
      } catch {
        if (!cancelled) prefetchBuf.current = null;
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, name, hasMore, nextOffset, loading, loadingMore]);

  useEffect(() => {
    const el = loadMoreRef.current;
    if (!el || !hasMore) return;
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) void loadMore();
      },
      { rootMargin: "520px" },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [loadMore, hasMore, results.length]);

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

  const title = useMemo(() => name || "Artist", [name]);

  if (!name) {
    return (
      <div className="space-y-4">
        <p className="text-spotify-muted">Не указано имя исполнителя.</p>
        <Link to="/search" className="text-sm text-spotify-accent hover:underline">
          К поиску
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <Link to="/search" className="inline-block text-sm text-spotify-muted hover:text-white">
        ← Поиск
      </Link>

      <header className="rounded-2xl bg-gradient-to-br from-spotify-highlight to-spotify-base p-5">
        <p className="text-xs font-medium uppercase tracking-widest text-spotify-muted">Исполнитель</p>
        <h1 className="mt-1 text-2xl font-bold text-white">{title}</h1>
        <p className="mt-2 text-sm text-spotify-muted">
          Каталог по имени исполнителя (быстрый режим).{' '}
          <button
            type="button"
            className="text-spotify-accent hover:underline"
            onClick={() => navigate(`/search?q=${encodeURIComponent(name)}&artist=1`)}
          >
            Открыть в поиске
          </button>
        </p>
      </header>

      {loading && <TrackListSkeleton rows={8} />}
      {err && <p className="text-sm text-red-400">{err}</p>}

      {!loading && (
        <TrackList
          tracks={results}
          activeId={activeId}
          favoriteIds={favoriteIds}
          onToggleFavorite={toggleFavorite}
          onArtistClick={openArtist}
          onPlay={(_t, index) => setQueue(results, index)}
          emptyLabel="Нет треков по этому исполнителю"
        />
      )}

      {hasMore && !loading && (
        <div ref={loadMoreRef} className="flex justify-center py-4">
          {loadingMore ? (
            <span className="text-sm text-spotify-muted">Загрузка…</span>
          ) : (
            <button
              type="button"
              onClick={() => void loadMore()}
              className="text-sm font-medium text-spotify-accent hover:underline"
            >
              Ещё треки
            </button>
          )}
        </div>
      )}
    </div>
  );
}
