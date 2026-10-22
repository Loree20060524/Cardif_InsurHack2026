"""Regressions observed in the three real competition demonstrations."""

import json
import unittest
from unittest.mock import patch

from regintel.application import evidence_review, event_evidence, management_summary, impact_assessment
from regintel.application.ai_support import sanitize_ai_analysis
from regintel.domain.law_comparison import comparison_evidence
from tests.evidence_fixtures import supported_review_reply


SOURCE = "退費作業未檢附付款憑證，未落實覆核；會計部通知清理懸帳。系統存在承辦與放行權限重疊，未落實職務分離。"


def approved(**kwargs):
    return supported_review_reply(kwargs)


class DemoRegressionTests(unittest.TestCase):
    def test_similar_added_and_deleted_articles_reach_model_together_under_budget(self):
        old = "充任公司負責人者應符合資格；不符合資格者，解任之。" * 3
        new = old.replace("解任之", "公司應予解任之")
        comparison = {
            "name": "測試規則", "status": "ready", "scope_note": "已保存版本",
            "before_version": {"date": "2025-01-01", "url": "https://example.com/old"},
            "after_version": {"date": "2026-01-01", "url": "https://example.com/new"},
            "changes": [
                {"article": "第 1 條", "kind": "modified", "before": "舊流程。" * 90, "after": "新流程。" * 90},
                {"article": "第 9-1 條", "kind": "added", "before": "", "after": new},
                {"article": "第 20 條", "kind": "deleted", "before": old, "after": "（刪除）"},
            ],
        }
        material = comparison_evidence([comparison], max_chars=1200)
        self.assertIn(old, material)
        self.assertIn(new, material)
        self.assertIn("移列", material)
        self.assertLessEqual(len(material), 1200)

    def test_missing_batch_judgments_can_recover_without_publishing_unchecked_text(self):
        source = {"source_id": "S1", "title": "官方裁罰", "text": SOURCE}
        statements = [{"id": str(i), "text": "可檢查退費憑證。", "source_ids": ["S1"]} for i in range(2)]

        def model(**kwargs):
            data = json.loads(kwargs["input_text"])
            if len(data["statements"]) > 1:
                return {"checks": []}
            return supported_review_reply(kwargs)

        result = evidence_review.review_statements(statements, [source], context="", model=model)
        self.assertEqual(result["supported"], 2)
        self.assertEqual(result["unverified"], 0)

    def test_refund_execution_is_not_assigned_to_legal_even_if_reviewer_approves(self):
        analysis = {"impact_processes": [{"process": "退費付款執行流程", "department": "法務", "impact": "需補齊付款憑證。"}]}
        result = event_evidence.review_event_analysis(analysis, {"title": "退費裁罰"}, SOURCE, model=approved)
        self.assertEqual(result["impact_processes"], [])

    def test_draft_cannot_publish_unconditional_compliance_actions(self):
        text = "主管機關預告修正投資辦法草案，既有投資者得依原投資比例參與增資，尚待徵詢意見。"
        analysis = {"actions": ["內部稽核部門應調整投資流程，確保符合修正後條文。"]}
        result = event_evidence.review_event_analysis(analysis, {"title": "投資辦法修正草案"}, text, model=approved)
        self.assertEqual(result["actions"], [])

    def test_conditional_prefix_does_not_turn_draft_permission_into_mandatory_capital_increase(self):
        text = "主管機關預告修正投資辦法草案，符合條件者得依原投資比例辦理增資。"
        result = event_evidence.review_event_analysis(
            {"actions": ["若公司有相關投資，則應依原比例辦理增資。"]},
            {"title": "投資辦法修正草案"}, text, model=approved)
        self.assertEqual(result["actions"], [])

    def test_optional_draft_preparation_remains_available(self):
        text = "主管機關預告修正投資辦法草案，符合條件者得依原投資比例辦理增資。"
        action = "若公司有相關投資，可先盤點持股並評估草案條件，追蹤正式發布。"
        result = event_evidence.review_event_analysis({"actions": [action]}, {"title": "投資辦法修正草案"}, text, model=approved)
        self.assertEqual(result["actions"], [action])

    def test_mixed_source_summary_checks_draft_conditions_on_actual_supporting_source(self):
        sources = [{"source_id": "S1", "text": SOURCE},
                   {"source_id": "S2", "text": "投資辦法修正草案尚在預告，符合條件者得依原投資比例辦理增資。", "is_draft": True}]
        def model(**kwargs):
            return {"checks": [{"id": "action", "status": "supported", "reason": "", "evidence_ids": ["E2"]}]}
        result = evidence_review.review_statements(
            [{"id": "action", "text": "應確保符合新修正辦法投資比例。", "source_ids": ["S1", "S2"], "kind": "recommendation"}],
            sources, context="", model=model)
        self.assertEqual(result["supported"], 0)

    def test_unknown_process_department_is_not_silently_assigned_to_legal_compliance(self):
        output = {"summary": SOURCE, "management_summary": SOURCE, "responsible_department": "法令遵循",
                  "impact_processes": [{"process": "外幣保單款項退還", "department": "國際業務部", "impact": "缺乏退還聯繫機制。"}]}
        result = sanitize_ai_analysis(output, {})
        self.assertEqual(result["impact_processes"], [])

    def test_unfilled_model_templates_are_not_published_even_when_reviewer_approves(self):
        candidate = {"departments": [{"department": "財務／會計", "reason": "若公司...可能涉及...（需填入具體作業關聯）"}],
                     "actions": ["若公司...可先檢查...（需填入可選準備）"]}
        result = event_evidence.review_event_analysis(candidate, {"title": "裁罰公告"}, SOURCE, model=approved)
        self.assertEqual(result["departments"], [])
        self.assertEqual(result["actions"], [])

    def test_novel_obligation_guess_does_not_override_program_comparison(self):
        analysis = {"actions": ["需新增負責人資格審查機制。"]}
        result = event_evidence.review_event_analysis(analysis, {"title": "修正公司規則"}, "原有條文已有資格要求。",
                                                     model=approved, program_facts="條文差異由程式比對。")
        self.assertEqual(result["actions"], [])

    def test_law_revision_date_cannot_be_replaced_with_event_publication_date(self):
        source = {"source_id": "S1", "title": "公司規則", "text": "官方法規於2026年9月30日修正公布，10月1日收錄。",
                  "law_revision_dates": ["2026-09-30"]}
        result = evidence_review.review_statements(
            [{"id": "summary", "text": "2026年10月1日修正公司規則。", "source_ids": ["S1"]}],
            [source], context="", model=approved)
        self.assertEqual(result["supported"], 0)
        self.assertEqual(result["checks"][0]["method"], "date_rule")

    def test_source_ids_as_evidence_require_fresh_valid_evidence_not_automatic_conversion(self):
        calls = []
        def model(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return {"checks": [{"id": "x", "status": "supported", "reason": "", "evidence_ids": ["S1"]}]}
            return supported_review_reply(kwargs)
        result = evidence_review.review_statements(
            [{"id": "x", "text": "退費覆核有缺失。", "source_ids": ["S1"]}],
            [{"source_id": "S1", "text": SOURCE}], context="", model=model)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["supported"], 1)
        self.assertEqual(calls[0]["schema"]["properties"]["checks"]["items"]["properties"]["evidence_ids"]["items"]["enum"], ["E1"])

    def test_focused_refinement_reuses_source_and_does_not_fill_from_rules(self):
        candidate = {"departments": [{"department": "業務通路／行銷", "reason": "負責退費及懸帳清理。"}],
                     "impact_processes": [], "actions": ["立即調整退費流程。"]}
        def model(**kwargs):
            self.assertEqual(json.loads(kwargs["input_text"])["source_text"], SOURCE)
            return {"responsible_department": "待確認", "departments": [{"department": "財務／會計", "reason": "若有退費作業，可檢查憑證。"}],
                    "impact_processes": [], "actions": ["若有退費作業，可檢查憑證與覆核紀錄。"]}
        result = impact_assessment.refine_impacts(candidate, {"title": "退費裁罰"}, SOURCE, model=model)
        checked = event_evidence.review_event_analysis(result, {"title": "退費裁罰"}, SOURCE, model=approved)
        self.assertEqual(checked["departments"][0]["department"], "財務／會計")
        self.assertTrue(checked["actions"][0].startswith("若"))

    def test_management_generation_and_review_both_see_later_control_failures(self):
        ending = "後段違失：系統承辦與放行權限重疊，且未落實職務分離。"
        event = {"id": "penalty", "title": "退費裁罰", "description": SOURCE * 25 + ending}
        generated_inputs, reviewed_inputs = [], []

        def model(**kwargs):
            if "checks" in kwargs["schema"]["properties"]:
                reviewed_inputs.append(kwargs["input_text"])
                return supported_review_reply(kwargs)
            generated_inputs.append(kwargs["input_text"])
            return {"headline": "退費作業控制缺失", "summary": ending}

        with patch.object(management_summary, "_cached_summary", return_value=None), \
             patch.object(management_summary, "_save_summary"), \
             patch.object(management_summary, "call_ollama_structured_json", side_effect=model):
            result = management_summary.generate_management_summary_ai([event])
        self.assertIn(ending, generated_inputs[0])
        self.assertTrue(all(ending in data for data in reviewed_inputs))
        self.assertEqual(result["selected_event_count"], 1)

    def test_long_selected_sources_are_reviewed_in_bounded_sections_without_losing_selection(self):
        events = [{"id": str(i), "title": f"裁罰案例{i}", "description": SOURCE * 60} for i in range(3)]

        def model(**kwargs):
            self.assertLessEqual(len(kwargs["input_text"]), 14000)
            if "checks" in kwargs["schema"]["properties"]:
                return supported_review_reply(kwargs)
            return {"headline": "退費缺失", "summary": "退費憑證及覆核有缺失。"}

        with patch.object(management_summary, "_cached_summary", return_value=None), \
             patch.object(management_summary, "_save_summary"), \
             patch.object(management_summary, "call_ollama_structured_json", side_effect=model):
            result = management_summary.generate_management_summary_ai(events)
        self.assertEqual([event["id"] for event in result["source_events"]], ["0", "1", "2"])
        self.assertEqual(result["support_review"]["unverified"], 0)
        self.assertEqual(len(result["support_review"]["sources"]), 3)


if __name__ == "__main__":
    unittest.main()
