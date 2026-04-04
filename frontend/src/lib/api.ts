import type { AuthUser, PlaylistDetail, PlaylistSummary, Track } from "../types";

/** From CI / .env at build time; no trailing slash. */
function envApiBase(): string {
  return (import.meta.env.VITE_API_BASE_URL || "").trim().replace(/\/$/, "");
}

/** True when the built-in API URL is an ngrok tunnel (free tier blocks `<audio src>` without extra headers). */
export function isNgrokApiBase(): boolean {
  return /ngrok/i.test(envApiBase());
}

function isGithubPagesHost(): boolean {
  return typeof window !== "undefined" && window.location.hostname.endsWith("github.io");
}

/**
 * Dev: Vite proxies `/api` → backend.
 * Prod: use `VITE_API_BASE_URL` (full `https://…` to FastAPI). On `*.github.io`, relative `/api`
 * would hit GitHub’s servers (405/HTML), not your API — so we require an explicit URL.
 */
function base(): string {
  const fromEnv = envApiBase();
  if (fromEnv) return fromEnv;
  if (import.meta.env.DEV) return "/api";
  return "/api";
}

function ghPagesNeedApiMessage(): string {
  const origin = typeof window !== "undefined" ? window.location.origin : "your GitHub Pages site";
  return (
    "This build is on GitHub Pages but VITE_API_BASE_URL was not set when the site was built. " +
    "In the repo: Settings → Secrets and variables → Actions → Variables → add VITE_API_BASE_URL " +
    "with your public FastAPI URL (https://…, no trailing slash). On the API, allow CORS for " +
    `${origin}. Then redeploy the Pages workflow.`
  );
}

/** Call before Telegram auth on static hosting. */
export function assertProductionApiReachable(): void {
  if (!import.meta.env.PROD || typeof window === "undefined") return;
  if (!isGithubPagesHost()) return;
  if (envApiBase()) return;
  throw new Error(ghPagesNeedApiMessage());
}

