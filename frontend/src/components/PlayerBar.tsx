import { useAudioElement } from "../context/AudioRefContext";
import { useCurrentTrack, usePlayerStore } from "../store/playerStore";
import { Cover } from "./TrackList";

export function PlayerBar() {
  const track = useCurrentTrack();
  const queue = usePlayerStore((s) => s.queue);
  const index = usePlayerStore((s) => s.index);
  const isPlaying = usePlayerStore((s) => s.isPlaying);
  const currentTime = usePlayerStore((s) => s.currentTime);
  const duration = usePlayerStore((s) => s.duration);
  const toggle = usePlayerStore((s) => s.toggle);
  const next = usePlayerStore((s) => s.next);
  const prev = usePlayerStore((s) => s.prev);
  const seek = usePlayerStore((s) => s.seek);
  const audioRef = useAudioElement();

  if (!track) return null;

  const dur = duration > 0 ? duration : track.duration_sec ?? 0;
  const pct = dur > 0 ? Math.min(100, (currentTime / dur) * 100) : 0;
  const canPrev = index > 0 || currentTime > 3;
  const canNext = index < queue.length - 1;

  return (
    <div className="fixed bottom-[calc(3.75rem+max(env(safe-area-inset-bottom),0px))] left-0 right-0 z-40 border-t border-spotify-border bg-spotify-elevated/95 px-3 pt-2 backdrop-blur-md">
      <div className="relative mb-3 h-1.5 w-full">
        <div className="pointer-events-none absolute inset-0 rounded-full bg-white/10" />
        <div
          className="pointer-events-none absolute inset-y-0 left-0 rounded-full bg-spotify-accent"
          style={{ width: `${pct}%` }}
        />
        <input
          type="range"
          min={0}
          max={Math.max(dur, 0.001)}
          step={0.25}
          value={Math.min(currentTime, dur || 0)}
          onChange={(e) => {
            const t = parseFloat(e.target.value);
            seek(t);
            if (audioRef?.current) audioRef.current.currentTime = t;
          }}
          className="absolute inset-0 z-10 h-full w-full cursor-pointer opacity-0"
          aria-label="Seek"
        />
      </div>
      <div className="flex items-center gap-3">
        <Cover url={track.cover_url} title={track.title} small priority />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-white">{track.title}</p>
          <p className="truncate text-xs text-spotify-muted">{track.artist}</p>
        </div>
        <div className="flex shrink-0 items-center gap-0.5">
          <IconButton label="Previous" disabled={!canPrev} onClick={() => prev()}>
            <PrevIcon />
          </IconButton>
          <button
            type="button"
            onClick={() => toggle()}
            className="mx-0.5 flex h-10 w-10 items-center justify-center rounded-full bg-white text-black shadow-lg transition hover:scale-105 active:scale-95"
            aria-label={isPlaying ? "Pause" : "Play"}
          >
            {isPlaying ? <PauseIcon /> : <PlayIcon />}
          </button>
          <IconButton label="Next" disabled={!canNext} onClick={() => next()}>
            <NextIcon />
          </IconButton>
        </div>
      </div>
    </div>
  );
}

function IconButton({
  children,
  onClick,
  disabled,
  label,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  label: string;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="rounded-full p-2 text-spotify-muted transition enabled:hover:text-white disabled:opacity-30"
    >
      {children}
    </button>
  );
}

function PlayIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
      <path d="M8 5v14l11-7z" />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
      <path d="M6 5h4v14H6V5Zm8 0h4v14h-4V5Z" />
    </svg>
  );
}

function PrevIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
      <path d="M6 6h2v12H6V6Zm11 6-8 5V7l8 5Z" />
    </svg>
  );
}

function NextIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
      <path d="M16 6h2v12h-2V6ZM6 18V6l8 6-8 6Z" />
    </svg>
  );
}
