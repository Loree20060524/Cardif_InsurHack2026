"""Environment and filesystem configuration."""

from __future__ import annotations

import os
import ssl
import tempfile
from pathlib import Path


# =========================================================


# =========================================================
# 基本設定
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent
APP_VERSION = "10.22"

# Keep deployed data on an attached volume; local runs keep their existing files.
_data_directory = os.environ.get("REGINTEL_DATA_DIR", "").strip()
IS_VERCEL = os.environ.get("VERCEL") == "1"
DATA_DIR = (
    (BASE_DIR / Path(_data_directory).expanduser()).resolve() if _data_directory
    else Path(tempfile.gettempdir()) / "regintel" if IS_VERCEL
    else BASE_DIR
)
HOST = os.environ.get("REGINTEL_HOST", "127.0.0.1").strip() or "127.0.0.1"

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


AI_PROVIDER = os.environ.get(
    "REGINTEL_AI_PROVIDER", "vercel_gateway" if IS_VERCEL else "ollama"
).strip().lower()
if AI_PROVIDER not in {"ollama", "vercel_gateway"}:
    raise ValueError("REGINTEL_AI_PROVIDER 必須是 ollama 或 vercel_gateway。")
AI_MODEL = (
    os.environ.get("REGINTEL_AI_MODEL", "alibaba/qwen-3-14b").strip()
    if AI_PROVIDER == "vercel_gateway" else OLLAMA_MODEL
)
AI_THINK = False if AI_PROVIDER == "vercel_gateway" else OLLAMA_THINK
AI_PROVIDER_LABEL = "Vercel AI Gateway" if AI_PROVIDER == "vercel_gateway" else "Ollama（本機）"
AI_GATEWAY_TIMEOUT = min(240, max(10, int(os.environ.get("AI_GATEWAY_TIMEOUT", "180"))))
AI_GATEWAY_MAX_TOKENS = min(8192, max(512, int(os.environ.get("AI_GATEWAY_MAX_TOKENS", "4096"))))


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
