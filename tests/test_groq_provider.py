"""Verify the provider boundary, safe failures, and serverless snapshot behavior."""

import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from regintel.infrastructure import ai, groq
from regintel.application import ai_support, refresh


class GroqProviderTests(unittest.TestCase):
    def call_model(self, payload):
        with patch.object(groq, "GROQ_API_KEY", "test-secret"), patch.object(groq.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(payload).encode())) as opened:
            result = groq.call_groq_structured_json(instructions="Only official evidence.", input_text="Public text", schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False})
        return result, opened.call_args.args[0]

    def test_groq_uses_strict_schema_and_server_side_auth(self):
        result, request = self.call_model({"choices": [{"finish_reason": "stop", "message": {"content": '{"summary":"answer"}'}}], "usage": {"prompt_tokens": 20, "completion_tokens": 40}})
        body = json.loads(request.data)
        self.assertEqual(request.full_url, "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")
        self.assertEqual(body["model"], "openai/gpt-oss-120b")
        self.assertTrue(body["response_format"]["json_schema"]["strict"])
        self.assertNotIn("test-secret", request.data.decode())
        self.assertEqual(result["_model_timing"]["output_tokens"], 40)

    def test_missing_key_does_not_send_request(self):
        with patch.object(groq, "GROQ_API_KEY", ""), patch.object(groq.urllib.request, "urlopen") as opened:
            with self.assertRaisesRegex(RuntimeError, "GROQ_API_KEY"):
                groq.call_groq_structured_json(instructions="", input_text="", schema={})
            opened.assert_not_called()

    def test_provider_errors_do_not_expose_response_body(self):
        error = urllib.error.HTTPError(groq.GROQ_CHAT_URL, 429, "limit", {}, io.BytesIO(b"test-secret private question"))
        with patch.object(groq, "GROQ_API_KEY", "test-secret"), patch.object(groq.urllib.request, "urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "使用量已達限制") as raised:
                groq.call_groq_structured_json(instructions="", input_text="", schema={})
            self.assertNotIn("test-secret", str(raised.exception))
            self.assertNotIn("private question", str(raised.exception))
            self.assertEqual(raised.exception.status, 429)

    def test_incomplete_generation_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "完整"):
            self.call_model({"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]})

    def test_local_only_cannot_reach_cloud_provider(self):
        with patch.object(ai, "AI_PROVIDER", "groq"), patch.object(ai, "call_groq_structured_json") as cloud:
            with self.assertRaisesRegex(RuntimeError, "本機"):
                ai.call_structured_json(instructions="", input_text="", schema={}, local_only=True)
            cloud.assert_not_called()

    def test_provider_boundary_preserves_application_generation_limits(self):
        for provider, function in (("ollama", "call_ollama_structured_json"), ("groq", "call_groq_structured_json")):
            with self.subTest(provider=provider), patch.object(ai, "AI_PROVIDER", provider), patch.object(ai, function, return_value={"summary": "bounded"}) as model:
                result = ai.call_structured_json(instructions="Only public evidence.", input_text="Public text", schema={},
                                                 max_output_tokens=1800, request_timeout=60)
                self.assertEqual(result["summary"], "bounded")
                self.assertEqual(model.call_args.kwargs["max_output_tokens"], 1800)
                self.assertEqual(model.call_args.kwargs["request_timeout"], 60)

    def test_groq_request_respects_explicit_generation_limits(self):
        payload = {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
        with patch.object(groq, "GROQ_API_KEY", "test-secret"), patch.object(groq.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(payload).encode())) as opened:
            groq.call_groq_structured_json(instructions="", input_text="", schema={}, max_output_tokens=1800, request_timeout=60)
        self.assertEqual(json.loads(opened.call_args.args[0].data)["max_completion_tokens"], 1800)
        self.assertEqual(opened.call_args.kwargs["timeout"], 60)

    def test_provider_switch_cannot_reuse_other_provider_cache(self):
        with patch.object(ai_support, "AI_PROVIDER", "groq"):
            cloud_key = ai_support.ai_event_cache_key({"id": "same"})
        with patch.object(ai_support, "AI_PROVIDER", "ollama"):
            local_key = ai_support.ai_event_cache_key({"id": "same"})
        self.assertNotEqual(cloud_key, local_key)

    def test_serverless_snapshot_uses_current_model_without_fetching_sources(self):
        with patch.object(refresh, "IS_VERCEL", True), patch.object(refresh, "load_json_file", return_value={"events": [{"id": "public-event"}], "ai": {"model": "old-model"}, "stale": False, "refresh_summary": {"failed": 0}}), patch.object(refresh, "fetch_url") as fetched:
            result = refresh.refresh_data(False)
        fetched.assert_not_called()
        self.assertEqual(result["ai"]["model"], refresh.AI_MODEL)
        self.assertTrue(result["deployment_snapshot"])
        self.assertFalse(result["stale"], "A saved snapshot must not claim official sources failed when none failed.")

    def test_serverless_snapshot_preserves_actual_source_failures(self):
        payload = {"events": [{"id": "public-event"}], "stale": True, "refresh_summary": {"failed": 1}}
        with patch.object(refresh, "IS_VERCEL", True), patch.object(refresh, "load_json_file", return_value=payload):
            result = refresh.refresh_data(False)
        self.assertTrue(result["stale"])
        self.assertEqual(result["refresh_summary"]["failed"], 1)


if __name__ == "__main__":
    unittest.main()
