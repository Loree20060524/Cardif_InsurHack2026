"""Retain source records and load official archive pages on demand."""

from __future__ import annotations

import html
import re
import threading
import urllib.parse
from typing import Any

from ..config import EVENT_HISTORY_FILE
from ..domain.event_selection import select_visible_events
from ..domain.text import clean_text, decode_bytes
from ..infrastructure.http_client import fetch_url, robots_allowed
from ..infrastructure.json_store import atomic_write_json, document_transaction, load_json_file
from ..infrastructure.parsers import parse_announcement_html
from ..infrastructure.postgres_store import StorageError
from ..source_catalog import SOURCES


ARCHIVE_SOURCE_KEYS = ("fsc_announcement", "fsc_penalty", "reg_news")
_history_lock = threading.RLock()
_fetch_lock = threading.Lock()


def _load_history() -> dict[str, Any]:
    data = load_json_file(EVENT_HISTORY_FILE)
    return {
        "events": data.get("events", []) if isinstance(data.get("events"), list) else [],
        "sources": data.get("sources", {}) if isinstance(data.get("sources"), dict) else {},
    }


def _identity(event: dict[str, Any]) -> tuple[str, str]:
    source = str(event.get("source_key", ""))
    serial = urllib.parse.parse_qs(urllib.parse.urlsplit(html.unescape(event.get("url", ""))).query).get("dataserno", [""])[0]
    return source, serial or str(event.get("id", ""))


def _merge_records(old: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    combined = {}
    for event in old + new:
        if not isinstance(event, dict) or not event.get("id") or event.get("source_key") not in SOURCES:
            continue
        key = _identity(event)
        previous = combined.get(key)
        record = {name: value for name, value in event.items() if name != "analysis"}
        record["url"] = html.unescape(record.get("url", ""))
        if previous:
            # RSS and HTML can link to the same document with different query order.
            record["id"] = previous["id"]
            if "請開啟官方原始來源確認完整內容" in record.get("description", ""):
                record["description"] = previous.get("description") or record["description"]
            if previous.get("change_basis") and not record.get("change_basis") and previous.get("description") == record.get("description"):
                for name in ("change_status", "change_basis", "detected_at"):
                    if name in previous:
                        record[name] = previous[name]
        combined[key] = record
    return select_visible_events(combined.values(), limit=None)


def remember_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with _history_lock, document_transaction(EVENT_HISTORY_FILE):
        history = _load_history()
        merged = _merge_records(history["events"], events)
        if merged != history["events"]:
            history["events"] = merged
            try:
                atomic_write_json(EVENT_HISTORY_FILE, history)
            except OSError:
                # Current source records remain readable if local persistence fails.
                pass
        return merged


def history_metadata() -> dict[str, Any]:
    with _history_lock:
        history = _load_history()
        sources = {}
        for key in ARCHIVE_SOURCE_KEYS:
            entry = history["sources"].get(key, {})
            sources[key] = {
                "label": SOURCES[key]["label"],
                "loaded_pages": entry.get("loaded_pages", 0),
                "has_more": entry.get("has_more", True),
            }
        return {"sources": sources}


def load_older_events(source_keys: Any) -> dict[str, Any]:
    if not isinstance(source_keys, list) or not source_keys or any(key not in ARCHIVE_SOURCE_KEYS for key in source_keys):
        raise ValueError("請選擇有效的公告、裁罰或監理新聞來源。")
    if not _fetch_lock.acquire(blocking=False):
        raise RuntimeError("正在載入歷史資料，請稍後再試。")
    try:
        errors = []
        fetched = 0
        for key in dict.fromkeys(source_keys):
            with _history_lock:
                entry = _load_history()["sources"].get(key, {})
                if not entry.get("has_more", True):
                    continue
                page = int(entry.get("loaded_pages", 0)) + 1
            try:
                parsed = urllib.parse.urlsplit(SOURCES[key]["public_url"])
                params = dict(urllib.parse.parse_qsl(parsed.query))
                params.update({"page": str(page), "pagesize": "100"})
                url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(params), ""))
                if not robots_allowed(key, url=url):
                    raise RuntimeError("官方來源目前不允許自動讀取。")
                status, data, mime, _ = fetch_url(url)
                if status != 200:
                    raise RuntimeError(f"官方來源回應 HTTP {status}。")
                text = decode_bytes(data, mime)
                pagination = re.search(r"頁數\s*(\d+)\s*/\s*(\d+)", clean_text(text))
                if not pagination or int(pagination[1]) != page:
                    raise RuntimeError("官方來源未回傳指定頁面，已保留原有資料。")
                records = parse_announcement_html(key, data, mime)
                if not records:
                    raise RuntimeError("官方頁面未解析到資料，請稍後重試。")
                with _history_lock, document_transaction(EVENT_HISTORY_FILE):
                    history = _load_history()
                    history["events"] = _merge_records(history["events"], records)
                    # A slower request for an earlier page must not move the
                    # shared pagination cursor backwards.
                    current_page = history["sources"].get(key, {}).get("loaded_pages", 0)
                    if page >= current_page:
                        history["sources"][key] = {"loaded_pages": page, "has_more": page < int(pagination[2])}
                    atomic_write_json(EVENT_HISTORY_FILE, history)
                fetched += 1
            except StorageError:
                raise
            except Exception as exc:
                errors.append(f"{SOURCES[key]['label']}：{clean_text(str(exc))[:180]}")
        return {"fetched_sources": fetched, "errors": errors}
    finally:
        _fetch_lock.release()
