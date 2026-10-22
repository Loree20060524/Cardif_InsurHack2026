"""Source-support integration checks; model stubs do not measure legal accuracy."""

import copy
import json
import unittest
from unittest.mock import Mock, patch

from regintel.application import event_analysis
from regintel.application.event_evidence import EVENT_REVIEW_VERSION, review_event_analysis
from tests.evidence_fixtures import supported_review_reply


TEXT = "主管機關指出保險公司辦理退費及帳務覆核有缺失，要求改善相關內部控制措施，並保存交易紀錄與覆核證據供查核。"
EVENT = {"id": "support-event", "source_key": "reg_news", "title": "內部控制公告", "description": TEXT,
         "published_at": "2026-01-01", "url": "https://example.com/notice"}
OUTPUT = {"summary": TEXT, "management_summary": TEXT, "event_nature": "監理公告",
          "risk_level": "中", "importance": "重要", "rating_reason": "涉及退費及帳務覆核的內部控制改善。",
          "responsible_department": "法令遵循", "regulatory_points": ["改善相關內部控制措施。"],
          "departments": [{"department": "法令遵循", "reason": "確認內部控制改善的適用範圍。"}],
          "impact_processes": [{"process": "帳務覆核", "department": "財務會計", "impact": "需改善覆核並保存紀錄。"}],
          "attention_items": ["應保存覆核證據。"], "actions": ["建議檢查帳務覆核紀錄是否完整。"]}


class EventEvidenceTests(unittest.TestCase):
    def test_every_inferred_field_is_reviewed_with_server_owned_source_quotes(self):
        model = Mock(side_effect=lambda **kwargs: supported_review_reply(kwargs))
        result = review_event_analysis(OUTPUT, EVENT, TEXT, model=model)
        report = result["support_review"]
        ids = {row["id"] for row in report["checks"]}
        self.assertTrue({"summary", "management_summary", "event_nature", "rating", "responsible_department",
                         "departments:0", "impact_processes:0", "actions:0", "attention_items:0", "regulatory_points:0"} <= ids)
        self.assertEqual(report["withheld"], 0)
        self.assertEqual(result["risk_level"], "中")
        source = f"標題：{EVENT['title']}\n發布日期：{EVENT['published_at']}\n{TEXT}"
        for row in report["checks"]:
            self.assertIn(row["citations"][0]["quote"], source)
        self.assertEqual(report["version"], EVENT_REVIEW_VERSION)
        self.assertNotIn("text", report["sources"][0])

    def test_unsupported_fields_are_removed_without_rule_refill_or_rejected_text_leak(self):
        def model(**kwargs):
            reply = supported_review_reply(kwargs)
            for row in reply["checks"]:
                if row["id"] in {"summary", "rating", "departments:0", "impact_processes:0", "actions:0"}:
                    row.update(status="insufficient", reason="原文未支持。", evidence_ids=[])
            return reply
        candidate = {**OUTPUT, "summary": "虛構的強制申報義務。", "actions": ["虛構的強制表單。"]}
        result = review_event_analysis(candidate, EVENT, TEXT, model=model)
        self.assertNotIn("虛構", json.dumps(result, ensure_ascii=False))
        for name in ("actions", "departments", "impact_processes"):
            self.assertEqual(result[name], [])
        self.assertEqual(result["risk_level"], "待確認")
        self.assertEqual(result["importance"], "待確認")
        self.assertEqual(result["rating_reason"], "")
        self.assertEqual(result["regulatory_points"], OUTPUT["regulatory_points"])
        self.assertIn("省略", result["verification_notice"])

    def test_missing_rating_reason_does_not_publish_unexplained_rating(self):
        result = review_event_analysis({**OUTPUT, "rating_reason": ""}, EVENT, TEXT,
                                       model=lambda **kwargs: supported_review_reply(kwargs))
        self.assertEqual(result["risk_level"], "待確認")
        self.assertIn("缺少判斷依據", result["verification_notice"])

    def test_checker_failure_keeps_program_facts_but_no_inferences(self):
        candidate = {**OUTPUT, "summary": "程式比對的差異摘要。", "regulatory_points": ["程式比對第1條。"]}
        result = review_event_analysis(candidate, EVENT, TEXT, model=Mock(side_effect=RuntimeError("private")), program_facts="程式比對官方版本")
        self.assertEqual(result["summary"], candidate["summary"])
        self.assertEqual(result["regulatory_points"], candidate["regulatory_points"])
        self.assertEqual(result["actions"], [])
        self.assertEqual(result["responsible_department"], "待確認")
        self.assertGreater(result["support_review"]["unverified"], 0)
        self.assertNotIn("private", json.dumps(result))

    def test_wrong_currency_is_rejected_even_when_reviewer_would_accept(self):
        result = review_event_analysis({**OUTPUT, "summary": "本次裁罰500萬元。"}, EVENT, TEXT,
                                       model=lambda **kwargs: supported_review_reply(kwargs))
        check = next(row for row in result["support_review"]["checks"] if row["id"] == "summary")
        self.assertEqual(check["method"], "numeric_rule")
        self.assertNotIn("500萬元", result["summary"])


