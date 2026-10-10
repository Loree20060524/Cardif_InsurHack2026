from __future__ import annotations

import unittest

from regintel.application.ai_support import sanitize_ai_analysis
from regintel.application.event_analysis import ground_law_amendment_analysis, latest_amendment_record
from regintel.domain.risk_analysis import apply_regulatory_amendment_triage


class AIAnalysisQualityTests(unittest.TestCase):

    def test_single_law_summary_uses_its_actual_name(self) -> None:
        analysis = ground_law_amendment_analysis(
            {}, {}, {"title": "保險業財務報告編製準則"},
            "修正發布第4、9、12條條文。",
        )
        self.assertIn("保險業財務報告編製準則", analysis["management_summary"])
        self.assertNotIn("兩部管理規則", analysis["management_summary"])

    def test_latest_amendment_record_excludes_old_history_entries(self) -> None:
        description = (
            "1. 中華民國一百十一年九月二十二日修正，涉及高齡客戶權益。 "
            "2. 中華民國一百十五年九月三十日修正第21、33-1、49條，"
            "增訂第49-1條並刪除第60條。"
        )

        latest = latest_amendment_record(description)

        self.assertNotIn("高齡客戶權益", latest)
        self.assertIn("修正第21、33-1、49條", latest)

    def test_regulatory_amendment_gets_provisional_triage_rating(self) -> None:
        event = {
            "category": "法規命令",
            "change_status": "異動",
            "description": (
                "修正發布第21、33-1、49條，增訂第49-1條並刪除第60條；"
                "實際適用內容仍應依官方修正條文對照表核實。"
            ),
        }

        analysis = apply_regulatory_amendment_triage(
            event,
            {"risk_level": "待確認", "importance": "待確認"},
        )

        self.assertEqual(analysis["risk_level"], "中")
        self.assertEqual(analysis["importance"], "重要")
        self.assertIn("初步分級", analysis["rating_note"])

    def test_triage_does_not_rate_an_unsubstantiated_announcement(self) -> None:
        event = {
            "category": "重要公告",
            "change_status": "無",
            "description": "金管會重要公告。請開啟官方原始來源確認完整內容。",
        }
        original = {"risk_level": "待確認", "importance": "待確認"}

        analysis = apply_regulatory_amendment_triage(event, original)

        self.assertEqual(analysis, original)

    def test_placeholder_only_ai_result_uses_rule_fallback(self) -> None:
        fallback = {
            "summary": "系統偵測法規內容異動。",
            "event_nature": "法規異動",
            "risk_level": "中",
            "importance": "重要",
            "responsible_department": "法令遵循",
            "regulatory_points": ["應比對前後版本。"],
            "departments": [
                {
                    "department": "法令遵循",
                    "reason": "需要進行法規適用性評估。",
                }
            ],
            "impact_processes": [],
            "attention_items": ["確認生效日期。"],
            "actions": ["啟動版本差異比對。"],
            "management_summary": "請先確認法規適用性。",
        }
        result = {
            "summary": "待確認",
            "event_nature": "待確認",
            "risk_level": "待確認",
            "importance": "待確認",
            "responsible_department": "法令遵循",
            "regulatory_points": ["待確認"],
            "departments": [],
            "impact_processes": [],
            "attention_items": ["待確認"],
            "actions": ["待確認"],
            "management_summary": "待確認",
        }

        analysis = sanitize_ai_analysis(result, fallback)

        self.assertEqual(analysis["summary"], fallback["summary"])
        self.assertEqual(analysis["risk_level"], "中")
        self.assertEqual(analysis["importance"], "重要")
        self.assertEqual(
            analysis["regulatory_points"],
            fallback["regulatory_points"],
        )
        self.assertEqual(analysis["actions"], fallback["actions"])
        self.assertEqual(analysis["analysis_mode"], "規則備援")


if __name__ == "__main__":
    unittest.main()
