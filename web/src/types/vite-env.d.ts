interface ImportMetaEnv {
  readonly VITE_NEWS_CANDIDATE_PREVIEW?: string;
  readonly VITE_CHAT_ENABLED?: string;
  readonly VITE_CHAT_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
