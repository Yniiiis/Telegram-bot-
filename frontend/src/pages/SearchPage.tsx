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
  type SearchFilters,
} from "../lib/api";
import { useAuthStore } from "../store/authStore";
import { usePlayerStore } from "../store/playerStore";

const PAGE_SIZE = 20;

const CATALOG_SOURCES = ["zaycev", "hitmotop", "jamendo", "youtube_music", "soundcloud", "mock"] as const;

const SOURCE_LABELS: Record<(typeof CATALOG_SOURCES)[number], string> = {
  zaycev: "Zaycev",
  hitmotop: "Hitmotop",
  jamendo: "Jamendo",
  youtube_music: "YouTube Music",
  soundcloud: "SoundCloud",
  mock: "Demo",
};

type FilterState = {
  sources: Set<string>;
  minSec: string;
  maxSec: string;
};

function parseFiltersFromParams(sp: URLSearchParams): FilterState {
  const sources = new Set<string>();
  const raw = sp.get("sources");
  if (raw) {
    for (const part of raw.split(",")) {
      const t = part.trim().toLowerCase();
      if (t) sources.add(t);
    }
  }
  return {
    sources,
    minSec: sp.get("min_duration_sec") ?? "",
    maxSec: sp.get("max_duration_sec") ?? "",
  };
}

function filtersToApi(f: FilterState): SearchFilters | undefined {
  const out: SearchFilters = {};
  if (f.sources.size > 0) out.sources = [...f.sources];
  if (f.minSec.trim() !== "") {
    const n = Number(f.minSec);
    if (!Number.isNaN(n) && n >= 0) out.min_duration_sec = n;
  }
  if (f.maxSec.trim() !== "") {
    const n = Number(f.maxSec);
    if (!Number.isNaN(n) && n >= 0) out.max_duration_sec = n;
  }
  if (!out.sources?.length && out.min_duration_sec == null && out.max_duration_sec == null) {
    return undefined;
  }
  return out;
}

function appendFilters(sp: URLSearchParams, f: FilterState) {
  if (f.sources.size > 0) sp.set("sources", [...f.sources].join(","));
  else sp.delete("sources");
  if (f.minSec.trim() !== "") sp.set("min_duration_sec", f.minSec.trim());
  else sp.delete("min_duration_sec");
  if (f.maxSec.trim() !== "") sp.set("max_duration_sec", f.maxSec.trim());
  else sp.delete("max_duration_sec");
}

export function SearchPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const initialQ = params.get("q") ?? "";
  const addToPlaylistId = params.get("addTo");

  const token = useAuthStore((s) => s.token);
  const [q, setQ] = useState(initialQ);
  const [filters, setFilters] = useState<FilterState>(() => parseFiltersFromParams(params));
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
    setFilters(parseFiltersFromParams(params));
  }, [params]);

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
      filterArg?: FilterState,
    ) => {
      const t = query.trim();
      if (!token || !t) {
        if (!append) {
          setResults([]);
          setHasMore(false);
        }
        return;
      }
      const f = filterArg ?? filters;
      const apiFilters = filtersToApi(f);
      const page = await searchTracksPage(token, t, offset, pageLimit, apiFilters);
      if (append) {
        setResults((prev) => [...prev, ...page.tracks]);
      } else {
        setResults(page.tracks);
      }
      setNextOffset(page.offset + page.tracks.length);
      setHasMore(page.has_more);
    },
    [token, filters],
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
      await fetchPage(t, nextOffset, true, PAGE_SIZE, filters);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not load more");
    } finally {
      setLoadingMore(false);
    }
  }, [token, q, hasMore, loadingMore, loading, nextOffset, fetchPage, addToPlaylistId, filters]);

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
          appendFilters(sp, filters);
          const qs = sp.toString();
          navigate(qs ? `/search?${qs}` : "/search");
          if (t) void runSearch(t, true);
        }}
        autoFocus
      />

      {!addToPlaylistId && (
        <details className="rounded-lg bg-spotify-elevated px-3 py-2 text-sm text-spotify-muted">
          <summary className="cursor-pointer font-medium text-white">Фильтры поиска</summary>
          <div className="mt-3 space-y-3 border-t border-white/10 pt-3">
            <p className="text-xs">Источники каталога</p>
            <div className="flex flex-wrap gap-2">
              {CATALOG_SOURCES.map((src) => (
                <label key={src} className="flex cursor-pointer items-center gap-1.5 text-xs text-white">
                  <input
                    type="checkbox"
                    checked={filters.sources.has(src)}
                    onChange={() => {
                      setFilters((prev) => {
                        const next = new Set(prev.sources);
                        if (next.has(src)) next.delete(src);
                        else next.add(src);
                        return { ...prev, sources: next };
                      });
                    }}
                    className="rounded border-spotify-muted"
                  />
                  {SOURCE_LABELS[src]}
                </label>
              ))}
            </div>
            <div className="flex flex-wrap gap-3">
              <label className="flex flex-col gap-1 text-xs">
                <span>Мин. длительность (сек)</span>
                <input
                  type="number"
                  min={0}
                  className="w-28 rounded bg-spotify-base px-2 py-1 text-white"
                  value={filters.minSec}
                  onChange={(e) => setFilters((p) => ({ ...p, minSec: e.target.value }))}
                />
              </label>
              <label className="flex flex-col gap-1 text-xs">
                <span>Макс. длительность (сек)</span>
                <input
                  type="number"
                  min={0}
                  className="w-28 rounded bg-spotify-base px-2 py-1 text-white"
                  value={filters.maxSec}
                  onChange={(e) => setFilters((p) => ({ ...p, maxSec: e.target.value }))}
                />
              </label>
            </div>
            <button
              type="button"
              className="text-xs font-medium text-spotify-accent hover:underline"
              onClick={() => {
                const t = q.trim();
                const sp = new URLSearchParams();
                if (t) sp.set("q", t);
                appendFilters(sp, filters);
                const qs = sp.toString();
                navigate(qs ? `/search?${qs}` : "/search");
                if (t) void runSearch(t, true);
              }}
            >
              Применить к результатам
            </button>
          </div>
        </details>
      )}

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
