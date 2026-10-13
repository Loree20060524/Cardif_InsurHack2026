"""Structured model calls with explicit local/cloud selection and safe diagnostics."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from ..config import (
    AI_CACHE_FILE, AI_GATEWAY_MAX_TOKENS, AI_GATEWAY_TIMEOUT, AI_MODEL,
    AI_PROVIDER, AI_PROVIDER_LABEL, USER_AGENT,
)
from ..domain.text import now_iso
from .json_store import atomic_write_json, document_transaction, load_json_file
from .ollama import call_ollama_structured_json
from .postgres_store import StorageError, get_store


GATEWAY_URL = "https://ai-gateway.vercel.sh/v1/chat/completions"
GATEWAY_RESPONSE_LIMIT = 1_048_576
STATUS_MAX_AGE_SECONDS = 86400
_status_lock = threading.Lock()
_last_status: dict[str, Any] = {}


class ModelServiceError(RuntimeError):
    """Only safe, actionable messages may cross the HTTP boundary."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ModelServiceError("redirect", "雲端 AI 連線收到非預期的重新導向，請稍後再試。")


def _credential() -> str:
    # Read per call: deployed OIDC tokens are managed by Vercel, not cached here.
    return (os.environ.get("VERCEL_OIDC_TOKEN", "").strip()
            or os.environ.get("AI_GATEWAY_API_KEY", "").strip())


def _record_status(status: str, code: str = "", message: str = "") -> None:
    record = {"provider": AI_PROVIDER, "model": AI_MODEL, "status": status,
              "checked_at": now_iso(), "checked_epoch": time.time(),
              "code": code, "message": message}
    with _status_lock:
        _last_status.clear()
        _last_status.update(record)
    # Persist the result across cold starts only in the shared database. Local
    # Ollama files and the other four saved documents are never touched here.
    try:
        if get_store() is not None:
            with document_transaction(AI_CACHE_FILE):
                cache = load_json_file(AI_CACHE_FILE)
                cache["gateway_status"] = record
                atomic_write_json(AI_CACHE_FILE, cache)
    except (StorageError, OSError):
        pass  # The feature's normal data save will still report storage failure.


def model_health() -> dict[str, Any]:
    """Report observed calls; a token's presence never proves model readiness."""
    base = {"provider": AI_PROVIDER, "model": AI_MODEL, "ready": False}
    if AI_PROVIDER != "vercel_gateway":
        return {**base, "status": "local", "message": "目前使用本機 Ollama。"}
    if not _credential():
        return {**base, "status": "missing_credentials", "message": "尚未取得 Vercel OIDC 或 AI Gateway 金鑰。"}
    with _status_lock:
        record = dict(_last_status)
    if get_store() is not None:
        saved = load_json_file(AI_CACHE_FILE).get("gateway_status", {})
        if isinstance(saved, dict):
            record = saved
    if (record.get("provider") != AI_PROVIDER or record.get("model") != AI_MODEL
            or not isinstance(record.get("checked_epoch"), (int, float))
            or not 0 <= time.time() - record["checked_epoch"] <= STATUS_MAX_AGE_SECONDS):
        return {**base, "status": "unverified", "message": "雲端 AI 尚待實際生成驗證。"}
    return {**base, "ready": record.get("status") == "verified",
            **{name: record.get(name, "") for name in ("status", "checked_at", "code", "message")}}


