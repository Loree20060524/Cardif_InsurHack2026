from __future__ import annotations

import unittest

from regintel.application.ai_support import sanitize_ai_analysis


class AIAnalysisQualityTests(unittest.TestCase):

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
