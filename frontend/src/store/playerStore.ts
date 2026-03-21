import { create } from "zustand";

import type { Track } from "../types";

interface PlayerState {
  queue: Track[];
  index: number;
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  playbackError: string | null;
  setQueue: (tracks: Track[], startIndex?: number) => void;
  appendToQueue: (tracks: Track[]) => void;
  setIndex: (index: number) => void;
  play: () => void;
  pause: () => void;
  toggle: () => void;
  next: () => void;
  prev: () => void;
  seek: (time: number) => void;
  setTimes: (currentTime: number, duration: number) => void;
  resetProgress: () => void;
  setPlaybackError: (message: string | null) => void;
  clearPlaybackError: () => void;
}

export const usePlayerStore = create<PlayerState>((set, get) => ({
  queue: [],
  index: 0,
  isPlaying: false,
  currentTime: 0,
  duration: 0,
  playbackError: null,

  setQueue: (tracks, startIndex = 0) =>
    set({
      queue: tracks,
      index: Math.min(startIndex, Math.max(0, tracks.length - 1)),
      isPlaying: tracks.length > 0,
      currentTime: 0,
      duration: 0,
      playbackError: null,
    }),

  appendToQueue: (tracks) =>
    set((s) => ({
      queue: [...s.queue, ...tracks],
    })),

  setIndex: (index) => {
    const { queue } = get();
    if (index < 0 || index >= queue.length) return;
    set({ index, currentTime: 0, duration: 0, isPlaying: true, playbackError: null });
  },

  play: () => set({ isPlaying: true }),
  pause: () => set({ isPlaying: false }),
  toggle: () => set((s) => ({ isPlaying: !s.isPlaying })),

  next: () => {
    const { queue, index } = get();
    if (index < queue.length - 1) {
      set({
        index: index + 1,
        currentTime: 0,
        duration: 0,
        isPlaying: true,
        playbackError: null,
      });
    } else {
      set({ isPlaying: false, currentTime: 0 });
    }
  },

  prev: () => {
    const { index, currentTime } = get();
    if (currentTime > 3) {
      set({ currentTime: 0 });
      return;
    }
    if (index > 0) {
      set({
        index: index - 1,
        currentTime: 0,
        duration: 0,
        isPlaying: true,
        playbackError: null,
      });
    } else {
      set({ currentTime: 0 });
    }
  },

  seek: (time) => set({ currentTime: time }),

  setTimes: (currentTime, duration) => set({ currentTime, duration }),

  resetProgress: () => set({ currentTime: 0, duration: 0 }),

  setPlaybackError: (message) => set({ playbackError: message }),

  clearPlaybackError: () => set({ playbackError: null }),
}));

export function useCurrentTrack(): Track | null {
  const queue = usePlayerStore((s) => s.queue);
  const index = usePlayerStore((s) => s.index);
  return queue[index] ?? null;
}
