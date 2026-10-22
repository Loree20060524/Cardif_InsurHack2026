"""Refine unsafe operational guesses using the same sources and a focused contract."""

import json

from ..domain.interpretation import DEPARTMENT_GUIDANCE, department_hints, interpretation_issue, is_draft_event, unfilled_template
from ..domain.rules import AI_ALLOWED_DEPARTMENTS


IMPACT_FIELDS = ("responsible_department", "departments", "impact_processes", "actions")
_DEPARTMENT = {"type": "string", "enum": AI_ALLOWED_DEPARTMENTS}
_OPTIONAL = {"type": "string", "minLength": 15, "maxLength": 160}
_ACTION = {"type": "string", "pattern": "^若公司", "minLength": 15, "maxLength": 160}
IMPACT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": list(IMPACT_FIELDS),
    "properties": {
        "responsible_department": {"type": "string", "enum": [*AI_ALLOWED_DEPARTMENTS, "待確認"]},
        "departments": {"type": "array", "maxItems": 5, "items": {
            "type": "object", "additionalProperties": False, "required": ["department", "reason"],
            "properties": {"department": _DEPARTMENT, "reason": _OPTIONAL},
        }},
        "impact_processes": {"type": "array", "maxItems": 3, "items": {
            "type": "object", "additionalProperties": False, "required": ["department", "process", "impact"],
            "properties": {"department": _DEPARTMENT, "process": {"type": "string"}, "impact": _OPTIONAL},
        }},
        "actions": {"type": "array", "maxItems": 3, "items": _ACTION},
    },
}


def refine_impacts(analysis: dict, event: dict, text: str, *, model, has_comparison: bool = False) -> dict:
    """One focused generation, with one bounded retry for unfilled templates only."""
    source = {"is_draft": is_draft_event(event, text), "is_law_comparison": has_comparison}
    statements = []
    for item in analysis.get("departments", []):
        statements.append({**item, "text": item["reason"], "kind": "department"})
    for item in analysis.get("impact_processes", []):
        statements.append({**item, "text": item["impact"], "kind": "process"})
    statements.extend({"text": item, "kind": "recommendation"} for item in analysis.get("actions", []))
    issues = list(dict.fromkeys(reason for statement in statements if (reason := interpretation_issue(statement, [source]))))
    if not analysis.get("departments") and analysis.get("actions"):
        issues.append("尚無可保留的職能關聯，請只針對來源的具體作業重新判讀。")
    if not issues:
        return analysis
    instructions = (
        "你只整理可能的作業職能及可選檢查建議，不改寫法規事實。只依提供的同一份官方內容。"
        + DEPARTMENT_GUIDANCE +
        "不要宣稱新增、擴大義務，不新增原文未涉及的商品、模型、會計計量、表單、期限或核准人。"
        "reason與impact必須寫出來源提到的具體工作與可能相關的職能，保留是否有相關業務的條件。"
        "action必須寫出具體可選檢查事項，以若公司起頭，使用可先檢查、盤點、確認、評估或追蹤等準備動詞。"
        "若是草案，只能先盤點、評估草案影響及追蹤正式發布，不可要求符合新條文或立即變更流程。"
        "直接規範經紀人或銀行時，保險公司只能先確認合作通路的關聯，不把通路內部職責套用自己。"
        "建議檢查控制點是否合理，不要求其他公司沿用裁罰個案中的交易事由或代碼；不把個案違失當成應遵守的操作方法。"
        "職能候選僅供選擇；需保留具體來源關聯，無依據留空。全部繁體中文，短句。"
        "必須提供完成的文字，不得輸出格式範本、待填字樣、省略號或要求使用者填入內容。"
    )
    payload = {"title": event.get("title", ""), "work_context": analysis.get("regulatory_points", []),
               "source_text": text, "is_draft": source["is_draft"],
               "source_bound_candidates": department_hints(text), "problems_to_avoid": issues}
    for attempt in range(2):
        try:
            output = model(instructions=instructions, input_text=json.dumps(payload, ensure_ascii=False),
                           schema=IMPACT_SCHEMA, context_window=16384, max_output_tokens=1600,
                           request_timeout=180 if len(text) > 6000 else 90)
        except Exception:
            return analysis  # Existing candidates still go through the caller's fail-closed review.
        if not unfilled_template(json.dumps(output, ensure_ascii=False)):
            break
        payload["previous_output_problem"] = "上次只輸出未填寫的範本。請根據已確認的文字差異與原文，寫出實際作業名稱及可選檢查事項。"
    else:
        return analysis
    if not isinstance(output, dict) or not all(key in output for key in IMPACT_FIELDS):
        return analysis
    result = dict(analysis)
    result["responsible_department"] = output["responsible_department"] if output["responsible_department"] in AI_ALLOWED_DEPARTMENTS else "待確認"
    for field, required in (("departments", ("department", "reason")), ("impact_processes", ("department", "process", "impact"))):
        values = output.get(field)
        result[field] = [{key: item[key] for key in required} for item in values if isinstance(item, dict)
                         and all(isinstance(item.get(key), str) and item[key].strip() for key in required)
                         and item["department"] in AI_ALLOWED_DEPARTMENTS][:5] if isinstance(values, list) else []
    values = output.get("actions")
    result["actions"] = [item for item in values if isinstance(item, str) and item.strip()][:3] if isinstance(values, list) else []
    result["impact_refinement"] = "Same-source focused generation; all returned claims still require source-support review."
    return result
