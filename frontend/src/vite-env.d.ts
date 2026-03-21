/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  readonly VITE_DEV_BEARER_TOKEN?: string;
  /** Set to 1 on Vercel preview only: allows POST /auth/dev when backend has ALLOW_DEV_AUTH=1. Never in public prod. */
  readonly VITE_PREVIEW_AUTH?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