class EventPipelineEvidenceTests(unittest.TestCase):
    def run_analysis(self, output=None, reviewer=None, cache=None, event=None, **changes):
        cache = cache if cache is not None else {"analyses": {}}
        output = copy.deepcopy(OUTPUT if output is None else output)
        def model(**kwargs):
            if "checks" in kwargs["schema"]["properties"]:
                return reviewer(**kwargs) if reviewer else supported_review_reply(kwargs)
            return output
        with patch.object(event_analysis, "load_ai_cache", return_value=cache), \
             patch.object(event_analysis, "get_law_comparisons", return_value=[]), \
             patch.object(event_analysis, "call_ollama_structured_json", side_effect=model) as call, \
             patch.object(event_analysis, "atomic_write_json") as write:
            result = event_analysis.analyze_event_with_ai(event or EVENT, **changes)
        return result, call, write

    def test_pipeline_writes_only_reviewed_results_and_can_reuse_them(self):
        cache = {"analyses": {}}
        result, call, write = self.run_analysis(cache=cache)
        self.assertGreater(call.call_count, 1)
        write.assert_called_once()
        self.assertEqual(result["support_review"]["unverified"], 0)
        again, call, write = self.run_analysis(cache=cache)
        call.assert_not_called()
        write.assert_not_called()
        self.assertEqual(again, result)

    def test_legacy_or_incomplete_cache_cannot_bypass_review(self):
        for review in (None, {"version": "old", "unverified": 0}, {"version": EVENT_REVIEW_VERSION, "unverified": 1}):
            old = {"analysis_mode": "AI 深度分析", "summary": "舊的未核對結論。", "support_review": review}
            cache = {"analyses": {event_analysis.ai_event_cache_key(EVENT): old}}
            result, call, _ = self.run_analysis(cache=cache)
            self.assertGreater(call.call_count, 1)
            self.assertNotEqual(result["summary"], old["summary"])

    def test_unavailable_review_is_never_cached(self):
        result, _, write = self.run_analysis(reviewer=Mock(side_effect=RuntimeError("offline")))
        write.assert_not_called()
        self.assertGreater(result["support_review"]["unverified"], 0)
        self.assertEqual(result["actions"], [])

    def test_failed_forced_review_preserves_previous_valid_cache(self):
        cache = {"analyses": {}}
        previous, _, _ = self.run_analysis(cache=cache)
        failed, _, write = self.run_analysis(cache=cache, force=True, reviewer=Mock(side_effect=RuntimeError("offline")))
        write.assert_not_called()
        self.assertGreater(failed["support_review"]["unverified"], 0)
        self.assertEqual(cache["analyses"][event_analysis.ai_event_cache_key(EVENT)], previous)

    def test_official_diff_survives_checker_failure_in_actual_pipeline(self):
        comparison = {"name": "測試法規", "status": "ready", "signature": "first", "counts": {"added": 0, "deleted": 0, "modified": 1},
                      "scope_note": "跨版本比較", "before_version": {"date": "2025-01-01", "url": "https://example.com/before"},
                      "after_version": {"date": "2026-01-01", "url": "https://example.com/after"},
                      "changes": [{"article": "第 1 條", "kind": "modified", "before": "應於三十日內申報。", "after": "應於十五日內申報。"}]}
        def model(**kwargs):
            if "checks" in kwargs["schema"]["properties"]:
                raise RuntimeError("offline")
            return copy.deepcopy(OUTPUT)
        event = {**EVENT, "category": "法規命令", "change_status": "異動", "source_key": "insurance_law"}
        with patch.object(event_analysis, "get_law_comparisons", return_value=[comparison]), \
             patch.object(event_analysis, "load_ai_cache", return_value={"analyses": {}}), \
             patch.object(event_analysis, "call_ollama_structured_json", side_effect=model), \
             patch.object(event_analysis, "atomic_write_json") as write:
            result = event_analysis.analyze_event_with_ai(event)
        self.assertIn("修正 1 條", result["summary"])
        self.assertTrue(result["regulatory_points"])
        self.assertEqual(result["actions"], [])
        self.assertIn("程式比對", result["support_review"]["program_facts"])
        write.assert_not_called()

    def test_partial_ai_output_does_not_inherit_rule_departments_or_actions(self):
        result, _, _ = self.run_analysis(output={"summary": TEXT, "management_summary": TEXT})
        self.assertEqual(result["analysis_mode"], "AI 深度分析")
        for field in ("regulatory_points", "attention_items", "actions", "departments", "impact_processes"):
            self.assertEqual(result[field], [])
        self.assertEqual(result["responsible_department"], "待確認")

    def test_review_uses_generation_excerpt_not_unseen_remainder(self):
        event = {**EVENT, "description": TEXT * 130 + "未送入生成的機密尾段"}
        result, call, _ = self.run_analysis(event=event)
        generation = call.call_args_list[0].kwargs["input_text"]
        self.assertNotIn("機密尾段", generation)
        for item in call.call_args_list[1:]:
            data = json.loads(item.kwargs["input_text"])
            self.assertNotIn("機密尾段", data["sources"][0]["text"])
            self.assertIn("僅核對", data["sources"][0]["version_note"])
        self.assertTrue(result["support_review"]["source_is_excerpt"])


if __name__ == "__main__":
    unittest.main()
