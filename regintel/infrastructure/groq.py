"""Server-side Groq adapter for schema-constrained public-source analysis."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from ..config import GROQ_API_KEY, GROQ_MODEL, GROQ_REASONING_EFFORT, GROQ_TIMEOUT, MAX_RESPONSE_BYTES, USER_AGENT

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


class ModelServiceError(RuntimeError):
    """A safe, user-visible model service failure."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def call_groq_structured_json(*, instructions: str, input_text: str, schema: dict[str, Any],
                              max_output_tokens: int | None = None, request_timeout: float | None = None) -> dict[str, Any]:
    if not GROQ_API_KEY:
        raise RuntimeError("尚未設定 GROQ_API_KEY，請設定伺服器環境變數後再試。")
    body = {
        "model": GROQ_MODEL,
        "messages": [{"role": "system", "content": instructions}, {"role": "user", "content": input_text}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "regintel_response", "strict": True, "schema": schema}},
        "temperature": 0,
        "reasoning_effort": GROQ_REASONING_EFFORT,
        "max_completion_tokens": max_output_tokens if max_output_tokens is not None else 8192,
        "stream": False,
    }
    request = urllib.request.Request(
        GROQ_CHAT_URL, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json", "Accept": "application/json", "User-Agent": USER_AGENT},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=request_timeout if request_timeout is not None else GROQ_TIMEOUT) as response:
            payload = json.loads(response.read(MAX_RESPONSE_BYTES).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Never forward provider response bodies: they can contain request data.
        message = {401: "Groq API key 無效或已撤銷。", 403: "Groq 帳號無權使用此模型。", 429: "Groq 使用量已達限制，請稍後再試。"}.get(exc.code, f"Groq 暫時無法完成請求（HTTP {exc.code}）。")
        raise ModelServiceError(message, 429 if exc.code == 429 else 502) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError("無法連線 Groq，請稍後再試。") from None
    except (ValueError, UnicodeDecodeError):
        raise RuntimeError("Groq 回應格式不正確，請稍後再試。") from None
    try:
        choice = payload["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise ValueError("Incomplete generation")
        result = json.loads(choice["message"]["content"])
        if not isinstance(result, dict):
            raise ValueError("Expected object")
    except (KeyError, IndexError, TypeError, ValueError):
        raise RuntimeError("Groq 未回傳完整的 JSON 分析內容，請稍後再試。") from None
    usage = payload.get("usage", {})
    result["_model_timing"] = {
        "request_seconds": round(time.perf_counter() - started, 3),
        "input_tokens": usage.get("prompt_tokens", 0), "output_tokens": usage.get("completion_tokens", 0),
    }
    for source, target in (("prompt_time", "input_seconds"), ("completion_time", "generation_seconds")):
        if isinstance(usage.get(source), (int, float)):
            result["_model_timing"][target] = round(usage[source], 3)
    return result
