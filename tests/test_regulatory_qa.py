from __future__ import annotations

import json
import threading
import tempfile
import unittest
from pathlib import Path
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from regintel.application import regulatory_qa as qa
from regintel.domain.knowledge_search import KnowledgeIndex, public_documents
from regintel.web import Handler
from tests.evidence_fixtures import supported_review_reply


def record(key="investment", text="保險業辦理投資作業應建立內部控制制度，並保存投資決策與覆核紀錄。", **changes):
    return {"id": key, "title": "保險業投資內部控制裁罰", "description": text,
            "source_key": "fsc_penalty", "source": "金管會裁罰", "published_at": "2026-10-02",
            "url": f"https://www.fsc.gov.tw/{key}", **changes}


FILTERS = {"type": "全部", "date_from": "", "date_to": ""}


class RegulatoryQATests(unittest.TestCase):
    def setUp(self):
        self.index = KnowledgeIndex(public_documents([
            record(),
            record("privacy", "保險業處理客戶個人資料，應保留存取權限核准與查核紀錄，保障消費者權益。", title="個人資料保護裁罰"),
            record("old", published_at="2024-01-01"),
        ], {}))

    def test_retrieval_finds_relevant_passages_and_expands_financial_terms(self):
        hits = self.index.search("資金運用有哪些內控缺失？", FILTERS)
        self.assertEqual(hits[0]["document_id"], "investment")
        self.assertNotIn("privacy", [item["document_id"] for item in hits])

    def test_explicit_filters_exclude_out_of_period_and_wrong_type(self):
        hits = self.index.search("投資內控", {**FILTERS, "date_from": "2026-01-01", "type": "裁罰"})
        self.assertEqual([item["document_id"] for item in hits], ["investment"])
        self.assertEqual(self.index.search("投資內控", {**FILTERS, "type": "公告"}), [])

    def test_law_index_keeps_newest_captured_version_and_version_warning(self):
        laws = {"law": [{"name": "保險業投資管理辦法", "origin": "官方法規原文", "version": value,
                          "text": text * 4, "url": "https://law.fsc.gov.tw/law"}
                         for value, text in [("2024-01-01", "舊版本規定禁止相關投資。"), ("2026-01-01", "新版本規定應保存投資紀錄。")]]}
        docs = public_documents([], laws)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["date"], "2026-01-01")
        self.assertNotIn("舊版本", docs[0]["text"])
        self.assertIn("不等同生效日", docs[0]["version_note"])

    def test_ai_generated_prose_and_placeholder_sources_are_not_evidence(self):
        docs = public_documents([record(description="金管會重要公告。請開啟官方原始來源確認完整內容。", analysis={"summary": "投資限額是百分之九十九。"}),
                                 record("safe", analysis={"summary": "投資限額是百分之九十九。"})], {})
        self.assertEqual(len(docs), 1)
        self.assertNotIn("百分之九十九", docs[0]["text"])

    def test_proposal_is_labelled_and_duplicate_records_use_more_complete_text(self):
        docs = public_documents([record(title="預告保險業投資管理辦法", description="此為預告草案，將依程序徵詢公眾意見，尚未完成法規修正發布。"),
                                 record(title="預告保險業投資管理辦法", description="此為預告草案，將依程序徵詢公眾意見，尚未完成法規修正發布。補充說明適用範圍與公開意見徵詢程序。")], {})
        self.assertEqual(len(docs), 1)
        self.assertIn("補充說明", docs[0]["text"])
        self.assertIn("不能視為已生效", docs[0]["version_note"])

    def test_late_passage_of_long_document_is_retrievable(self):
        text = "保險業應保存年度財務資料及核准紀錄。" * 150 + "特別注意量子資訊系統的設備保管規範，應保留存取紀錄供查核。"
        index = KnowledgeIndex(public_documents([record(text=text)], {}))
        self.assertIn("量子資訊", index.search("量子資訊設備", FILTERS)[0]["text"])

    def test_no_relevant_sources_does_not_call_model(self):
        with patch.object(qa, "knowledge_index", return_value=self.index), patch.object(qa, "call_ollama_structured_json") as model:
            result = qa.answer_regulatory_question({"question": "火星殖民太空船引擎", "filters": FILTERS})
        self.assertEqual(result["status"], "insufficient")
        self.assertEqual(result["claims"], [])
        model.assert_not_called()

    def test_answer_contains_only_real_passage_quotes_and_server_owned_urls(self):
        def model(**kwargs):
            if "checks" in kwargs["schema"].get("properties", {}):
                return supported_review_reply(kwargs)
            self.assertIn("不能視為已生效條文", kwargs["instructions"])
            self.assertIn("問題：投資內控", kwargs["input_text"])
            return {"facts": [
                {"source_id": "S1", "quote": "保險業辦理投資作業應建立內部控制制度"},
                {"source_id": "S99", "quote": "保險業辦理投資作業應建立內部控制制度"},
                {"source_id": "S1", "quote": "投資決策不須任何覆核或查核紀錄"},
            ], "inferences": [{"text": "推測須加強覆核。", "citations": [{"source_id": "S1", "quote": "並保存投資決策與覆核紀錄。"}]}], "missing_information": []}
        with patch.object(qa, "knowledge_index", return_value=self.index), patch.object(qa, "call_ollama_structured_json", side_effect=model):
            result = qa.answer_regulatory_question({"question": "投資內控"})
        self.assertEqual([item["kind"] for item in result["claims"]], ["fact", "inference"])
        self.assertTrue(all(source["url"].startswith("https://www.fsc.gov.tw/") for source in result["sources"]))
        self.assertTrue(any("已省略" in item for item in result["missing_information"]))

    def test_all_invalid_quotes_produce_insufficient_response(self):
        result = {"facts": [{"source_id": "S1", "quote": "官方已全面取消投資內控制度的要求"}], "inferences": []}
        with patch.object(qa, "knowledge_index", return_value=self.index), patch.object(qa, "call_ollama_structured_json", return_value=result):
            answer = qa.answer_regulatory_question({"question": "投資內控"})
        self.assertEqual(answer["status"], "insufficient")
        self.assertEqual(answer["claims"], [])

    def test_fact_display_keeps_original_exception_instead_of_model_paraphrase(self):
        sources = [{"source_id": "S1", "text": "除現行已投資者得繼續持有並依相關規定參與增資外，已無新投資項目。"}]
        result = {"facts": [{"source_id": "S1", "quote": sources[0]["text"], "text": "刪除已投資者得繼續持有的例外。"}]}
        claims, dropped = qa.checked_claims(result, sources)
        self.assertEqual(claims[0]["text"], sources[0]["text"])
        self.assertNotIn("刪除", claims[0]["text"])
        self.assertEqual(dropped, 0)

    def test_question_echo_is_not_accepted_as_an_inference(self):
        sources = [{"source_id": "S1", "text": "保險業辦理投資作業應建立內部控制制度。"}]
        question = "保險業投資內控應注意什麼？"
        result = {"inferences": [{"text": question, "citations": [{"source_id": "S1", "quote": sources[0]["text"]}]}]}
        claims, dropped = qa.checked_claims(result, sources, question)
        self.assertEqual(claims, [])
        self.assertEqual(dropped, 1)

    def test_latest_law_history_is_retained_without_old_amendments(self):
        text = "1.中華民國一百零一年修正第三條，應保存投資交易資料與帳務紀錄。 2.中華民國一百十五年修正第五條，應建立保險業投資風險管理制度。"
        docs = public_documents([record(text=text, source_key="insurance_law")], {})
        self.assertIn("一百十五年", docs[0]["text"])
        self.assertNotIn("一百零一年", docs[0]["text"])
        self.assertIn("沿革", docs[0]["version_note"])

    def test_source_updates_invalidate_in_memory_index(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = {name: Path(directory) / (name + ".json") for name in ("CACHE_FILE", "EVENT_HISTORY_FILE", "SOURCE_STORE_FILE", "LAW_VERSIONS_FILE")}
            with patch.multiple(qa, **paths), patch.object(qa, "_index", None), patch.object(qa, "_index_signature", None):
                paths["CACHE_FILE"].write_text(json.dumps({"events": [record()]}), encoding="utf-8")
                first = qa.knowledge_index()
                self.assertEqual(first.document_count, 1)
                self.assertIs(qa.knowledge_index(), first)
                paths["CACHE_FILE"].write_text(json.dumps({"events": [record(), record("new")]}), encoding="utf-8")
                self.assertEqual(qa.knowledge_index().document_count, 2)

    def test_current_shorter_source_replaces_longer_historical_text(self):
        current = "保險業最新公告已調整投資作業之內部控制措施，並要求保存重新核准後的紀錄。"
        docs = public_documents([record(text="保險業舊公告要求保留既有投資覆核紀錄與各項內控制度資料。" * 3), record(text=current)], {})
        self.assertEqual(docs[0]["text"], current)
        self.assertNotIn("舊公告", docs[0]["text"])

    def test_concurrent_question_returns_busy_without_starting_another_generation(self):
        qa._generation_lock.acquire()
        try:
            with patch.object(qa, "knowledge_index", return_value=self.index), patch.object(qa, "call_ollama_structured_json") as model:
                with self.assertRaises(qa.QABusyError):
                    qa.answer_regulatory_question({"question": "投資內控"})
                model.assert_not_called()
        finally:
            qa._generation_lock.release()

    def test_invalid_question_and_date_ranges_are_rejected(self):
        for body in ({}, {"question": ["投資"]}, {"question": "a"}, {"question": "a" * 501},
                     {"question": "投資", "filters": []}, {"question": "投資", "filters": {"type": []}},
                     {"question": "投資", "filters": {"date_from": "2026-02-30"}},
                     {"question": "投資", "filters": {"date_from": "2026-10-02", "date_to": "2026-01-01"}}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                qa.validate_question(body)

    def test_model_failure_releases_question_generation_lock(self):
        with patch.object(qa, "knowledge_index", return_value=self.index), patch.object(qa, "call_ollama_structured_json", side_effect=RuntimeError("offline")):
            with self.assertRaises(RuntimeError):
                qa.answer_regulatory_question({"question": "投資內控"})
        self.assertTrue(qa._generation_lock.acquire(blocking=False))
        qa._generation_lock.release()

    def test_http_question_endpoint_rejects_invalid_payload(self):
        class QuietHandler(Handler):
            def log_message(self, *_args):
                pass
        with patch.object(qa, "knowledge_index", return_value=self.index), patch.object(qa, "call_ollama_structured_json") as model:
            server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/api/regulatory-qa"
                request = urllib.request.Request(url, data=json.dumps({"question": "火星殖民太空船引擎"}).encode(), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request, timeout=5) as response:
                    self.assertEqual(json.load(response)["answer"]["status"], "insufficient")
                for data in (b'{}', b'[]', b'bad-json'):
                    with self.subTest(data=data), self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=5)
                    self.assertEqual(error.exception.code, 400)
                model.assert_not_called()
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
