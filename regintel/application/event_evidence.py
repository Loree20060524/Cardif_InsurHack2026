"""Review single-event interpretations without filling rejected fields from rules."""

from __future__ import annotations

from ..domain.text import clean_text
from ..domain.interpretation import is_draft_event
from .evidence_review import REVIEW_VERSION, review_notice, review_statements


EVENT_REVIEW_VERSION = "event-support-v1-" + REVIEW_VERSION
EVENT_REVIEW_INPUT_CHARS = 5000
LAW_COMPARISON_INPUT_CHARS = 8000
NARRATIVE_FIELDS = ("summary", "management_summary")
LIST_FIELDS = ("regulatory_points", "attention_items", "actions", "departments", "impact_processes")


def review_event_analysis(analysis: dict, event: dict, source_text: str, *, model,
                          program_facts: str = "", source_is_excerpt: bool = False) -> dict:
    """Publish only supported candidates; keep separately identified program facts."""
    result = dict(analysis)
    sources = [{
        "source_id": "S1", "title": clean_text(event.get("title", "")),
        "url": event.get("url", ""), "date": event.get("published_at", ""),
        "date_label": "發布日期（不代表生效日期）", "type": analysis.get("content_source", "官方來源"),
        "version_note": "僅核對本次生成使用的來源；不代表完整條文或最終適用性。",
        "text": f"標題：{clean_text(event.get('title', ''))}\n發布日期：{event.get('published_at', '')}\n{source_text}",
        "is_draft": is_draft_event(event, source_text),
        "is_law_comparison": bool(program_facts and "條文" in program_facts),
    }]
    deterministic = {"summary", "management_summary", "regulatory_points"} if program_facts else set()
    statements = []

    def add(identity, text, kind="fact", **metadata):
        if clean_text(text):
            statements.append({"id": identity, "text": text, "source_ids": ["S1"], "kind": kind, **metadata})

    for name in NARRATIVE_FIELDS:
        if name not in deterministic:
            add(name, analysis.get(name, ""))
    nature = analysis.get("event_nature", "待確認")
    if nature != "待確認":
        add("event_nature", f"此事件性質初步判斷為{nature}。")
    reason = clean_text(analysis.get("rating_reason", ""))
    if reason and analysis.get("risk_level") in {"高", "中", "低"} and analysis.get("importance") in {"重大", "重要", "一般"}:
        add("rating", f"依原文初步判斷風險程度為{analysis['risk_level']}、重要性為{analysis['importance']}。判斷依據：{reason}", "assessment")
    responsible = analysis.get("responsible_department", "待確認")
    if responsible and responsible != "待確認":
        add("responsible_department", f"初步建議由{responsible}確認此事件的適用性與影響。", "department")
    for name in LIST_FIELDS:
        if name in deterministic:
            continue
        for index, item in enumerate(analysis.get(name, [])):
            if name == "departments":
                text = f"可能受影響部門：{item['department']}。理由：{item['reason']}"
            elif name == "impact_processes":
                text = f"可能受影響流程：{item['process']}；相關部門：{item['department']}。影響：{item['impact']}"
            else:
                text = item
            kind = {"actions": "recommendation", "departments": "department", "impact_processes": "process", "attention_items": "inference"}.get(name, "fact")
            metadata = {key: item[key] for key in ("department", "process") if isinstance(item, dict) and key in item}
            add(f"{name}:{index}", text, kind, **metadata)

    review = review_statements(statements, sources, context=(
        "核對單則監理資訊的摘要及初步影響判讀。分級與部門屬初步研判，並非官方指定結論。"
        "分級依強制性、影響範圍、流程變更、裁罰與急迫性判斷；須核對所附理由，不能只因標籤合理就接受。"
        "部門與建議須有原文所述事項支持，不得擴大成未記載的法定義務。"
        "若含官方前後版本，舊版內容不可當成現行要求；修正日不是生效日。"
    ), model=model)
    accepted = {row["id"] for row in review["checks"] if row["status"] == "supported"}
    for name in NARRATIVE_FIELDS:
        if name not in deterministic and name not in accepted:
            result[name] = "未取得可保留的分析摘要，請查看官方原文。"
    if "event_nature" not in accepted:
        result["event_nature"] = "待確認"
    if "rating" not in accepted:
        result.update(risk_level="待確認", importance="待確認", rating_reason="")
    if "responsible_department" not in accepted:
        result["responsible_department"] = "待確認"
    for name in LIST_FIELDS:
        if name not in deterministic:
            result[name] = [item for index, item in enumerate(analysis.get(name, [])) if f"{name}:{index}" in accepted]

    review["version"] = EVENT_REVIEW_VERSION
    review["sources"] = [{key: value for key, value in source.items() if key != "text"} for source in sources]
    review["checks"] = [{**row, "text": statements[index]["text"] if row["status"] == "supported" else ""}
                        for index, row in enumerate(review["checks"])]
    review["program_facts"] = program_facts
    review["source_is_excerpt"] = source_is_excerpt
    result["support_review"] = review
    result["verification_notice"] = review_notice(review)
    if not reason:
        result["verification_notice"] = (result["verification_notice"] + " 分級缺少判斷依據，暫列待確認。").strip()
    result["analysis_note"] = (
        (program_facts + "；" if program_facts else "")
        + "AI 摘要及影響判讀另經模型核對來源，未獲支持的內容已省略。"
        + ("本次只使用來源節錄，未涵蓋全文。" if source_is_excerpt else "")
        + "核對仍可能誤判或漏判，法規適用性與法律效果須由專業人員確認。"
    )
    return result


def reusable_event_review(analysis: dict) -> bool:
    review = analysis.get("support_review")
    return isinstance(review, dict) and review.get("version") == EVENT_REVIEW_VERSION and review.get("unverified") == 0
