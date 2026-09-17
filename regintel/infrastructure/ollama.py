"""Ollama HTTP adapter and health probe."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from ..config import (
    MAX_RESPONSE_BYTES,
    OLLAMA_API_URL,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT,
    USER_AGENT,
)
from ..domain.text import clean_text


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

) -> dict[
    str,
    Any
]:

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
            "10m",
    }


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


    try:

        with urllib.request.urlopen(
            request,
            timeout=OLLAMA_TIMEOUT
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
