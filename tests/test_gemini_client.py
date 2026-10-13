"""Direct Gemini requests use free-project credentials and never fall back to billing."""

import io
import json
import unittest
import urllib.error
from unittest.mock import Mock, patch

from regintel.infrastructure import model_client as client


SCHEMA = {"type": "object", "properties": {"summary": {"type": "string"}},
          "required": ["summary"], "additionalProperties": False}


class GeminiClientTests(unittest.TestCase):
    def setUp(self):
        for patcher in (
            patch.object(client, "AI_PROVIDER", "gemini"),
            patch.object(client, "AI_MODEL", "gemini-3.8-flash"),
            patch.object(client, "get_store", return_value=None),
            patch.dict(client.os.environ, {"GEMINI_API_KEY": "private-google-key", "VERCEL_OIDC_TOKEN": "oidc-is-not-google"}, clear=True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        client._last_status.clear()

    def call(self):
        return client.call_structured_json(instructions="Only supplied official sources.",
                                          input_text="公開監理資料", schema=SCHEMA, context_window=16384)

    def payload(self, result=None, finish="STOP"):
        return {"candidates": [{"finishReason": finish, "content": {"parts": [
            {"thought": True, "text": "private reasoning must be discarded"},
            {"text": json.dumps(result if result is not None else {"summary": "摘要"})},
        ]}}], "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 60, "thoughtsTokenCount": 10}}

    def test_gemini_uses_server_key_header_json_schema_and_low_thinking(self):
        opener = Mock()
        opener.open.return_value = io.BytesIO(json.dumps(self.payload()).encode())
        with patch.object(client.urllib.request, "build_opener", return_value=opener), \
             patch.object(client, "_call_gateway") as gateway:
            result = self.call()
        request = opener.open.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(request.get_header("X-goog-api-key"), "private-google-key")
        self.assertNotIn("private-google-key", request.full_url)
        self.assertNotIn("private-google-key", request.data.decode())
        self.assertNotIn("oidc-is-not-google", str(request.headers))
        self.assertEqual(body["generationConfig"]["responseFormat"]["text"]["schema"], SCHEMA)
        self.assertEqual(body["generationConfig"]["thinkingConfig"]["thinkingLevel"], "LOW")
        self.assertFalse(body["generationConfig"]["thinkingConfig"]["includeThoughts"])
        self.assertNotIn("tools", body)
        self.assertEqual(result["summary"], "摘要")
        self.assertEqual(result["_model_timing"]["thinking_tokens"], 10)
        self.assertNotIn("reasoning", json.dumps(result))
        self.assertTrue(client.model_health()["ready"])
        gateway.assert_not_called()

    def test_missing_google_key_is_not_replaced_by_vercel_oidc(self):
        with patch.dict(client.os.environ, {"GEMINI_API_KEY": ""}), \
             patch.object(client.urllib.request, "build_opener") as opener:
            with self.assertRaises(client.ModelServiceError) as caught:
                self.call()
            self.assertEqual(caught.exception.code, "missing_credentials")
            self.assertEqual(client.model_health()["status"], "missing_credentials")
            opener.assert_not_called()

    def test_truncated_blocked_malformed_and_wrong_schema_outputs_fail_closed(self):
        cases = [self.payload({}, "STOP"), self.payload({"summary": 2}),
                 self.payload({"summary": "partial"}, "MAX_TOKENS"),
                 self.payload({"summary": "blocked"}, "SAFETY"),
                 {"promptFeedback": {"blockReason": "SAFETY"}}, [],
                 {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "not json"}]}}]}]
        for payload in cases:
            opener = Mock()
            opener.open.return_value = io.BytesIO(json.dumps(payload).encode())
            with self.subTest(payload=payload), patch.object(client.urllib.request, "build_opener", return_value=opener):
                with self.assertRaises(client.ModelServiceError) as caught:
                    self.call()
                self.assertEqual(caught.exception.code, "invalid_output")
                self.assertFalse(client.model_health()["ready"])

    def test_quota_failure_never_retries_or_uses_gateway_and_does_not_echo_secrets(self):
        for status, code in ((403, "authentication"), (429, "rate_limited"),
                             (402, "billing_required"), (404, "model_configuration"),
                             (503, "upstream_unavailable")):
            opener = Mock()
            opener.open.side_effect = urllib.error.HTTPError("https://generativelanguage.googleapis.com/", status, "error", {},
                io.BytesIO(b'{"error":{"message":"private-google-key private prompt"}}'))
            with self.subTest(status=status), \
                 patch.object(client.urllib.request, "build_opener", return_value=opener), \
                 patch.object(client, "_call_gateway") as gateway:
                with self.assertRaises(client.ModelServiceError) as caught:
                    self.call()
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn("private-google-key", str(caught.exception))
                self.assertNotIn("private prompt", json.dumps(client.model_health()))
                opener.open.assert_called_once()
                gateway.assert_not_called()

    def test_model_name_cannot_change_the_endpoint_or_add_a_query(self):
        with patch.object(client, "AI_MODEL", "gemini-x?key=secret"), \
             patch.object(client.urllib.request, "build_opener") as opener:
            with self.assertRaises(client.ModelServiceError):
                self.call()
            opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
