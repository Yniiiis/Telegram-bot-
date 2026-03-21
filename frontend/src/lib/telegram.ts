import WebApp from "@twa-dev/sdk";

export function initTelegramUi(): void {
  WebApp.ready();
  WebApp.expand();
  const bg = WebApp.themeParams.bg_color ?? "#121212";
  const fg = WebApp.themeParams.text_color ?? "#ffffff";
  document.documentElement.style.setProperty("--tg-theme-bg-color", bg);
  document.documentElement.style.setProperty("--tg-theme-text-color", fg);
}

export function getInitData(): string {
  return WebApp.initData;
}
