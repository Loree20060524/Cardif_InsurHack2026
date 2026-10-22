from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from regintel.application import regulatory_qa as qa
from regintel.application import scenario_consultation as scenarios
from regintel.domain.knowledge_search import KnowledgeIndex
from regintel.domain.scenario_sops import matching_demo_sops
from regintel.web import Handler
from tests.evidence_fixtures import with_review_replies


TEXT = "保險業處理個人資料應確認使用目的，並建立資料存取權限與查核紀錄。"
FILTERS = {"type": "全部", "date_from": "", "date_to": ""}


def index():
    return KnowledgeIndex([{
        "document_id": "law:privacy", "title": "測試用個人資料規範", "text": TEXT,
        "url": "https://law.fsc.gov.tw/test", "source": "官方法規原文", "date": "2026-01-01",
        "date_label": "修正／公布日期", "type": "法規", "version_note": "測試資料，不作為實際法規",
    }])


def plan(**changes):
    return {"summary": "員工想將客戶名單交給合作廠商。", "search_queries": ["個人資料 使用目的 存取權限"], "follow_up_questions": [], **changes}


def answer():
    citation = {"source_id": "S1", "quote": TEXT}
    return {"facts": [citation], "inferences": [{"text": "本情境可先確認資料使用目的與權限安排。", "source_ids": ["S1"]}],
            "next_steps": [{"text": "先整理預計提供資料的使用目的，供權責人員核對。", "source_ids": ["S1"]}], "missing_information": []}


