"""HTTP interface and process entry point."""

from __future__ import annotations

import errno
import json
import socket
import threading
import urllib.parse
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .application.event_analysis import analyze_event_with_ai
from .application.management_summary import generate_management_summary_ai, select_management_events
from .application.regulatory_qa import QABusyError, answer_regulatory_question
from .application.refresh import invalidate_refresh_cache, refresh_data
from .application.event_history import load_older_events
from .application.law_comparison import get_law_comparisons
from .config import AI_PROMPT_VERSION, AI_PROVIDER_LABEL, APP_VERSION, BASE_DIR, OLLAMA_MODEL, PORT
from .domain.risk_analysis import rule_based_analyze_event
from .domain.text import clean_text, now_iso
from .infrastructure.ollama import preload_ollama, probe_ollama


# =========================================================
# HTTP Server
# =========================================================

class RegIntelHTTPServer(ThreadingHTTPServer):
    """Reserve the Windows listener so an old process cannot share its port."""
    allow_reuse_port = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.allow_reuse_address = False
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Handler(
    SimpleHTTPRequestHandler
):

    def log_request(self, code="-", size="-"):
        if urllib.parse.urlsplit(self.path).path.startswith("/api/compliance/"):
            return  # Do not log stale tokens sent by pages using the retired API.
        super().log_request(code, size)


    def static_file_allowed(self):
        if urllib.parse.urlsplit(self.path).path == "/":
            target = (BASE_DIR / "index.html").resolve()
        else:
            target = Path(self.translate_path(self.path)).resolve()
        if not target.is_file():
            return False
        if target == BASE_DIR / "index.html":
            return True
        suffixes = {".css", ".js", ".html", ".svg", ".png", ".jpg", ".jpeg", ".ico", ".woff", ".woff2"}
        return target.suffix.lower() in suffixes and any(target.is_relative_to(BASE_DIR / root) for root in ("assets", "prototypes"))

    def do_HEAD(self):
        if not self.static_file_allowed():
            self.send_error(404)
            return
        super().do_HEAD()

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


    def send_management_summary(self, event_ids: Any):
        try:
            events = select_management_events(refresh_data(False).get("events", []), event_ids)
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        try:
            summary = generate_management_summary_ai(events)
            self.send_json({"ok": True, "summary": summary})
        except Exception as exc:
            self.send_json({"ok": False, "error": clean_text(str(exc))[:400]}, status=502)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/compliance/"):
            self.send_json({"ok": False, "error": "公司作業檢查功能已移除，請重新整理頁面。"}, status=410)
            return
        if path not in {"/api/management-summary", "/api/events/history", "/api/regulatory-qa"}:
            self.send_json({"ok": False, "error": "找不到此服務。"}, status=404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 65536:
                raise ValueError("請提供有效的請求內容。")
            body = json.loads(self.rfile.read(size).decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError("請提供有效的請求內容。")
        except (ValueError, UnicodeDecodeError) as exc:
            self.send_json({"ok": False, "error": "請求格式不正確，請檢查輸入內容。"}, status=400)
            return
        if path == "/api/regulatory-qa":
            try:
                self.send_json({"ok": True, "answer": answer_regulatory_question(body)})
            except ValueError as exc:
                self.send_json({"ok": False, "error": str(exc)}, status=400)
            except QABusyError as exc:
                self.send_json({"ok": False, "error": str(exc)}, status=429)
            except Exception:
                self.send_json({"ok": False, "error": "AI 問答暫時無法完成，請確認本機 Ollama 與模型已啟動後再試。"}, status=502)
            return
        if path == "/api/management-summary":
            self.send_management_summary(body.get("event_ids"))
            return
        try:
            result = load_older_events(body.get("source_keys"))
            invalidate_refresh_cache()
            self.send_json({"ok": True, **refresh_data(False), "history_result": result})
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
        except Exception as exc:
            self.send_json({"ok": False, "error": clean_text(str(exc))[:400]}, status=502)

    def do_GET(
        self
    ):

        parsed = (
            urllib.parse.urlparse(
                self.path
            )
        )

        if parsed.path.startswith("/api/compliance/"):
            self.send_json({"ok": False, "error": "公司作業檢查功能已移除，請重新整理頁面。"}, status=410)
            return


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

        if parsed.path == "/api/law-comparison":
            params = urllib.parse.parse_qs(parsed.query)
            event_id = clean_text(params.get("id", [""])[0])
            event = next((item for item in refresh_data(False).get("events", []) if item.get("id") == event_id), None)
            if event is None:
                self.send_json({"ok": False, "error": "找不到指定的監理資訊。"}, status=404)
                return
            self.send_json({"ok": True, "comparisons": get_law_comparisons(event, fetch_missing=True)})
            return

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
                        event,
                        force=params.get("force", ["0"])[0] == "1",
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

        if parsed.path == "/api/management-summary":
            params = urllib.parse.parse_qs(parsed.query)
            self.send_management_summary(params.get("id", []))
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
                        APP_VERSION,
                    "analysis_prompt_version": AI_PROMPT_VERSION,
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


        if not self.static_file_allowed():
            self.send_error(404)
            return
        return super().do_GET()


# =========================================================
# Main
# =========================================================

def main():

    try:
        server = RegIntelHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE and getattr(exc, "winerror", None) != 10048:
            raise
        print(f"RegIntel 未啟動：連接埠 {PORT} 已有服務使用。")
        print(f"若 RegIntel 已在執行，請直接開啟 http://127.0.0.1:{PORT}")
        print("如需重新啟動，請先停止原本的 RegIntel 服務，再執行 server.py。")
        return 1

    print(
        (
            f"RegIntel v{APP_VERSION}｜"
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

        def warm_model():
            try:
                timing = preload_ollama()
                print(f"Ollama 模型已預載（{timing['request_seconds']:.1f} 秒）。", flush=True)
            except Exception as exc:
                print(f"Ollama 預載未完成，首次分析時會再嘗試載入：{clean_text(str(exc))[:180]}", flush=True)

        threading.Thread(target=warm_model, name="ollama-preload", daemon=True).start()


    print(
        "按 Ctrl+C 停止服務。\n"
    )


    try:

        server.serve_forever()


    except KeyboardInterrupt:

        print(
            "\n服務已停止。"
        )


    finally:

        server.server_close()

    return 0
