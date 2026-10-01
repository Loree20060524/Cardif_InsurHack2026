from __future__ import annotations

import unittest

from regintel.domain.event_selection import select_visible_events
from regintel.domain.text import date_sort_key


class EventSelectionTests(unittest.TestCase):

    def test_date_sort_key_does_not_use_detection_time(self) -> None:
        event = {
            "published_at": "",
            "detected_at": "2026-09-18T15:02:41+08:00",
        }

        self.assertEqual(date_sort_key(event), 0)

    def test_visible_events_keep_law_signals_when_news_exceeds_limit(self) -> None:
        news = [
            {
                "id": f"news-{index}",
                "source_key": "reg_news",
                "title": "保險監理新聞",
                "description": "保險",
                "published_at": f"2026-09-{17 - (index % 10):02d}T08:00:00+08:00",
            }
            for index in range(130)
        ]
        law = {
            "id": "law-1",
            "source_key": "insurance_law",
            "title": "保險業風險管理實務守則修正對照表.pdf",
            "description": "",
            "published_at": "",
            "detected_at": "2026-08-01T09:00:00+08:00",
            "change_status": "異動",
        }

        visible = select_visible_events([*news, law], limit=120)

        self.assertEqual(len(visible), 120)
        self.assertIn("law-1", {event["id"] for event in visible})

    def test_undated_detection_does_not_outrank_published_event(self) -> None:
        detected_without_publication = {
            "id": "law-undated",
            "source_key": "insurance_law",
            "title": "法規附件.odt",
            "description": "保險法規內容",
            "published_at": "",
            "detected_at": "2026-09-18T15:02:41+08:00",
        }
        officially_published = {
            "id": "news-dated",
            "source_key": "reg_news",
            "title": "金管會發布保險監理資訊",
            "description": "保險監理",
            "published_at": "2026-09-17T08:00:00+08:00",
            "detected_at": "2026-09-17T09:00:00+08:00",
        }

        visible = select_visible_events(
            [detected_without_publication, officially_published],
            limit=2,
            minimum_per_group=0,
        )

        self.assertEqual(
            [event["id"] for event in visible],
            ["news-dated", "law-undated"],
        )

    def test_generic_law_attachments_are_not_management_signals(self) -> None:
        generic_attachment = {
            "id": "law-attachment",
            "source_key": "insurance_law",
            "title": "附件.pdf",
            "description": "",
            "category": "",
            "published_at": "",
            "detected_at": "2026-09-18T15:02:41+08:00",
            "change_status": "異動",
        }
        meaningful_law = {
            **generic_attachment,
            "id": "law-meaningful",
            "title": "財產保險商品審查應注意事項修正對照表.pdf",
        }

        visible = select_visible_events(
            [generic_attachment, meaningful_law],
            limit=120,
        )

        self.assertEqual(
            [event["id"] for event in visible],
            ["law-meaningful"],
        )

    def test_consumer_insurance_news_is_not_a_management_signal(self) -> None:
        lifestyle_news = {
            "id": "lifestyle-news",
            "source_key": "reg_news",
            "title": "金管會提醒國人可規劃投保住宅火災及地震基本保險",
            "description": "保障居家安全的一般性投保宣導。",
            "published_at": "2026-09-17T08:00:00+08:00",
        }

        visible = select_visible_events([lifestyle_news], limit=120)

        self.assertEqual(visible, [])

    def test_enterprise_regulatory_news_remains_visible(self) -> None:
        regulatory_news = {
            "id": "regulatory-news",
            "source_key": "reg_news",
            "title": "金管會發布保險業自有資本與風險資本計算方法",
            "description": "推動保險業新一代清償能力監理制度。",
            "published_at": "2026-09-08T08:00:00+08:00",
        }

        visible = select_visible_events([regulatory_news], limit=120)

        self.assertEqual(
            [event["id"] for event in visible],
            ["regulatory-news"],
        )

    def test_non_insurance_cross_finance_news_is_not_visible(self) -> None:
        accountant_news = {
            "id": "accountant-news",
            "source_key": "reg_news",
            "title": "金管會提醒會計師應確實落實洗錢防制",
            "description": "會計師防制洗錢實務說明。",
            "published_at": "2026-08-13T08:00:00+08:00",
        }

        visible = select_visible_events([accountant_news], limit=120)

        self.assertEqual(visible, [])

    def test_non_insurance_financial_consumer_news_is_not_visible(self) -> None:
        leasing_news = {
            "id": "leasing-news",
            "source_key": "reg_news",
            "title": "預告將融資租賃業者納入金融消費者保護法適用",
            "description": "完善融資租賃業消費爭議處理。",
            "published_at": "2026-07-30T08:00:00+08:00",
        }

        visible = select_visible_events([leasing_news], limit=120)

        self.assertEqual(visible, [])


if __name__ == "__main__":
    unittest.main()
