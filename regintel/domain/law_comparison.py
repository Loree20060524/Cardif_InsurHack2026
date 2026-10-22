"""Article-level textual comparison; legal interpretation belongs to a separate step."""

from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher

_HEADER = re.compile(r"(?m)^[^\S\n]*第[^\S\n]*([0-9０-９]+(?:[ \t]*[-－之][ \t]*[0-9０-９]+)?)[^\S\n]*條(?:[ \t]*之[ \t]*([0-9０-９]+))?[^\S\n]*")
_CHAPTER = re.compile(r"(?m)^[^\S\n]*第[ 一二三四五六七八九十百零〇0-9]+[編章節][^\n]*")
_DIGITS = str.maketrans("０１２３４５６７８９－", "0123456789-")


def compact_text(text: str) -> str:
    # Only presentation whitespace is ignored. Numbers, exceptions and punctuation remain.
    return re.sub(r"\s+", "", str(text))


def parse_articles(text: str, *, strict_headers: bool = False) -> dict[str, str]:
    """Accept official XML texts and HTML converted to explicit article headings."""
    text = str(text).replace("\r\n", "\n").replace("\r", "\n")
    # Some official feeds join a chapter title directly to the first article.
    text = re.sub(r"(?m)^([ \t　]*第[ 一二三四五六七八九十百零〇0-9]+[編章節][^\n]*?)(?=第\s*[0-9０-９]+\s*條)", r"\1\n", text)
    text = _CHAPTER.sub("", text)
    headers = list(_HEADER.finditer(text))
    if strict_headers:
        # HTML has explicit paragraph/BR boundaries: a body citation is not a heading.
        headers = [match for match in headers if not text[match.end():].split("\n", 1)[0].strip()]
    articles: dict[str, str] = {}
    for index, match in enumerate(headers):
        number = re.sub(r"\s+", "", match[1]).translate(_DIGITS).replace("之", "-")
        if match[2]:
            number += "-" + match[2].translate(_DIGITS)
        content = text[match.end():headers[index + 1].start() if index + 1 < len(headers) else len(text)].strip()
        if not content or number in articles:
            # Ambiguous/partial extraction must never turn into apparent legal changes.
            return {}
        articles[number] = compact_text(content)
    return articles


def _deleted(text: str) -> bool:
    return text in {"（刪除）", "(刪除)", "刪除"}


def text_segments(before: str, after: str) -> tuple[list[dict], list[dict]]:
    """Return escaped-by-consumer text segments, never HTML from source documents."""
    old, new = [], []
    # Bound quadratic character matching for very long articles.
    if max(len(before), len(after)) > 16000:
        return ([{"text": before, "changed": True}] if before else [],
                [{"text": after, "changed": True}] if after else [])
    for tag, i, j, k, l in SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
        if i != j:
            old.append({"text": before[i:j], "changed": tag != "equal"})
        if k != l:
            new.append({"text": after[k:l], "changed": tag != "equal"})
    return old, new


def compare_versions(before: dict, after: dict) -> dict:
    """Compare two dated official snapshots without inventing missing articles."""
    if (before.get("name") != after.get("name") or not before.get("version")
            or not after.get("version") or before["version"] >= after["version"]):
        return {"status": "unavailable", "note": "無法確認同一法規的前後修正日期。", "changes": []}
    old = before.get("articles") or parse_articles(before.get("text", ""))
    new = after.get("articles") or parse_articles(after.get("text", ""))
    if not old or not new:
        return {"status": "unavailable", "note": "條文格式無法完整解析，請查閱官方原文。", "changes": []}
    changes = []
    counts = {"added": 0, "deleted": 0, "modified": 0}
    for number in sorted(old.keys() | new.keys(), key=lambda value: tuple(map(int, value.split("-")))):
        left, right = old.get(number, ""), new.get(number, "")
        if left == right or (not left and _deleted(right)) or (not right and _deleted(left)):
            continue
        kind = "added" if not left or _deleted(left) else ("deleted" if not right or _deleted(right) else "modified")
        counts[kind] += 1
        left_segments, right_segments = text_segments(left, right)
        changes.append({"article": f"第 {number} 條", "kind": kind, "before": left, "after": right,
                        "before_segments": left_segments, "after_segments": right_segments})
    signature = hashlib.sha256((before.get("digest", "") + after.get("digest", "") + str(changes)).encode()).hexdigest()
    return {"status": "ready", "changes": changes, "counts": counts,
            "unchanged_count": len(old.keys() & new.keys()) - sum(1 for item in changes if item["before"] and item["after"]),
            "signature": signature}


def relocation_pairs(changes: list[dict]) -> list[tuple[dict, dict]]:
    """Suggest unambiguous text matches, without equating legal effects."""
    added = [row for row in changes if row["kind"] == "added"]
    deleted = [row for row in changes if row["kind"] == "deleted"]
    pairs, used = [], set()
    for new in added:
        text = compact_text(new["after"])
        if not 40 <= len(text) <= 16000:
            continue
        candidates = sorted(
            [(SequenceMatcher(None, compact_text(old["before"]), text, autojunk=False).ratio(), index, old)
             for index, old in enumerate(deleted) if 40 <= len(compact_text(old["before"])) <= 16000],
            key=lambda item: item[0], reverse=True,
        )
        if (candidates and candidates[0][0] >= .85 and candidates[0][1] not in used
                and (len(candidates) == 1 or candidates[0][0] - candidates[1][0] >= .05)):
            used.add(candidates[0][1])
            pairs.append((candidates[0][2], new))
    return pairs


