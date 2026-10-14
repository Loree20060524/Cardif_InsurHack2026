"""Realistic law differences must preserve conditions and never invent a baseline."""

import json
import tempfile
import unittest
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from regintel.application import law_comparison as service
from regintel.domain.law_comparison import compare_versions, comparison_evidence, parse_articles, verified_change_summary
from regintel.infrastructure import law_versions
from regintel.infrastructure.law_history import parse_history_list, parse_law_page, official_law_url
from regintel.application import event_analysis
from regintel import web


def version(date, text, name="測試法規"):
    return {"name": name, "version": date, "text": text, "origin": "官方法規原文", "url": "https://law.fsc.gov.tw/LawContent.aspx?id=FL123456"}


class LawComparisonTests(unittest.TestCase):
    def test_matches_articles_and_preserves_exception_numbers_and_punctuation(self):
        before = version("2025-01-01", "第 1 條\n應於三十日內申報。但免申報者，不在此限。\n第 2 條\n應保存紀錄。\n第 3 條\n其他規定。")
        after = version("2026-01-01", "第 1 條\n應於十五日內申報。\n第 2 條\n（刪除）\n第 3 條\n其他規定。\n第 3-1 條\n應辦理覆核。")
        result = compare_versions(before, after)
        self.assertEqual(result["counts"], {"added": 1, "deleted": 1, "modified": 1})
        self.assertEqual(result["unchanged_count"], 1)
        self.assertIn("不在此限", result["changes"][0]["before"])
        for row in result["changes"]:
            self.assertEqual("".join(part["text"] for part in row["before_segments"]), row["before"])
            self.assertEqual("".join(part["text"] for part in row["after_segments"]), row["after"])

    def test_layout_only_changes_are_ignored(self):
        old = version("2025-01-01", "第 1 條\n應保 存\n紀錄。\n\n　　\u00a0 第 二 章 覆核\n第 2 條\n應覆核。")
        new = version("2026-01-01", "第 一 章 通則第 1 條應保存紀錄。\n第 2 條應覆核。")
        self.assertEqual(compare_versions(old, new)["changes"], [])

    def test_verified_points_keep_changed_article_references_readable(self):
        before = version("2025-01-01", "第 1 條\n主管準用第六十條規定；副主管準用第六十條規定。")
        after = version("2026-01-01", "第 1 條\n主管準用第四十九條之一規定；副主管準用第四十九條之一規定。")
        comparison = dict(compare_versions(before, after), name="測試法規",
                          before_version={"date": before["version"]}, after_version={"date": after["version"]})
        _, points = verified_change_summary([comparison])
        self.assertIn("第六十條", points[0])
        self.assertIn("第四十九條之一", points[0])
        self.assertIn("前版片段", points[0])

    def test_ambiguous_duplicate_headings_are_not_compared(self):
        self.assertEqual(parse_articles("第 1 條\n完整內容。\n第 1 條\n另一段內容。"), {})

    def test_body_citation_is_not_an_article_heading_in_html(self):
        text = "第 1 條\n依其他法規\n第 99 條規定辦理。\n第 2 條\n第二條內容。"
        articles = parse_articles(text, strict_headers=True)
        self.assertEqual(list(articles), ["1", "2"])
        self.assertIn("第99條規定", articles["1"])

    def test_undated_announcement_cannot_use_current_law_as_its_revision(self):
        self.assertEqual(service.get_law_comparisons({"source_key": "fsc_announcement", "title": "修正保險經紀人管理規則"}), [])

    def test_same_date_or_other_law_cannot_be_baseline(self):
        before = version("2026-01-01", "第 1 條\n前版。")
        for after in (version("2026-01-01", "第 1 條\n後版。"), version("2026-02-01", "第 1 條\n後版。", "別部法規")):
            self.assertEqual(compare_versions(before, after)["status"], "unavailable")

    def test_missing_baseline_and_future_versions_never_imply_added_law(self):
        event = {"source_key": "insurance_law", "title": "測試法規", "published_at": "2026-01-01"}
        with patch.object(service, "stored_versions", return_value=[version("2026-02-01", "第 1 條\n未來。"), version("2025-01-01", "第 1 條\n現有。")]):
            result = service.get_law_comparisons(event)[0]
        self.assertEqual(result["status"], "missing_previous")
        self.assertEqual(result["after_version"]["date"], "2025-01-01")
        self.assertEqual(result["changes"], [])

    def test_same_date_snapshots_are_deduplicated_and_gaps_are_disclosed(self):
        records = [version("2026-01-01", "第 1 條\n後版。"), version("2026-01-01", "第 1 條\n後版。 "), version("2024-01-01", "第 1 條\n前版。")]
        with patch.object(service, "stored_versions", return_value=records):
            result = service.get_law_comparisons({"source_key": "insurance_law", "title": "測試法規"})[0]
        self.assertEqual(result["before_version"]["date"], "2024-01-01")
        self.assertIn("跨越多次修正", result["scope_note"])
        self.assertEqual(result["counts"]["modified"], 1)

    def test_draft_does_not_compare_enacted_versions(self):
        self.assertEqual(service.get_law_comparisons({"source_key": "insurance_law", "title": "保險法修正草案"}, fetch_missing=True), [])

    def test_ai_reads_no_network_and_receives_whole_articles_with_scope(self):
        with patch.object(service, "capture_law_history") as network, patch.object(service, "stored_versions", return_value=[]):
            service.get_law_comparisons({"source_key": "insurance_law", "title": "保險法"})
            network.assert_not_called()
        comparison = {"name": "測試法規", "status": "ready", "scope_note": "跨版本比較", "before_version": {"date": "2025-01-01", "url": "前版來源"}, "after_version": {"date": "2026-01-01", "url": "後版來源"}, "changes": [{"article": "第 1 條", "kind": "modified", "before": "完整前版。", "after": "完整後版。"}]}
        evidence = comparison_evidence([comparison], 1000)
        self.assertIn("非生效日", evidence)
        self.assertIn("跨版本比較", evidence)
        self.assertIn("完整前版", evidence)
        self.assertEqual(comparison_evidence([comparison], 10), "")

    def test_official_page_parser_excludes_navigation_and_preserves_dates(self):
        page = '''<a href="/">導覽</a><table class="tab-edit"><tr><th>法規名稱：</th><td>測試法規<span class="label-eng">英</span></td></tr><tr><th>公發布日：</th><td>民國 100 年 01 月 01 日</td></tr><tr><th>修正日期：</th><td>民國 115 年 09 月 30 日</td></tr></table><div class="law-article"><p>第 1 條</p><p>應保存紀錄。但另有規定者，不在此限。</p></div>'''
        parsed = parse_law_page(page.encode(), "text/html; charset=utf-8", "https://law.fsc.gov.tw/LawContent.aspx?id=FL123456")
        self.assertEqual(parsed["name"], "測試法規")
        self.assertEqual(parsed["version"], "2026-09-30")
        self.assertNotIn("導覽", parsed["text"])
        self.assertIn("不在此限", parsed["articles"]["1"])

    def test_history_dates_belong_to_their_own_link(self):
        page = '''<tr><td>1.</td><td>114.07.30</td><td><a href="LawContentHistory.aspx?hid=1&amp;id=FL123456">測試法規</a></td></tr><tr><td>2.</td><td>113.01.01</td><td><a href="https://example.org/LawContentHistory.aspx?hid=2">測試法規</a></td></tr>'''
        records = parse_history_list(page.encode(), "text/html", "https://law.fsc.gov.tw/LawContentHistoryList.aspx?id=FL123456", "測試法規")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["version"], "2025-07-30")
        self.assertIn("&id=FL123456", records[0]["url"])
        self.assertEqual(official_law_url("https://law.fsc.gov.tw.evil.example/LawContent.aspx?id=FL123456"), "")

    def test_historical_page_uses_its_own_metadata_table_layout(self):
        page = '<table class="table tab-list tab-law law-content"><tr><th>法規名稱：</th><td>測試法規</td></tr><tr><th>歷史法規：</th><td>民國 113 年 07 月 22 日</td></tr></table><div class="law-article">第 1 條<br>歷史版本原文。<br></div>'
        result = parse_law_page(page.encode(), "text/html", "https://law.fsc.gov.tw/LawContentHistory.aspx?hid=1")
        self.assertEqual(result["version"], "2024-07-22")
        self.assertEqual(result["articles"]["1"], "歷史版本原文。")

    def test_official_structured_articles_are_retained_with_provenance(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(law_versions, "LAW_VERSIONS_FILE", Path(directory) / "versions.json"):
            document = version("2026-01-01", "第 1 條\n完整官方條文內容足夠保存與比對。")
            document["articles"] = {"1": "完整官方條文內容足夠保存與比對。"}
            law_versions.save_public_versions([document])
            saved = law_versions.stored_versions("測試法規")[0]
            self.assertEqual(saved["articles"], document["articles"])
            self.assertEqual(saved["version"], "2026-01-01")

    def test_analysis_uses_verified_diff_and_does_not_overwrite_with_history_only_warning(self):
        comparison = {"name": "測試法規", "status": "ready", "signature": "first", "counts": {"added": 0, "deleted": 0, "modified": 1}, "scope_note": "跨版本比較", "before_version": {"date": "2025-01-01", "url": "https://law.fsc.gov.tw/LawContentHistory.aspx?hid=1"}, "after_version": {"date": "2026-01-01", "url": "https://law.fsc.gov.tw/LawContent.aspx?id=FL123456"}, "changes": [{"article": "第 1 條", "kind": "modified", "before": "應於三十日內申報。", "after": "應於十五日內申報。"}]}
        event = {"id": "law-test", "source_key": "insurance_law", "title": "測試法規", "category": "法規命令", "change_status": "異動", "description": "官方沿革列出修正第1條；目前未提供前後條文全文，實際義務及適用範圍須比對官方文件。"}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(event_analysis, "AI_CACHE_FILE", Path(directory) / "ai.json"), \
             patch.object(event_analysis, "load_ai_cache", return_value={"analyses": {}}), \
             patch.object(event_analysis, "get_law_comparisons", return_value=[comparison]), \
             patch.object(event_analysis, "call_ollama_structured_json", return_value={}) as model, \
             patch.object(event_analysis, "sanitize_ai_analysis", return_value={"analysis_mode": "AI 深度分析", "summary": "新增未出現在差異中的要求。", "regulatory_points": ["新增未出現在差異中的要求。"]}):
            first = event_analysis.analyze_event_with_ai(event)
            second = event_analysis.analyze_event_with_ai(event)
            self.assertEqual(first, second)
            model.assert_called_once()
            args = model.call_args.kwargs
            self.assertIn("應於三十日內申報", args["input_text"])
            self.assertIn("應於十五日內申報", args["input_text"])
            self.assertIn("不能當成生效日期", args["instructions"])
            self.assertEqual(first["content_source"], "官方條文前後對照")
            self.assertIn("修正 1 條", first["summary"])
            self.assertNotIn("新增未出現", first["summary"])
            self.assertNotIn("新增未出現", "".join(first["regulatory_points"]))
            self.assertEqual(first["law_comparison_signatures"], ["first"])

    def test_http_comparison_uses_event_identity_and_handles_missing_event(self):
        event = {"id": "law-http", "title": "測試法規", "source_key": "insurance_law"}
        class QuietHandler(web.Handler):
            def log_message(self, *_args):
                pass
        with patch.object(web, "refresh_data", return_value={"events": [event]}), \
             patch.object(web, "get_law_comparisons", return_value=[{"status": "missing_previous"}]) as compare:
            server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}/api/law-comparison?id="
                with urllib.request.urlopen(base + "law-http", timeout=5) as response:
                    self.assertEqual(json.load(response)["comparisons"][0]["status"], "missing_previous")
                compare.assert_called_once_with(event, fetch_missing=True)
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(base + "missing", timeout=5)
                self.assertEqual(raised.exception.code, 404)
                compare.assert_called_once()
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
