"""Exercise public packaging and the real Vercel API handler over HTTP."""

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from api import index
from regintel import web
from regintel.infrastructure.postgres_store import StorageError
from scripts.build_vercel import build_public


class StaticBuildTests(unittest.TestCase):
    def test_build_exposes_only_ui_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "assets" / "js").mkdir(parents=True)
            for name in ("index.html", "assets/js/app.js", "assets/style.css", ".env",
                         "server.py", "regintel_ai_cache_v10.json", "assets/private.json",
                         "assets/.env", "assets/.hidden.js"):
                (root / name).write_text("fixture", encoding="utf-8")
            output = build_public(root)
            files = {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()}
            self.assertEqual(files, {"index.html", "assets/js/app.js", "assets/style.css"})

    def test_old_unexpected_public_files_fail_the_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "public").mkdir()
            (root / "index.html").write_text("fixture", encoding="utf-8")
            (root / "public" / ".env").write_text("fixture", encoding="utf-8")
            with self.assertRaises(ValueError):
                build_public(root)


class VercelHandlerTests(unittest.TestCase):
    def setUp(self):
        self.server = web.RegIntelHTTPServer(("127.0.0.1", 0), index.handler)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=5)

    def request(self, path, body=None):
        request = urllib.request.Request(self.base + path,
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            headers={"Content-Type": "application/json"})
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_direct_and_rewritten_events_preserve_refresh_parameter(self):
        with patch.object(web, "refresh_data", return_value={"events": []}) as refresh:
            for path in ("/api/events?refresh=1", "/api?__regintel_route=events&refresh=1"):
                status, result = self.request(path)
                self.assertEqual(status, 200)
                self.assertEqual(result["events"], [])
                refresh.assert_called_with(True)

    def test_rewritten_analysis_preserves_encoded_event_id(self):
        event = {"id": "event&1+2"}
        with patch.object(web, "refresh_data", return_value={"events": [event]}), \
             patch.object(web, "analyze_event_with_ai", return_value={"analysis_mode": "AI 深度分析"}) as analyze:
            status, _ = self.request("/api?__regintel_route=analyze&id=event%261%2B2&force=1")
        self.assertEqual(status, 200)
        analyze.assert_called_once_with(event, force=True)

    def test_post_rewrite_preserves_json_body(self):
        body = {"question": "近期監理要求有哪些？", "filters": {"type": "全部"}}
        with patch.object(web, "answer_regulatory_question", return_value={"status": "insufficient"}) as answer:
            status, result = self.request("/api?__regintel_route=regulatory-qa", body)
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        answer.assert_called_once_with(body)

    def test_unknown_routes_and_files_are_never_served_by_api(self):
        for path in ("/api?__regintel_route=../index.html", "/api?__regintel_route=server.py",
                     "/api?__regintel_route=.env", "/api/unknown", "/index.html", "/api"):
            status, result = self.request(path)
            self.assertEqual(status, 404, path)
            self.assertFalse(result["ok"])

    def test_health_distinguishes_liveness_from_incomplete_deployment(self):
        with patch.object(index, "IS_VERCEL", True):
            status, result = self.request("/api?__regintel_route=health")
        self.assertEqual(status, 200)
        self.assertIn("version", result)
        self.assertTrue(result["ok"])
        self.assertFalse(result["deployment"]["ready"])
        self.assertEqual(result["deployment"]["storage"], "temporary")
        self.assertIn("cloud_ai", result["deployment"]["pending"])

    def test_database_failure_is_a_clear_retryable_response(self):
        with patch.object(web, "refresh_data", side_effect=StorageError("資料庫暫時無法讀寫")):
            status, result = self.request("/api/events")
        self.assertEqual(status, 503)
        self.assertFalse(result["ok"])
        self.assertIn("資料庫", result["error"])

    def test_health_reports_verified_storage_separately_from_cloud_ai(self):
        with patch.object(index, "storage_health", return_value={"backend": "postgres", "connected": True}):
            status, result = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(result["deployment"]["storage"], "postgres")
        self.assertEqual(result["deployment"]["pending"], ["cloud_ai"])
        self.assertFalse(result["deployment"]["ready"])


if __name__ == "__main__":
    unittest.main()
