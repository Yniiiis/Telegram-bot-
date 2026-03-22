import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { authDev, authTelegram } from "./lib/api";
import { getInitData, initTelegramUi, isTelegramWebApp } from "./lib/telegram";
import { useAuthStore } from "./store/authStore";
import { AppShell } from "./layout/AppShell";
import { FavoritesPage } from "./pages/FavoritesPage";
import { HomePage } from "./pages/HomePage";
import { PlaylistDetailPage } from "./pages/PlaylistDetailPage";
import { PlaylistsPage } from "./pages/PlaylistsPage";
import { SearchPage } from "./pages/SearchPage";

function previewAuthEnabled(): boolean {
  const v = import.meta.env.VITE_PREVIEW_AUTH;
  return v === "1" || v === "true";
}

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
    const allowPreviewLogin = import.meta.env.DEV || previewAuthEnabled();

    async function bootstrap() {
      let initData = getInitData();
      if (!initData && isTelegramWebApp()) {
        await new Promise((r) => setTimeout(r, 100));
        initData = getInitData();
      }
      if (!initData && isTelegramWebApp()) {
        await new Promise((r) => setTimeout(r, 400));
        initData = getInitData();
      }
      try {
        if (initData) {
          const { access_token, user } = await authTelegram(initData);
          if (!cancelled) setSession(access_token, user);
        } else if (allowPreviewLogin && devToken) {
          if (!cancelled) {
            setSession(devToken, {
              id: 0,
              telegram_id: 0,
              username: "dev",
              first_name: "Dev",
            });
          }
        } else if (allowPreviewLogin) {
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
          {import.meta.env.PROD && !previewAuthEnabled() ? (
            <>
              Open the app with your bot&apos;s <strong>Web App</strong> button inside Telegram. If you open the
              Vercel URL in a normal browser, Telegram does not pass login data. In BotFather, the Mini App URL must
              be this same HTTPS address.
            </>
          ) : (
            <>
              Open this Mini App from your bot to stream music.{" "}
              {import.meta.env.DEV && (
                <>
                  Local dev: set <code className="text-spotify-accent">ALLOW_DEV_AUTH=1</code> in{" "}
                  <code className="text-spotify-accent">backend/.env</code> and restart the API, or paste a JWT in{" "}
                  <code className="text-spotify-accent">VITE_DEV_BEARER_TOKEN</code> in{" "}
                  <code className="text-spotify-accent">frontend/.env</code>.
                </>
              )}
              {import.meta.env.PROD && previewAuthEnabled() && (
                <>
                  {" "}
                  Preview: <code className="text-spotify-accent">VITE_PREVIEW_AUTH=1</code> is on — backend needs{" "}
                  <code className="text-spotify-accent">ALLOW_DEV_AUTH=1</code> and matching{" "}
                  <code className="text-spotify-accent">VITE_API_BASE_URL</code>.
                </>
              )}
            </>
          )}
        </p>
        {error && <p className="text-sm text-red-400">{error}</p>}
        {!error && isTelegramWebApp() && (
          <p className="max-w-md text-xs text-amber-200/90">
            If you opened this from Telegram but still see this screen, register your app URL in @BotFather:
            <span className="text-spotify-muted"> /mybots → your bot → Bot Settings → </span>
            <strong>Mini App</strong>
            <span className="text-spotify-muted"> → enable / add domain </span>
            (your <code className="text-spotify-accent">*.vercel.app</code> host). Then open the app using the
            bot&apos;s <strong>Web App</strong> keyboard button, not a plain browser link.
          </p>
        )}
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
