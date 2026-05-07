# oratorIA-backend

Backend de **OratorIA**, plataforma SaaS que usa IA para entrenar habilidades de oratoria. Provee un agente conversacional en tiempo real (sesiones live) y análisis asíncrono de video, con feedback estructurado en tres dimensiones: verbal, paraverbal y estratégica.

Segmentos: **Educativo**, **Empresarial** y **RRHH**.

## Stack

| Capa            | Tecnología                                            |
| --------------- | ----------------------------------------------------- |
| Lenguaje        | Python 3.12                                           |
| Framework       | FastAPI 0.115+                                        |
| Server ASGI     | Uvicorn (dev) / Gunicorn (prod)                       |
| ORM             | SQLAlchemy 2.0 async + asyncpg                        |
| Migraciones     | Alembic                                               |
| Validación      | Pydantic v2                                           |
| Auth            | fastapi-users + JWT                                   |
| Tasks async     | Celery + Redis                                        |
| WebSockets      | FastAPI nativo                                        |
| Package mgr     | uv (Astral)                                           |
| Lint / types    | Ruff + mypy                                           |
| Tests           | pytest + pytest-asyncio                               |
| Container       | Docker + docker-compose                               |
| IA core         | LangChain + LangGraph                                 |
| LLM             | Claude Sonnet 4.5 (primario) + GPT-4o (fallback)      |
| STT             | OpenAI Whisper                                        |
| TTS             | ElevenLabs Multilingual v2                            |
| Paraverbal      | pyannote.audio + librosa                              |
| DB              | PostgreSQL + pgvector                                 |
| Storage         | Cloudflare R2 (boto3)                                 |
| Pagos           | Stripe + Culqi                                        |
| Observabilidad  | Sentry + Langfuse                                     |

## Requisitos previos

Antes de arrancar, asegúrate de tener instalado:

| Tool             | Versión mínima | Cómo instalar (Windows)                       |
| ---------------- | -------------- | --------------------------------------------- |
| **Python 3.12**  | 3.12.x         | `winget install Python.Python.3.12`           |
| **uv** (Astral)  | 0.9+           | https://docs.astral.sh/uv/getting-started/installation/ |
| **Docker Desktop** | 25+          | https://www.docker.com/products/docker-desktop |
| **OpenSSL**      | cualquiera     | viene con Git for Windows (Git Bash) o `winget install ShiningLight.OpenSSL.Light` |
| **Bun**          | 1.3+           | sólo si vas a correr el frontend; ver `oratorIA-frontend/README.md` |

> Tip: el backend pin en `.python-version` es `3.12`. Si `uv` no encuentra una distribución 3.12 local, intentará bajarla de GitHub (`python-build-standalone`). Si tu red bloquea `github.com`, instala Python con `winget` antes de correr `uv sync`.

## Setup local

Primera vez en una máquina nueva — pegar los bloques en orden:

```bash
# 1. Clonar y entrar
git clone https://github.com/nullVoice/oratorIA-backend.git
cd oratorIA-backend

# 2. Variables de entorno
cp .env.example .env

# Generar secretos reales (en Git Bash o WSL)
echo "SECRET_KEY=$(openssl rand -hex 32)" >> .env.tmp
echo "JWT_SECRET=$(openssl rand -hex 32)" >> .env.tmp
# Mezclar manualmente .env.tmp en .env (sobrescribir SECRET_KEY y JWT_SECRET)
# y borrar .env.tmp.

# 3. Pin de Python e instalar deps
uv python pin 3.12
# La línea siguiente excluye torch/torchaudio/pyannote.audio porque pesan
# varios GB; se instalan más adelante (Épica 6 — análisis paraverbal real).
uv sync \
    --no-install-package torch \
    --no-install-package torchaudio \
    --no-install-package pyannote.audio

# 4. Servicios de infraestructura (postgres + redis)
docker compose up -d postgres redis

# 5. Habilitar pgvector en Postgres (sólo la primera vez)
docker compose exec -T postgres psql -U oratoria -d oratoria \
    -c "CREATE EXTENSION IF NOT EXISTS vector"

# 6. Migraciones (cuando existan — ver Épica 2 del TODO.md)
# uv run alembic upgrade head

# 7. Servidor de desarrollo
# Mientras torch no esté instalado, usar --no-sync para que `uv run`
# no intente bajarlo automáticamente.
uv run --no-sync uvicorn src.oratoria.main:app --reload --host 0.0.0.0 --port 8000
```

API disponible en `http://localhost:8000`. Docs en `/docs` (Swagger) y `/redoc`.

### Verificación rápida

```bash
curl http://localhost:8000/        # {"name":"OratorIA API","version":"0.1.0"}
curl http://localhost:8000/health  # {"status":"ok"}
```

## Comandos útiles

```bash
# Desarrollo
uv run --no-sync uvicorn src.oratoria.main:app --reload          # API
uv run --no-sync celery -A src.oratoria.workers.celery_app worker --loglevel=info
uv run --no-sync celery -A src.oratoria.workers.celery_app beat --loglevel=info

# Migraciones
uv run alembic revision --autogenerate -m "mensaje"
uv run alembic upgrade head
uv run alembic downgrade -1

# Tests
uv run --no-sync pytest
uv run --no-sync pytest --cov=src/oratoria

# Lint / types
uv run --no-sync ruff check .
uv run --no-sync ruff format .
uv run --no-sync mypy src

# Stack completo en Docker
docker compose up --build
```

> Una vez instaladas las deps pesadas en Épica 6, el flag `--no-sync` deja de ser necesario.

## Estructura

```
src/oratoria/
├── main.py            # entrypoint FastAPI
├── config.py          # Settings (pydantic-settings)
├── database.py        # async engine + session factory
├── api/               # routers HTTP + WebSocket
│   ├── v1/            # endpoints v1 (auth, users, sessions, reports, ...)
│   └── ws/            # endpoints WebSocket (live sessions)
├── domain/            # capa de servicio + repositorio por bounded context
├── ai/                # capa de IA: agentes, chains, prompts, parsers, memory
├── services/          # adaptadores externos: STT, TTS, paraverbal, storage, payments, email
├── models/            # SQLAlchemy ORM
├── schemas/           # Pydantic DTOs (request/response)
├── workers/           # Celery app + tasks
├── core/              # security, exceptions, middleware, logger, events
└── utils/             # helpers genéricos
```

## Variables de entorno

Ver [`.env.example`](./.env.example) para la lista completa con descripciones. Las variables marcadas con `# TODO: agregar` se configuran en la épica que las consume (ver `TODO.md` en la carpeta padre del repo).

## Frontend

El frontend vive en [`oratorIA-frontend`](../oratorIA-frontend/) (otro repo, mismo workspace). Stack: TanStack Start + Bun + TypeScript. Setup en su propio README.

## Licencia

Propietaria — © OratorIA.
