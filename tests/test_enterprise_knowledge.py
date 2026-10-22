from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from regintel.application import enterprise_knowledge as enterprise
from regintel.application import regulatory_qa as qa
from regintel.domain.enterprise_knowledge import CATEGORIES, DOCUMENTS, search_documents
from regintel.web import Handler


class EnterpriseKnowledgeTests(unittest.TestCase):
    def test_everyday_questions_retrieve_the_correct_company_knowledge(self):
        examples = [("要把客戶名單交給外包廠商，該找哪些 SOP 與表單？", {"data-sharing", "data-request-form"}),
                    ("新人接到理賠補件詢問，要去哪裡找指引？", {"claims-intake", "claims-form", "new-starter"}),
                    ("忘記公司帳號密碼，應該怎麼辦？", {"account-faq"}),
                    ("在家 VPN 連不上，先檢查什麼？", {"vpn-faq"})]
        for question, expected in examples:
            with self.subTest(question=question):
                sources = search_documents(question)
                self.assertTrue(sources)
                self.assertIn(sources[0]["id"], expected)
                self.assertTrue(all(source["url"].startswith("/api/enterprise-knowledge/document?id=") for source in sources))

    def test_password_question_prioritizes_reset_guidance_without_unrelated_vpn_faq(self):
        sources = search_documents("忘記公司帳號密碼，應該怎麼處理？", "IT 支援")
        self.assertEqual(sources[0]["section"], "忘記密碼或帳號鎖定")
        self.assertIn("使用忘記密碼或帳號解鎖功能", sources[0]["text"])
        self.assertTrue(all(source["id"] == "account-faq" for source in sources))

    def test_category_filter_and_form_download_use_real_documents(self):
        sources = search_documents("客戶資料提供要用哪張表單？", "表單")
        self.assertTrue(sources)
        self.assertTrue(all(source["category"] == "表單" for source in sources))
        filename, text = enterprise.document_text(sources[0]["id"])
        self.assertTrue(filename.endswith("_示範.txt"))
        self.assertIn("自建示範", text)
        self.assertIn("＿＿＿＿", text)
        for source in sources:
            self.assertIn(source["section_id"], enterprise.document_html(source["id"]))

    def test_unrelated_question_does_not_call_a_model_or_fabricate_company_rules(self):
        with patch.object(qa, "call_structured_json") as model:
            result = enterprise.answer({"question": "明天台北天氣及火星人口有多少"})
        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["sources"], [])
        model.assert_not_called()

    def test_ai_answer_retrieves_only_internal_documents_and_checks_each_quote(self):
        body = {"question": "忘記公司密碼怎麼辦？"}
        first = enterprise.search(body)["sources"][0]
        output = {"points": [{"text": "可先從正式登入入口使用忘記密碼功能，依文件確認後續處理。", "source_id": "K1", "quote": first["text"][:60]}], "steps": [], "follow_up_questions": []}
        with patch.object(qa, "knowledge_index", side_effect=AssertionError("must not search official regulations")), patch.object(qa, "call_structured_json", return_value=output) as model:
            result = enterprise.answer(body)
        self.assertEqual(result["status"], "answered")
        self.assertEqual(len(result["points"]), 1)
        self.assertEqual(result["points"][0]["citations"][0]["quote"], first["text"][:60])
        self.assertEqual(model.call_args.kwargs["request_timeout"], 45)
        self.assertEqual(model.call_args.kwargs["max_output_tokens"], 900)
        self.assertEqual(model.call_args.kwargs["context_window"], 4096)

    def test_invented_sources_or_quotes_never_appear_as_an_ai_answer(self):
        for source_id, quote in (("K999", "虛構文件中的句子並不是知識庫的原文。"), ("K1", "虛構文件中的句子並不是知識庫的原文。")):
            with self.subTest(source_id=source_id), patch.object(qa, "call_structured_json", return_value={"points": [{"text": "虛構公司規定", "source_id": source_id, "quote": quote}]}):
                result = enterprise.answer({"question": "忘記公司密碼怎麼辦？"})
            self.assertEqual(result["status"], "documents_only")
            self.assertEqual(result["points"], [])
            self.assertTrue(result["sources"])

    def test_model_failure_or_busy_state_preserves_the_search_results(self):
        with patch.object(qa, "call_structured_json", side_effect=TimeoutError()):
            result = enterprise.answer({"question": "VPN連不上"})
        self.assertEqual(result["status"], "documents_only")
        self.assertTrue(result["sources"])
        self.assertTrue(qa._generation_lock.acquire(blocking=False))
        try:
            with patch.object(qa, "call_structured_json") as model:
                result = enterprise.answer({"question": "VPN連不上"})
            self.assertEqual(result["status"], "documents_only")
            model.assert_not_called()
        finally:
            qa._generation_lock.release()

    def test_validation_and_catalog_cover_the_theme_four_knowledge_types(self):
        self.assertEqual(set(enterprise.catalog()["categories"]), set(CATEGORIES))
        self.assertEqual(len(enterprise.catalog()["documents"]), len(DOCUMENTS))
        for body in ({}, {"question": "a"}, {"question": "x" * 501}, {"question": "查詢密碼", "category": "官方裁罰"}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                enterprise.search(body)
        with self.assertRaises(ValueError):
            enterprise.document_html("../../secrets")

    def test_http_search_document_and_download(self):
        class QuietHandler(Handler):
            def log_message(self, *_args): pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            request = urllib.request.Request(base + "/api/enterprise-knowledge/search", data=json.dumps({"question": "VPN連不上"}).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=5) as response:
                source = json.load(response)["result"]["sources"][0]
            with urllib.request.urlopen(base + source["url"], timeout=5) as response:
                self.assertIn("VPN", response.read().decode())
            with urllib.request.urlopen(base + source["download_url"], timeout=5) as response:
                self.assertIn("attachment", response.headers["Content-Disposition"])
                self.assertIn("自建示範", response.read().decode("utf-8-sig"))
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(base + "/api/enterprise-knowledge/document?id=missing", timeout=5)
            self.assertEqual(error.exception.code, 404)
        finally:
            server.shutdown(); server.server_close(); worker.join(timeout=5)


if __name__ == "__main__": unittest.main()
