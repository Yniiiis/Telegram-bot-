import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { PlaylistManager } from "../components/PlaylistManager";
import { createPlaylist, listPlaylists } from "../lib/api";
import { useAuthStore } from "../store/authStore";
import type { PlaylistSummary } from "../types";

export function PlaylistsPage() {
  const token = useAuthStore((s) => s.token);
  const [items, setItems] = useState<PlaylistSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [modal, setModal] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setErr(null);
    try {
      const list = await listPlaylists(token);
      setItems(list);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not load playlists");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-5">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Your playlists</h1>
          <p className="mt-1 text-sm text-spotify-muted">Curate sets for any mood.</p>
        </div>
        <button
          type="button"
          onClick={() => setModal(true)}
          className="shrink-0 rounded-full bg-spotify-accent px-4 py-2 text-sm font-semibold text-black hover:bg-spotify-accentHover"
        >
          New
        </button>
      </header>

      {loading && <p className="text-sm text-spotify-muted">Loading…</p>}
      {err && <p className="text-sm text-red-400">{err}</p>}

      <ul className="flex flex-col gap-2">
        {items.map((pl) => (
          <li key={pl.id}>
            <Link
              to={`/playlists/${pl.id}`}
              className="flex items-center gap-3 rounded-xl bg-spotify-elevated px-3 py-3 transition hover:bg-spotify-highlight active:scale-[0.99]"
            >
              <div className="flex h-14 w-14 items-center justify-center rounded-md bg-gradient-to-br from-indigo-600 to-spotify-accent text-lg font-bold text-black">
                {pl.name.slice(0, 1).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-white">{pl.name}</p>
                <p className="text-xs text-spotify-muted">Playlist</p>
              </div>
              <Chevron />
            </Link>
          </li>
        ))}
      </ul>

      {!loading && items.length === 0 && (
        <p className="text-center text-sm text-spotify-muted">No playlists yet — create one.</p>
      )}

      <PlaylistManager
        open={modal}
        onClose={() => setModal(false)}
        onCreate={async (name) => {
          if (!token) return;
          await createPlaylist(token, name);
          await load();
        }}
      />
    </div>
  );
}

function Chevron() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" className="text-spotify-muted">
      <path d="M9 6 15 12l-6 6V6Z" />
    </svg>
  );
}
