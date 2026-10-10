from __future__ import annotations

import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from regintel.application import refresh


class RefreshCacheInvalidationTests(unittest.TestCase):

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        history = patch("regintel.application.event_history.EVENT_HISTORY_FILE", Path(directory.name) / "history.json")
        history.start()
        self.addCleanup(history.stop)

    def test_stale_parser_cache_is_refetched_without_http_validators(self) -> None:
        now = time.time()
        old_event = {
            "id": "old",
            "source_key": "insurance_law",
            "source": "保險相關法規",
            "source_detail": "保險局主管法規",
            "title": "財產保險商品審查應注意事項",
            "url": "https://law.fsc.gov.tw/LawContent.aspx?id=1",
            "published_at": "",
            "description": "財產保險商品審查應依主管機關規定辦理並保存相關審查紀錄。",
            "category": "行政規則",
            "change_status": "異動",
            "detected_at": "2026-09-18T15:02:41+08:00",
        }
        parsed_event = {
            **old_event,
            "id": "new",
            "published_at": "2023-12-18T00:00:00+08:00",
        }
        store = {
            "insurance_law": {
                "events": [old_event],
                "signal_events": [old_event],
                "last_checked_ts": now,
                "last_success_ts": now,
                "etag": '"old-etag"',
                "last_modified": "old-date",
                "parser_version": "old-parser",
            }
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

        original_cache = refresh._mem_cache
        original_manual_refresh = refresh._last_manual_refresh_ts
        refresh._mem_cache = {"timestamp": 0.0, "events": [], "sources": {}}
        refresh._last_manual_refresh_ts = 0.0

        try:
            with (
                patch.object(refresh, "SOURCES", {"insurance_law": source}),
                patch.object(
                    refresh,
                    "SOURCE_MIN_INTERVAL_SECONDS",
                    {"insurance_law": 3600},
                ),
                patch.object(refresh, "load_json_file", return_value=store),
                patch.object(refresh, "robots_allowed", return_value=True),
                patch.object(
                    refresh,
                    "fetch_url",
                    return_value=(
                        200,
                        b"<LAWS />",
                        "application/xml",
                        {"etag": '"new-etag"', "last_modified": "new-date"},
                    ),
                ) as fetch,
                patch.object(refresh, "parse_source", return_value=[parsed_event]),
                patch.object(refresh, "atomic_write_json"),
            ):
                payload = refresh.refresh_data(False)
        finally:
            refresh._mem_cache = original_cache
            refresh._last_manual_refresh_ts = original_manual_refresh

        fetch.assert_called_once_with(source["url"], "", "")
        self.assertEqual(
            payload["events"][0]["published_at"],
            "2023-12-18T00:00:00+08:00",
        )


if __name__ == "__main__":
    unittest.main()
