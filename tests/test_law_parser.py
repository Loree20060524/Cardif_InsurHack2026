from __future__ import annotations

import unittest

from regintel.infrastructure.parsers import parse_law_xml


class LawParserTests(unittest.TestCase):

    def test_attachment_inherits_publication_fields_from_parent_law(self) -> None:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<LAWS>
  <Law>
    <法規類別>行政規則</法規類別>
    <法規體系>通用目</法規體系>
    <公發布日>20231218</公發布日>
    <修正日期>20231218</修正日期>
    <法規名稱>保險商品審查規定</法規名稱>
    <主旨>修正保險商品送審規定。</主旨>
    <圖表附件>
      <檔案>
        <檔案名稱>保險商品審查修正規定.odt</檔案名稱>
        <下載網址>https://law.fsc.gov.tw/Download.ashx?id=1</下載網址>
      </檔案>
    </圖表附件>
  </Law>
</LAWS>"""

        events = parse_law_xml("insurance_law", xml.encode("utf-8"))
        attachment = next(
            event
            for event in events
            if event["title"].endswith(".odt")
        )

        self.assertTrue(attachment["published_at"].startswith("2023-12-18"))
        self.assertEqual(attachment["category"], "行政規則")


if __name__ == "__main__":
    unittest.main()
