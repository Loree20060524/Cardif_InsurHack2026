"""Read the body of official FSC announcement pages, excluding site navigation."""

from __future__ import annotations

import threading
import time
import urllib.parse
from html.parser import HTMLParser
from typing import Any

from ..config import AI_MAX_INPUT_CHARS, CACHE_TTL_SECONDS
from ..domain.text import clean_text, decode_bytes
from ..source_catalog import SOURCES
from .attachment_text import extract_attachment_text
from .http_client import fetch_url


_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()
_MAX_NOTICE_TEXT = min(AI_MAX_INPUT_CHARS, 6000)
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class _AnnouncementParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, set[str]]] = []
        self.title: list[str] = []
        self.body: list[str] = []
        self.attachments: list[dict[str, str]] = []
        self.in_article = False
        self.past_article = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        inherited = self.stack[-1][1] if self.stack else set()
        scopes = set(inherited)
        if "maincontent" in classes:
            scopes.add("article")
            self.in_article = True
        if "article" in scopes and "page-edit" in classes:
            scopes.add("body")
        if "article" in scopes and tag == "h3":
            scopes.add("title")
        if tag in {"script", "style", "noscript"}:
            scopes.add("ignored")
        if tag == "a" and self.past_article:
            href = values.get("href") or ""
            # Only download links after the article and before the site footer.
            if urllib.parse.urlsplit(href).path.lower() in {"/websitedowndoc", "/uploaddowndoc"}:
                self.attachments.append({"url": href, "title": clean_text(values.get("title", ""))})
        if tag not in _VOID_TAGS:
            self.stack.append((tag, scopes))
        elif tag in {"br", "hr"} and "body" in scopes:
            self.body.append(" ")
        if "fat_box" in classes or values.get("id") == "fatfoot":
            self.past_article = False

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] != tag:
                continue
            removed = self.stack[index:]
            del self.stack[index:]
            if self.in_article and any("article" in scopes for _, scopes in removed):
                if not self.stack or "article" not in self.stack[-1][1]:
                    self.in_article = False
                    self.past_article = True
            return

    def handle_data(self, data: str):
        scopes = self.stack[-1][1] if self.stack else set()
        if "ignored" in scopes:
            return
        if "title" in scopes:
            self.title.append(data)
        if "body" in scopes:
            self.body.append(data)


def official_announcement_url(event: dict[str, Any]) -> str:
    source = SOURCES.get(clean_text(event.get("source_key", "")), {})
    if event.get("source_key") not in {"fsc_announcement", "fsc_penalty", "reg_news"}:
        return ""
    parsed = urllib.parse.urlsplit(clean_text(event.get("url", "")))
    host = urllib.parse.urlsplit(source.get("url", "")).hostname
    params = urllib.parse.parse_qs(parsed.query)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname != host
        or parsed.username or parsed.password
        or parsed.path not in {"/home.jsp", "/ch/home.jsp"}
        or params.get("mcustomize") not in (["multimessage_view.jsp"], ["multimessages_view.jsp"])
        or not params.get("dataserno")
    ):
        return ""
    return urllib.parse.urlunsplit(("https", parsed.netloc, "/ch/home.jsp", parsed.query, ""))


def parse_announcement_detail(data: bytes, content_type: str, url: str) -> dict[str, Any]:
    parser = _AnnouncementParser()
    parser.feed(decode_bytes(data, content_type))
    attachments = []
    host = urllib.parse.urlsplit(url).hostname
    for item in parser.attachments:
        link = urllib.parse.quote(urllib.parse.urljoin(url, item["url"]), safe=":/?&=%,+")
        parsed = urllib.parse.urlsplit(link)
        if parsed.scheme in {"http", "https"} and parsed.hostname == host and not parsed.username and not parsed.password:
            query = urllib.parse.parse_qs(parsed.query)
            filename = query.get("filedisplay", query.get("file", [""]))[0]
            attachments.append({"url": link, "title": item["title"], "filename": filename})
    return {
        "title": clean_text(" ".join(parser.title)),
        "description": clean_text(" ".join(parser.body)),
        "url": url,
        "attachments": attachments,
    }


def fetch_announcement_content(event: dict[str, Any]) -> dict[str, Any]:
    """Resolve a genuine announcement to its own official body and attachments."""
    url = official_announcement_url(event)
    if not url:
        return {}
    with _cache_lock:
        cached = _cache.get(url)
        if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
            return dict(cached[1])
    try:
        status, data, content_type, _ = fetch_url(url)
        if status != 200 or not data:
            return {}
        result = parse_announcement_detail(data, content_type, url)
        if not result["title"]:
            return {}
        parts = [result["description"]] if result["description"] else []
        attachments = sorted(result["attachments"], key=lambda item: -(2 * int("說明" in item["filename"]) + int("對照" in item["filename"])))
        parsed_attachments = 0
        for attachment in attachments[:3]:
            if sum(map(len, parts)) >= _MAX_NOTICE_TEXT:
                break
            try:
                status, document, mime, _ = fetch_url(attachment["url"])
                text = extract_attachment_text(document, filename=attachment["filename"], content_type=mime) if status == 200 else ""
                if text:
                    parts.append(f"官方附件 {attachment['filename']}：{text}")
                    parsed_attachments += 1
            except Exception:
                # An unreadable attachment must not discard the official page body.
                continue
        complete_text = clean_text("\n".join(parts))
        excerpted = len(complete_text) > _MAX_NOTICE_TEXT or parsed_attachments < len(attachments)
        result["description"] = complete_text[:_MAX_NOTICE_TEXT]
        if attachments and excerpted:
            result["description"] += " （附件僅提供部分內容節錄，未包含所有附件全文；其餘數值及條文須查閱官方原始文件。）"
        source_label = "官方公告原文" if event.get("source_key") == "fsc_announcement" else "官方原文"
        result["content_source"] = f"{source_label}及附件節錄" if parsed_attachments else source_label
        with _cache_lock:
            _cache[url] = (time.monotonic(), result)
        return dict(result)
    except Exception:
        return {}
