import { useEffect } from "react";

import type { Track } from "../types";

/** Warm browser cache for upcoming row covers (best-effort). */
export function usePrefetchCovers(tracks: Track[], max = 18): void {
  useEffect(() => {
    const n = Math.min(max, tracks.length);
    for (let i = 0; i < n; i++) {
      const u = tracks[i]?.cover_url;
      if (!u?.trim()) continue;
      const img = new Image();
      img.decoding = "async";
      img.src = u;
    }
  }, [tracks, max]);
}
