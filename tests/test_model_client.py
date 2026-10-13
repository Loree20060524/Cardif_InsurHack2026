"""Cloud contract, redaction, provider isolation, and observed readiness."""

import io
import json
import time
import unittest
import urllib.error
from unittest.mock import Mock, patch

from regintel.application import ai_support, management_summary
from regintel.infrastructure import model_client as client


SCHEMA = {"type": "object", "properties": {"summary": {"type": "string"}},
          "required": ["summary"], "additionalProperties": False}


class ModelClientTests(unittest.TestCase):
    def setUp(self):
        for patcher in (
            patch.object(client, "AI_PROVIDER", "vercel_gateway"),
            patch.object(client, "AI_MODEL", "alibaba/qwen-3-14b"),
            patch.object(client, "get_store", return_value=None),
            patch.dict(client.os.environ, {"VERCEL_OIDC_TOKEN": "test-oidc-secret"}, clear=True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        with client._status_lock:
            client._last_status.clear()

    def call(self):
        return client.call_structured_json(instructions="Only public sources.",
                                          input_text="官方監理資料", schema=SCHEMA,
                                          context_window=16384)

    def completion(self, result=None, finish="stop"):
        return {"choices": [{"finish_reason": finish, "message": {
            "content": json.dumps(result if result is not None else {"summary": "官方資料摘要"}),
        }}], "usage": {"prompt_tokens": 100, "completion_tokens": 30}}

    def open_payload(self, payload):
        opener = Mock()
        opener.open.return_value = io.BytesIO(json.dumps(payload).encode())
        return patch.object(client.urllib.request, "build_opener", return_value=opener), opener

    def test_cloud_request_uses_oidc_strict_schema_and_bounded_output(self):
        patched, opener = self.open_payload(self.completion())
        with patched:
            result = self.call()
        request = opener.open.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(request.full_url, client.GATEWAY_URL)
        self.assertEqual(request.get_header("Authorization"), "Bearer test-oidc-secret")
        self.assertEqual(body["response_format"]["json_schema"]["schema"], SCHEMA)
        self.assertTrue(body["response_format"]["json_schema"]["strict"])
        self.assertEqual(body["reasoning"], {"effort": "none"})
        self.assertEqual(body["max_tokens"], client.AI_GATEWAY_MAX_TOKENS)
        self.assertNotIn("providerOptions", body)  # No different-model/paid fallback.
        self.assertNotIn("options", body)  # Ollama's num_ctx must not reach Gateway.
        self.assertEqual(result["_model_timing"]["input_tokens"], 100)
        self.assertTrue(client.model_health()["ready"])

    def test_oidc_is_read_again_on_each_request(self):
        patched, opener = self.open_payload(self.completion())
        with patched:
            self.call()
        with patch.dict(client.os.environ, {"VERCEL_OIDC_TOKEN": "refreshed-oidc"}):
            patched, opener = self.open_payload(self.completion())
            with patched:
                self.call()
        self.assertEqual(opener.open.call_args.args[0].get_header("Authorization"), "Bearer refreshed-oidc")

    def test_api_key_fallback_and_missing_credentials_never_call_network(self):
        with patch.dict(client.os.environ, {"VERCEL_OIDC_TOKEN": "", "AI_GATEWAY_API_KEY": "test-api-key"}):
            self.assertEqual(client._credential(), "test-api-key")
        with patch.dict(client.os.environ, {}, clear=True), patch.object(client.urllib.request, "build_opener") as opener:
            with self.assertRaises(client.ModelServiceError) as caught:
                self.call()
            self.assertEqual(caught.exception.code, "missing_credentials")
            opener.assert_not_called()
            self.assertFalse(client.model_health()["ready"])

    def test_invalid_and_incomplete_results_cannot_be_marked_ready(self):
        for payload in (self.completion({}, "stop"), self.completion({"summary": 1}),
                        self.completion({"summary": "partial"}, "length"),
                        self.completion({"summary": "text", "secret": "unexpected"}),
                        [], {"choices": [{}]}):
            with self.subTest(payload=payload):
                patched, _ = self.open_payload(payload)
                with patched, self.assertRaises(client.ModelServiceError) as caught:
                    self.call()
                self.assertEqual(caught.exception.code, "invalid_output")
                self.assertFalse(client.model_health()["ready"])

    def test_gateway_errors_are_actionable_and_never_echo_upstream_secrets(self):
        for status, upstream_code, expected in (
            (401, "invalid_api_key", "authentication"),
            (403, "customer_verification_required", "verification_required"),
            (403, "forbidden", "access_denied"), (402, "insufficient_funds", "quota_exhausted"),
            (429, "rate_limit", "rate_limited"), (400, "bad_schema", "model_configuration"),
            (503, "overloaded", "upstream_unavailable"),
        ):
            raw = json.dumps({"error": {"code": upstream_code, "message": "test-oidc-secret private prompt"}}).encode()
            error = urllib.error.HTTPError(client.GATEWAY_URL, status, "upstream", {}, io.BytesIO(raw))
            opener = Mock()
            opener.open.side_effect = error
            with self.subTest(status=status), patch.object(client.urllib.request, "build_opener", return_value=opener):
                with self.assertRaises(client.ModelServiceError) as caught:
                    self.call()
                self.assertEqual(caught.exception.code, expected)
                self.assertNotIn("test-oidc-secret", str(caught.exception))
                self.assertNotIn("private prompt", json.dumps(client.model_health()))
                self.assertFalse(client.model_health()["ready"])
                opener.open.assert_called_once()

    def test_timeouts_and_redirects_do_not_leak_credentials(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.URLError("private secret endpoint")
        with patch.object(client.urllib.request, "build_opener", return_value=opener), self.assertRaises(client.ModelServiceError) as caught:
            self.call()
        self.assertNotIn("private secret", str(caught.exception))
        with self.assertRaises(client.ModelServiceError):
            client._NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example")

    def test_response_size_limit_is_enforced(self):
        opener = Mock()
        opener.open.return_value = io.BytesIO(b"x" * (client.GATEWAY_RESPONSE_LIMIT + 10))
        with patch.object(client.urllib.request, "build_opener", return_value=opener), self.assertRaises(client.ModelServiceError):
            self.call()

    def test_token_presence_alone_and_stale_or_other_model_status_are_not_ready(self):
        self.assertEqual(client.model_health()["status"], "unverified")
        for age, model in ((90000, client.AI_MODEL), (0, "another/model")):
            client._last_status.update(provider="vercel_gateway", model=model,
                                       status="verified", checked_epoch=time.time() - age)
            self.assertFalse(client.model_health()["ready"])

    def test_observed_result_is_merged_and_loaded_across_instances(self):
        saved = {"analyses": {"existing": {"summary": "retain"}}, "management": {"selected": {"summary": "retain"}}}
        with patch.object(client, "get_store", return_value=object()), \
             patch.object(client, "load_json_file", side_effect=lambda _: dict(saved)), \
             patch.object(client, "document_transaction"), \
             patch.object(client, "atomic_write_json", side_effect=lambda _, value: saved.update(value)):
            client._record_status("verified")
            client._last_status.clear()  # A different function instance.
            self.assertTrue(client.model_health()["ready"])
            self.assertIn("existing", saved["analyses"])
            self.assertIn("selected", saved["management"])
            client._record_status("unavailable", "quota_exhausted", "額度不足")
            self.assertFalse(client.model_health()["ready"])

    def test_local_mode_preserves_ollama_context_and_timings(self):
        with patch.object(client, "AI_PROVIDER", "ollama"), \
             patch.object(client, "call_ollama_structured_json", return_value={"summary": "local", "_ollama_timing": {"load_seconds": 1}}) as local, \
             patch.object(client, "_call_gateway") as cloud:
            result = self.call()
            self.assertEqual(local.call_args.kwargs["context_window"], 16384)
            self.assertEqual(result["_model_timing"]["load_seconds"], 1)
            cloud.assert_not_called()

    def test_cloud_and_local_provider_caches_are_isolated_even_for_same_model(self):
        events = [{"id": "same", "description": "same public source"}]
        for module, key in ((ai_support, lambda: ai_support.ai_event_cache_key(events[0])),
                            (management_summary, lambda: management_summary.management_cache_key(events))):
            with patch.object(module, "AI_MODEL", "same/model"), patch.object(module, "AI_THINK", False):
                with patch.object(module, "AI_PROVIDER", "ollama"):
                    local = key()
                with patch.object(module, "AI_PROVIDER", "vercel_gateway"):
                    cloud = key()
            self.assertNotEqual(local, cloud)


if __name__ == "__main__":
    unittest.main()
