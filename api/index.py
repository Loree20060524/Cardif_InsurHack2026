"""Vercel entry point for the existing HTTP API; never starts a local listener."""

import urllib.parse

from regintel.config import IS_VERCEL
from regintel.web import Handler
from regintel.infrastructure.json_store import storage_health
from regintel.infrastructure.model_client import model_health, model_request_context
from regintel.infrastructure.postgres_store import StorageError


class handler(Handler):
    def send_json(self, payload, status=200):
        if urllib.parse.urlsplit(self.path).path == "/api/health":
            storage = storage_health()
            persistent = storage["backend"] == "postgres" and storage["connected"]
            try:
                ai = model_health()
            except StorageError:
                ai = {"ready": False, "status": "storage_unavailable"}
            payload = {**payload, "deployment": {
                "platform": "vercel" if IS_VERCEL else "local-preview",
                "ready": bool(persistent and ai["ready"]),
                "storage": "postgres" if persistent else "unavailable" if not storage["connected"] else "temporary" if IS_VERCEL else "local",
                "storage_check": storage,
                "ai_check": ai,
                "pending": ([] if persistent else ["persistent_storage"]) + ([] if ai["ready"] else ["cloud_ai"]),
            }}
        super().send_json(payload, status)

    def _restore_api_path(self):
        parsed = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        route = query.pop("__regintel_route", [])
        # Vercel rewrites may expose the destination URL to the runtime. Pass
        # the captured public route explicitly so GET queries and POST bodies
        # reach the same endpoints in either runtime behavior.
        if parsed.path in {"/api", "/api/", "/api/index.py"} and len(route) == 1:
            path = "/api/" + route[0].lstrip("/")
        else:
            path = parsed.path
        if not path.startswith("/api/") or any(part in {".", ".."} for part in path.split("/")):
            self.send_json({"ok": False, "error": "找不到此服務。"}, status=404)
            return False
        self.path = path + ("?" + urllib.parse.urlencode(query, doseq=True) if query else "")
        return True

    def do_GET(self):
        with model_request_context(self.headers.get("x-vercel-oidc-token") if IS_VERCEL else None):
            self._handle_GET()

    def _handle_GET(self):
        if self._restore_api_path():
            if self.path.split("?", 1)[0] not in {
                "/api/health",
                "/api/events", "/api/analyze", "/api/law-comparison",
                "/api/management-summary", "/api/source-status",
            } and not self.path.startswith("/api/compliance/"):
                self.send_json({"ok": False, "error": "找不到此服務。"}, status=404)
                return
            super().do_GET()

    def do_POST(self):
        with model_request_context(self.headers.get("x-vercel-oidc-token") if IS_VERCEL else None):
            if self._restore_api_path():
                super().do_POST()

    def do_HEAD(self):
        self.send_response(405)
        self.send_header("Allow", "GET, POST")
        self.end_headers()
