import type { AuthUser, PlaylistDetail, PlaylistSummary, Track } from "../types";

const base = () => import.meta.env.VITE_API_BASE_URL || "/api";

function authHeader(token: string | null): HeadersInit {
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly detail?: unknown;

  constructor(message: string, status: number, code?: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

async function parseJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    if (!text.trim()) {
      throw new ApiError(res.statusText || "Request failed", res.status);
    }
    try {
      const parsed = JSON.parse(text) as { detail?: unknown };
      const d = parsed.detail;
      let message = text || res.statusText;
      let code: string | undefined;
      if (typeof d === "string") {
        message = d;
      } else if (d && typeof d === "object" && "message" in d) {
        message = String((d as { message: string }).message);
        if ("code" in d) code = String((d as { code: string }).code);
      }
      throw new ApiError(message, res.status, code, d);
    } catch (e) {
      if (e instanceof ApiError) throw e;
      throw new Error(text || res.statusText);
    }
  }
  return res.json() as Promise<T>;
}

export async function authTelegram(initData: string): Promise<{
  access_token: string;
  user: AuthUser;
}> {
  const res = await fetch(`${base()}/auth/telegram`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ init_data: initData }),
  });
  return parseJson(res);
}

/** Backend must have ALLOW_DEV_AUTH=1. Returns null if disabled or network error. */
export async function authDev(): Promise<{
  access_token: string;
  user: AuthUser;
} | null> {
  try {
    const res = await fetch(`${base()}/auth/dev`, { method: "POST" });
    if (res.status === 404) return null;
    if (!res.ok) return null;
    return parseJson(res);
  } catch {
    return null;
  }
}

export interface SearchPageResult {
  tracks: Track[];
  offset: number;
  limit: number;
  has_more: boolean;
}

/** Optional search filters (passed as query params). */
export interface SearchFilters {
  sources?: string[];
  min_duration_sec?: number | null;
  max_duration_sec?: number | null;
}

export async function searchTracksPage(
  token: string,
  q: string,
  offset: number,
  limit: number,
  filters?: SearchFilters,
  opts?: { artistFocus?: boolean },
): Promise<SearchPageResult> {
  const params = new URLSearchParams({
    q,
    offset: String(offset),
    limit: String(limit),
  });
  if (filters?.sources?.length) params.set("sources", filters.sources.join(","));
  if (filters?.min_duration_sec != null && filters.min_duration_sec >= 0) {
    params.set("min_duration_sec", String(filters.min_duration_sec));
  }
  if (filters?.max_duration_sec != null && filters.max_duration_sec >= 0) {
    params.set("max_duration_sec", String(filters.max_duration_sec));
  }
  if (opts?.artistFocus) params.set("artist_focus", "true");
  const res = await fetch(`${base()}/search?${params}`, {
    headers: { ...authHeader(token) },
  });
  return parseJson<SearchPageResult>(res);
}

/** First page only (backward compatible). */
export async function searchTracks(token: string, q: string, limit = 25): Promise<Track[]> {
  const page = await searchTracksPage(token, q, 0, limit, undefined);
  return page.tracks;
}

export interface DailyContextMeta {
  id: string;
  label: string;
  query: string;
}

export interface DiscoveryMetaResponse {
  contexts: DailyContextMeta[];
  catalog_sources: string[];
  weekday_mood_query: string;
}

export async function getDiscoveryMeta(token: string): Promise<DiscoveryMetaResponse> {
  const res = await fetch(`${base()}/discovery/meta`, { headers: { ...authHeader(token) } });
  return parseJson<DiscoveryMetaResponse>(res);
}

export async function getNewReleases(token: string, limit = 20): Promise<Track[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  const res = await fetch(`${base()}/discovery/new-releases?${params}`, {
    headers: { ...authHeader(token) },
  });
  const data = await parseJson<{ tracks: Track[] }>(res);
  return data.tracks;
}

export interface DiscoveryPicksResponse {
  tracks: Track[];
  used_query: string;
  context_id: string | null;
  mode: string;
}

