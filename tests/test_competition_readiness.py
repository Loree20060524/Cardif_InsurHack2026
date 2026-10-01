"""Regression checks for the core regulatory-intelligence experience."""

import unittest
import time
from unittest.mock import patch

from regintel.application import refresh
from regintel.application.ai_support import ai_event_cache_key
from regintel.application.event_analysis import analyze_event_with_ai
from regintel.application.management_summary import generate_management_summary_ai
from regintel.domain.classification import is_relevant
from regintel.domain.law_changes import detect_law_changes, merge_recent_law_signals
from regintel.domain.risk_analysis import rule_based_analyze_event
from regintel.infrastructure.parsers import parse_rss
from regintel.infrastructure.parsers import SOURCE_PARSER_VERSION


class CompetitionReadinessTests(unittest.TestCase):
    def test_rss_article_url_decodes_nested_html_entities(self) -> None:
        xml = (
            "<rss><channel><item><title>保險公司裁罰</title>"
            "<link>https://www.fsc.gov.tw/ch/home.jsp?id=131"
            "&amp;amp;dataserno=202609240002</link>"
            "<description>保險公司受裁罰</description>"
            "<pubDate>Thu, 24 Sep 2026 08:00:00 +0800</pubDate>"
            "</item></channel></rss>"
        ).encode("utf-8")
        event, = parse_rss("fsc_penalty", xml)
        self.assertIn("&dataserno=202609240002", event["url"])
        self.assertNotIn("&amp;", event["url"])

    def test_attachment_metadata_change_is_not_called_a_law_change(self) -> None:
        previous = {
            "source_key": "insurance_law", "title": "保險法條文對照表.pdf",
            "description": "", "published_at": "2025-01-01", "category": "附件",
        }
        current = {**previous, "published_at": "2025-01-02"}
        self.assertEqual(detect_law_changes([previous], [current], True), [])

    def test_readable_law_update_requires_a_text_difference(self) -> None:
        previous = {
            "source_key": "insurance_law", "title": "保險業風險管理辦法",
            "description": "本辦法規範保險業風險管理與內部控制。",
            "published_at": "2025-01-01", "category": "行政規則",
        }
        metadata_only = {**previous, "published_at": "2025-01-02"}
        changed_text = {**metadata_only, "description": "本辦法規範保險業風險管理與內部控制，並新增通報要求。"}
        self.assertEqual(detect_law_changes([previous], [metadata_only], True), [])
        changes = detect_law_changes([previous], [changed_text], True)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["change_status"], "異動")
        self.assertIn("待核對", changes[0]["change_basis"])

        previously_empty = {**previous, "description": ""}
        self.assertEqual(detect_law_changes([previously_empty], [changed_text], True), [])

    def test_old_attachment_only_signal_is_not_retained(self) -> None:
        old = {
            "source_key": "insurance_law", "title": "附件.pdf", "description": "",
            "detected_at": "2026-09-30T10:00:00+08:00", "change_status": "異動",
        }
        self.assertEqual(merge_recent_law_signals([old], []), [])
        legacy_text_signal = {
            **old, "title": "保險業風險管理辦法", "description": "官方法規內容摘要",
        }
        self.assertEqual(merge_recent_law_signals([legacy_text_signal], []), [])

    def test_cached_law_snapshot_keeps_readable_records_without_fake_changes(self) -> None:
        law = {
            "id": "law-1", "source_key": "insurance_law",
            "title": "保險業風險管理辦法", "description": "保險業應建立風險管理制度及內部控制程序。",
            "published_at": "2026-09-01T00:00:00+08:00",
            "url": "https://law.fsc.gov.tw/LawQuery.aspx?id=1&amp;kind=law",
        }
        false_change = {
            **law, "id": "attachment-1", "title": "附件.pdf", "description": "",
            "change_status": "異動", "detected_at": "2026-09-30T10:00:00+08:00",
        }
        store = {"insurance_law": {
            "events": [law], "signal_events": [false_change],
            "parser_version": SOURCE_PARSER_VERSION,
            "last_checked_ts": time.time(), "last_success_ts": time.time(),
        }}
        original_cache = refresh._mem_cache
        refresh._mem_cache = {"timestamp": 0.0, "events": [], "sources": {}}
        try:
            with patch.object(
                refresh, "SOURCES", {"insurance_law": refresh.SOURCES["insurance_law"]}
            ), patch.object(
                refresh, "SOURCE_MIN_INTERVAL_SECONDS", {"insurance_law": 3600}
            ), patch.object(
                refresh, "load_json_file", return_value=store
            ), patch.object(refresh, "atomic_write_json"):
                payload = refresh.refresh_data()
        finally:
            refresh._mem_cache = original_cache
        self.assertEqual([event["id"] for event in payload["events"]], ["law-1"])
        self.assertNotIn("change_status", payload["events"][0])
        self.assertIn("&kind=law", payload["events"][0]["url"])
        self.assertEqual(payload["sources"]["insurance_law"]["signal_count"], 0)

    def test_placeholder_announcement_never_receives_deep_ai_label(self) -> None:
        event = {
            "id": "announcement-1", "source_key": "fsc_announcement",
            "source": "金管會公告", "source_detail": "金管會重要公告",
            "title": "修正保險經紀人管理規則", "published_at": "2026-09-30",
            "description": "金管會重要公告。請開啟官方原始來源確認完整內容。",
            "category": "重要公告",
        }
        with patch(
            "regintel.application.event_analysis.load_ai_cache",
            return_value={
                "analyses": {
                    ai_event_cache_key(event): {"analysis_mode": "AI 深度分析"}
                },
                "management": {},
            },
        ), patch(
            "regintel.application.event_analysis.call_ollama_structured_json"
        ) as model:
            result = analyze_event_with_ai(event)
        model.assert_not_called()
        self.assertEqual(result["analysis_mode"], "規則備援")

    def test_management_ai_ignores_placeholder_announcement(self) -> None:
        placeholder = {
            "id": "announcement-1", "title": "金管會公告保險規則",
            "description": "金管會重要公告。請開啟官方原始來源確認完整內容。",
        }
        substantive = {
            "id": "penalty-1", "title": "保險公司內控裁罰",
            "description": "主管機關指出該保險公司在退款及帳務覆核流程有缺失，要求改善相關內部控制措施，並定期檢查交易紀錄與覆核證據。",
        }
        with patch(
            "regintel.application.management_summary.load_ai_cache",
            return_value={"analyses": {}, "management": {}},
        ), patch(
            "regintel.application.management_summary.atomic_write_json"
        ), patch(
            "regintel.application.management_summary.call_ollama_structured_json",
            return_value={},
        ) as model:
            result = generate_management_summary_ai([placeholder, substantive])
        prompt = model.call_args.kwargs["input_text"]
        self.assertIn("保險公司內控裁罰", prompt)
        self.assertNotIn("金管會公告保險規則", prompt)
        self.assertIn("1 件", result["management_note"])

    def test_penalty_fallback_does_not_infer_unrelated_capital_or_product_work(self) -> None:
        event = {
            "source_key": "fsc_penalty", "title": "台灣人壽懸帳退款內控缺失裁罰",
            "description": (
                "公司辦理退費及懸帳清理，未落實覆核與交易對象姓名檢核。"
                "失效保單的保單價值準備金未即時沖轉。"
                "辦理失效保單個案融通復效或依保單條款約定申請增加保險金額。"
                "法令依據列舉保險商品銷售、復效、保全與收費之控制作業。"
            ),
        }
        analysis = rule_based_analyze_event(event)
        advice = " ".join(analysis["attention_items"] + analysis["actions"])
        self.assertNotIn("資本適足", advice)
        self.assertNotIn("商品條款", advice)
        self.assertIn("懸帳", advice)
        self.assertIn("退費", advice)

    def test_unrelated_bank_penalty_is_not_an_insurance_event(self) -> None:
        event = {
            "source_key": "fsc_penalty",
            "title": "合作金庫商業銀行辦理信用卡疑義帳款作業缺失",
            "description": "違反銀行法及金融機構內部控制規定。",
        }
        self.assertFalse(is_relevant(event))
        self.assertTrue(is_relevant({
            "source_key": "fsc_penalty", "title": "台灣人壽退費內控缺失裁罰",
            "description": "退費及懸帳處理有缺失。",
        }))


if __name__ == "__main__":
    unittest.main()
