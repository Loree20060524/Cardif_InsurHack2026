"""Request settings and measurements that keep analysis latency observable."""

from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from regintel.application import ai_support, management_summary
from regintel.infrastructure import ollama
from regintel import web


class OllamaPerformanceTests(unittest.TestCase):
    def request_analysis(self, **kwargs):
        payload = {
            "message": {"content": '{"summary":"source-grounded result"}'},
            "load_duration": 2_000_000_000,
            "prompt_eval_duration": 3_000_000_000,
            "eval_duration": 4_000_000_000,
            "prompt_eval_count": 100,
            "eval_count": 200,
        }
        with patch.object(ollama.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(payload).encode())) as opened:
            result = ollama.call_ollama_structured_json(
                instructions="Use only the official source.", input_text="Public source.",
                schema={"type": "object"}, **kwargs,
            )
        return json.loads(opened.call_args.args[0].data), result

    def test_default_analysis_disables_thinking_without_reducing_context(self):
        with patch.object(ollama, "OLLAMA_THINK", False, create=True):
            body, _ = self.request_analysis(context_window=16384)
        self.assertIs(body.get("think"), False)
        self.assertEqual(body["options"]["num_ctx"], 16384)

    def test_explicit_thinking_setting_overrides_the_default(self):
        with patch.object(ollama, "OLLAMA_THINK", False, create=True):
            body, _ = self.request_analysis(think=True)
        self.assertIs(body["think"], True)

    def test_auto_setting_preserves_the_models_default(self):
        with patch.object(ollama, "OLLAMA_THINK", None, create=True):
            body, _ = self.request_analysis()
        self.assertNotIn("think", body)

    def test_preserves_server_timings_and_token_counts(self):
        _, result = self.request_analysis()
        timings = result.get("_ollama_timing", {})
        self.assertEqual(timings.get("load_seconds"), 2)
        self.assertEqual(timings.get("input_seconds"), 3)
        self.assertEqual(timings.get("generation_seconds"), 4)
        self.assertEqual(timings.get("input_tokens"), 100)
        self.assertEqual(timings.get("output_tokens"), 200)
        self.assertEqual(result["summary"], "source-grounded result")

    def test_thinking_modes_cannot_reuse_each_others_event_cache(self):
        event = {"id": "public-event", "description": "Official source."}
        with patch.object(ai_support, "AI_THINK", False, create=True):
            fast = ai_support.ai_event_cache_key(event)
        with patch.object(ai_support, "AI_THINK", True, create=True):
            thinking = ai_support.ai_event_cache_key(event)
        self.assertNotEqual(fast, thinking)

    def test_thinking_modes_cannot_reuse_each_others_summary_cache(self):
        events = [{"id": "public-event", "description": "Official source."}]
        with patch.object(management_summary, "management_source_text", return_value="Official source."):
            with patch.object(management_summary, "AI_THINK", False, create=True):
                fast = management_summary.management_cache_key(events)
            with patch.object(management_summary, "AI_THINK", True, create=True):
                thinking = management_summary.management_cache_key(events)
        self.assertNotEqual(fast, thinking)

    def test_preloading_does_not_generate_an_analysis(self):
        preload = getattr(ollama, "preload_ollama", None)
        self.assertTrue(callable(preload), "A preload request must be available before the first analysis.")
        with patch.object(ollama.urllib.request, "urlopen", return_value=io.BytesIO(b'{"done":true}')) as opened:
            preload()
        body = json.loads(opened.call_args.args[0].data)
        self.assertEqual(body["messages"], [])
        self.assertEqual(body["model"], ollama.OLLAMA_MODEL)
        self.assertEqual(body["keep_alive"], ollama.OLLAMA_KEEP_ALIVE)

    def test_server_starts_preloading_in_the_background(self):
        with (
            patch.object(web, "RegIntelHTTPServer") as server,
            patch.object(web, "probe_ollama", return_value={"reachable": True, "model_installed": True}),
            patch.object(web, "preload_ollama", return_value={"request_seconds": 0.1}) as preload,
            patch.object(web.threading, "Thread") as worker,
            patch("builtins.print"),
        ):
            self.assertEqual(web.main(), 0)
            self.assertIs(worker.call_args.kwargs["daemon"], True)
            worker.return_value.start.assert_called_once()
            server.return_value.serve_forever.assert_called_once()
            preload.assert_not_called()
            worker.call_args.kwargs["target"]()
            preload.assert_called_once()


if __name__ == "__main__":
    unittest.main()
