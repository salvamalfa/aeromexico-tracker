# Airline Tracker chat API

The local API is an optional service over the verified `site/` publication. Run
it from the repository root with `python -m src.conversational_analytics`; it
binds only to loopback. State defaults to
`~/.local/state/airline-tracker/chat.sqlite3` and can be moved with
`CHAT_STATE_PATH`. The API never opens the private warehouse.

The default `mock` provider calls the same deterministic, read-only tool
registry used by the agent adapter and presents the tool's values directly. It
does not generate or estimate a missing answer. `openai` requires explicit
`CHAT_PROVIDER=openai`, `CHAT_OPENAI_ENABLED=true`, and `CHAT_MODEL`; credentials
stay in the server environment. The default has no paid provider calls.

## HTTP contract

- `GET /api/chat/health` reports service, worker, provider name, admission flag,
  and snapshot version. It does not report secret readiness.
- `POST /api/chat/conversations` returns `{id,snapshot_version,semantic_version,created_at}`.
- `GET /api/chat/conversations/{id}` returns the pinned versions, visible
  messages, and turn states. Ownership is checked on every request.
- `DELETE /api/chat/conversations/{id}` cancels active work, requests provider
  session deletion, then removes local messages and events.
- `POST /api/chat/conversations/{id}/messages` accepts
  `{content,client_message_id,context}` and returns `{turn_id,status,deduplicated}`.
  Reusing the same client ID returns the original turn. A conversation accepts
  one active turn. Context keys and values must match
  `semantic.context.validate_context`.
- `GET /api/chat/turns/{id}/events?after=N` streams durable SSE with `id` equal
  to a per-turn sequence number; `Last-Event-ID` can resume a dropped stream.
- `POST /api/chat/turns/{id}/cancel` requests cancellation and returns the state.

Events include `turn.queued`, `turn.started`, `message.delta`,
`message.completed` (`content`, `references`, `chart`), `tool.started`,
`tool.completed`, and one of `turn.completed`, `turn.failed`, or
`turn.cancelled`. Provider IDs never enter the public event stream.

Local mode trusts only loopback peers and loopback origins; run behind a local
same-origin proxy for the dashboard. A deployed backend uses
`CHAT_AUTH_MODE=bearer`, `CHAT_USERS_JSON` entries with `user_id` and the
SHA-256 hash of each bearer token, and explicit comma-separated
`CHAT_ALLOWED_ORIGINS`. It does not use cookies. Configure daily token/cost
budgets, message/tool limits, global concurrency, admission, and retention with
the corresponding `CHAT_*` environment variables.

Conversations are pinned to data and semantic versions. If either changes,
existing conversations remain readable but new turns fail with a clear version
conflict. A provider call interrupted by process restart is marked failed, its
session is canceled/deleted, and that ambiguous turn is never replayed.
