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

- Python **3.12** (recomendado vía [`uv`](https://docs.astral.sh/uv/))
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) >= 0.5
- Docker + Docker Compose
- (opcional) `ffmpeg` y `libsndfile` si vas a correr análisis paraverbal localmente fuera de Docker

## Setup local

```bash
# 1. Clonar y entrar
git clone https://github.com/nullVoice/oratorIA-backend.git
cd oratorIA-backend

# 2. Variables de entorno
cp .env.example .env
# editar .env con tus claves

# 3. Instalar dependencias y crear venv
uv sync

# 4. Servicios de infraestructura
docker compose up -d postgres redis

# 5. Migraciones
uv run alembic upgrade head

# 6. Servidor de desarrollo
uv run uvicorn src.oratoria.main:app --reload
```

API disponible en `http://localhost:8000`. Docs en `/docs` (Swagger) y `/redoc`.

## Comandos útiles

```bash
# Desarrollo
uv run uvicorn src.oratoria.main:app --reload          # API
uv run celery -A src.oratoria.workers.celery_app worker --loglevel=info
uv run celery -A src.oratoria.workers.celery_app beat --loglevel=info

# Migraciones
uv run alembic revision --autogenerate -m "mensaje"
uv run alembic upgrade head
uv run alembic downgrade -1

# Tests
uv run pytest
uv run pytest --cov=src/oratoria

# Lint / types
uv run ruff check .
uv run ruff format .
uv run mypy src

# Stack completo en Docker
docker compose up --build
```

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

Ver [`.env.example`](./.env.example) para la lista completa con descripciones.

## Frontend

El frontend vive en otro repo y está construido con TanStack Start + Bun + TypeScript.

## Licencia

Propietaria — © OratorIA.
