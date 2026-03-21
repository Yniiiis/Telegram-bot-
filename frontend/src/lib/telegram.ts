import WebApp from "@twa-dev/sdk";

declare global {
  interface Window {
    Telegram?: { WebApp?: { initData: string; ready: () => void; expand: () => void } };
  }
}

/** Survives client-side navigations after first load (same tab). */
const INIT_DATA_SESSION_KEY = "tg-music-raw-init-data";

/**
 * Telegram may pass signed init data in the URL hash as query-style params:
 * #tgWebAppData=...&tgWebAppVersion=...
 * @see https://docs.telegram-mini-apps.com/platform/launch-parameters
 */
function getInitDataFromLocation(): string {
  if (typeof window === "undefined") return "";

  const parse = (raw: string): string => {
    if (!raw) return "";
    const trimmed = raw.startsWith("#") ? raw.slice(1) : raw.startsWith("?") ? raw.slice(1) : raw;
    const params = new URLSearchParams(trimmed);
    const data = params.get("tgWebAppData");
    return data?.trim() ?? "";
  };

  const fromHash = parse(window.location.hash);
  if (fromHash) return fromHash;
  return parse(window.location.search);
}

function rememberInitData(value: string): void {
  if (!value) return;
  try {
    sessionStorage.setItem(INIT_DATA_SESSION_KEY, value);
  } catch {
    /* private mode / quota */
  }
}

function recallInitData(): string {
  try {
    return sessionStorage.getItem(INIT_DATA_SESSION_KEY)?.trim() ?? "";
  } catch {
    return "";
  }
}

export function initTelegramUi(): void {
  window.Telegram?.WebApp?.ready();
  WebApp.ready();
  WebApp.expand();
  const bg = WebApp.themeParams.bg_color ?? "#121212";
  const fg = WebApp.themeParams.text_color ?? "#ffffff";
  document.documentElement.style.setProperty("--tg-theme-bg-color", bg);
  document.documentElement.style.setProperty("--tg-theme-text-color", fg);
}

/** True when running inside Telegram’s WebView (Mini App or web_app link). */
export function isTelegramWebApp(): boolean {
  return typeof window !== "undefined" && Boolean(window.Telegram?.WebApp);
}

/**
 * Raw signed init_data for POST /auth/telegram.
 * Order: WebApp API → URL launch params → session backup (after first successful read).
 */
export function getInitData(): string {
  const fromNative = window.Telegram?.WebApp?.initData?.trim() ?? "";
  if (fromNative) {
    rememberInitData(fromNative);
    return fromNative;
  }

  const fromSdk = WebApp.initData?.trim() ?? "";
  if (fromSdk) {
    rememberInitData(fromSdk);
    return fromSdk;
  }

  const fromUrl = getInitDataFromLocation();
  if (fromUrl) {
    rememberInitData(fromUrl);
    return fromUrl;
  }

  return recallInitData();
}