def _http_error(status: int, raw: bytes) -> ModelServiceError:
    # Never echo upstream messages, prompts, headers, or action URLs into logs/UI.
    code = ""
    try:
        error = json.loads(raw).get("error", {})
        if isinstance(error, dict):
            code = error.get("code") or error.get("type") or ""
    except (ValueError, AttributeError):
        pass
    if status == 401:
        return ModelServiceError("authentication", "雲端 AI 驗證失敗，請確認 Vercel OIDC 或 AI Gateway 金鑰設定。")
    if status == 403 and code == "customer_verification_required":
        return ModelServiceError("verification_required", "Vercel AI Gateway 尚未完成帳號驗證。請到 Loree 工作區的 AI Gateway 完成免費額度啟用；目前沒有購買額度。")
    if status == 403:
        return ModelServiceError("access_denied", "雲端 AI 尚未取得使用權限，請檢查 Loree 工作區的 AI Gateway 設定。")
    if status == 402:
        return ModelServiceError("quota_exhausted", "雲端 AI 額度不足或已達預算上限，暫停生成；請查看 AI Gateway 額度，系統不會購買額度。")
    if status == 429:
        return ModelServiceError("rate_limited", "雲端 AI 目前請求過多，請稍後再試。")
    if status in {400, 404, 422}:
        return ModelServiceError("model_configuration", "雲端模型或結構化輸出設定無法使用，請檢查 REGINTEL_AI_MODEL。")
    return ModelServiceError("upstream_unavailable", "雲端 AI 服務暫時無法回應，請稍後再試。")


def _call_gateway(*, instructions: str, input_text: str, schema: dict) -> dict:
    credential = _credential()
    if not credential:
        raise ModelServiceError("missing_credentials", "雲端 AI 尚未設定驗證，請在 Vercel 啟用 OIDC 或設定 AI_GATEWAY_API_KEY 後重新部署。")
    body = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": input_text + "\n\n請只輸出符合指定 JSON Schema 的 JSON，不要加入 Markdown 或額外說明。"},
        ],
        "stream": False, "temperature": 0, "max_tokens": AI_GATEWAY_MAX_TOKENS,
        "reasoning": {"effort": "none"},
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "regintel_result", "strict": True, "schema": schema,
        }},
    }
    request = urllib.request.Request(
        GATEWAY_URL, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + credential, "Content-Type": "application/json",
                 "Accept": "application/json", "User-Agent": USER_AGENT}, method="POST",
    )
    opener = urllib.request.build_opener(_NoRedirect())
    started = time.perf_counter()
    try:
        with opener.open(request, timeout=AI_GATEWAY_TIMEOUT) as response:
            raw = response.read(GATEWAY_RESPONSE_LIMIT + 1)
    except urllib.error.HTTPError as exc:
        raise _http_error(exc.code, exc.read(8192)) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ModelServiceError("connection", "雲端 AI 連線逾時或暫時中斷，請稍後再試。") from None
    except ValueError:
        raise ModelServiceError("authentication", "雲端 AI 驗證設定格式不正確，請檢查伺服器環境變數。") from None
    if len(raw) > GATEWAY_RESPONSE_LIMIT:
        raise ModelServiceError("invalid_output", "雲端 AI 回覆超出大小限制，請縮小分析範圍。")
    try:
        payload = json.loads(raw)
        choice = payload["choices"][0]
        if choice.get("finish_reason") != "stop" or choice["message"].get("refusal"):
            raise ValueError()
        result = json.loads(choice["message"]["content"])
        Draft202012Validator(schema).validate(result)
        if not isinstance(result, dict):
            raise ValueError()
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, ValidationError):
        raise ModelServiceError("invalid_output", "雲端 AI 回覆未通過完整格式檢查，請稍後重試。") from None
    timings = {"request_seconds": round(time.perf_counter() - started, 3)}
    usage = payload.get("usage", {})
    if isinstance(usage, dict):
        for source, target in (("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens")):
            value = usage.get(source)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                timings[target] = value
    result["_model_timing"] = timings
    return result


def call_structured_json(*, instructions: str, input_text: str, schema: dict,
                         context_window: int | None = None) -> dict:
    if AI_PROVIDER == "ollama":
        result = call_ollama_structured_json(instructions=instructions, input_text=input_text,
                                             schema=schema, context_window=context_window)
        if "_ollama_timing" in result:
            result["_model_timing"] = result.pop("_ollama_timing")
        return result
    try:
        result = _call_gateway(instructions=instructions, input_text=input_text, schema=schema)
    except ModelServiceError as exc:
        _record_status("unavailable", exc.code, str(exc))
        raise
    _record_status("verified")
    return result


def model_unavailable_message() -> str:
    return f"AI 問答暫時無法完成，請確認 {AI_PROVIDER_LABEL} 與模型設定後再試。"