function authHeader(token: string | null): HeadersInit {
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

/** Free ngrok interstitial — skip for programmatic fetches (Telegram WebView). */
function ngrokBypassHeaders(): Record<string, string> {
  const b = envApiBase();
  if (!b || !/^https?:\/\//i.test(b)) return {};
  try {
    const host = new URL(b).hostname;
    if (host.includes("ngrok-free.") || host.endsWith(".ngrok.io") || host.includes("ngrok")) {
      return { "ngrok-skip-browser-warning": "1" };
    }
  } catch {
    /* ignore */
  }
  return {};
}

function mergeHeaders(extra?: HeadersInit): Headers {
  const h = new Headers(extra as HeadersInit);
  for (const [k, v] of Object.entries(ngrokBypassHeaders())) {
    h.set(k, v);
  }
  return h;
}

async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  return fetch(input, { ...init, headers: mergeHeaders(init?.headers) });
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
    if (res.status === 405 || /<html[\s>]/i.test(text)) {
      throw new ApiError(
        "The server returned HTML or 405 instead of JSON — the request did not reach your FastAPI. " +
          "On GitHub Pages you must set VITE_API_BASE_URL to your API’s HTTPS origin and redeploy.",
        res.status,
      );
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
  assertProductionApiReachable();
  const res = await apiFetch(`${base()}/auth/telegram`, {
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
    const res = await apiFetch(`${base()}/auth/dev`, { method: "POST" });
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

/** Hitmotop charts/list page (backend: HITMOTOP_CHARTS_PATH, default /2026). */
export async function searchHitmotopFeedPage(
  token: string,
  offset: number,
  limit: number,
): Promise<SearchPageResult> {
  const params = new URLSearchParams({
    offset: String(offset),
    limit: String(limit),
  });
  const res = await apiFetch(`${base()}/search/feed?${params}`, {
    headers: { ...authHeader(token) },
  });
  return parseJson<SearchPageResult>(res);
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
  const res = await apiFetch(`${base()}/search?${params}`, {
    headers: { ...authHeader(token) },
  });
  return parseJson<SearchPageResult>(res);
}

/** First page only (backward compatible). */
export async function searchTracks(token: string, q: string, limit = 25): Promise<Track[]> {
  const page = await searchTracksPage(token, q, 0, limit, undefined);
  return page.tracks;
}

/** Fire-and-forget: прогревает разрешение URL воспроизведения Hitmotop на сервере до нажатия play. */
export function warmTrackPlayback(token: string, trackId: string): void {
  void apiFetch(`${base()}/track/${trackId}/prepare`, {
    method: "POST",
    headers: { ...authHeader(token) },
  }).catch(() => {
    /* optional — ignore 502 for dead rows */
  });
}

export function warmTrackPlaybackBatch(token: string, trackIds: string[], maxTracks = 15): void {
  for (const id of trackIds.slice(0, maxTracks)) {
    warmTrackPlayback(token, id);
  }
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
  const res = await apiFetch(`${base()}/discovery/meta`, { headers: { ...authHeader(token) } });
  return parseJson<DiscoveryMetaResponse>(res);
}

export async function getNewReleases(token: string, limit = 20): Promise<Track[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  const res = await apiFetch(`${base()}/discovery/new-releases?${params}`, {
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
  const res = await apiFetch(`${base()}/recommendations/similar?${params}`, {
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
  const res = await apiFetch(`${base()}/discovery/picks?${params}`, {
    headers: { ...authHeader(token) },
  });
  return parseJson<DiscoveryPicksResponse>(res);
}

export async function recordPlay(token: string, trackId: string): Promise<void> {
  try {
    const res = await apiFetch(`${base()}/history/play`, {
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
  const res = await apiFetch(`${base()}/history/recent?${params}`, {
    headers: { ...authHeader(token) },
  });
  const data = await parseJson<{ tracks: Track[] }>(res);
  return data.tracks;
}

export async function getFavorites(token: string): Promise<Track[]> {
  const res = await apiFetch(`${base()}/favorites`, { headers: { ...authHeader(token) } });
  const data = await parseJson<{ tracks: Track[] }>(res);
  return data.tracks;
}

export async function addFavorite(token: string, trackId: string): Promise<void> {
  const res = await apiFetch(`${base()}/favorites`, {
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
  const res = await apiFetch(`${base()}/favorites/${trackId}`, {
    method: "DELETE",
    headers: { ...authHeader(token) },
  });
  if (!res.ok && res.status !== 404) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
}

export async function listPlaylists(token: string): Promise<PlaylistSummary[]> {
  const res = await apiFetch(`${base()}/playlists`, { headers: { ...authHeader(token) } });
  return parseJson(res);
}

export async function createPlaylist(token: string, name: string): Promise<PlaylistSummary> {
  const res = await apiFetch(`${base()}/playlists`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ name }),
  });
  return parseJson(res);
}

export async function getPlaylist(token: string, id: string): Promise<PlaylistDetail> {
  const res = await apiFetch(`${base()}/playlists/${id}`, { headers: { ...authHeader(token) } });
  return parseJson(res);
}

export async function renamePlaylist(token: string, id: string, name: string): Promise<void> {
  const res = await apiFetch(`${base()}/playlists/${id}`, {
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
  const res = await apiFetch(`${base()}/playlists/${id}`, {
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
  const res = await apiFetch(`${base()}/playlists/${playlistId}/tracks`, {
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
  const res = await apiFetch(`${base()}/playlists/${playlistId}/tracks/${trackId}`, {
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
  const path = `/stream/${trackId}`;
  if (b.startsWith("http://") || b.startsWith("https://")) {
    const u = new URL(`${b.replace(/\/$/, "")}${path}`);
    u.searchParams.set("token", token);
    return u.toString();
  }
  const u = new URL(`${b.replace(/\/$/, "")}${path}`, window.location.origin);
  u.searchParams.set("token", token);
  return u.toString();
}

/** Hitmotop proxy is always MP3; Telegram WebView often rejects blob: without an audio/* type. */
const STREAM_PLAYBACK_BLOB_TYPE = "audio/mpeg";

/**
 * Load full stream for Telegram blob fallback: **same auth as `<audio src>`** — JWT only in `?token=`
 * (no `Authorization` header). A custom header turns the request into a CORS preflight; many Telegram
 * WebViews fail that while still playing the same URL on `<audio>`.
 * Uses explicit MIME on the Blob — some WebViews refuse playback when type is empty/octet-stream.
 *
 * Order: **fetch first**, **XHR** on transport failure only; HTTP status errors are not retried.
 */
export async function fetchStreamBlobForTelegram(
  url: string,
  _token: string,
  signal?: AbortSignal,
): Promise<Blob> {
  const fromResponse = async (res: Response): Promise<Blob> => {
    const ab = await res.arrayBuffer();
    return new Blob([ab], { type: STREAM_PLAYBACK_BLOB_TYPE });
  };

  try {
    const res = await apiFetch(url, {
      method: "GET",
      mode: "cors",
      credentials: "omit",
      cache: "no-store",
      signal,
    });
    if (!res.ok) {
      throw new Error(`stream ${res.status}`);
    }
    const blob = await fromResponse(res);
    return blob;
  } catch (e) {
    if (signal?.aborted) {
      throw e;
    }
    const msg = e instanceof Error ? e.message : String(e);
    if (/^stream \d/.test(msg)) {
      throw e;
    }
    return fetchStreamBlobViaXhr(url, signal);
  }
}

function fetchStreamBlobViaXhr(url: string, signal: AbortSignal | undefined): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("GET", url, true);
    xhr.responseType = "blob";
    xhr.timeout = 180_000;
    for (const [k, v] of Object.entries(ngrokBypassHeaders())) {
      xhr.setRequestHeader(k, v);
    }
    const onAbort = () => {
      xhr.abort();
    };
    signal?.addEventListener("abort", onAbort);
    xhr.onload = () => {
      signal?.removeEventListener("abort", onAbort);
      if (xhr.status >= 200 && xhr.status < 300) {
        const raw = xhr.response as Blob;
        const out = new Blob([raw], { type: STREAM_PLAYBACK_BLOB_TYPE });
        resolve(out);
        return;
      }
      reject(new Error(`stream ${xhr.status}`));
    };
    xhr.onerror = () => {
      signal?.removeEventListener("abort", onAbort);
      reject(new Error("xhr network"));
    };
    xhr.ontimeout = () => {
      signal?.removeEventListener("abort", onAbort);
      reject(new Error("xhr timeout"));
    };
    xhr.send();
  });
}
