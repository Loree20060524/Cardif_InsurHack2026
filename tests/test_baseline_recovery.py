"""Regression checks for restoring the original RegIntel baseline safely."""

from __future__ import annotations

import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from regintel.application import event_analysis, refresh
from regintel.domain.law_changes import detect_law_changes, merge_recent_law_signals


class BaselineRecoveryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        history = patch("regintel.application.event_history.EVENT_HISTORY_FILE", Path(directory.name) / "history.json")
        history.start()
        self.addCleanup(history.stop)

    def test_placeholder_announcement_ignores_cached_deep_analysis(self) -> None:
        event = {
            "id": "announcement-1",
            "source_key": "fsc_announcement",
            "title": "修正保險經紀人管理規則",
            "description": "金管會重要公告。請開啟官方原始來源確認完整內容。",
            "category": "重要公告",
        }
        cached = {
            "analysis_mode": "AI 深度分析",
            "risk_level": "待確認",
            "importance": "待確認",
        }
        with (
            patch.object(event_analysis, "ai_event_cache_key", return_value="key"),
            patch.object(
                event_analysis,
                "load_ai_cache",
                return_value={"analyses": {"key": cached}},
            ),
            patch.object(event_analysis, "fetch_event_attachment_text", return_value=""),
            patch.object(event_analysis, "call_ollama_structured_json") as model,
        ):
            result = event_analysis.analyze_event_with_ai(event)

        self.assertEqual(result["analysis_mode"], "規則備援")
        model.assert_not_called()

    def test_placeholder_without_cache_does_not_call_ai(self) -> None:
        event = {
            "id": "announcement-2",
            "source_key": "fsc_announcement",
            "title": "監理公告",
            "description": "金管會重要公告。請開啟官方原始來源確認完整內容。",
        }
        with (
            patch.object(event_analysis, "load_ai_cache", return_value={"analyses": {}}),
            patch.object(event_analysis, "fetch_event_attachment_text", return_value=""),
            patch.object(event_analysis, "call_ollama_structured_json") as model,
        ):
            result = event_analysis.analyze_event_with_ai(event)

        self.assertEqual(result["analysis_mode"], "規則備援")
        model.assert_not_called()

    def test_substantive_source_can_still_use_cached_ai_analysis(self) -> None:
        event = {
            "id": "penalty-1",
            "source_key": "fsc_penalty",
            "title": "保險業內控裁罰",
            "description": (
                "主管機關指出保險公司辦理退費及帳務覆核有缺失，"
                "要求改善相關內部控制措施，並保存交易紀錄與覆核證據供查核。"
            ),
        }
        cached = {"analysis_mode": "AI 深度分析", "summary": "已核對來源內容"}
        with (
            patch.object(event_analysis, "ai_event_cache_key", return_value="key"),
            patch.object(
                event_analysis,
                "load_ai_cache",
                return_value={"analyses": {"key": cached}},
            ),
            patch.object(event_analysis, "call_ollama_structured_json") as model,
        ):
            result = event_analysis.analyze_event_with_ai(event)

        self.assertEqual(result, cached)
        model.assert_not_called()

    def test_substantive_source_still_reaches_ai_when_not_cached(self) -> None:
        event = {
            "id": "penalty-2",
            "source_key": "fsc_penalty",
            "title": "保險業內控裁罰",
            "description": (
                "主管機關指出保險公司辦理退費及帳務覆核有缺失，"
                "要求改善相關內部控制措施，並保存交易紀錄與覆核證據供查核。"
            ),
        }
        with (
            patch.object(event_analysis, "load_ai_cache", return_value={"analyses": {}}),
            patch.object(event_analysis, "call_ollama_structured_json", return_value={})
            as model,
        ):
            event_analysis.analyze_event_with_ai(event)

        model.assert_called_once()

    def test_law_metadata_and_attachments_are_not_verified_changes(self) -> None:
        previous = {
            "source_key": "insurance_law",
            "title": "保險代理人管理規則",
            "description": "保險代理人應遵守主管機關所定之管理規範。",
            "published_at": "2026-09-01",
        }
        metadata_only = {**previous, "published_at": "2026-09-30"}
        attachment = {
            **previous,
            "title": "修正對照表.pdf",
            "description": "",
        }
        self.assertEqual(detect_law_changes([previous], [metadata_only], True), [])
        self.assertEqual(detect_law_changes([previous], [attachment], True), [])
        legacy_signal = {
            **attachment,
            "change_status": "異動",
            "detected_at": "2026-09-30T10:00:00+08:00",
        }
        self.assertEqual(merge_recent_law_signals([legacy_signal], []), [])
        changed_text = {
            **previous,
            "description": "保險代理人應遵守主管機關所定之管理規範及新增通報要求。",
        }
        changes = detect_law_changes([previous], [changed_text], True)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["change_status"], "異動")
        self.assertIn("待核對", changes[0]["change_basis"])

    def test_law_snapshot_visible_without_change_signal(self) -> None:
        now = time.time()
        law = {
            "id": "law-1",
            "source_key": "insurance_law",
            "source": "保險相關法規",
            "source_detail": "保險局主管法規",
            "title": "保險代理人管理規則",
            "url": "https://law.fsc.gov.tw/LawContent.aspx?id=1",
            "published_at": "2026-09-30T00:00:00+08:00",
            "description": "保險代理人應遵守主管機關所定之管理規範及相關作業要求。",
            "category": "法規命令",
        }
        source = {
            "label": "保險局主管法規",
            "group_label": "保險相關法規",
            "url": "https://law.fsc.gov.tw/opendata/insurance.xml",
            "public_url": "https://law.fsc.gov.tw/LawQuery.aspx",
            "dataset_url": "https://data.gov.tw/dataset/138801",
            "kind": "law_xml",
            "access_type": "官方 XML 開放資料",
        }
        store = {
            "insurance_law": {
                "events": [law],
                "signal_events": [],
                "last_checked_ts": now,
                "last_success_ts": now,
                "parser_version": refresh.SOURCE_PARSER_VERSION,
            }
        }
        original_cache = refresh._mem_cache
        refresh._mem_cache = {"timestamp": 0.0, "events": [], "sources": {}}
        try:
            with (
                patch.object(refresh, "SOURCES", {"insurance_law": source}),
                patch.object(
                    refresh,
                    "SOURCE_MIN_INTERVAL_SECONDS",
                    {"insurance_law": 3600},
                ),
                patch.object(refresh, "load_json_file", return_value=store),
                patch.object(refresh, "atomic_write_json"),
            ):
                payload = refresh.refresh_data(False)
        finally:
            refresh._mem_cache = original_cache

        self.assertEqual([event["id"] for event in payload["events"]], ["law-1"])
        self.assertNotIn("change_status", payload["events"][0])


if __name__ == "__main__":
    unittest.main()
