import { useEffect, useRef } from "react";

import { recordPlay, streamUrl } from "../lib/api";
import { useAuthStore } from "../store/authStore";
import { useMediaSession } from "./useMediaSession";
import { useCurrentTrack, usePlayerStore } from "../store/playerStore";

/** Binds hidden <audio> to Zustand player state. */
export function usePlayerEngine(): React.RefObject<HTMLAudioElement | null> {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const streamErrorRetries = useRef(0);
  useMediaSession(audioRef);
  const token = useAuthStore((s) => s.token);
  const track = useCurrentTrack();
  const isPlaying = usePlayerStore((s) => s.isPlaying);
  const setTimes = usePlayerStore((s) => s.setTimes);
  const next = usePlayerStore((s) => s.next);
  const clearPlaybackError = usePlayerStore((s) => s.clearPlaybackError);
  const setPlaybackError = usePlayerStore((s) => s.setPlaybackError);

  useEffect(() => {
    if (!track?.id || !token) return;
    void recordPlay(token, track.id);
  }, [track?.id, token]);

  useEffect(() => {
    const el = audioRef.current;
    if (!el || !track || !token) return;

    streamErrorRetries.current = 0;
    const url = streamUrl(track.id, token);
    if (el.src !== url) {
      clearPlaybackError();
      el.src = url;
      el.load();
    }
  }, [track?.id, token, clearPlaybackError]);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    if (!track || !token) return;

    let rafId = 0;
    const onTime = () => {
      if (rafId) return;
      rafId = requestAnimationFrame(() => {
        rafId = 0;
        setTimes(el.currentTime, Number.isFinite(el.duration) ? el.duration : 0);
      });
    };
    const onEnded = () => next();

    const isStillThisTrack = () => {
      const st = usePlayerStore.getState();
      if (st.queue[st.index]?.id !== track.id) return false;
      if (!el.src) return false;
      try {
        const path = new URL(el.src, window.location.origin).pathname;
        return path.includes(`/stream/${track.id}`);
      } catch {
        return el.src.includes(track.id);
      }
    };

    const onError = () => {
      // Switching `src` often aborts the previous load — do not skip the new track.
      const code = el.error?.code;
      if (code === MediaError.MEDIA_ERR_ABORTED) return;
      if (!isStillThisTrack()) return;

      const st = usePlayerStore.getState();
      if (streamErrorRetries.current < 1) {
        streamErrorRetries.current += 1;
        clearPlaybackError();
        el.load();
        if (st.isPlaying) void el.play().catch(() => {});
        return;
      }

      setPlaybackError(
        "This track could not be played (unavailable or blocked). Skipping to the next one…",
      );
      next();
    };

    el.addEventListener("timeupdate", onTime);
    el.addEventListener("ended", onEnded);
    el.addEventListener("error", onError);
    return () => {
      if (rafId) cancelAnimationFrame(rafId);
      el.removeEventListener("timeupdate", onTime);
      el.removeEventListener("ended", onEnded);
      el.removeEventListener("error", onError);
    };
  }, [track?.id, token, next, setTimes, setPlaybackError, clearPlaybackError]);

  useEffect(() => {
    const el = audioRef.current;
    if (!el || !track) return;
    if (isPlaying) {
      void el.play().catch(() => {
        setPlaybackError("Playback failed to start. The track may be unavailable.");
        usePlayerStore.getState().pause();
      });
    } else {
      el.pause();
    }
  }, [isPlaying, track?.id, setPlaybackError]);

  // If the browser / WebView pauses the element when the tab or mini-app goes to background, try to resume when the user expects playback.
  useEffect(() => {
    const el = audioRef.current;
    if (!el || !track) return;
    const resumeIfNeeded = () => {
      const { isPlaying: shouldPlay } = usePlayerStore.getState();
      if (shouldPlay && el.paused) void el.play().catch(() => {});
    };
    document.addEventListener("visibilitychange", resumeIfNeeded);
    return () => document.removeEventListener("visibilitychange", resumeIfNeeded);
  }, [track?.id]);

  return audioRef;
}
