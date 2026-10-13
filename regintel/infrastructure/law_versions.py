"""Persist only official public texts, with their real revision dates and provenance."""

from __future__ import annotations

import hashlib
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import date

from ..config import LAW_VERSIONS_FILE
from ..domain.text import clean_text, local_tag, normalize_document_text, now_iso
from ..source_catalog import SOURCES
from .json_store import atomic_write_json, document_transaction, load_json_file

_lock = threading.RLock()


def version_date(value: str) -> str:
    """Parse Gregorian/feed and ROC/site dates. Never use observation time as revision."""
    value = str(value).strip()
    match = re.search(r"(\d{2,4})\s*(?:年|[./-])\s*(\d{1,2})\s*(?:月|[./-])\s*(\d{1,2})", value)
    if match:
        year, month, day = map(int, match.groups())
        if year < 1911:
            year += 1911
    elif re.fullmatch(r"\d{8}", value):
        year, month, day = int(value[:4]), int(value[4:6]), int(value[6:])
    else:
        return ""
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def law_key(name: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", "", name).encode("utf-8")).hexdigest()[:24]


def stored_versions(name: str) -> list[dict]:
    with _lock:
        records = load_json_file(LAW_VERSIONS_FILE).get("laws", {}).get(law_key(name), [])
        return [dict(item) for item in records if isinstance(item, dict)]


def history_capture_is_fresh(identifier: str, revision: str) -> bool:
    with _lock:
        check = load_json_file(LAW_VERSIONS_FILE).get("history_checks", {}).get(f"{identifier}|{revision}", 0)
        return isinstance(check, (int, float)) and 0 <= time.time() - check < 3600


def remember_history_capture(identifier: str, revision: str) -> None:
    with _lock, document_transaction(LAW_VERSIONS_FILE):
        store = load_json_file(LAW_VERSIONS_FILE)
        store.setdefault("history_checks", {})[f"{identifier}|{revision}"] = time.time()
        atomic_write_json(LAW_VERSIONS_FILE, store)


def save_public_versions(documents: list[dict]) -> None:
    """Store the public text, revision date, and provenance fields."""
    with _lock, document_transaction(LAW_VERSIONS_FILE):
        store = load_json_file(LAW_VERSIONS_FILE)
        laws = store.setdefault("laws", {})
        changed = False
        for document in documents:
            if document.get("origin") != "官方法規原文" or not document.get("name") or not document.get("version"):
                continue
            text = normalize_document_text(document.get("text", ""))
            if len(text) < 20 or len(text) > 120000:
                continue
            digest = hashlib.sha256(re.sub(r"\s+", "", text).encode("utf-8")).hexdigest()
            key = law_key(document["name"])
            records = laws.setdefault(key, [])
            existing = next((item for item in records if item.get("version") == document["version"] and item.get("digest") == digest), None)
            if existing:
                # Prefer the individual law page over a feed when it becomes available.
                if "/opendata/" in existing.get("url", "") and "/opendata/" not in document.get("url", ""):
                    existing["url"] = document["url"]
                    changed = True
                for field in ("articles", "attachments"):
                    if document.get(field) and existing.get(field) != document[field]:
                        existing[field] = document[field]
                        changed = True
                continue
            records.append({
                "name": document["name"], "text": text, "version": document["version"],
                "origin": "官方法規原文", "url": document.get("url", ""),
                "law_key": key, "digest": digest, "observed_at": now_iso(),
                **({"articles": document["articles"]} if document.get("articles") else {}),
                **({"attachments": document["attachments"]} if document.get("attachments") else {}),
            })
            records.sort(key=lambda item: (item["version"], item["observed_at"]), reverse=True)
            changed = True
        if changed:
            store["updated_at"] = now_iso()
            atomic_write_json(LAW_VERSIONS_FILE, store)


def capture_feed_versions(source_key: str, data: bytes) -> None:
    """Capture full law content on every successful official feed refresh."""
    source = SOURCES.get(source_key, {})
    if source.get("kind") != "law_xml":
        return
    root = ET.fromstring(data)
    documents = []
    for node in root.iter():
        if local_tag(node.tag) != "Law":
            continue
        values = {local_tag(child.tag): "".join(child.itertext()).strip() for child in node}
        name = clean_text(values.get("法規名稱", ""))
        revision = version_date(values.get("修正日期", "")) or version_date(values.get("公發布日", ""))
        text = normalize_document_text(values.get("法規內容", "") or values.get("條文內容", ""))
        if name and revision and text:
            documents.append({"name": name, "text": text, "version": revision, "url": source["url"], "origin": "官方法規原文"})
    save_public_versions(documents)
