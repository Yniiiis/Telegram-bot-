import { useEffect, type RefObject } from "react";
import { useCurrentTrack, usePlayerStore } from "../store/playerStore";

const MEDIA_ACTIONS: MediaSessionAction[] = [
  "play",
  "pause",
  "stop",
  "previoustrack",
  "nexttrack",
  "seekbackward",
  "seekforward",
  "seekto",
];

function trySetActionHandler(
  ms: MediaSession,
  action: MediaSessionAction,
  handler: MediaSessionActionHandler | null,
): void {
  try {
    ms.setActionHandler(action, handler);
  } catch {
    /* action not supported on this browser */
  }
}

function resolveArtworkUrl(cover: string | null | undefined): string | undefined {
  if (!cover?.trim()) return undefined;
  try {
    return new URL(cover, window.location.origin).href;
  } catch {
    return undefined;
  }
}

function guessImageType(url: string): string | undefined {
  const lower = url.split("?")[0]?.toLowerCase() ?? "";
  if (lower.endsWith(".png")) return "image/png";
  if (lower.endsWith(".webp")) return "image/webp";
  if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
  return undefined;
}

/**
 * Lock screen / notification / headset controls and better background audio hints
 * (Chrome, Edge, Android; partial support in Safari / in-app WebViews).
 */
export function useMediaSession(audioRef: RefObject<HTMLAudioElement | null>): void {
  const track = useCurrentTrack();
  const isPlaying = usePlayerStore((s) => s.isPlaying);
  const currentTime = usePlayerStore((s) => s.currentTime);
  const duration = usePlayerStore((s) => s.duration);

  useEffect(() => {
    if (typeof navigator === "undefined" || !("mediaSession" in navigator)) return;
    const ms = navigator.mediaSession;

    for (const action of MEDIA_ACTIONS) {
      trySetActionHandler(ms, action, null);
    }

    trySetActionHandler(ms, "play", () => {
      usePlayerStore.getState().play();
    });
    trySetActionHandler(ms, "pause", () => {
      usePlayerStore.getState().pause();
    });
    trySetActionHandler(ms, "stop", () => {
      usePlayerStore.getState().pause();
    });
    trySetActionHandler(ms, "previoustrack", () => {
      usePlayerStore.getState().prev();
    });
    trySetActionHandler(ms, "nexttrack", () => {
      usePlayerStore.getState().next();
    });
    trySetActionHandler(ms, "seekbackward", (d) => {
      const el = audioRef.current;
      if (!el) return;
      const skip = d.seekOffset ?? 10;
      el.currentTime = Math.max(0, el.currentTime - skip);
      usePlayerStore.getState().seek(el.currentTime);
    });
    trySetActionHandler(ms, "seekforward", (d) => {
      const el = audioRef.current;
      if (!el) return;
      const skip = d.seekOffset ?? 10;
      const end = Number.isFinite(el.duration) && el.duration > 0 ? el.duration : el.currentTime + skip;
      el.currentTime = Math.min(end, el.currentTime + skip);
      usePlayerStore.getState().seek(el.currentTime);
    });
    trySetActionHandler(ms, "seekto", (d) => {
      if (d.seekTime == null) return;
      const el = audioRef.current;
      if (el) el.currentTime = d.seekTime;
      usePlayerStore.getState().seek(d.seekTime);
    });

    return () => {
      for (const action of MEDIA_ACTIONS) {
        trySetActionHandler(ms, action, null);
      }
    };
  }, [audioRef]);

  useEffect(() => {
    if (typeof navigator === "undefined" || !("mediaSession" in navigator)) return;
    navigator.mediaSession.playbackState = isPlaying ? "playing" : "paused";
  }, [isPlaying]);

  useEffect(() => {
    if (typeof navigator === "undefined" || !("mediaSession" in navigator)) return;
    const ms = navigator.mediaSession;

    if (!track) {
      ms.metadata = null;
      return;
    }

    const artUrl = resolveArtworkUrl(track.cover_url);
    const artwork: MediaImage[] = [];
    if (artUrl) {
      const type = guessImageType(artUrl);
      artwork.push(
        type
          ? { src: artUrl, sizes: "512x512", type }
          : { src: artUrl, sizes: "512x512" },
      );
    }

    ms.metadata = new MediaMetadata({
      title: track.title,
      artist: track.artist,
      album: track.source,
      artwork,
    });
  }, [track]);

  useEffect(() => {
    if (typeof navigator === "undefined" || !("mediaSession" in navigator)) return;
    const el = audioRef.current;
    const durFromAudio =
      el && Number.isFinite(el.duration) && el.duration > 0 ? el.duration : 0;
    const durFromStore = duration > 0 ? duration : 0;
    const durFromTrack = track && track.duration_sec && track.duration_sec > 0 ? track.duration_sec : 0;
    const dur = durFromAudio || durFromStore || durFromTrack;
    if (!track || dur <= 0 || !Number.isFinite(dur)) return;

    const position = Number.isFinite(currentTime) ? Math.min(Math.max(0, currentTime), dur) : 0;
    const rate = el?.playbackRate && el.playbackRate > 0 ? el.playbackRate : 1;

    try {
      navigator.mediaSession.setPositionState({
        duration: dur,
        playbackRate: isPlaying ? rate : 0,
        position,
      });
    } catch {
      /* invalid state on some browsers */
    }
  }, [audioRef, track?.id, track?.duration_sec, currentTime, duration, isPlaying]);
}
