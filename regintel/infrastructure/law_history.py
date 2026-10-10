"""Read official FSC law pages and dated historical versions on demand."""

from __future__ import annotations

import re
import threading
import time
import urllib.parse
from html.parser import HTMLParser

from ..domain.text import clean_text, decode_bytes
from ..domain.law_comparison import parse_articles
from .http_client import fetch_url, robots_allowed
from .law_versions import save_public_versions, stored_versions, version_date, history_capture_is_fresh, remember_history_capture

OFFICIAL_ROOT = "https://law.fsc.gov.tw/"
# Verified official law identities for the initial competition demo scope.
KNOWN_LAWS = {
    "保險法": "FL006746",
    "保險代理人管理規則": "FL006749",
    "保險經紀人管理規則": "FL027603",
    "保險業招攬及核保理賠辦法": "FL006828",
}
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
_lock = threading.RLock()
_checked: dict[str, float] = {}


def official_law_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme not in {"http", "https"} or parsed.hostname != "law.fsc.gov.tw"
            or parsed.username or parsed.password or parsed.port not in {None, 443, 80}
            or parsed.path not in {"/LawContent.aspx", "/LawContentHistory.aspx", "/LawContentHistoryList.aspx", "/LawSearchResult.aspx", "/LawResult.aspx"}):
        return ""
    return urllib.parse.urlunsplit(("https", "law.fsc.gov.tw", parsed.path, parsed.query, ""))


class _LawPageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.body, self.row, self.rows, self.links = [], [], [], []
        self.anchor = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        scopes = set(self.stack[-1][1]) if self.stack else set()
        classes = set((values.get("class") or "").split())
        if "law-article" in classes or (values.get("id") or "").endswith("divLawContent"):
            scopes.add("body")
        if tag == "table" and ("tab-edit" in classes or "law-content" in classes):
            scopes.add("metadata")
        if tag in {"script", "style", "noscript"} or "label-eng" in classes:
            scopes.add("ignored")
        if tag == "tr":
            self.row = []
        if tag == "a":
            self.anchor = {"url": values.get("href", ""), "parts": []}
        if "body" in scopes and tag in {"p", "div", "br", "tr", "li"}:
            self.body.append("\n")
        if tag not in _VOID:
            self.stack.append((tag, scopes))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_data(self, data):
        scopes = self.stack[-1][1] if self.stack else set()
        if "ignored" in scopes:
            return
        if "body" in scopes:
            self.body.append(data)
        if "metadata" in scopes:
            self.row.append(data)
        if self.anchor is not None:
            self.anchor["parts"].append(data)

    def handle_endtag(self, tag):
        scopes = self.stack[-1][1] if self.stack else set()
        if tag == "tr" and "metadata" in scopes:
            row = clean_text(" ".join(self.row))
            if row:
                self.rows.append(row)
        if tag == "a" and self.anchor is not None:
            self.links.append({"url": self.anchor["url"], "text": clean_text("".join(self.anchor["parts"]))})
            self.anchor = None
        if "body" in scopes and tag in {"p", "div", "tr", "li"}:
            self.body.append("\n")
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break


def parse_law_page(data: bytes, mime: str, url: str) -> dict:
    parser = _LawPageParser()
    parser.feed(decode_bytes(data, mime))
    metadata = {}
    for row in parser.rows:
        match = re.match(r"([^：:]+)[：:]\s*(.*)", row)
        if match:
            metadata[match[1].strip()] = match[2].strip()
    name = metadata.get("法規名稱", "")
    revision = version_date(metadata.get("歷史法規", "") or metadata.get("修正日期", "") or metadata.get("公發布日", ""))
    text = "".join(parser.body).strip()
    articles = parse_articles(text, strict_headers=True)
    if not name or not revision or not articles or len(text) > 120000:
        return {}
    attachments = []
    for link in parser.links:
        parsed = urllib.parse.urlsplit(urllib.parse.urljoin(url, link["url"]))
        if parsed.scheme in {"http", "https"} and parsed.hostname == "law.fsc.gov.tw" and parsed.path == "/Download.ashx" and not parsed.username and not parsed.password:
            attachments.append({"title": link["text"], "url": urllib.parse.urlunsplit(("https", "law.fsc.gov.tw", parsed.path, parsed.query, ""))})
    return {"name": name, "version": revision, "text": text, "articles": articles,
            "origin": "官方法規原文", "url": url, "attachments": attachments}


