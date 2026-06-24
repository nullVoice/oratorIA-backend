"""
SPK-01 — Validación de retención de muletillas en español (Deepgram).

Go/no-go del riesgo #1 del plan Audiencia Digital v2.

Qué hace:
  1. Si NO se pasa un archivo de audio: genera uno en español con muletillas
     usando ElevenLabs (valida de paso la key de TTS).
  2. Manda ese audio a Deepgram (nova-2, es, filler_words=true).
  3. Cuenta cuántas muletillas objetivo retuvo el transcript y reporta.

Criterio de aceptación:
  - Léxicas ("este", "o sea", "tipo", "como que", "digamos", "a ver", "bueno",
    "pues", "vale"): deberían retenerse ~100% (son palabras reales).
  - Vocalizaciones ("eh", "em", "mmm", "ah"): si retención < 60% → plan B
    (detección propia + aceptar solo léxicas).

Uso:
  uv run --no-sync --with httpx --with python-dotenv \
      python scripts/spk01_deepgram_fillers.py [ruta_audio.mp3|.webm|.wav]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
import os

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DEEPGRAM_KEY = os.environ.get("DEEPGRAM_API_KEY", "").strip()
ELEVENLABS_KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()

# Texto con muletillas deliberadas (léxicas + vocalizaciones).
SAMPLE_TEXT = (
    "Eh... bueno, este, hoy les voy a presentar, o sea, mi proyecto. "
    "Eh, digamos que la idea es, este, mejorar la oratoria. Mmm, tipo, "
    "con inteligencia artificial. A ver, como que el objetivo es, eh, "
    "ayudar a la gente a hablar mejor. O sea, em, eso es todo, bueno, gracias."
)

# Muletillas objetivo y cuántas veces aparecen en el texto fuente.
EXPECTED = {
    # léxicas
    "bueno": 2, "este": 3, "o sea": 3, "digamos": 1, "tipo": 1,
    "a ver": 1, "como que": 1, "pues": 0, "vale": 0,
    # vocalizaciones
    "eh": 4, "em": 1, "mmm": 1, "ah": 0,
}
LEXICAL = {"bueno", "este", "o sea", "digamos", "tipo", "a ver", "como que", "pues", "vale"}
VOCALIZED = {"eh", "ehh", "em", "mmm", "ah"}

SAMPLE_PATH = ROOT / "scripts" / "spk01_sample.mp3"


def list_account_voices() -> list[dict]:
    r = httpx.get(
        "https://api.elevenlabs.io/v1/voices",
        headers={"xi-api-key": ELEVENLABS_KEY},
        timeout=30,
    )
    if r.status_code != 200:
        sys.exit(f"ElevenLabs /voices error {r.status_code}: {r.text[:300]}")
    return r.json().get("voices", [])


def generate_sample() -> bytes:
    if not ELEVENLABS_KEY:
        sys.exit("Falta ELEVENLABS_API_KEY en el .env del backend.")
    voices = list_account_voices()
    print(f"→ Voces en tu cuenta: {len(voices)}")
    for v in voices:
        print(f"   - {v.get('name'):<22} {v.get('voice_id')}  [{v.get('category')}]")
    # Probar las propias/cloned primero; las 'premade'/library suelen estar
    # bloqueadas en free tier vía API.
    ordered = sorted(voices, key=lambda v: 0 if v.get("category") != "premade" else 1)
    print("→ Generando audio de prueba (eleven_multilingual_v2)…")
    last = None
    for v in ordered:
        vid, name, cat = v["voice_id"], v.get("name"), v.get("category")
        r = httpx.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{vid}",
            headers={"xi-api-key": ELEVENLABS_KEY, "Content-Type": "application/json"},
            params={"output_format": "mp3_44100_128"},
            json={"text": SAMPLE_TEXT, "model_id": "eleven_multilingual_v2"},
            timeout=60,
        )
        if r.status_code == 200:
            print(f"   ✓ voz usable: {name} ({vid}, {cat}) — {len(r.content)} bytes")
            SAMPLE_PATH.write_bytes(r.content)
            return r.content
        last = f"{name} [{cat}] → {r.status_code}: {r.text[:120]}"
        print(f"   ✗ {last}")
    sys.exit(f"Ninguna voz usable en free tier. Última: {last}")


def transcribe(audio: bytes, content_type: str) -> str:
    if not DEEPGRAM_KEY:
        sys.exit("Falta DEEPGRAM_API_KEY en el .env del backend.")
    model = os.environ.get("DG_MODEL", "nova-2")
    lang = os.environ.get("DG_LANG", "es")
    print(f"→ Enviando a Deepgram ({model}, {lang}, filler_words=true)…")
    r = httpx.post(
        "https://api.deepgram.com/v1/listen",
        params={
            "model": model,
            "language": lang,
            "filler_words": "true",
            "punctuate": "true",
            "smart_format": "true",
        },
        headers={"Authorization": f"Token {DEEPGRAM_KEY}", "Content-Type": content_type},
        content=audio,
        timeout=120,
    )
    if r.status_code != 200:
        sys.exit(f"Deepgram error {r.status_code}: {r.text[:300]}")
    data = r.json()
    return data["results"]["channels"][0]["alternatives"][0]["transcript"]


def count(transcript: str, phrase: str) -> int:
    esc = re.escape(phrase)
    return len(re.findall(rf"\b{esc}\b", transcript.lower()))


# Lista completa de muletillas que detecta el producto (fillers.ts).
ALL_FILLERS = [
    "este", "eh", "ehh", "em", "mmm", "ah", "pues", "o sea", "como que",
    "tipo", "bueno", "vale", "okey", "okay", "y entonces", "digamos",
    "verdad", "a ver",
]
VOCALIZED_SET = {"eh", "ehh", "em", "mmm", "ah"}


def main() -> None:
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        audio = path.read_bytes()
        ext = path.suffix.lstrip(".").lower()
        ct = {"mp3": "audio/mpeg", "webm": "audio/webm", "wav": "audio/wav",
              "ogg": "audio/ogg", "m4a": "audio/mp4"}.get(ext, "audio/mpeg")
        print(f"→ Usando audio real: {path} ({len(audio)} bytes)")
        real = True
    else:
        audio = generate_sample()
        ct = "audio/mpeg"
        real = False

    transcript = transcribe(audio, ct)
    print("\n===== TRANSCRIPT =====")
    print(transcript)
    print("======================\n")

    if real:
        # Audio humano: no hay ground-truth automático → reportar qué retuvo
        # Deepgram para cada muletilla; el juicio lo hacemos contra lo dicho.
        print(f"{'muletilla':<12}{'tipo':<14}{'encontrado':>10}")
        print("-" * 36)
        lex_hits = voc_hits = 0
        for f in ALL_FILLERS:
            got = count(transcript, f)
            kind = "vocalizada" if f in VOCALIZED_SET else "léxica"
            mark = "" if got == 0 else f"  ({got})"
            print(f"{f:<12}{kind:<14}{got:>10}")
            if f in VOCALIZED_SET:
                voc_hits += got
            else:
                lex_hits += got
        print("\n===== RESULTADO SPK-01 (audio real) =====")
        print(f"Total muletillas léxicas retenidas:        {lex_hits}")
        print(f"Total vocalizaciones (eh/em/mmm) retenidas: {voc_hits}")
        print("Veredicto: comparar con lo que dijiste —")
        print("  · si las vocalizaciones que dijiste aparecen ≥60% → PASA")
        print("  · si Deepgram las limpia → PLAN B (solo léxicas, igual válido)")
        print("=========================================")
        return

    lex_total = lex_found = voc_total = voc_found = 0
    print(f"{'muletilla':<12}{'esperado':>9}{'encontrado':>12}")
    print("-" * 33)
    for phrase, exp in EXPECTED.items():
        if exp == 0:
            continue
        got = count(transcript, phrase)
        print(f"{phrase:<12}{exp:>9}{got:>12}")
        if phrase in LEXICAL:
            lex_total += exp
            lex_found += min(got, exp)
        elif phrase in VOCALIZED:
            voc_total += exp
            voc_found += min(got, exp)

    lex_pct = (lex_found / lex_total * 100) if lex_total else 0
    voc_pct = (voc_found / voc_total * 100) if voc_total else 0
    print("\n===== RESULTADO SPK-01 (TTS, optimista) =====")
    print(f"Léxicas:        {lex_found}/{lex_total}  ({lex_pct:.0f}%)")
    print(f"Vocalizaciones: {voc_found}/{voc_total}  ({voc_pct:.0f}%)")
    print("=============================================")


if __name__ == "__main__":
    main()
