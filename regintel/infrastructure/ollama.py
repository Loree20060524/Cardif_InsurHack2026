"""Ollama HTTP adapter and health probe."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ..config import (
    MAX_RESPONSE_BYTES,
    OLLAMA_API_URL,
    OLLAMA_MODEL,
    OLLAMA_THINK,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_TIMEOUT,
    USER_AGENT,
)
from ..domain.text import clean_text


def ollama_timings(payload: dict[str, Any], elapsed: float) -> dict[str, Any]:
    """Keep server measurements without retaining model reasoning text."""
    timings: dict[str, Any] = {"request_seconds": round(elapsed, 3)}
    for source, target in (
        ("load_duration", "load_seconds"),
        ("prompt_eval_duration", "input_seconds"),
        ("eval_duration", "generation_seconds"),
    ):
        value = payload.get(source)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            timings[target] = round(value / 1_000_000_000, 3)
    for source, target in (("prompt_eval_count", "input_tokens"), ("eval_count", "output_tokens")):
        value = payload.get(source)
        if isinstance(value, int) and not isinstance(value, bool):
            timings[target] = value
    return timings


def preload_ollama() -> dict[str, Any]:
    """Load the installed model without generating text or touching analysis caches."""
    body = {"model": OLLAMA_MODEL, "messages": [], "stream": False, "keep_alive": OLLAMA_KEEP_ALIVE}
    request = urllib.request.Request(
        OLLAMA_API_URL, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=OLLAMA_TIMEOUT) as response:
        payload = json.loads(response.read(MAX_RESPONSE_BYTES).decode("utf-8"))
    return ollama_timings(payload, time.perf_counter() - started)


# =========================================================
# Ollama AI
# =========================================================

def call_ollama_structured_json(

    *,

    instructions: str,

    input_text: str,

    schema: dict[
        str,
        Any
    ],

    context_window: int | None = None,

    local_only: bool = False,

    think: bool | None = None,

    max_output_tokens: int | None = None,

    request_timeout: float | None = None,

) -> dict[
    str,
    Any
]:

    if local_only:
        endpoint = urllib.parse.urlsplit(OLLAMA_API_URL)
        if endpoint.hostname not in {"127.0.0.1", "localhost", "::1"} or endpoint.scheme not in {"http", "https"} or endpoint.username or endpoint.password or "cloud" in OLLAMA_MODEL.lower():
            raise RuntimeError("此分析僅允許本機 Ollama 與本機模型，請檢查模型服務設定。")

    request_body = {

        "model":
            OLLAMA_MODEL,

        "messages": [

            {

                "role":
                    "system",

                "content":
                    instructions,
            },

            {

                "role":
                    "user",

                "content":
                    (
                        input_text
                        +
                        "\n\n"
                        "請只輸出符合指定 "
                        "JSON Schema 的 JSON，"
                        "不要加入 Markdown "
                        "或額外說明。"
                    ),
            },
        ],

        "stream":
            False,

        "format":
            schema,

        "options": {
            "temperature":
                0
        },

        "keep_alive":
            "0" if local_only else OLLAMA_KEEP_ALIVE,
    }


    if context_window is not None:
        request_body["options"]["num_ctx"] = context_window
    if max_output_tokens is not None:
        if not isinstance(max_output_tokens, int) or isinstance(max_output_tokens, bool) or max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be a positive integer")
        request_body["options"]["num_predict"] = max_output_tokens
    if request_timeout is not None and (not isinstance(request_timeout, (int, float)) or isinstance(request_timeout, bool) or request_timeout <= 0):
        raise ValueError("request_timeout must be positive")

    effective_think = OLLAMA_THINK if think is None else think
    if effective_think is not None:
        request_body["think"] = effective_think

    if local_only:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                raise urllib.error.HTTPError(req.full_url, code, "本機分析不允許重新導向。", headers, fp)

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        open_url = opener.open
    else:
        open_url = urllib.request.urlopen

    request = (
        urllib.request.Request(

            OLLAMA_API_URL,

            data=json.dumps(
                request_body,
                ensure_ascii=False
            ).encode(
                "utf-8"
            ),

            headers={

                "Content-Type":
                    "application/json",

                "Accept":
                    "application/json",

                "User-Agent":
                    USER_AGENT,
            },

            method="POST",
        )
    )


    request_started = time.perf_counter()
    try:

        with open_url(
            request,
            timeout=OLLAMA_TIMEOUT if request_timeout is None else request_timeout
        ) as response:

            raw = response.read(
                MAX_RESPONSE_BYTES
            )


    except urllib.error.HTTPError as exc:

        detail = ""

        try:

            detail = (
                exc.read(
                    4096
                )
                .decode(
                    "utf-8",
                    errors="replace"
                )
            )

        except Exception:

            pass


        raise RuntimeError(

            f"Ollama HTTP "
            f"{exc.code}。"
            f"{clean_text(detail)[:260]}"
        ) from exc


    except urllib.error.URLError as exc:

        raise RuntimeError(

            (
                "無法連線本機 Ollama。"
                "請確認 Ollama 已啟動，"
                "並確認 "
                "http://127.0.0.1:11434 "
                "可用。"
            )

        ) from exc


    except Exception as exc:

        raise RuntimeError(

            (
                "Ollama 連線失敗："
                f"{clean_text(str(exc))[:180]}"
            )

        ) from exc


    try:

        payload = json.loads(
            raw.decode(
                "utf-8"
            )
        )


    except Exception as exc:

        raise RuntimeError(
            "Ollama 回應不是有效 JSON。"
        ) from exc


    message = payload.get(
        "message",
        {}
    )


    output_text = (

        message.get(
            "content",
            ""
        )

        if isinstance(
            message,
            dict
        )

        else ""
    )


    if not output_text:

        raise RuntimeError(
            "Ollama 未回傳可解析的分析內容。"
        )


    try:

        result = json.loads(
            output_text
        )


    except Exception as exc:

        raise RuntimeError(

            (
                "Ollama 模型未輸出"
                "有效 JSON。"
                "回應前段："
                f"{clean_text(output_text)[:220]}"
            )

        ) from exc


    if not isinstance(
        result,
        dict
    ):

        raise RuntimeError(
            "Ollama AI 結果格式不正確。"
        )


    result["_ollama_timing"] = ollama_timings(payload, time.perf_counter() - request_started)
    return result


def probe_ollama() -> dict[
    str,
    Any
]:

    parsed = (
        urllib.parse.urlparse(
            OLLAMA_API_URL
        )
    )


    tags_url = (

        f"{parsed.scheme}://"
        f"{parsed.netloc}/"
        "api/tags"
    )


    try:

        request = (
            urllib.request.Request(

                tags_url,

                headers={

                    "Accept":
                        "application/json",

                    "User-Agent":
                        USER_AGENT,
                },
            )
        )


        with urllib.request.urlopen(
            request,
            timeout=3
        ) as response:

            payload = json.loads(

                response.read(
                    2
                    *
                    1024
                    *
                    1024
                )
                .decode(
                    "utf-8"
                )
            )


        models: list[str] = []


        for item in payload.get(
            "models",
            []
        ):

            if not isinstance(
                item,
                dict
            ):

                continue


            name = clean_text(

                item.get(
                    "name",
                    ""
                )

                or

                item.get(
                    "model",
                    ""
                )
            )


            if name:

                models.append(
                    name
                )


        wanted = (
            OLLAMA_MODEL.lower()
        )


        installed = any(

            name.lower()
            ==
            wanted

            for name
            in models
        )


        return {

            "reachable":
                True,

            "model_installed":
                installed,

            "models":
                models,
        }


    except Exception as exc:

        return {

            "reachable":
                False,

            "model_installed":
                False,

            "models":
                [],

            "error":
                clean_text(
                    str(exc)
                )[:180],
        }
