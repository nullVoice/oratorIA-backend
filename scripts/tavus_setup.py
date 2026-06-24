"""Tavus setup helper for OratorIA's Audiencia Digital (F1-E-01).

Lists the replicas and personas available to your TAVUS_API_KEY so you can grab
the IDs for .env. With --create-persona it provisions a minimal BYO-LLM persona
(the LLM layer is overridden per-conversation by the backend, so the persona
itself only needs a name + replica + base prompt).

Run from oratorIA-backend/:
    PYTHONUTF8=1 uv run --no-sync --with httpx --with python-dotenv \
        python scripts/tavus_setup.py
    # then, only if you have NO usable persona:
    PYTHONUTF8=1 uv run --no-sync --with httpx --with python-dotenv \
        python scripts/tavus_setup.py --create-persona
"""

from __future__ import annotations

import os
import sys

import httpx
from dotenv import load_dotenv

BASE_URL = "https://tavusapi.com/v2"


def _key() -> str:
    load_dotenv()
    key = os.environ.get("TAVUS_API_KEY", "").strip()
    if not key:
        sys.exit("TAVUS_API_KEY not found in environment/.env — set it first.")
    return key


def _client(key: str) -> httpx.Client:
    return httpx.Client(
        base_url=BASE_URL,
        headers={"x-api-key": key, "Content-Type": "application/json"},
        timeout=30.0,
    )


def list_replicas(client: httpx.Client) -> None:
    print("\n=== REPLICAS (caras del avatar) ===")
    for rtype in ("system", "user"):
        try:
            resp = client.get("/replicas", params={"replica_type": rtype})
            resp.raise_for_status()
            items = resp.json().get("data", [])
        except httpx.HTTPStatusError as exc:
            print(f"  [{rtype}] error {exc.response.status_code}: {exc.response.text[:200]}")
            continue
        print(f"  -- {rtype} ({len(items)}):")
        for r in items[:25]:
            print(
                f"     replica_id={r.get('replica_id')}  "
                f"name={r.get('replica_name')!r}  status={r.get('status')}"
            )


def list_personas(client: httpx.Client) -> None:
    print("\n=== PERSONAS (cerebro / config) ===")
    try:
        resp = client.get("/personas")
        resp.raise_for_status()
        items = resp.json().get("data", [])
    except httpx.HTTPStatusError as exc:
        print(f"  error {exc.response.status_code}: {exc.response.text[:200]}")
        return
    if not items:
        print("  (ninguna) — corré con --create-persona para crear una.")
        return
    for p in items[:25]:
        print(
            f"  persona_id={p.get('persona_id')}  "
            f"name={p.get('persona_name')!r}  pipeline={p.get('pipeline_mode')}"
        )


def create_persona(client: httpx.Client, default_replica_id: str | None) -> None:
    print("\n=== CREANDO PERSONA (BYO-LLM) ===")
    body: dict[str, object] = {
        "persona_name": "OratorIA Audiencia",
        "pipeline_mode": "full",
        "system_prompt": (
            "Eres una audiencia profesional que escucha una presentacion y, "
            "cuando corresponde, formula preguntas breves y agudas. El backend "
            "de OratorIA controla tus respuestas via un LLM propio."
        ),
        "context": "Audiencia digital de practica de oratoria.",
    }
    if default_replica_id:
        body["default_replica_id"] = default_replica_id
    try:
        resp = client.post("/personas", json=body)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        sys.exit(f"  create persona failed {exc.response.status_code}: {exc.response.text[:300]}")
    data = resp.json()
    print(f"  CREADA → persona_id={data.get('persona_id')}")
    print("  Copiá ese persona_id a TAVUS_PERSONA_ID en .env.")


def main() -> None:
    key = _key()
    create = "--create-persona" in sys.argv
    replica_arg = None
    for arg in sys.argv:
        if arg.startswith("--replica="):
            replica_arg = arg.split("=", 1)[1]
    with _client(key) as client:
        list_replicas(client)
        list_personas(client)
        if create:
            create_persona(client, replica_arg)
    print(
        "\nListo. Para .env necesitás: TAVUS_REPLICA_ID (de la lista de replicas) "
        "y TAVUS_PERSONA_ID (de la lista de personas).\n"
    )


if __name__ == "__main__":
    main()
