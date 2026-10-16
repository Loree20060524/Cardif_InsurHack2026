"""Environment and filesystem configuration."""

from __future__ import annotations

import os
import shutil
import ssl
import tempfile
from pathlib import Path


# =========================================================


# =========================================================
# 基本設定
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent
APP_VERSION = "10.22"

# Local secrets stay outside source control. Vercel injects its own variables.
if not os.environ.get("VERCEL"):
    local_env = BASE_DIR / ".env.local"
    if local_env.is_file():
        for line in local_env.read_text(encoding="utf-8-sig").splitlines():
            name, separator, value = line.strip().partition("=")
            if separator and name in {"AI_PROVIDER", "GROQ_API_KEY", "GROQ_MODEL", "GROQ_TIMEOUT", "GROQ_REASONING_EFFORT"}:
                os.environ.setdefault(name, value.strip().strip("\"'"))

IS_VERCEL = os.environ.get("VERCEL") == "1"
DATA_DIR = Path(tempfile.gettempdir()) / "regintel" if IS_VERCEL else BASE_DIR
if IS_VERCEL:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("regintel_cache_v10.json", "regintel_source_store_v10.json", "regintel_event_history_v10.json", "regintel_law_versions_v1.json"):
        seed = BASE_DIR / "deployment_data" / name
        if seed.is_file() and not (DATA_DIR / name).exists():
            shutil.copyfile(seed, DATA_DIR / name)

CACHE_FILE = (
    DATA_DIR
    /
    "regintel_cache_v10.json"
)

SOURCE_STORE_FILE = (
    DATA_DIR
    /
    "regintel_source_store_v10.json"
)

AI_CACHE_FILE = (
    DATA_DIR
    /
    "regintel_ai_cache_v10.json"
)


PORT = int(
    os.environ.get(
        "PORT",
        "8082"
    )
)


REQUEST_TIMEOUT = int(
    os.environ.get(
        "REQUEST_TIMEOUT",
        "15"
    )
)


MAX_RESPONSE_BYTES = int(
    os.environ.get(
        "MAX_RESPONSE_BYTES",
        str(
            10
            *
            1024
            *
            1024
        )
    )
)


CACHE_TTL_SECONDS = int(
    os.environ.get(
        "CACHE_TTL_SECONDS",
        "120"
    )
)


MANUAL_REFRESH_COOLDOWN_SECONDS = int(
    os.environ.get(
        "MANUAL_REFRESH_COOLDOWN_SECONDS",
        "180"
    )
)


HOST_MIN_GAP_SECONDS = float(
    os.environ.get(
        "HOST_MIN_GAP_SECONDS",
        "1.2"
    )
)


LAW_SIGNAL_RETENTION_DAYS = int(
    os.environ.get(
        "LAW_SIGNAL_RETENTION_DAYS",
        "45"
    )
)


USER_AGENT = os.environ.get(
    "REGINTEL_USER_AGENT",
    (
        "RegIntel-Hackathon/1.0 "
        "(academic prototype)"
    )
)


# =========================================================
# Ollama
# =========================================================

OLLAMA_MODEL = os.environ.get(
    "OLLAMA_MODEL",
    "qwen3:4b"
).strip()


OLLAMA_API_URL = os.environ.get(
    "OLLAMA_API_URL",
    (
        "http://127.0.0.1:"
        "11434/api/chat"
    )
).strip()


OLLAMA_TIMEOUT = int(
    os.environ.get(
        "OLLAMA_TIMEOUT",
        "180"
    )
)


_thinking_setting = os.environ.get("OLLAMA_THINK", "false").strip().lower()
if _thinking_setting not in {"false", "true", "auto"}:
    raise ValueError("OLLAMA_THINK 必須是 false、true 或 auto。")
OLLAMA_THINK = {"false": False, "true": True, "auto": None}[_thinking_setting]
OLLAMA_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "10m").strip()


AI_MAX_INPUT_CHARS = int(
    os.environ.get(
        "AI_MAX_INPUT_CHARS",
        "14000"
    )
)


AI_PROMPT_VERSION = (
    "regintel-v10.15-official-announcement-content"
)

EVENT_HISTORY_FILE = DATA_DIR / "regintel_event_history_v10.json"
LAW_VERSIONS_FILE = DATA_DIR / "regintel_law_versions_v1.json"


AI_PROVIDER = os.environ.get("AI_PROVIDER", "groq" if os.environ.get("GROQ_API_KEY") else "ollama").strip().lower()
if AI_PROVIDER not in {"ollama", "groq"}:
    raise ValueError("AI_PROVIDER 必須是 ollama 或 groq。")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b").strip()
GROQ_TIMEOUT = int(os.environ.get("GROQ_TIMEOUT", "90"))
GROQ_REASONING_EFFORT = os.environ.get("GROQ_REASONING_EFFORT", "low").strip().lower()
if GROQ_REASONING_EFFORT not in {"low", "medium", "high"}:
    raise ValueError("GROQ_REASONING_EFFORT 必須是 low、medium 或 high。")
AI_MODEL = GROQ_MODEL if AI_PROVIDER == "groq" else OLLAMA_MODEL
AI_PROVIDER_LABEL = "Groq（雲端）" if AI_PROVIDER == "groq" else "Ollama（本機）"


AI_ENABLED = True


# =========================================================
# SSL
# =========================================================

def create_ssl_context() -> ssl.SSLContext:

    context = (
        ssl.create_default_context()
    )

    if hasattr(
        ssl,
        "VERIFY_X509_STRICT"
    ):

        context.verify_flags &= (
            ~ssl.VERIFY_X509_STRICT
        )

    return context


SSL_CONTEXT = (
    create_ssl_context()
)
