import { usePlayerStore } from "../store/playerStore";

export function PlaybackErrorBanner() {
  const message = usePlayerStore((s) => s.playbackError);
  const clear = usePlayerStore((s) => s.clearPlaybackError);

  if (!message) return null;

  return (
    <div
      role="alert"
      className="mb-4 flex items-start gap-2 rounded-lg border border-amber-600/40 bg-amber-950/40 px-3 py-2 text-sm text-amber-100"
    >
      <span className="min-w-0 flex-1">{message}</span>
      <button
        type="button"
        onClick={() => clear()}
        className="shrink-0 rounded px-2 py-0.5 text-amber-200 hover:bg-white/10"
      >
        Dismiss
      </button>
    </div>
  );
}
