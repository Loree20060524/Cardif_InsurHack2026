"""Environment and filesystem configuration."""

from __future__ import annotations

import os
import ssl
from pathlib import Path


# =========================================================


# =========================================================
# 基本設定
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent
APP_VERSION = "10.20"

CACHE_FILE = (
    BASE_DIR
    /
    "regintel_cache_v10.json"
)

SOURCE_STORE_FILE = (
    BASE_DIR
    /
    "regintel_source_store_v10.json"
)

AI_CACHE_FILE = (
    BASE_DIR
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

EVENT_HISTORY_FILE = BASE_DIR / "regintel_event_history_v10.json"
LAW_VERSIONS_FILE = BASE_DIR / "regintel_law_versions_v1.json"


AI_PROVIDER_LABEL = (
    "Ollama（本機）"
)


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
