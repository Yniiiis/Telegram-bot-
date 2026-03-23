import { memo, useEffect, useState } from "react";

import { HypeMark } from "./HypeMark";
import type { Track } from "../types";

interface TrackListProps {
  tracks: Track[];
  activeId?: string | null;
  favoriteIds?: Set<string>;
  onPlay: (track: Track, index: number) => void;
  /** Tap artist name → artist page (does not start playback). */
  onArtistClick?: (artist: string) => void;
  onToggleFavorite?: (track: Track) => void;
  /** When set, show remove control instead of Hype (e.g. playlist editing). */
  onRemoveFromList?: (track: Track) => void;
  emptyLabel?: string;
}

export function TrackList({
  tracks,
  activeId,
  favoriteIds,
  onPlay,
  onArtistClick,
  onToggleFavorite,
  onRemoveFromList,
  emptyLabel = "Nothing here yet",
}: TrackListProps) {
  if (tracks.length === 0) {
    return (
      <p className="px-1 py-8 text-center text-sm text-spotify-muted">{emptyLabel}</p>
    );
  }

  return (
    <ul className="flex flex-col gap-0.5">
      {tracks.map((track, index) => {
        const active = track.id === activeId;
        const fav = favoriteIds?.has(track.id);
        return (
          <li key={track.id}>
            <button
              type="button"
              onClick={() => onPlay(track, index)}
              className={`flex w-full items-center gap-3 rounded-lg px-2 py-2.5 text-left transition active:scale-[0.99] ${
                active ? "bg-spotify-highlight" : "hover:bg-white/5"
              }`}
            >
              <Cover url={track.cover_url} title={track.title} small lazy />
              <div className="min-w-0 flex-1">
                <p
                  className={`truncate text-sm font-medium ${active ? "text-spotify-accent" : "text-white"}`}
                >
                  {track.title}
                </p>
                {onArtistClick ? (
                  <button
                    type="button"
                    className="block w-full truncate text-left text-xs text-spotify-muted hover:text-spotify-accent hover:underline"
                    onClick={(e) => {
                      e.stopPropagation();
                      onArtistClick(track.artist);
                    }}
                  >
                    {track.artist}
                  </button>
                ) : (
                  <p className="truncate text-xs text-spotify-muted">{track.artist}</p>
                )}
              </div>
              {track.duration_sec != null && (
                <span className="shrink-0 tabular-nums text-xs text-spotify-muted">
                  {formatDuration(track.duration_sec)}
                </span>
              )}
              {onRemoveFromList && (
                <span
                  role="button"
                  tabIndex={0}
                  className="shrink-0 p-1 text-spotify-muted hover:text-red-400"
                  onClick={(e) => {
                    e.stopPropagation();
                    onRemoveFromList(track);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      e.stopPropagation();
                      onRemoveFromList(track);
                    }
                  }}
                >
                  <RemoveIcon />
                </span>
              )}
              {onToggleFavorite && !onRemoveFromList && (
                <span
                  role="button"
                  tabIndex={0}
                  className="shrink-0 p-1 text-spotify-muted hover:text-white"
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleFavorite(track);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      e.stopPropagation();
                      onToggleFavorite(track);
                    }
                  }}
                >
                  <HypeMark filled={!!fav} />
                </span>
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export const Cover = memo(function Cover({
  url,
  title,
  small,
  lazy,
  priority,
}: {
  url: string | null;
  title: string;
  small?: boolean;
  /** Defer loading until near viewport (lists). */
  lazy?: boolean;
  /** Current track / hero — load immediately. */
  priority?: boolean;
}) {
  const size = small ? "h-12 w-12" : "h-14 w-14";
  const [imgFailed, setImgFailed] = useState(false);

  useEffect(() => {
    setImgFailed(false);
  }, [url]);

  if (url && !imgFailed) {
    return (
      <img
        src={url}
        alt=""
        width={small ? 48 : 56}
        height={small ? 48 : 56}
        loading={priority ? "eager" : lazy ? "lazy" : "eager"}
        decoding="async"
        fetchPriority={priority ? "high" : lazy ? "low" : "auto"}
        className={`${size} shrink-0 rounded-md bg-spotify-highlight object-cover`}
        onError={() => setImgFailed(true)}
      />
    );
  }
  return (
    <div
      className={`${size} flex shrink-0 items-center justify-center rounded-md bg-gradient-to-br from-spotify-highlight to-spotify-border text-xs font-bold text-spotify-muted`}
    >
      {title.slice(0, 1).toUpperCase()}
    </div>
  );
});

function formatDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function RemoveIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden>
      <path d="M6 7h12M10 7V5h4v2M9 7l1 12h4l1-12" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
