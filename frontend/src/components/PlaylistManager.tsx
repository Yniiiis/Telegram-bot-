import { useState } from "react";

interface PlaylistManagerProps {
  open: boolean;
  onClose: () => void;
  onCreate: (name: string) => Promise<void>;
}

/** Modal to create a new playlist. */
export function PlaylistManager({ open, onClose, onCreate }: PlaylistManagerProps) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (!open) return null;

  async function submit() {
    const n = name.trim();
    if (!n) return;
    setBusy(true);
    setErr(null);
    try {
      await onCreate(n);
      setName("");
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not create");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[60] flex items-end justify-center bg-black/60 sm:items-center"
      role="dialog"
      aria-modal
      aria-labelledby="playlist-manager-title"
    >
      <button type="button" className="absolute inset-0" aria-label="Close" onClick={onClose} />
      <div className="relative z-10 w-full max-w-md rounded-t-2xl bg-spotify-elevated p-5 shadow-2xl sm:rounded-2xl">
        <h2 id="playlist-manager-title" className="text-lg font-semibold text-white">
          New playlist
        </h2>
        <p className="mt-1 text-sm text-spotify-muted">Give it a name you’ll recognize.</p>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="My playlist"
          className="mt-4 w-full rounded-lg border border-spotify-border bg-spotify-highlight px-3 py-2.5 text-white placeholder:text-spotify-muted outline-none focus:border-spotify-accent"
          maxLength={255}
          autoFocus
        />
        {err && <p className="mt-2 text-sm text-red-400">{err}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-full px-4 py-2 text-sm font-medium text-spotify-muted hover:text-white"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={busy || !name.trim()}
            onClick={() => void submit()}
            className="rounded-full bg-spotify-accent px-5 py-2 text-sm font-semibold text-black transition enabled:hover:bg-spotify-accentHover disabled:opacity-40"
          >
            {busy ? "Creating…" : "Create"}
          </button>
        </div>
      </div>
    </div>
  );
}