def parse_history_list(data: bytes, mime: str, url: str, name: str) -> list[dict]:
    """Bind each official date to the historical link in its own table row."""
    markup = decode_bytes(data, mime)
    results = []
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", markup, re.S | re.I):
        parser = _LawPageParser()
        parser.feed(row)
        date = version_date(clean_text(re.sub(r"<[^>]+>", " ", row)))
        for link in parser.links:
            target = official_law_url(urllib.parse.urljoin(url, link["url"]))
            if date and target and urllib.parse.urlsplit(target).path == "/LawContentHistory.aspx" and link["text"] == name:
                results.append({"version": date, "url": target})
    return sorted(results, key=lambda item: item["version"], reverse=True)


def law_identity(name: str, url: str = "") -> str:
    target = official_law_url(url)
    if target:
        identifier = urllib.parse.parse_qs(urllib.parse.urlsplit(target).query).get("id", [""])[0]
        if re.fullmatch(r"FL\d{6}", identifier):
            return identifier
    return KNOWN_LAWS.get(name, "")


def _fetch(url: str) -> tuple[bytes, str]:
    if not official_law_url(url) or not robots_allowed("insurance_law", url):
        raise ValueError("此官方法規頁面目前無法讀取。")
    status, data, mime, _ = fetch_url(url)
    if status != 200 or not data:
        raise ValueError("尚未取得官方法規內容。")
    return data, mime


def capture_law_history(name: str, identifier: str, target_date: str = "") -> None:
    """Save the official current text plus the nearest available older text.

    Fetching occurs only on an explicit comparison request, once/hour per target.
    Dates may have gaps; callers must not call this an immediately preceding revision.
    """
    if not re.fullmatch(r"FL\d{6}", identifier):
        return
    cache_key = f"{identifier}|{target_date}"
    with _lock:
        existing = stored_versions(name)
        if existing:
            latest = max(record.get("version", "") for record in existing)
            requested = min(target_date, latest) if target_date else latest
            if history_capture_is_fresh(identifier, requested):
                return
        if time.monotonic() - _checked.get(cache_key, -3600) < 3600:
            return
        current_url = f"{OFFICIAL_ROOT}LawContent.aspx?id={identifier}"
        data, mime = _fetch(current_url)
        current = parse_law_page(data, mime, current_url)
        if not current or current["name"] != name:
            raise ValueError("官方法規名稱或條文格式無法確認。")
        save_public_versions([current])
        date = min(target_date, current["version"]) if target_date else current["version"]
        list_url = f"{OFFICIAL_ROOT}LawContentHistoryList.aspx?id={identifier}"
        data, mime = _fetch(list_url)
        histories = parse_history_list(data, mime, list_url, name)
        # If targeting an earlier event, include that version before finding its predecessor.
        needed = [record for record in histories if record["version"] <= date][:2 if date < current["version"] else 1]
        existing = stored_versions(name)
        known_dates = {record["version"] for record in existing if record.get("articles")}
        for record in needed:
            if record["version"] in known_dates:
                continue
            data, mime = _fetch(record["url"])
            document = parse_law_page(data, mime, record["url"])
            if not document or document["name"] != name or document["version"] != record["version"]:
                raise ValueError("官方歷史版本日期或條文格式無法確認。")
            save_public_versions([document])
        _checked[cache_key] = time.monotonic()
        remember_history_capture(identifier, date)
