"""Official RSS and HTML links can refer to the same source document."""

import unittest

from regintel.application.event_history import _merge_records
from regintel.infrastructure.parsers import normalize_event


class EventHistoryIdentityTests(unittest.TestCase):
    def record(self, identifier, url, **extra):
        return {"id": identifier, "source_key": "fsc_penalty", "title": "保險業違反內部控制規定裁罰案",
                "description": "保險業應強化內部控制制度與法令遵循。", "published_at": "2026-09-24T00:00:00+08:00",
                "url": url, **extra}

    def test_escaped_html_and_rss_links_merge_with_stable_id(self):
        html_record = self.record("html-id", "https://www.fsc.gov.tw/ch/home.jsp?id=131&amp;dataserno=202609240001&amp;dtable=Penalty")
        rss_record = self.record("rss-id", "https://www.fsc.gov.tw/RSS/home.jsp?dataserno=202609240001&id=131&dtable=Penalty")
        merged = _merge_records([html_record], [rss_record])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["id"], "html-id")
        self.assertNotIn("&amp;", merged[0]["url"])
        self.assertEqual(html_record["url"], "https://www.fsc.gov.tw/ch/home.jsp?id=131&amp;dataserno=202609240001&amp;dtable=Penalty")

    def test_same_title_with_different_official_serials_is_preserved(self):
        first = self.record("first", "https://www.fsc.gov.tw/ch/home.jsp?dataserno=111")
        second = self.record("second", "https://www.fsc.gov.tw/ch/home.jsp?dataserno=222")
        self.assertEqual(len(_merge_records([first], [second])), 2)

    def test_existing_escaped_links_are_repaired_without_a_new_fetch(self):
        record = self.record("old", "https://www.fsc.gov.tw/ch/home.jsp?id=131&amp;dataserno=111")
        self.assertIn("&dataserno=111", _merge_records([record], [])[0]["url"])

    def test_normalization_decodes_link_entities_before_generating_an_id(self):
        args = ("fsc_penalty", "保險業違反內控裁罰案")
        escaped = normalize_event(*args, "https://www.fsc.gov.tw/ch/home.jsp?id=131&amp;dataserno=111", "保險業內部控制", "2026-09-24")
        plain = normalize_event(*args, "https://www.fsc.gov.tw/ch/home.jsp?id=131&dataserno=111", "保險業內部控制", "2026-09-24")
        self.assertEqual(escaped["id"], plain["id"])
        self.assertEqual(escaped["url"], plain["url"])


if __name__ == "__main__":
    unittest.main()
