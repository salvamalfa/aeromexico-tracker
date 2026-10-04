interface ImportMetaEnv {
  readonly VITE_CHAT_ENABLED?: string;
  readonly VITE_CHAT_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
