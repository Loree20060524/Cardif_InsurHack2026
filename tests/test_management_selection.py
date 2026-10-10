from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from regintel.application import management_summary as summaries
from regintel.web import Handler


def event(index: int) -> dict:
    return {
        "id": f"event-{index}",
        "title": f"所選監理資訊 {index}",
        "description": f"來源記載第 {index} 筆資訊的官方內容。" * 5,
        "source": "官方來源",
        "published_at": "2026-10-02T00:00:00+08:00",
        "url": f"https://example.com/{index}",
    }


class ManagementSelectionTests(unittest.TestCase):
    def test_selection_uses_requested_order_and_never_auto_selects(self):
        events = [event(index) for index in range(12)]
        chosen = summaries.select_management_events(events, ["event-11", "event-2", "event-11"])
        self.assertEqual([item["id"] for item in chosen], ["event-11", "event-2"])
        for invalid in (None, [], "event-1", ["unknown"], [1]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                summaries.select_management_events(events, invalid)

    def test_cache_includes_selection_beyond_seven_events(self):
        first = [event(index) for index in range(8)]
        second = first[:7] + [event(99)]
        self.assertNotEqual(summaries.management_cache_key(first), summaries.management_cache_key(second))

    def test_all_selected_events_reach_model_in_batches_and_remain_in_sources(self):
        events = [event(index) for index in range(9)]
        inputs = []

        def model(**kwargs):
            inputs.append(kwargs["input_text"])
            return {
                "headline": "管理摘要",
                "summary": "依所選資訊彙整。",
                "risk_outlook": "中",
                "priority_events": [{"title": "未選取的事件", "reason": "不應納入"}],
                "priority_actions": [],
                "trend_observations": [],
                "management_note": "所選資訊摘要。",
            }

        with patch.object(summaries, "_cached_summary", return_value=None), \
             patch.object(summaries, "_save_summary"), \
             patch.object(summaries, "call_ollama_structured_json", side_effect=model):
            result = summaries.generate_management_summary_ai(events)

        self.assertEqual(len(inputs), 3)
        for item in events:
            self.assertTrue(any(f"ID：{item['id']}\n" in text for text in inputs[:2]))
        self.assertEqual([item["id"] for item in result["source_events"]], [item["id"] for item in events])
        self.assertEqual(result["selected_event_count"], 9)
        self.assertEqual(result["priority_events"], [])

    def test_http_post_uses_selection_and_rejects_missing_selection(self):
        events = [event(index) for index in range(12)]
        received = []

        def generate(chosen):
            received.append([item["id"] for item in chosen])
            return {"source_events": chosen, "selected_event_count": len(chosen)}

        class QuietHandler(Handler):
            def log_message(self, *_args):
                pass

        with patch("regintel.web.refresh_data", return_value={"events": events}), \
             patch("regintel.web.generate_management_summary_ai", side_effect=generate):
            server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            url = f"http://127.0.0.1:{server.server_port}/api/management-summary"
            try:
                request = urllib.request.Request(url, data=json.dumps({"event_ids": ["event-11", "event-2"]}).encode(), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request, timeout=5) as response:
                    payload = json.load(response)
                self.assertEqual(received, [["event-11", "event-2"]])
                self.assertTrue(payload["ok"])
                for data in (None, b'{"event_ids": []}', b'{"event_ids": ["unknown"]}', b'{}', b'not-json'):
                    with self.subTest(data=data), self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=5)
                    self.assertEqual(error.exception.code, 400)
                self.assertEqual(len(received), 1)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
