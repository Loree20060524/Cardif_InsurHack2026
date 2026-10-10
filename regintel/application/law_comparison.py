"""Resolve an event to dated law snapshots and expose a truthful comparison scope."""

from __future__ import annotations

import re

from ..domain.law_comparison import compare_versions
from ..domain.text import clean_text
from ..infrastructure.law_history import KNOWN_LAWS, capture_law_history, law_identity
from ..infrastructure.law_versions import LAW_VERSIONS_FILE, law_key, stored_versions, version_date
from ..infrastructure.json_store import load_json_file


def event_laws(event: dict) -> list[str]:
    title = clean_text(event.get("title", ""))
    if event.get("source_key") in {"insurance_law", "law_db"} and not re.search(r"\.(pdf|odt|docx?)$", title, re.I):
        return [title]
    if not re.search(r"修正|增訂|刪除|訂定", title) or "草案" in title or "預告" in title:
        return []
    if not version_date(event.get("published_at", "")):
        # An undated placeholder cannot be bound to a particular legal revision.
        return []
    stored = load_json_file(LAW_VERSIONS_FILE).get("laws", {})
    names = set(KNOWN_LAWS)
    for records in stored.values():
        if isinstance(records, list) and records and isinstance(records[0], dict):
            names.add(records[0].get("name", ""))
    return sorted((name for name in names if name and name in title), key=lambda name: -len(name))[:3]


def _version_metadata(record: dict) -> dict:
    return {"date": record["version"], "url": record.get("url", ""), "observed_at": record.get("observed_at", "")}


def _compare_law(name: str, event: dict, fetch_missing: bool) -> dict:
    identifier = law_identity(name, event.get("url", "") if event.get("title") == name else "")
    event_date = version_date(event.get("published_at", ""))
    error = ""
    if fetch_missing and identifier:
        try:
            capture_law_history(name, identifier, event_date)
        except Exception:
            error = "官方歷史版本暫時讀取失敗，可稍後重試。"
    # Deduplicate whitespace-only recaptures of the same dated official version.
    by_date = {}
    for record in stored_versions(name):
        date = record.get("version", "")
        if not date or (event_date and date > event_date):
            continue
        existing = by_date.get(date)
        if existing is None or (record.get("articles") and not existing.get("articles")):
            by_date[date] = record
    versions = sorted(by_date.values(), key=lambda item: item["version"], reverse=True)
    result = {"name": name, "law_key": law_key(name), "status": "missing_previous", "changes": [],
              "note": "缺少可比較的官方前版條文。", "can_fetch": bool(identifier)}
    if error:
        result["fetch_note"] = error
    if not versions:
        result.update(status="missing_current", note="尚未取得此法規的官方條文版本。")
        return result
    after = versions[0]
    result["after_version"] = _version_metadata(after)
    result["attachments"] = after.get("attachments", [])
    if len(versions) < 2:
        return result
    before = versions[1]
    # Equal dates never qualify as two revisions, even when site text was corrected.
    result["before_version"] = _version_metadata(before)
    result["scope_note"] = "兩個已取得官方版本的文字差異；可能跨越多次修正，未確認為緊接前版。附件與格式表未納入比對。"
    result["scope"] = "available_versions"
    result.update(compare_versions(before, after))
    if result["status"] == "ready":
        result["note"] = "版本日期為修正／公布日，不代表所有條文生效日期。"
    return result


def get_law_comparisons(event: dict, *, fetch_missing: bool = False) -> list[dict]:
    """Network access is explicit; ordinary AI analysis reads existing snapshots only."""
    if "草案" in clean_text(event.get("title", "")) or "預告" in clean_text(event.get("title", "")):
        return []
    return [_compare_law(name, event, fetch_missing) for name in event_laws(event)]
