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
  auth mode (`local` or `password`) and snapshot version. OpenAI mode also
  reports the selected model, reasoning effort, text verbosity and the number
  of minimum reservations that fit the configured daily budgets. It is public
  in password mode and does not report secret readiness.
- `POST /api/chat/login` / `POST /api/chat/logout`: see password mode below.
- `POST /api/chat/conversations` returns the pinned data, semantic and model
  settings. OpenAI turns also record model, effort and verbosity in SQLite and
  in the conversation response.
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

Local mode trusts only loopback peers, loopback `Host` and loopback origins,
and rejects any request carrying `Forwarded`, `X-Forwarded-*` or `X-Real-IP`:
behind a reverse proxy every client would look like loopback. It cannot be
combined with `CHAT_PROVIDER=openai` unless `CHAT_ALLOW_LOCAL_OPENAI=true` is
set on the owner's own machine.

A deployed backend uses `CHAT_AUTH_MODE=password`:

- `CHAT_PASSWORDS_JSON` is a list of `{"user_id", "password_hash"}` entries.
  Hashes come from `python -m src.conversational_analytics hash-password`
  (scrypt, salted; `--generate` creates a random password and prints it once
  with its hash). Passwords and hashes never go to Git.
- `POST /api/chat/login` with `{"password"}` returns `{session, expires_at}`.
  Only the SHA-256 of the session is stored; it expires after
  `CHAT_SESSION_TTL_HOURS` (12) and dies when that user's hash is rotated.
  `POST /api/chat/logout` revokes it. Every other route except
  `GET /api/chat/health` requires `Authorization: Bearer <session>`.
- Failed logins are throttled at 5 per client per 15 minutes with `429` and
  `Retry-After`. Fifty failures globally within an hour trigger an operator
  alert; they do not block logins. The client address comes from
  `X-Forwarded-For` only when the peer is in `CHAT_TRUSTED_PROXY` (IPs, or
  CIDR networks inside loopback/private/shared-address ranges); the header is
  read from the right, skipping trusted hops. The Railway launcher defaults it
  to the edge network `100.64.0.0/10`.
- `CHAT_ALLOWED_ORIGINS` (HTTPS, no paths) is mandatory. No cookies are used:
  Pages and the API are cross-site, so the session travels in the header and
  the browser keeps it only in memory.

POST bodies are limited by actual received bytes, including requests without
`Content-Length` and chunked uploads. Invalid or mismatched declared lengths are
rejected; reading has a bounded deadline, and the login body is limited to 1 KB.
Configure daily token/cost budgets,
message/tool limits, queue bound (`CHAT_MAX_CONCURRENT_GLOBAL` counts pending
plus running turns; a single worker thread runs them in order), admission, and
retention with the corresponding `CHAT_*` environment variables.

Conversations are pinned to data and semantic versions. If either changes,
existing conversations remain readable but new turns fail with a clear version
conflict. OpenAI conversations also pin model, effort and verbosity; existing
conversations without these settings, or after a setting changes, remain
readable but require a new conversation before another question. A provider
call interrupted by process restart is marked failed, its session is
canceled/deleted, and that ambiguous turn is never replayed.