def comparison_evidence(comparisons: list[dict], max_chars: int = 10000) -> str:
    """Include whole changed articles only, with dates/sources and explicit scope."""
    parts, used = [], 0
    for comparison in comparisons:
        if comparison.get("status") != "ready" or not comparison.get("changes"):
            continue
        before, after = comparison["before_version"], comparison["after_version"]
        heading = (f"官方條文差異資料 v2\n法規：{comparison['name']}\n比較日期：{before['date']} → {after['date']}（修正／公布日，非生效日）\n"
                   f"比較範圍：{comparison['scope_note']}\n前版來源：{before['url']}\n後版來源：{after['url']}\n")
        pairs = relocation_pairs(comparison["changes"])
        paired = {id(row) for pair in pairs for row in pair}
        groups = [(list(pair), f"疑似移列：{pair[0]['article']} → {pair[1]['article']}。文字高度相似，須比較實質修改，不可僅憑新增條號稱為新增義務。\n") for pair in pairs]
        groups += [([row], "") for row in comparison["changes"] if id(row) not in paired]

        def render(change):
            inserted = [part['text'] for part in change.get('after_segments', []) if part['changed']]
            deleted = [part['text'] for part in change.get('before_segments', []) if part['changed']]
            fragments = (f"實際新增文字片段：{inserted}\n實際刪除文字片段：{deleted}\n"
                         if change["kind"] == "modified" else "")
            return (f"{change['article']}（{change['kind']}）\n{fragments}"
                    f"前版原文：{change['before'] or '此版本無此條次'}\n後版原文：{change['after'] or '此版本無此條次'}\n")

        rows, included = [], 0
        for group, note in groups:
            row = note + "".join(render(change) for change in group)
            if used + len(heading) + sum(map(len, rows)) + len(row) + 150 > max_chars:
                continue
            rows.append(row)
            included += len(group)
        if rows:
            section = heading + "".join(rows) + f"本段提供 {included}/{len(comparison['changes'])} 條差異；未列條文及附件不在本次 AI 分析範圍。\n"
            parts.append(section)
            used += len(section)
    return "\n".join(parts)


def _changed_context(segments: list[dict], limit: int = 110) -> list[str]:
    """Show changed clauses, so a revised article reference is readable as a whole."""
    text = "".join(part["text"] for part in segments)
    bounds = [0] + [match.end() for match in re.finditer(r"[，。；：！？]", text)] + [len(text)]
    excerpts, offset = [], 0
    for part in segments:
        end = offset + len(part["text"])
        if part["changed"] and end > offset:
            start = max(bound for bound in bounds if bound <= offset)
            stop = next((bound for bound in bounds if bound >= end), len(text))
            # Keep the changed text in view even when its surrounding clause is long.
            if stop - start > limit:
                start = max(start, offset - 25)
                stop = min(stop, max(end, start + limit))
            excerpt = text[start:stop]
            if len(excerpt) > limit:
                excerpt = excerpt[:limit] + "…"
            if start and text[start - 1] not in "，。；：！？":
                excerpt = "…" + excerpt
            if stop < len(text) and text[stop - 1] not in "，。；：！？" and not excerpt.endswith("…"):
                excerpt += "…"
            if excerpt not in excerpts:
                excerpts.append(excerpt)
        offset = end
    return excerpts[:3]


def verified_change_summary(comparisons: list[dict]) -> tuple[str, list[str]]:
    """Mechanical facts only. A model must not describe unchanged text as a new duty."""
    summaries, points = [], []
    for item in comparisons:
        if item.get("status") != "ready" or not item.get("changes"):
            continue
        counts = item["counts"]
        summaries.append(f"{item['name']}：比較 {item['before_version']['date']} 與 {item['after_version']['date']}，"
                         f"新增 {counts['added']} 條、修正 {counts['modified']} 條、刪除 {counts['deleted']} 條。")
        for change in item["changes"]:
            prefix = f"{item['name']} {change['article']}"
            if change["kind"] in {"added", "deleted"}:
                points.append(f"{prefix}：{'新增條文' if change['kind'] == 'added' else '刪除條文'}，完整內容見前後對照。")
                continue
            fragments = []
            for field, label in (("before_segments", "前版片段"), ("after_segments", "後版片段")):
                values = _changed_context(change.get(field, []))
                if values:
                    excerpt = "、".join(f"「{value}」" for value in values)
                    fragments.append(label + excerpt)
            points.append(f"{prefix}：" + "；".join(fragments) + "。完整條件見前後對照。")
    summary = "\n".join(summaries)
    if summary:
        summary += "\n以上為已取得官方版本的文字差異，可能跨越多次修正；日期為修正／公布日，生效安排須依官方文件確認。"
    if len(points) > 8:
        remaining = len(points) - 8
        points = points[:8] + [f"另有 {remaining} 條差異，請展開前後對照查看。"]
    return summary, points
