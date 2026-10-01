"""HTTP interface and process entry point."""

from __future__ import annotations

import json
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .application.event_analysis import analyze_event_with_ai
from .application.management_summary import generate_management_summary_ai
from .application.refresh import refresh_data
from .config import AI_PROVIDER_LABEL, BASE_DIR, OLLAMA_MODEL, PORT
from .domain.risk_analysis import rule_based_analyze_event
from .domain.text import clean_text, now_iso
from .infrastructure.ollama import probe_ollama


# =========================================================
# HTTP Server
# =========================================================

class Handler(
    SimpleHTTPRequestHandler
):

    def __init__(
        self,
        *args,
        **kwargs
    ):

        super().__init__(
            *args,
            directory=str(
                BASE_DIR
            ),
            **kwargs
        )


    def end_headers(
        self
    ):

        self.send_header(
            "Cache-Control",
            (
                "no-store, no-cache, "
                "must-revalidate, max-age=0"
            )
        )

        self.send_header(
            "Pragma",
            "no-cache"
        )

        self.send_header(
            "Expires",
            "0"
        )

        super().end_headers()


    def send_json(

        self,

        payload: Any,

        status: int = 200

    ):

        data = json.dumps(
            payload,
            ensure_ascii=False
        ).encode(
            "utf-8"
        )


        self.send_response(
            status
        )


        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )


        self.send_header(
            "X-Content-Type-Options",
            "nosniff"
        )


        self.send_header(
            "Content-Length",
            str(
                len(data)
            )
        )


        self.end_headers()


        self.wfile.write(
            data
        )


    def do_GET(
        self
    ):

        parsed = (
            urllib.parse.urlparse(
                self.path
            )
        )


        # ---------------------------------------------
        # Events
        # ---------------------------------------------

        if (
            parsed.path
            ==
            "/api/events"
        ):

            params = (
                urllib.parse.parse_qs(
                    parsed.query
                )
            )


            force = (

                params.get(
                    "refresh",
                    ["0"]
                )[0]

                ==

                "1"
            )


            self.send_json(

                refresh_data(
                    force
                )
            )


            return


        # ---------------------------------------------
        # Event AI analysis
        # ---------------------------------------------

        if (
            parsed.path
            ==
            "/api/analyze"
        ):

            params = (
                urllib.parse.parse_qs(
                    parsed.query
                )
            )


            event_id_value = clean_text(

                params.get(
                    "id",
                    [""]
                )[0]
            )


            payload = (
                refresh_data(
                    False
                )
            )


            event = next(

                (

                    item

                    for item
                    in payload.get(
                        "events",
                        []
                    )

                    if item.get(
                        "id"
                    )
                    ==
                    event_id_value
                ),

                None
            )


            if event is None:

                self.send_json(

                    {

                        "ok":
                            False,

                        "error":
                            (
                                "找不到指定的"
                                "監理事件。"
                            ),
                    },

                    status=404
                )


                return


            try:

                analysis = (
                    analyze_event_with_ai(
                        event
                    )
                )


                self.send_json(

                    {

                        "ok":
                            True,

                        "ai_used":
                            (
                                analysis.get(
                                    "analysis_mode"
                                )
                                ==
                                "AI 深度分析"
                            ),

                        "analysis":
                            analysis,

                        "model":
                            OLLAMA_MODEL,

                        "provider":
                            AI_PROVIDER_LABEL,
                    }
                )


            except Exception as exc:

                error_message = clean_text(
                    str(exc)
                )[:1000]


                print(

                    (
                        "[AI 分析錯誤] "
                        f"事件={event.get('id', '')} "
                        f"標題="
                        f"{clean_text(event.get('title', ''))[:80]} "
                        f"原因={error_message}"
                    ),

                    flush=True
                )


                fallback = (
                    rule_based_analyze_event(
                        event
                    )
                )


                fallback[
                    "analysis_note"
                ] = (

                    "AI 分析暫時無法完成，"
                    "已切換規則式備援；"
                    "最終適用性仍應由"
                    "相關單位確認。"
                )


                self.send_json(

                    {

                        "ok":
                            True,

                        "ai_used":
                            False,

                        "analysis":
                            fallback,

                        "message":
                            error_message[:500],
                    }
                )


            return


        # ---------------------------------------------
        # Management summary
        # ---------------------------------------------

        if (
            parsed.path
            ==
            "/api/management-summary"
        ):

            payload = (
                refresh_data(
                    False
                )
            )


            events = (
                payload.get(
                    "events",
                    []
                )[:7]
            )


            try:

                summary = (
                    generate_management_summary_ai(
                        events
                    )
                )


                self.send_json(

                    {

                        "ok":
                            True,

                        "summary":
                            summary,
                    }
                )


            except Exception as exc:

                self.send_json(

                    {

                        "ok":
                            False,

                        "error":
                            clean_text(
                                str(exc)
                            )[:400],
                    },

                    status=502
                )


            return


        # ---------------------------------------------
        # Source status
        # ---------------------------------------------

        if (
            parsed.path
            ==
            "/api/source-status"
        ):

            payload = (
                refresh_data(
                    False
                )
            )


            self.send_json(

                {

                    "last_sync":
                        payload.get(
                            "last_sync"
                        ),

                    "sources":
                        payload.get(
                            "sources",
                            {}
                        ),

                    "stale":
                        payload.get(
                            "stale",
                            False
                        ),
                }
            )


            return


        # ---------------------------------------------
        # Health
        # ---------------------------------------------

        if (
            parsed.path
            ==
            "/api/health"
        ):

            self.send_json(

                {

                    "ok":
                        True,

                    "time":
                        now_iso(),

                    "version":
                        "10.6",
                }
            )


            return


        # ---------------------------------------------
        # Index
        # ---------------------------------------------

        if (
            parsed.path
            ==
            "/"
        ):

            self.path = (
                "/index.html"
            )


        return super().do_GET()


# =========================================================
# Main
# =========================================================

def main():

    print(
        (
            "RegIntel v10.6｜"
            "保險業 AI 監理情報"
            "與風險預警平台"
        )
    )


    print(
        f"服務目錄：{BASE_DIR}"
    )


    print(
        (
            "開啟網址："
            f"http://127.0.0.1:{PORT}"
        )
    )


    print(
        (
            "AI 分析："
            f"本機 Ollama（{OLLAMA_MODEL}）"
        )
    )


    ollama_status = (
        probe_ollama()
    )


    if not ollama_status.get(
        "reachable"
    ):

        print(
            (
                "Ollama 狀態：無法連線。"
                "請先啟動 Ollama。"
            )
        )

        print(
            (
                "若尚未下載模型，請執行："
                f"ollama pull {OLLAMA_MODEL}"
            )
        )


    elif not ollama_status.get(
        "model_installed"
    ):

        print(

            (
                "Ollama 狀態：已連線，"
                f"但尚未找到模型 {OLLAMA_MODEL}。"
            )
        )

        print(
            (
                "請執行："
                f"ollama pull {OLLAMA_MODEL}"
            )
        )


    else:

        print(
            (
                "Ollama 狀態："
                "已連線，模型已就緒。"
            )
        )


    print(
        "按 Ctrl+C 停止服務。\n"
    )


    server = (
        ThreadingHTTPServer(

            (
                "127.0.0.1",
                PORT
            ),

            Handler
        )
    )


    try:

        server.serve_forever()


    except KeyboardInterrupt:

        print(
            "\n服務已停止。"
        )


    finally:

        server.server_close()
