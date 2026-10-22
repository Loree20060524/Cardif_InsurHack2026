from __future__ import annotations

import json
import unittest
from unittest.mock import Mock, patch

from regintel.application import evidence_review as review
from regintel.application import regulatory_qa as qa
from regintel.application import management_summary as summaries
from regintel.domain.knowledge_search import KnowledgeIndex
from tests.evidence_fixtures import supported_review_reply


TEXT = "測試規範要求資料提供前確認使用目的；未經核准，不得提供資料。但已依法公開的資訊不在此限。"
SOURCES = [{"source_id": "S1", "document_id": "law:test", "title": "測試規範", "text": TEXT, "type": "法規",
            "url": "https://example.com/law", "date": "2026-01-01", "date_label": "修正日", "version_note": "測試資料"}]


def claim(text="提供前需確認使用目的。"):
    return {"kind": "inference", "text": text, "citations": [{"source_id": "S1", "quote": TEXT}]}


def verdict(status="supported", **changes):
    return {"checks": [{"id": "0", "status": status, "reason": "測試核對結果。",
                        "evidence_ids": ["E1"], **changes}]}


class EvidenceReviewTests(unittest.TestCase):
    def test_review_sees_full_context_and_keeps_supported_statement_with_bound_evidence(self):
        model = Mock(return_value=verdict())
        kept, result = review.review_cited_claims([claim()], SOURCES, context="假設資料交給廠商。", model=model)
        self.assertEqual(len(kept), 1)
        material = json.loads(model.call_args.kwargs["input_text"])
        self.assertIn("但已依法公開", material["sources"][0]["text"])
        self.assertEqual(result["supported"], 1)
        self.assertEqual(kept[0]["support_review"]["method"], "model_review")

    def test_real_quote_does_not_save_a_contradicted_or_only_partly_supported_conclusion(self):
        for status in ("contradicted", "insufficient"):
            with self.subTest(status=status):
                kept, result = review.review_cited_claims([claim("不需任何核准即可提供所有資料。")], SOURCES, context="", model=Mock(return_value=verdict(status)))
                self.assertEqual(kept, [])
                self.assertEqual(result["withheld"], 1)

    def test_missing_duplicate_unknown_and_malformed_judgments_fail_closed(self):
        for output in ({}, {"checks": []}, {"checks": verdict()["checks"] * 2}, verdict("uncertain"), verdict([]), verdict({}),
                       verdict(evidence_ids=[]), verdict(evidence_ids=["E99"]),
                       verdict(evidence_ids="E1"), verdict(evidence_ids=[[]])):
            with self.subTest(output=output):
                kept, result = review.review_cited_claims([claim()], SOURCES, context="", model=Mock(return_value=output))
                self.assertEqual(kept, [])
                self.assertEqual(result["unverified"], 1)

    def test_model_failure_does_not_publish_unreviewed_claims_or_leak_diagnostics(self):
        kept, result = review.review_cited_claims([claim()], SOURCES, context="", model=Mock(side_effect=RuntimeError("private diagnostic")))
        self.assertEqual(kept, [])
        self.assertEqual(result["unverified"], 1)
        self.assertNotIn("private diagnostic", json.dumps(result))

    def test_empty_and_oversized_reviews_never_call_model(self):
        model = Mock()
        _, empty = review.review_cited_claims([], SOURCES, context="", model=model)
        _, large = review.review_cited_claims([claim()], [{**SOURCES[0], "text": TEXT * 500}], context="", model=model)
        model.assert_not_called()
        self.assertEqual(empty["requested"], 0)
        self.assertEqual(large["unverified"], 1)

    def test_money_rule_rejects_false_total_even_if_model_would_approve(self):
        text = "針對4家金融機構，總罰鍰達新臺幣4,000萬元。甲被罰960萬元；乙被罰1,200萬元；丙被罰400萬元；丁被罰800萬元。"
        model = Mock(return_value=verdict())
        _, result = review.review_cited_claims([claim(text)], [{**SOURCES[0], "text": text}], context="", model=model)
        model.assert_not_called()
        self.assertEqual(result["checks"][0]["method"], "numeric_rule")
        self.assertEqual(result["checks"][0]["status"], "contradicted")
        self.assertEqual(review.numeric_issue(text.replace("4,000", "3,360"), text), "")
        self.assertEqual(review.numeric_issue("總計30萬元，其中甲被罰10萬元，乙被罰5萬元。", "總計30萬元，甲被罰10萬元，乙被罰5萬元。"), "")

    def test_review_evidence_cannot_switch_to_an_uncited_document(self):
        sources = SOURCES + [{**SOURCES[0], "source_id": "S2"}]
        kept, result = review.review_cited_claims([claim()], sources, context="", model=Mock(return_value=verdict(evidence_ids=["E2"])))
        self.assertEqual(kept, [])
        self.assertEqual(result["unverified"], 1)

    def test_conditional_consent_cannot_be_strengthened_to_a_universal_prerequisite(self):
        source = "資料蒐集須具有特定目的及法定情形；其經當事人同意者，並應確保符合本法第七條之規定。"
        text = "經當事人同意後，才能進行非行銷用途的資料處理。"
        model = Mock(return_value=verdict())
        kept, result = review.review_cited_claims([claim(text)], [{**SOURCES[0], "text": source}], context="", model=model)
        self.assertEqual(kept, [])
        self.assertEqual(result["checks"][0]["method"], "condition_rule")
        model.assert_not_called()
        self.assertEqual(review.condition_issue(text, source + "提供前應取得當事人同意。"), "")
        self.assertEqual(review.condition_issue("若以當事人同意為依據，應確認同意範圍。", source), "")
        self.assertEqual(review.condition_issue("經當事人同意者，應確認同意範圍。", source), "")

    def test_article_in_an_unrelated_clause_does_not_support_binding_a_contract_obligation(self):
        source = "資料蒐集應符合本法第十九條規定。" + "確認使用目的及適用範圍。" * 15 + "對受託人依本法施行細則第八條為監督，並於委託契約明確約定其內容。"
        text = "應於委託契約明確約定處理內容，以符合本法第十九條。"
        self.assertTrue(review.condition_issue(text, source))
        self.assertEqual(review.condition_issue("依第八條核對委託契約。", source), "")

    def test_question_pipeline_withholds_reversed_conclusion_and_retains_literal_source(self):
        index = Mock(document_count=1)
        index.search.return_value = SOURCES
        generated = {"facts": [{"source_id": "S1", "quote": TEXT}], "inferences": [claim("資料可直接提供，不須核准。")], "missing_information": []}
        with patch.object(qa, "knowledge_index", return_value=index), patch.object(qa, "call_ollama_structured_json", side_effect=[generated, verdict("contradicted")]):
            result = qa.answer_regulatory_question({"question": "資料提供要先核准嗎？"})
        self.assertEqual([item["kind"] for item in result["claims"]], ["fact"])
        self.assertEqual(result["claims"][0]["text"], TEXT)
        self.assertTrue(any("未獲原文" in note for note in result["missing_information"]))

    def test_management_summary_removes_unsupported_fields_and_preserves_every_selected_source(self):
        events = [{"id": "e1", "title": "測試公告", "description": TEXT, "url": "https://example.com/law"}]
        original = summaries._normalize_summary({"headline": "所有資料均可提供", "summary": "無須核准，且免保存紀錄。", "priority_actions": ["新增五層核准流程。"]}, events)
        def model(**kwargs):
            data = json.loads(kwargs["input_text"])
            return {"checks": [{"id": item["id"], "status": "insufficient", "reason": "原文未支持。", "evidence_ids": []} for item in data["statements"]]}
        with patch.object(summaries, "call_ollama_structured_json", side_effect=model):
            result = summaries.review_management_summary(original, events)
        self.assertNotIn("無須核准", result["summary"])
        self.assertEqual(result["priority_actions"], [])
        self.assertEqual(result["risk_outlook"], "待確認")
        self.assertEqual(result["source_events"][0]["id"], "e1")

    def test_unified_scenario_reviews_inferences_and_next_steps_together(self):
        index = Mock(document_count=1)
        index.search.return_value = [{**SOURCES[0], "passage": 1}]
        plan = {"summary": "提供資料", "search_queries": ["資料提供"], "follow_up_questions": []}
        generated = {"facts": [{"source_id": "S1", "quote": TEXT}],
                     "inferences": [{"text": "不須核准即可提供未公開資料。", "source_ids": ["S1"]}],
                     "next_steps": [{"text": "填寫A-17表單並交董事長核准。", "source_ids": ["S1"]}], "missing_information": []}
        judgments = {"checks": [{"id": "0", "status": "contradicted", "reason": "與原文相反。", "evidence_ids": []},
                                 {"id": "1", "status": "insufficient", "reason": "原文沒有此流程。", "evidence_ids": []}]}
        with patch.object(qa, "knowledge_index", return_value=index), patch.object(qa, "call_ollama_structured_json", side_effect=[plan, generated, judgments]):
            result = qa.answer_regulatory_question({"mode": "auto", "question": "提供未公開資料要核准嗎？"})
        self.assertEqual([item["kind"] for item in result["claims"]], ["fact"])
        self.assertEqual(result["conversation"]["next_steps"], [])
        self.assertEqual(result["support_review"]["withheld"], 2)
        self.assertNotIn("_section", json.dumps(result))

    def test_unavailable_management_review_is_not_saved_to_cache(self):
        events = [{"id": "e1", "title": "測試公告", "description": TEXT}]
        def model(**kwargs):
            if "checks" in kwargs["schema"].get("properties", {}):
                raise RuntimeError("offline")
            return {"headline": "測試摘要", "summary": "資料提供前需確認使用目的。"}
        with patch.object(summaries, "_cached_summary", return_value=None), patch.object(summaries, "_save_summary") as save, patch.object(summaries, "call_ollama_structured_json", side_effect=model):
            result = summaries.generate_management_summary_ai(events)
        save.assert_not_called()
        self.assertGreater(result["support_review"]["unverified"], 0)


if __name__ == "__main__":
    unittest.main()
