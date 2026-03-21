import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { TrackListSkeleton } from "../components/Skeleton";
import { TrackList } from "../components/TrackList";
import {
  deletePlaylist,
  getPlaylist,
  removeTrackFromPlaylist,
  renamePlaylist,
} from "../lib/api";
import { useAuthStore } from "../store/authStore";
import { usePlayerStore } from "../store/playerStore";
import type { Track } from "../types";

export function PlaylistDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const token = useAuthStore((s) => s.token);
  const [name, setName] = useState("");
  const [tracks, setTracks] = useState<Track[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const setQueue = usePlayerStore((s) => s.setQueue);
  const activeId = usePlayerStore((s) => s.queue[s.index]?.id ?? null);

  const load = useCallback(async () => {
    if (!token || !id) return;
    setLoading(true);
    setErr(null);
    try {
      const pl = await getPlaylist(token, id);
      setName(pl.name);
      setTracks(pl.tracks);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not load playlist");
    } finally {
      setLoading(false);
    }
  }, [token, id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function saveName() {
    if (!token || !id) return;
    const n = name.trim();
    if (!n) return;
    try {
      await renamePlaylist(token, id, n);
      setEditing(false);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Rename failed");
    }
  }

  async function removeTrack(track: Track) {
    if (!token || !id) return;
    try {
      await removeTrackFromPlaylist(token, id, track.id);
      setTracks((prev) => prev.filter((t) => t.id !== track.id));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Remove failed");
    }
  }

  async function trashPlaylist() {
    if (!token || !id) return;
    if (!confirm("Delete this playlist?")) return;
    try {
      await deletePlaylist(token, id);
      navigate("/playlists");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Delete failed");
    }
  }

  if (!id) return null;

  return (
    <div className="space-y-5">
      <Link
        to="/playlists"
        className="inline-flex items-center gap-1 text-sm text-spotify-muted hover:text-white"
      >
        ← Playlists
      </Link>

      <header className="space-y-2">
        {editing ? (
          <div className="flex gap-2">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="flex-1 rounded-lg border border-spotify-border bg-spotify-highlight px-3 py-2 text-xl font-bold text-white outline-none focus:border-spotify-accent"
            />
            <button
              type="button"
              onClick={() => void saveName()}
              className="rounded-full bg-spotify-accent px-4 text-sm font-semibold text-black"
            >
              Save
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="rounded-full px-3 text-sm text-spotify-muted"
            >
              Cancel
            </button>
          </div>
        ) : (
          <div className="flex items-start justify-between gap-2">
            <h1 className="text-2xl font-bold text-white">{name || "Playlist"}</h1>
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="text-sm text-spotify-accent hover:underline"
            >
              Rename
            </button>
          </div>
        )}
        <div className="flex flex-wrap gap-3 text-sm">
          <Link
            to={`/search?addTo=${encodeURIComponent(id)}`}
            className="font-medium text-spotify-accent hover:underline"
          >
            Add songs
          </Link>
          <button type="button" onClick={() => void trashPlaylist()} className="text-red-400 hover:underline">
            Delete playlist
          </button>
        </div>
      </header>

      {loading && <TrackListSkeleton rows={8} />}
      {err && <p className="text-sm text-red-400">{err}</p>}

      {!loading && (
      <TrackList
        tracks={tracks}
        activeId={activeId}
        onPlay={(_t, index) => setQueue(tracks, index)}
        onRemoveFromList={(track) => void removeTrack(track)}
        emptyLabel="This playlist is empty. Add songs from search."
      />
      )}
    </div>
  );
}
