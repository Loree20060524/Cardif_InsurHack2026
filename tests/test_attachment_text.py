from __future__ import annotations

import io
import unittest
import zipfile

from regintel.infrastructure.attachment_text import extract_attachment_text


class AttachmentTextTests(unittest.TestCase):

    def test_extracts_traditional_chinese_text_from_odt(self) -> None:
        content_xml = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
    xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
  <office:body>
    <office:text>
      <text:p>財產保險商品審查應注意事項</text:p>
      <text:p>應將相關文件以電子檔案送交主管機關。</text:p>
    </office:text>
  </office:body>
</office:document-content>"""
        buffer = io.BytesIO()

        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("content.xml", content_xml.encode("utf-8"))

        extracted = extract_attachment_text(
            buffer.getvalue(),
            filename="修正規定.odt",
            content_type="application/octet-stream",
        )

        self.assertIn("財產保險商品審查應注意事項", extracted)
        self.assertIn("送交主管機關", extracted)


if __name__ == "__main__":
    unittest.main()
