# Deploy gratis — Neon · Upstash · Render · Vercel

Auth (registro/login/logout) funciona sin verificación de email, así que
cualquiera puede crear su cuenta y usar la app. El hosting es gratis; las APIs
de IA (Tavus / OpenAI·Anthropic / Deepgram) **se pagan por uso** aparte.

Notas del proyecto que hacen esto posible en free tier:

- **Sin Celery**: ningún endpoint usa tareas async (`.delay()`), el evaluador
  corre sincrónico. Solo se deploya el web service.
- **Sin torch**: el stack acústico pesado (`torch`/`pyannote`) está en el extra
  opcional `acoustic` y NO se instala en la imagen → cabe en Render free. El
  analizador paraverbal degrada de forma elegante sin él.

## 1) Neon — Postgres + pgvector (gratis)

1. Creá un proyecto en https://neon.tech (la extensión `pgvector` viene lista).
2. Copiá la connection string y **adaptala al driver async + SSL**:
   ```
   postgresql+asyncpg://USER:PASSWORD@HOST/DBNAME?ssl=require
   ```
   (Neon te da `postgresql://...` → cambiá el esquema a `postgresql+asyncpg://`
   y dejá `?ssl=require`.) Eso es tu `DATABASE_URL`.

## 2) Upstash — Redis (gratis)

1. Creá una base Redis en https://upstash.com.
2. Copiá la URL `rediss://...` → es tu `REDIS_URL`.

## 3) Render — backend (gratis, Docker)

1. Render → **New → Blueprint** y elegí el repo `oratorIA-backend` (usa el
   `render.yaml` incluido). Render buildea el `Dockerfile`.
2. Completá las env vars marcadas `sync: false`:
   - `DATABASE_URL` (Neon, paso 1) · `REDIS_URL` (Upstash, paso 2)
   - `CORS_ORIGINS` = tu URL de Vercel (la completás tras el paso 4; podés
     poner un placeholder y editarla después)
   - `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `DEEPGRAM_API_KEY`
   - `TAVUS_API_KEY` / `TAVUS_PERSONA_ID` / `TAVUS_REPLICA_ID`
   - `TAVUS_CALLBACK_BASE_URL` = la URL pública de este servicio Render
     (ej. `https://oratoria-backend.onrender.com`) para que Tavus alcance
     `/api/v1/webhooks/tavus`
   - `SECRET_KEY` y `JWT_SECRET` los **genera Render solo** (no toques).
3. El contenedor corre `alembic upgrade head` al arrancar (migraciones
   automáticas) y escucha en `$PORT`. Verificá `…onrender.com/health` → 200.

> Free tier "duerme" tras ~15 min sin tráfico (primer request lento ~30-50s).

## 4) Vercel — frontend (gratis, SSR)

TanStack Start detecta Vercel automáticamente. En Vercel → New Project →
repo `oratorIA-frontend`:

- **Root Directory**: `apps/web`
- **Framework**: Vite (lo detecta) · Install: `bun install` (detecta `bun.lock`)
- **Build Command**: `vite build` (default)
- **Env var**: `VITE_API_URL` = la URL de Render del paso 3
  (ej. `https://oratoria-backend.onrender.com`)

Luego volvé a Render y poné `CORS_ORIGINS` = la URL final de Vercel
(ej. `https://oratoria.vercel.app`) y redeployá.

## Checklist de variables (resumen)

| Variable                            | Dónde  | Valor                                       |
| ----------------------------------- | ------ | ------------------------------------------- |
| `DATABASE_URL`                      | Render | Neon (`postgresql+asyncpg://…?ssl=require`) |
| `REDIS_URL`                         | Render | Upstash (`rediss://…`)                      |
| `SECRET_KEY`, `JWT_SECRET`          | Render | autogenerados                               |
| `CORS_ORIGINS`                      | Render | URL de Vercel                               |
| `TAVUS_CALLBACK_BASE_URL`           | Render | URL de Render                               |
| `OPENAI/ANTHROPIC/DEEPGRAM/TAVUS_*` | Render | tus keys                                    |
| `VITE_API_URL`                      | Vercel | URL de Render                               |

## Local (sin deploy)

`uv sync` instala sin el stack acústico. Para features paraverbales finas:
`uv sync --extra acoustic`. Arranque local: ver README.
