"""Explicit analysis retries must bypass caches without changing normal reuse."""

import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from regintel.application import event_analysis as analysis
from regintel.application.event_evidence import EVENT_REVIEW_VERSION
from regintel import web


class AnalysisRetryTests(unittest.TestCase):
    def test_force_regenerates_and_replaces_cached_analysis(self):
        event = {"id": "retry-test", "source_key": "reg_news", "title": "保險業投資管理公告",
                 "description": "保險業辦理投資作業應依規定建立內部控制制度，保存投資評估、核准及覆核紀錄，並定期檢查風險限額。"}
        old = {"analysis_mode": "AI 深度分析", "summary": "先前結果"}
        new = {"analysis_mode": "AI 深度分析", "summary": "重新產生的結果"}
        for item in (old, new):
            item["support_review"] = {"version": EVENT_REVIEW_VERSION, "unverified": 0}
        cache = {"analyses": {analysis.ai_event_cache_key(event): old}}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(analysis, "AI_CACHE_FILE", Path(directory) / "ai.json"), \
             patch.object(analysis, "load_ai_cache", return_value=cache), \
             patch.object(analysis, "call_ollama_structured_json", return_value={}) as model, \
             patch.object(analysis, "sanitize_ai_analysis", return_value=dict(new)), \
             patch.object(analysis, "review_event_analysis", return_value=new):
            self.assertEqual(analysis.analyze_event_with_ai(event), old)
            model.assert_not_called()
            self.assertEqual(analysis.analyze_event_with_ai(event, force=True), new)
            model.assert_called_once()
            self.assertEqual(analysis.analyze_event_with_ai(event), new)
            model.assert_called_once()
            saved = json.loads(analysis.AI_CACHE_FILE.read_text(encoding="utf-8"))
            self.assertEqual(saved["analyses"][analysis.ai_event_cache_key(event)], new)

    def test_http_forwards_force_only_when_requested(self):
        event = {"id": "retry-test"}

        class QuietHandler(web.Handler):
            def log_message(self, *_args):
                pass

        with patch.object(web, "refresh_data", return_value={"events": [event]}), \
             patch.object(web, "analyze_event_with_ai", return_value={"analysis_mode": "AI 深度分析"}) as model:
            server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}/api/analyze?id=retry-test"
                for suffix, expected in (("", False), ("&force=1", True), ("&force=0", False)):
                    with urllib.request.urlopen(base + suffix, timeout=5) as response:
                        self.assertTrue(json.load(response)["ai_used"])
                    model.assert_called_with(event, force=expected)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
