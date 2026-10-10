"""Chinese lexical retrieval over attributable public source passages."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from urllib.parse import urlsplit

from .text import clean_text
from .classification import is_management_signal, is_relevant
from .law_changes import latest_amendment_record


STOP_PHRASES = (
    "請問", "幫我", "告訴我", "有哪些", "有什麼", "是什麼", "什麼", "如何", "是否",
    "最近", "近期", "目前", "相關", "常見", "需要", "注意", "重點", "問題", "哪些",
    "平台", "收錄", "資料", "內容", "說明", "整理", "可以", "規定", "監理", "公告", "最新",
)
ALIASES = (("內控", "內部控制"), ("資金運用", "投資"), ("防制洗錢", "洗錢防制"), ("裁罰", "處分"))


def safe_source_url(value: str) -> str:
    url = clean_text(value)
    try:
        parsed = urlsplit(url)
        return url if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password else ""
    except ValueError:
        return ""


def search_tokens(text: str, *, query: bool = False) -> list[str]:
    text = clean_text(text).lower()
    if query:
        for phrase in STOP_PHRASES:
            text = text.replace(phrase, " ")
        extra = [other for group in ALIASES for term in group if term in text for other in group if other != term]
        text += " " + " ".join(extra)
    tokens = re.findall(r"[a-z0-9]+(?:[-.][a-z0-9]+)*", text)
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        for size in (2, 3):
            tokens.extend(run[start:start + size] for start in range(len(run) - size + 1))
    return tokens


def source_type(event: dict) -> str:
    key = event.get("source_key", "")
    if key == "fsc_penalty":
        return "裁罰"
    if key in {"insurance_law", "law_db"}:
        return "法規"
    if key == "fsc_announcement":
        return "公告"
    return "監理新聞" if key == "reg_news" else "監理資訊"


def public_documents(events: list[dict], laws: dict) -> list[dict]:
    """Exclude AI prose and select only the newest captured version of each law."""
    documents = {}
    for event in events:
        if not isinstance(event, dict) or not event.get("id"):
            continue
        if not is_relevant(event) or not is_management_signal(event):
            continue
        text = clean_text(event.get("description", ""))
        is_history = False
        if event.get("source_key") in {"insurance_law", "law_db"}:
            latest = latest_amendment_record(text)
            is_history = latest != text
            text = latest
        if len(text) < 30 or "請開啟官方原始來源確認完整內容" in text:
            continue
        url = safe_source_url(event.get("url", ""))
        title = clean_text(event.get("title", ""))
        if not url or not title:
            continue
        key = str(event["id"])
        document = {
            "document_id": key, "title": title, "text": text, "url": url,
            "source": clean_text(event.get("source", "官方來源")),
            "date": clean_text(event.get("published_at", ""))[:10],
            "date_label": "發布日期", "type": source_type(event),
            "version_note": "僅提供最新修正沿革，不能代替修正前後條文或生效日期核對" if is_history else (
                "預告／草案，不能視為已生效規範" if re.search("預告|草案", title) else ""),
        }
        # Callers provide historical records first, current source snapshots last.
        documents[key] = document
    for key, versions in laws.items():
        if not isinstance(versions, list):
            continue
        valid = [v for v in versions if isinstance(v, dict) and v.get("origin") == "官方法規原文" and v.get("version") and len(clean_text(v.get("text", ""))) >= 30]
        if not valid:
            continue
        latest = max(valid, key=lambda v: (v["version"], v.get("observed_at", "")))
        if not is_relevant({"title": latest.get("name", ""), "description": latest["text"]}):
            continue
        url = safe_source_url(latest.get("url", ""))
        if not url:
            continue
        documents["law:" + key] = {
            "document_id": "law:" + key, "title": clean_text(latest.get("name", "")),
            "text": clean_text(latest["text"]), "url": url, "source": "官方法規原文",
            "date": latest["version"], "date_label": "修正／公布日期", "type": "法規",
            "version_note": "平台已保存的最新版本；修正／公布日不等同生效日，未提供完整歷史版本",
        }
    return list(documents.values())


def passages(text: str, size: int = 850):
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = max(text.rfind("。", start + size // 2, end), text.rfind("；", start + size // 2, end))
            if boundary >= 0:
                end = boundary + 1
        yield text[start:end]
        if end == len(text):
            break
        start = max(start + 1, end - 100)


class KnowledgeIndex:
    def __init__(self, documents: list[dict]):
        self.document_count = len(documents)
        self.chunks = []
        self.postings = defaultdict(list)
        self.lengths = []
        seen = set()
        for document in documents:
            for number, text in enumerate(passages(document["text"]), start=1):
                identity = (document["url"], document["date"], text)
                if identity in seen:
                    continue
                seen.add(identity)
                position = len(self.chunks)
                self.chunks.append({**document, "text": text, "passage": number})
                frequencies = Counter(search_tokens(document["title"] + " " + text))
                self.lengths.append(sum(frequencies.values()))
                for token, frequency in frequencies.items():
                    self.postings[token].append((position, frequency))
        self.average_length = sum(self.lengths) / max(1, len(self.lengths))

    def search(self, question: str, filters: dict, limit: int = 6) -> list[dict]:
        scores = defaultdict(float)
        matches = defaultdict(set)
        query_terms = set(search_tokens(question, query=True))
        for token in query_terms:
            hits = self.postings.get(token, [])
            weight = math.log(1 + (len(self.chunks) - len(hits) + .5) / (len(hits) + .5))
            for position, frequency in hits:
                chunk = self.chunks[position]
                if filters["type"] != "全部" and chunk["type"] != filters["type"]:
                    continue
                if filters["date_from"] and (not chunk["date"] or chunk["date"] < filters["date_from"]):
                    continue
                if filters["date_to"] and (not chunk["date"] or chunk["date"] > filters["date_to"]):
                    continue
                denominator = frequency + 1.2 * (.25 + .75 * self.lengths[position] / self.average_length)
                scores[position] += weight * frequency * 2.2 / denominator
                matches[position].add(token)
        for position in list(scores):
            chunk = self.chunks[position]
            exact_title = len(chunk["title"]) >= 5 and chunk["title"] in question
            if not exact_title and len(matches[position]) / max(1, len(query_terms)) < .2:
                del scores[position]
            elif exact_title:
                scores[position] += 80
        result, per_document = [], Counter()
        for position in sorted(scores, key=lambda p: (scores[p], self.chunks[p]["date"]), reverse=True):
            chunk = self.chunks[position]
            if per_document[chunk["document_id"]] >= 2:
                continue
            per_document[chunk["document_id"]] += 1
            result.append({**chunk, "source_id": f"S{len(result) + 1}"})
            if len(result) >= limit:
                break
        return result
