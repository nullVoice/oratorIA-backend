# oratoria-backend

This file provides context about the project for AI assistants.

## Project Overview

OratorIA es una plataforma digital que usa inteligencia artificial para mejorar las habilidades de hablar en público. Actúa como un coach personal de comunicación con retroalimentación inmediata y precisa, soluciona el alto costo de coaches profesionales, la falta de espacios seguros para practicar y la ausencia de retroalimentación personalizada en herramientas existentes. Funciona en un entorno digital seguro y disponible 24/7. Los usuarios pueden interactuar de dos maneras: en sesiones en vivo con simulación de audiencias o analizando videos de manera individual. Usuarios principales: estudiantes, ejecutivos y personas en búsqueda de empleo. Clientes: escuelas, empresas e individuos.

- **Ecosystem**: Python
- **Repo type**: Backend monolito modular con workers async

## Tech Stack

- **Runtime**: Python 3.12
- **Package manager**: uv (Astral)

### Backend

- Framework: FastAPI 0.115+
- ASGI: Uvicorn (dev) / Gunicorn (prod)
- Validation: Pydantic v2 + pydantic-settings
- WebSockets: FastAPI nativo

### Database

- Database: PostgreSQL + pgvector
- ORM: SQLAlchemy 2.0 async (asyncpg)
- Migrations: Alembic

### Authentication

- Provider: fastapi-users + JWT

### AI / ML

- Orchestration: LangChain + LangGraph
- LLM primario: Claude Sonnet 4.5 (langchain-anthropic)
- LLM fallback: GPT-4o (langchain-openai)
- STT: OpenAI Whisper
- TTS: ElevenLabs Multilingual v2
- Paraverbal: pyannote.audio + librosa
- Tracing: Langfuse

### Infra / Services

- Cache & broker: Redis
- Async tasks: Celery + Redis (+ Flower)
- Storage: Cloudflare R2 (boto3 / aioboto3)
- Payments: Stripe + Culqi
- Email: Resend
- Errors: Sentry

### Quality

- Lint / format: Ruff
- Types: mypy (strict)
- Tests: pytest + pytest-asyncio + pytest-cov

## Project Structure

```
oratoria-backend/
├── pyproject.toml
├── alembic/                # migraciones
├── src/oratoria/
│   ├── main.py             # FastAPI app
│   ├── config.py           # Settings
│   ├── database.py         # async engine + session
│   ├── api/                # HTTP + WS routers
│   ├── domain/             # services + repositories por bounded context
│   ├── ai/                 # agents, chains, prompts, parsers, memory, llm
│   ├── services/           # STT, TTS, paraverbal, storage, payments, email
│   ├── models/             # SQLAlchemy ORM
│   ├── schemas/            # Pydantic DTOs
│   ├── workers/            # Celery
│   ├── core/               # security, exceptions, middleware, logger
│   └── utils/
└── tests/
    ├── unit/
    ├── integration/
    └── e2e/
```

## Common Commands

- `uv sync` — instalar dependencias y crear venv
- `uv run uvicorn src.oratoria.main:app --reload` — dev server
- `uv run alembic upgrade head` — aplicar migraciones
- `uv run alembic revision --autogenerate -m "msg"` — generar migración
- `uv run pytest` — tests
- `uv run ruff check . && uv run ruff format .` — lint + format
- `uv run mypy src` — type check
- `docker compose up postgres redis` — solo dependencias
- `docker compose up --build` — stack completo

## Conventions

- Async-first: todos los handlers FastAPI y operaciones DB son `async def`.
- Capa AI desacoplada en `src/oratoria/ai/`. La capa `domain/` no importa proveedores LLM directamente: orquesta a través de `ai/agents/orchestrator.py`.
- Pydantic v2 para schemas (request/response) y para parseo estructurado de salidas LLM (`PydanticOutputParser` en `ai/parsers/`).
- Repositorio + servicio por bounded context (`domain/<context>/repository.py` + `service.py`).
- Migraciones SIEMPRE generadas con `--autogenerate` y luego revisadas a mano.
- Secretos solo vía `.env` y `Settings`. Nunca hardcoded.

## Maintenance

Mantener este archivo actualizado cuando:

- Se agreguen/quiten dependencias
- Cambie la estructura del proyecto
- Se agreguen nuevas features o servicios
- Cambien comandos o flujos de build/dev

AI assistants should suggest updates to this file when they notice relevant changes.