export async function getSimilarTracks(
  token: string,
  trackId: string,
  limit = 16,
): Promise<Track[]> {
  const params = new URLSearchParams({ track_id: trackId, limit: String(limit) });
  const res = await fetch(`${base()}/recommendations/similar?${params}`, {
    headers: { ...authHeader(token) },
  });
  const data = await parseJson<{ tracks: Track[] }>(res);
  return data.tracks;
}

export async function getDiscoveryPicks(
  token: string,
  opts: { mode: "weekday" | "context"; context?: string },
): Promise<DiscoveryPicksResponse> {
  const params = new URLSearchParams({ mode: opts.mode, limit: "18" });
  if (opts.context) params.set("context", opts.context);
  const res = await fetch(`${base()}/discovery/picks?${params}`, {
    headers: { ...authHeader(token) },
  });
  return parseJson<DiscoveryPicksResponse>(res);
}

export async function recordPlay(token: string, trackId: string): Promise<void> {
  try {
    const res = await fetch(`${base()}/history/play`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader(token) },
      body: JSON.stringify({ track_id: trackId }),
    });
    if (!res.ok) return;
  } catch {
    /* ignore — history is best-effort */
  }
}

export async function getRecentTracks(token: string, limit = 20): Promise<Track[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  const res = await fetch(`${base()}/history/recent?${params}`, {
    headers: { ...authHeader(token) },
  });
  const data = await parseJson<{ tracks: Track[] }>(res);
  return data.tracks;
}

export async function getFavorites(token: string): Promise<Track[]> {
  const res = await fetch(`${base()}/favorites`, { headers: { ...authHeader(token) } });
  const data = await parseJson<{ tracks: Track[] }>(res);
  return data.tracks;
}

export async function addFavorite(token: string, trackId: string): Promise<void> {
  const res = await fetch(`${base()}/favorites`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ track_id: trackId }),
  });
  if (!res.ok) {
    const text = await res.text();
    if (res.status === 409) return;
    throw new Error(text || res.statusText);
  }
}

export async function removeFavorite(token: string, trackId: string): Promise<void> {
  const res = await fetch(`${base()}/favorites/${trackId}`, {
    method: "DELETE",
    headers: { ...authHeader(token) },
  });
  if (!res.ok && res.status !== 404) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
}

export async function listPlaylists(token: string): Promise<PlaylistSummary[]> {
  const res = await fetch(`${base()}/playlists`, { headers: { ...authHeader(token) } });
  return parseJson(res);
}

export async function createPlaylist(token: string, name: string): Promise<PlaylistSummary> {
  const res = await fetch(`${base()}/playlists`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ name }),
  });
  return parseJson(res);
}

export async function getPlaylist(token: string, id: string): Promise<PlaylistDetail> {
  const res = await fetch(`${base()}/playlists/${id}`, { headers: { ...authHeader(token) } });
  return parseJson(res);
}

export async function renamePlaylist(token: string, id: string, name: string): Promise<void> {
  const res = await fetch(`${base()}/playlists/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
}

export async function deletePlaylist(token: string, id: string): Promise<void> {
  const res = await fetch(`${base()}/playlists/${id}`, {
    method: "DELETE",
    headers: { ...authHeader(token) },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
}

export async function addTrackToPlaylist(
  token: string,
  playlistId: string,
  trackId: string,
): Promise<void> {
  const res = await fetch(`${base()}/playlists/${playlistId}/tracks`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ track_id: trackId }),
  });
  if (!res.ok) {
    const text = await res.text();
    if (res.status === 409) return;
    throw new Error(text || res.statusText);
  }
}

export async function removeTrackFromPlaylist(
  token: string,
  playlistId: string,
  trackId: string,
): Promise<void> {
  const res = await fetch(`${base()}/playlists/${playlistId}/tracks/${trackId}`, {
    method: "DELETE",
    headers: { ...authHeader(token) },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
}

export function streamUrl(trackId: string, token: string): string {
  const b = base();
  const u = new URL(`${b}/stream/${trackId}`, window.location.origin);
  u.searchParams.set("token", token);
  return u.toString();
}
