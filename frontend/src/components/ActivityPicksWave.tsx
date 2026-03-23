import { HypeMark } from "./HypeMark";
import type { Track } from "../types";
import { Cover } from "./TrackList";

interface ActivityPicksWaveProps {
  tracks: Track[];
  activeId: string | null;
  favoriteIds: Set<string>;
  onPlay: (track: Track, index: number) => void;
  onToggleFavorite: (track: Track) => void;
  onArtistClick?: (artist: string) => void;
}

/** Horizontal «wave» strip for activity-based picks (scroll + decorative bars). */
export function ActivityPicksWave({
  tracks,
  activeId,
  favoriteIds,
  onPlay,
  onToggleFavorite,
  onArtistClick,
}: ActivityPicksWaveProps) {
  if (tracks.length === 0) return null;

  const barHeights = [10, 18, 8, 22, 14, 20, 6, 16, 12, 24, 9, 19, 7, 15, 11, 21, 13, 17, 8, 14, 10, 18, 12, 16];

  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-gradient-to-b from-spotify-elevated/95 to-spotify-base pb-4 pt-2 shadow-lg shadow-black/20">
      <svg
        className="pointer-events-none absolute inset-x-0 top-0 h-8 w-full text-spotify-accent/30"
        viewBox="0 0 480 32"
        preserveAspectRatio="none"
        aria-hidden
      >
        <path
          fill="currentColor"
          d="M0,20 Q60,4 120,18 T240,14 T360,20 T480,16 L480,32 L0,32 Z"
        />
      </svg>

      <div className="relative z-10 flex h-6 items-end justify-center gap-0.5 px-6 pt-4">
        {barHeights.map((h, i) => (
          <span
            key={i}
            className="w-0.5 shrink-0 rounded-full bg-spotify-accent/70"
            style={{ height: `${h}px` }}
          />
        ))}
      </div>

      <div className="relative z-10 mt-4 flex gap-3 overflow-x-auto px-3 pb-1 pt-1 snap-x snap-mandatory [-webkit-overflow-scrolling:touch]">
        {tracks.map((track, index) => {
          const active = track.id === activeId;
          const fav = favoriteIds.has(track.id);
          return (
            <div
              key={track.id}
              className={`snap-start w-[10.25rem] shrink-0 rounded-xl p-2 transition ${
                active ? "bg-spotify-highlight ring-1 ring-spotify-accent/60" : "bg-white/5 hover:bg-white/10"
              }`}
            >
              <button
                type="button"
                onClick={() => onPlay(track, index)}
                className="flex w-full flex-col gap-2 text-left"
              >
                <Cover url={track.cover_url} title={track.title} lazy />
                <div className="min-w-0">
                  <p
                    className={`line-clamp-2 text-sm font-medium leading-snug ${
                      active ? "text-spotify-accent" : "text-white"
                    }`}
                  >
                    {track.title}
                  </p>
                </div>
              </button>
              {onArtistClick ? (
                <button
                  type="button"
                  className="mt-0.5 line-clamp-2 w-full text-left text-xs text-spotify-muted hover:text-spotify-accent hover:underline"
                  onClick={() => onArtistClick(track.artist)}
                >
                  {track.artist}
                </button>
              ) : (
                <p className="mt-0.5 line-clamp-2 text-xs text-spotify-muted">{track.artist}</p>
              )}
              <button
                type="button"
                aria-label={fav ? "Убрать из Hype" : "В Hype"}
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleFavorite(track);
                }}
                className="mt-1 flex w-full items-center justify-end text-spotify-muted hover:text-white"
              >
                <HypeMark filled={fav} size={20} />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
