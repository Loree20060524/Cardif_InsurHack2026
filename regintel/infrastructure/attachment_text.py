"""Safe text extraction for official regulatory attachments."""

from __future__ import annotations

import io
import pathlib
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from typing import Any

from ..domain.text import clean_text, decode_bytes
from ..source_catalog import SOURCES
from .http_client import fetch_url


MAX_DOCUMENT_XML_BYTES = 5 * 1024 * 1024


def _extract_zipped_xml(data: bytes, member_name: str) -> str:
    buffer = io.BytesIO(data)

    if not zipfile.is_zipfile(buffer):
        return ""

    with zipfile.ZipFile(buffer) as archive:
        try:
            info = archive.getinfo(member_name)
        except KeyError:
            return ""

        if info.file_size > MAX_DOCUMENT_XML_BYTES:
            raise ValueError("官方附件解壓後內容過大。")

        root = ET.fromstring(archive.read(member_name))

    return clean_text(" ".join(root.itertext()))


def extract_attachment_text(
    data: bytes,
    *,
    filename: str,
    content_type: str = "",
) -> str:
    """Extract plain text from supported attachment bytes."""
    suffix = pathlib.PurePath(filename).suffix.lower()

    if suffix == ".odt":
        return _extract_zipped_xml(data, "content.xml")

    if suffix == ".docx":
        return _extract_zipped_xml(data, "word/document.xml")

    if suffix in {".txt", ".csv", ".xml", ".html", ".htm"}:
        return clean_text(decode_bytes(data, content_type))

    return ""


def fetch_event_attachment_text(event: dict[str, Any]) -> str:
    """Fetch text only from an official law feed's own host."""
    source = SOURCES.get(clean_text(event.get("source_key", "")), {})

    if source.get("kind") != "law_xml":
        return ""

    url = clean_text(event.get("url", ""))
    filename = clean_text(event.get("title", ""))
    parsed = urllib.parse.urlparse(url)
    source_host = urllib.parse.urlparse(source.get("url", "")).hostname

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.hostname.lower() != (source_host or "").lower()
    ):
        return ""

    status, data, content_type, _ = fetch_url(url)

    if status != 200 or not data:
        return ""

    return extract_attachment_text(
        data,
        filename=filename,
        content_type=content_type,
    )
