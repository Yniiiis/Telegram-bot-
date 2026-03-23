import type { RefObject } from "react";
import { Outlet } from "react-router-dom";

import { AudioRefContext } from "../context/AudioRefContext";
import { usePlayerEngine } from "../hooks/usePlayerEngine";
import { BottomNav } from "../components/BottomNav";
import { PlaybackErrorBanner } from "../components/PlaybackErrorBanner";
import { PlayerBar } from "../components/PlayerBar";
import { useCurrentTrack } from "../store/playerStore";

export function AppShell() {
  const audioRef = usePlayerEngine();
  const track = useCurrentTrack();
  const dockPad = track ? "pb-[11rem]" : "pb-20";

  return (
    <AudioRefContext.Provider value={audioRef}>
      <div className="min-h-dvh bg-spotify-base text-white">
        <main className={`mx-auto max-w-lg px-4 pt-6 ${dockPad}`}>
          <PlaybackErrorBanner />
          <Outlet />
        </main>
        <PlayerBar />
        <audio
          key={track?.id ?? "idle"}
          ref={audioRef as RefObject<HTMLAudioElement>}
          crossOrigin="anonymous"
          playsInline
          preload="auto"
          className="hidden"
        />
        <BottomNav />
      </div>
    </AudioRefContext.Provider>
  );
}