class ScenarioConsultationTests(unittest.TestCase):
    def consult(self, body, outputs):
        with patch.object(qa, "knowledge_index", return_value=index()), patch.object(qa, "call_ollama_structured_json", side_effect=with_review_replies(outputs)) as model:
            result = qa.answer_regulatory_question({"mode": "scenario", "question": "想把客戶名單交給廠商", **body})
        return result, model

    def test_unified_entry_answers_a_direct_law_question_without_requiring_a_work_scenario(self):
        question = "個人資料使用目的有哪些規定？"
        with patch.object(qa, "knowledge_index", return_value=index()), patch.object(qa, "call_ollama_structured_json", side_effect=with_review_replies([plan(summary=question), answer()])) as model:
            result = qa.answer_regulatory_question({"mode": "auto", "question": question, "history": []})
        self.assertEqual(result["mode"], "auto")
        self.assertEqual(result["status"], "answered")
        self.assertNotIn("scenario", result)
        self.assertEqual(result["conversation"]["follow_up_questions"], [])
        self.assertEqual(result["conversation"]["turn"], 1)
        self.assertEqual(model.call_count, 3)

    def test_unified_followup_passes_prior_question_and_new_conditions_to_the_agent(self):
        history = [{"question": "個人資料使用目的有哪些規定？", "follow_up_questions": []}]
        with patch.object(qa, "knowledge_index", return_value=index()), patch.object(qa, "call_ollama_structured_json", side_effect=with_review_replies([plan(), answer()])) as model:
            result = qa.answer_regulatory_question({"mode": "auto", "question": "如果提供給委外廠商呢？", "history": history})
        self.assertEqual(result["conversation"]["turn"], 2)
        for call in model.call_args_list:
            self.assertIn(history[0]["question"], call.kwargs["input_text"])
            self.assertIn("如果提供給委外廠商呢", call.kwargs["input_text"])

    def test_later_scope_correction_overrides_an_earlier_exclusion(self):
        self.assertTrue(scenarios._domestic_only("資料不傳境外。\n只用於既有保戶服務。"))
        self.assertFalse(scenarios._domestic_only("資料不傳境外。\n更正：資料會傳往境外。"))
        self.assertTrue(scenarios._domestic_only("資料可能傳境外。\n確認後改成不傳境外。"))

    def test_clarification_never_generates_applicability_claims(self):
        result, model = self.consult({}, [plan(follow_up_questions=["廠商將如何使用這份資料？"])])
        self.assertEqual(result["status"], "clarify")
        self.assertEqual(model.call_count, 1)
        self.assertEqual(result["sources"], [])
        self.assertEqual(result["claims"], [])
        self.assertEqual(result["scenario"]["next_steps"], [])
        self.assertNotIn("sops", result["scenario"])

    def test_followup_keeps_original_facts_and_prior_questions(self):
        history = [{"question": "想把客戶名單交給廠商", "follow_up_questions": ["資料內容與使用目的為何？"]}]
        result, model = self.consult({"question": "只有聯絡電話，用於既有保戶服務", "history": history}, [plan(), answer()])
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["scenario"]["turn"], 2)
        self.assertEqual(model.call_count, 3)
        for call in model.call_args_list[:2]:
            self.assertIn("想把客戶名單交給廠商", call.kwargs["input_text"])
            self.assertIn("資料內容與使用目的為何", call.kwargs["input_text"])
            self.assertIn("只有聯絡電話", call.kwargs["input_text"])
        self.assertEqual(result["sources"][0]["url"], "https://law.fsc.gov.tw/test")
        self.assertEqual(result["scenario"]["next_steps"][0]["citations"][0]["quote"], TEXT)

    def test_repeated_planner_questions_do_not_block_retrieval_after_employee_replies(self):
        history = [{"question": "想把客戶名單交給廠商", "follow_up_questions": ["用途為何？"]}]
        result, model = self.consult({"question": "提醒既有保戶繳費", "history": history},
            [plan(follow_up_questions=["使用目的具體說明"]), answer()])
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["scenario"]["follow_up_questions"], [])
        self.assertEqual(model.call_count, 3)

    def test_semantic_search_queries_find_evidence_without_changing_citations(self):
        result, _ = self.consult({"question": "這件事可以交出去嗎？"}, [plan(), answer()])
        self.assertEqual([s["source_id"] for s in result["sources"]], ["S1"])
        self.assertEqual(result["claims"][0]["text"], TEXT)
        self.assertNotIn("sops", result["scenario"])

    def test_fabricated_next_step_citation_is_dropped(self):
        output = answer()
        output["next_steps"][0]["source_ids"] = ["S999"]
        result, _ = self.consult({}, [plan(), output])
        self.assertEqual(result["scenario"]["next_steps"], [])
        self.assertTrue(any("已省略" in item for item in result["missing_information"]))

    def test_suggestions_cannot_use_a_source_whose_quote_failed_validation(self):
        output = answer()
        output["facts"][0]["quote"] = "這段文字並沒有出現在提供的官方來源之中。"
        result, _ = self.consult({}, [plan(), output])
        self.assertEqual(result["status"], "insufficient")
        self.assertEqual(result["claims"], [])
        self.assertEqual(result["scenario"]["next_steps"], [])

    def test_foreign_branch_excerpt_is_not_applied_to_explicitly_domestic_scenario(self):
        foreign = "保險業將其國外分支機構符合當地法令規定之作業項目中，無涉本國客戶個人資料之部分委外辦理。"
        ix = index()
        ix.chunks[0]["text"] = foreign
        output = answer()
        output["facts"][0]["quote"] = foreign
        with patch.object(qa, "knowledge_index", return_value=ix), patch.object(qa, "call_ollama_structured_json", side_effect=[plan(), output]) as model:
            result = qa.answer_regulatory_question({"mode": "scenario", "question": "廠商在台灣境內，客戶資料不傳境外，請查委外規範"})
        self.assertEqual(result["claims"], [])
        self.assertEqual(result["scenario"]["next_steps"], [])
        self.assertEqual(result["sources"], [])
        self.assertEqual(model.call_count, 1)
        self.assertTrue(any("缺少" in text for text in result["missing_information"]))

    def test_negated_sales_activity_does_not_select_sales_sop(self):
        sops = matching_demo_sops("客戶名單提供廠商續期繳費提醒，不進行商品銷售、不做招攬，也不行銷。")
        self.assertEqual([sop["id"] for sop in sops], ["demo-data-sharing"])

    def test_domestic_scenario_does_not_reask_or_recommend_foreign_only_arrangements(self):
        output = answer()
        output["next_steps"] = [{"text": "確認境外受託機構是否完成登錄。", "source_ids": ["S1"]}]
        output["missing_information"] = ["資料是否會交境外機構處理？", "資料提供用途是否已確認？"]
        result, _ = self.consult({"question": "廠商在台灣，資料不傳境外，想查委外個資規範。"}, [plan(), output])
        self.assertEqual(result["scenario"]["next_steps"], [])
        self.assertNotIn("資料是否會交境外機構處理？", result["missing_information"])
        self.assertIn("資料提供用途是否已確認？", result["missing_information"])
        self.assertTrue(any(claim["kind"] == "inference" for claim in result["claims"]))

    def test_guidance_cannot_add_an_article_number_absent_from_quoted_evidence(self):
        quote = "委託他人處理個人資料時，對受託人依本法施行細則第八條規定為適當之監督。"
        citation = {"source_id": "S1", "quote": quote}
        claims, dropped = scenarios._checked_guidance([
            {"text": "應符合個人資料保護法第21條之監督要求。", "source_ids": ["S1"]},
            {"text": "可依摘錄所述施行細則第8條核對監督安排。", "source_ids": ["S1"]},
        ], {"S1": [citation]}, [{"source_id": "S1", "text": quote}], "委外情境")
        self.assertEqual(dropped, 1)
        self.assertEqual(len(claims), 1)
        self.assertIn("第8條", claims[0]["text"])

    def test_no_evidence_returns_data_gap_without_demo_sop_or_invented_law(self):
        result, model = self.consult({"filters": {**FILTERS, "date_from": "2099-01-01"}}, [plan()])
        self.assertEqual(result["status"], "insufficient")
        self.assertEqual(result["claims"], [])
        self.assertNotIn("sops", result["scenario"])
        self.assertEqual(model.call_count, 1)
        self.assertIn("缺少", result["missing_information"][0])

    def test_combined_searches_deduplicate_passages_and_keep_document_diversity(self):
        class FakeIndex:
            def search(self, query, _filters):
                return [{"document_id": key, "passage": number, "type": kind} for key, number, kind in {
                    "first": [("case", 1, "裁罰"), ("law:a", 1, "法規"), ("law:a", 2, "法規")],
                    "second": [("law:a", 1, "法規"), ("law:a", 3, "法規"), ("law:b", 1, "法規")],
                }.get(query, [])]
        sources = scenarios.scenario_sources(FakeIndex(), ["first", "second"], FILTERS)
        self.assertEqual([s["document_id"] for s in sources], ["law:a", "law:a", "law:b", "case"])
        self.assertEqual([s["source_id"] for s in sources], ["S1", "S2", "S3", "S4"])

    def test_scope_filter_retains_general_evidence_and_reassigns_source_ids(self):
        class FakeIndex:
            def search(self, _query, _filters):
                return [
                    {"document_id": "law:foreign", "passage": 1, "type": "法規", "text": "保險業委託境外機構處理之作業事項。"},
                    {"document_id": "law:general", "passage": 1, "type": "法規", "text": TEXT},
                ]
        sources = scenarios.scenario_sources(FakeIndex(), ["個人資料 委外"], FILTERS, "資料只在台灣使用，不傳境外。")
        self.assertEqual([source["document_id"] for source in sources], ["law:general"])
        self.assertEqual(sources[0]["source_id"], "S1")

    def test_invalid_history_mode_and_turn_limit_fail_before_generation(self):
        for history in (None, "text", [{}], [{"question": "a"}], [{"question": "合法長度", "follow_up_questions": [123]}],
                        [{"question": "合法長度"}] * 6):
            with self.subTest(history=history), patch.object(qa, "call_ollama_structured_json") as model:
                with self.assertRaises(ValueError):
                    qa.answer_regulatory_question({"mode": "scenario", "question": "工作情境", "history": history})
                model.assert_not_called()
        for mode in ([], "unknown", None):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                qa.answer_regulatory_question({"mode": mode, "question": "工作情境"})

    def test_generation_failure_releases_shared_lock_and_busy_does_not_call_model(self):
        with patch.object(qa, "call_ollama_structured_json", side_effect=RuntimeError("offline")):
            with self.assertRaises(RuntimeError):
                qa.answer_regulatory_question({"mode": "scenario", "question": "工作情境"})
        self.assertTrue(qa._generation_lock.acquire(blocking=False))
        try:
            with patch.object(qa, "call_ollama_structured_json") as model, self.assertRaises(qa.QABusyError):
                qa.answer_regulatory_question({"mode": "scenario", "question": "工作情境"})
            model.assert_not_called()
        finally:
            qa._generation_lock.release()

    def test_http_unified_and_legacy_requests_support_followup_and_reject_invalid_history(self):
        class QuietHandler(Handler):
            def log_message(self, *_args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        def post(body):
            request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/api/regulatory-qa",
                data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=5) as response:
                return json.load(response)["answer"]
        try:
            for mode in ("auto", "scenario"):
                context_key = "conversation" if mode == "auto" else "scenario"
                with self.subTest(mode=mode), patch.object(qa, "knowledge_index", return_value=index()), patch.object(qa, "call_ollama_structured_json", side_effect=with_review_replies([plan(follow_up_questions=["用途為何？"]), plan(), answer()])):
                    first = post({"mode": mode, "question": "客戶名單交給廠商"})
                    second = post({"mode": mode, "question": "保戶聯繫服務", "history": [{"question": first["question"], "follow_up_questions": first[context_key]["follow_up_questions"]}]})
                    self.assertEqual(first["status"], "clarify")
                    self.assertEqual(second["status"], "answered")
                    self.assertEqual(second["mode"], mode)
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        post({"mode": mode, "question": "工作情境", "history": "bad"})
                    self.assertEqual(error.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
