import { useEffect, useRef } from "react";

import { getSimilarTracks, isNgrokApiBase, recordPlay, streamUrl } from "../lib/api";
import { ensureNgrokStreamSw } from "../lib/ngrokStreamSw";
import { useAuthStore } from "../store/authStore";
import { useMediaSession } from "./useMediaSession";
import { useCurrentTrack, usePlayerStore } from "../store/playerStore";

const PREMATURE_END_MAX_RETRIES = 2;

/**
 * WebViews often mis-report `HTMLMediaElement.duration` when the stream stalls or only a chunk
 * was buffered (e.g. ~10–15s) — then `ended` fires with cur≈dur and the old check did not treat
 * that as premature. Use catalog `duration_sec` when present to detect truncated playback.
 */
function isNaturalPlaybackEnd(
  currentTime: number,
  htmlDuration: number,
  catalogDurationSec: number | null | undefined,
): boolean {
  const meta =
    catalogDurationSec != null && catalogDurationSec > 0 ? catalogDurationSec : null;
  const html = Number.isFinite(htmlDuration) ? htmlDuration : NaN;

  if (meta != null && currentTime >= meta - 3) {
    return true;
  }

  const htmlLooksTruncated =
    meta != null && Number.isFinite(html) && html >= 2 && meta > html + 5;

  if (
    !htmlLooksTruncated &&
    Number.isFinite(html) &&
    html >= 2 &&
    currentTime >= html - 1.5
  ) {
    return true;
  }

  return false;
}

function playWhenBuffered(
  el: HTMLAudioElement,
  setPlaybackError: (msg: string) => void,
): void {
  const tryPlay = () => {
    if (!usePlayerStore.getState().isPlaying) return;
    void el.play().catch(() => {
      setPlaybackError("Playback failed to start. The track may be unavailable.");
      usePlayerStore.getState().pause();
    });
  };
  if (el.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
    tryPlay();
    return;
  }
  el.addEventListener("canplay", tryPlay, { once: true });
}

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
  const mergeSimilarAfterCurrent = usePlayerStore((s) => s.mergeSimilarAfterCurrent);

  useEffect(() => {
    if (!track?.id || !token) return;
    void recordPlay(token, track.id);
  }, [track?.id, token]);

  useEffect(() => {
    if (!track?.id || !token) return;
    const ac = new AbortController();
    void (async () => {
      try {
        const rows = await getSimilarTracks(token, track.id, 16);
        if (ac.signal.aborted || !rows.length) return;
        mergeSimilarAfterCurrent(rows);
      } catch {
        /* radio suggestions are optional */
      }
    })();
    return () => ac.abort();
  }, [track?.id, token, mergeSimilarAfterCurrent]);

  useEffect(() => {
    const el = audioRef.current;
    if (!el || !track || !token) return;

    streamErrorRetries.current = 0;
    const url = streamUrl(track.id, token);

    if (!isNgrokApiBase()) {
      if (el.src !== url) {
        clearPlaybackError();
        el.src = url;
        el.load();
        playWhenBuffered(el, setPlaybackError);
      }
      return;
    }

    const ac = new AbortController();
    let cancelled = false;
    clearPlaybackError();

    void (async () => {
      try {
        const swOk = await ensureNgrokStreamSw();
        if (cancelled || ac.signal.aborted) return;

        if (swOk) {
          if (el.src.startsWith("blob:")) URL.revokeObjectURL(el.src);
          el.src = url;
          el.load();
          playWhenBuffered(el, setPlaybackError);
          return;
        }

        const res = await fetch(url, {
          headers: { "ngrok-skip-browser-warning": "1" },
          signal: ac.signal,
        });
        if (!res.ok) throw new Error(String(res.status));
        const blob = await res.blob();
        if (cancelled || ac.signal.aborted) return;
        if (el.src.startsWith("blob:")) URL.revokeObjectURL(el.src);
        el.src = URL.createObjectURL(blob);
        el.load();
        playWhenBuffered(el, setPlaybackError);
      } catch (e) {
        if (cancelled || ac.signal.aborted || (e instanceof DOMException && e.name === "AbortError")) return;
        setPlaybackError(
          "Audio cannot load through ngrok. Allow the service worker (reload once) or use a public API URL without the ngrok browser warning.",
        );
      }
    })();

    return () => {
      cancelled = true;
      ac.abort();
      if (el.src.startsWith("blob:")) URL.revokeObjectURL(el.src);
    };
  }, [track?.id, token, clearPlaybackError, setPlaybackError]);

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

    const isStillThisTrack = () => {
      const st = usePlayerStore.getState();
      if (st.queue[st.index]?.id !== track.id) return false;
      if (!el.src) return false;
      if (el.src.startsWith("blob:")) return true;
      try {
        const path = new URL(el.src, window.location.origin).pathname;
        return path.includes(`/stream/${track.id}`);
      } catch {
        return el.src.includes(track.id);
      }
    };

    const onEnded = () => {
      if (!isStillThisTrack()) return;
      const dur = el.duration;
      const cur = el.currentTime;
      const natural = isNaturalPlaybackEnd(cur, dur, track.duration_sec);
      // Unknown HTML duration / very start: still treat as flaky end (retry).
      const looksPremature =
        !natural ||
        (!Number.isFinite(dur) && cur < 2) ||
        (Number.isFinite(dur) && dur >= 2 && cur < 1);
      if (looksPremature) {
        if (streamErrorRetries.current < PREMATURE_END_MAX_RETRIES) {
          streamErrorRetries.current += 1;
          clearPlaybackError();
          el.load();
          const st = usePlayerStore.getState();
          if (st.isPlaying) void el.play().catch(() => {});
          return;
        }
        setPlaybackError("Playback stopped before the end of the track. Try again or pick another track.");
        usePlayerStore.getState().pause();
        return;
      }
      next();
    };

    const onError = () => {
      // Switching `src` often aborts the previous load — do not skip the new track.
      const code = el.error?.code;
      if (code === MediaError.MEDIA_ERR_ABORTED) return;
      if (!isStillThisTrack()) return;

      const st = usePlayerStore.getState();
      if (streamErrorRetries.current < PREMATURE_END_MAX_RETRIES) {
        streamErrorRetries.current += 1;
        clearPlaybackError();
        el.load();
        if (st.isPlaying) void el.play().catch(() => {});
        return;
      }

      setPlaybackError(
        "This track could not be played (unavailable or blocked). Try another track or tap play again.",
      );
      usePlayerStore.getState().pause();
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
  }, [track?.id, track?.duration_sec, token, next, setTimes, setPlaybackError, clearPlaybackError]);

  useEffect(() => {
    const el = audioRef.current;
    if (!el || !track) return;
    if (isPlaying) {
      playWhenBuffered(el, setPlaybackError);
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
