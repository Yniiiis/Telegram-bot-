import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { authDev, authTelegram } from "./lib/api";
import { getInitData, initTelegramUi } from "./lib/telegram";
import { useAuthStore } from "./store/authStore";
import { AppShell } from "./layout/AppShell";
import { FavoritesPage } from "./pages/FavoritesPage";
import { HomePage } from "./pages/HomePage";
import { PlaylistDetailPage } from "./pages/PlaylistDetailPage";
import { PlaylistsPage } from "./pages/PlaylistsPage";
import { SearchPage } from "./pages/SearchPage";

export default function App() {
  const token = useAuthStore((s) => s.token);
  const setSession = useAuthStore((s) => s.setSession);
  const clearSession = useAuthStore((s) => s.clearSession);
  const [hydrated, setHydrated] = useState(() => useAuthStore.persist.hasHydrated());
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const unsub = useAuthStore.persist.onFinishHydration(() => setHydrated(true));
    if (useAuthStore.persist.hasHydrated()) setHydrated(true);
    return unsub;
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    initTelegramUi();
    let cancelled = false;
    const devToken = import.meta.env.VITE_DEV_BEARER_TOKEN;

    async function bootstrap() {
      const initData = getInitData();
      try {
        if (initData) {
          const { access_token, user } = await authTelegram(initData);
          if (!cancelled) setSession(access_token, user);
        } else if (import.meta.env.DEV && devToken) {
          if (!cancelled) {
            setSession(devToken, {
              id: 0,
              telegram_id: 0,
              username: "dev",
              first_name: "Dev",
            });
          }
        } else if (import.meta.env.DEV) {
          const dev = await authDev();
          if (!cancelled && dev) setSession(dev.access_token, dev.user);
        }
      } catch (e) {
        if (!cancelled) {
          clearSession();
          setError(e instanceof Error ? e.message : "Authentication failed");
        }
      } finally {
        if (!cancelled) setReady(true);
      }
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, [hydrated, setSession, clearSession]);

  if (!hydrated || !ready) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-spotify-base text-spotify-muted">
        Loading…
      </div>
    );
  }

  if (!token) {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-3 bg-spotify-base px-6 text-center">
        <p className="text-lg font-semibold text-white">Sign in with Telegram</p>
        <p className="text-sm text-spotify-muted">
          Open this Mini App from your bot to stream music.{" "}
          {import.meta.env.DEV && (
            <>
              Local dev: set <code className="text-spotify-accent">ALLOW_DEV_AUTH=1</code> in{" "}
              <code className="text-spotify-accent">backend/.env</code> and restart the API, or paste a JWT in{" "}
              <code className="text-spotify-accent">VITE_DEV_BEARER_TOKEN</code> in{" "}
              <code className="text-spotify-accent">frontend/.env</code>.
            </>
          )}
        </p>
        {error && <p className="text-sm text-red-400">{error}</p>}
      </div>
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<HomePage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/favorites" element={<FavoritesPage />} />
          <Route path="/playlists" element={<PlaylistsPage />} />
          <Route path="/playlists/:id" element={<PlaylistDetailPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
