# Deploy checklist — OratorIA backend

Auth (register / login / logout) works out of the box and email verification is
**not** required, so any user can sign up and use the app immediately. Before
exposing it publicly, set these production values — most live in env vars
(see `.env.example` for the full list).

## Critical (security — do not skip)

- [ ] **`SECRET_KEY`** — generate a strong one: `openssl rand -hex 32`.
      The default `change-me` is insecure.
- [ ] **`JWT_SECRET`** — generate a separate one: `openssl rand -hex 32`.
      The default `change-me-too` is insecure; with it, JWTs are forgeable.
- [ ] **`CORS_ORIGINS`** — add the deployed frontend origin(s), comma-separated,
      e.g. `https://app.oratoria.app`. Without it the browser blocks all API
      calls from the deployed frontend. (Local already has the localhost ports.)
- [ ] **`DATABASE_URL`** — point at the production Postgres (with pgvector).
- [ ] Run migrations on the prod DB: `uv run alembic upgrade head`.

## Required for full features

- [ ] **`REDIS_URL`** / Celery URLs — production Redis.
- [ ] **`OPENAI_API_KEY`** (evaluator/persona fallback) and/or
      **`ANTHROPIC_API_KEY`** (primary LLM — `claude-sonnet-4-5`).
- [ ] **`DEEPGRAM_API_KEY`** — live transcription (Audiencia Digital overlay).
- [ ] **Tavus** (`TAVUS_API_KEY`, `TAVUS_PERSONA_ID`, `TAVUS_REPLICA_ID`) +
      **`TAVUS_CALLBACK_BASE_URL`** = the public backend URL, so Tavus can reach
      `/api/v1/webhooks/tavus` and deliver the session transcript. Also set
      `TAVUS_WEBHOOK_SECRET` and register the URL in the Tavus dashboard.

## Frontend (separate repo)

- [ ] Build with **`VITE_API_URL`** set to the deployed backend URL (defaults to
      `http://localhost:8000` in dev).

## Optional

- [ ] Email verification + `RESEND_API_KEY` if you want verified emails
      (currently off — fine for an MVP).
- [ ] `SENTRY_DSN`, `LANGFUSE_*` for observability.

## Password policy (enforced server-side)

Registration rejects passwords shorter than 8 chars, longer than 128, or that
contain the email's local part (`UserManager.validate_password`).
