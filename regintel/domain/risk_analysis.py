"""Rule-based regulatory risk analysis."""

from __future__ import annotations

from typing import Any

from .classification import (
    detect_departments,
    detect_processes,
    is_enforcement_event,
)
from .text import clean_text, contains_any, summarize_description, unique_items


# =========================================================
# 規則式備援分析
# =========================================================

def rule_based_analyze_event(

    event: dict[
        str,
        Any
    ]

) -> dict[
    str,
    Any
]:

    text = (

        f"{event.get('title', '')} "
        f"{event.get('description', '')} "
        f"{event.get('category', '')}"
    ).lower()


    source_key = (
        event.get(
            "source_key",
            ""
        )
    )


    title = clean_text(
        event.get(
            "title",
            ""
        )
    )


    departments = (
        detect_departments(
            text,
            title
        )
    )


    if not departments:

        departments = [

            {

                "department":
                    "法令遵循",

                "reason":
                    (
                        "建議先由法令遵循單位"
                        "確認事件適用性及與"
                        "公司業務的關聯。"
                    ),
            },


            {

                "department":
                    "風險管理",

                "reason":
                    (
                        "建議確認是否需要"
                        "納入公司既有風險"
                        "監控與評估機制。"
                    ),
            },
        ]


    processes = (
        detect_processes(
            text,
            departments
        )
    )


    attention: list[str] = []

    actions: list[str] = []

    regulatory_points: list[
        str
    ] = []


    enforcement = (
        is_enforcement_event(
            event,
            text
        )
    )


    change_status = (
        event.get(
            "change_status",
            ""
        )
    )


    if enforcement:

        event_nature = (
            "裁罰／處分"
        )


        attention += [

            (
                "此事件屬主管機關裁罰"
                "或行政處分訊號，應辨識"
                "違失事實、法令依據與"
                "可能的內部控制缺口。"
            ),

            (
                "若公司具有相同或相近"
                "業務流程，應確認是否"
                "存在類似執行落差。"
            ),
        ]


        actions += [

            (
                "比對裁罰事實與公司"
                "現行制度及作業流程，"
                "確認是否存在相同"
                "或類似風險。"
            ),

            (
                "針對主管機關指出的缺失，"
                "檢視控制措施、核准程序"
                "與證據留存是否充分。"
            ),
        ]


        regulatory_points.append(

            (
                "主管機關已出現具體"
                "裁罰或處分訊號，應優先"
                "作為風險案例參考。"
            )
        )


    elif change_status in {
        "新增",
        "異動",
    }:

        event_nature = (
            "法規異動"
        )


        attention.append(

            (
                f"系統偵測此法規為"
                f"「{change_status}」，"
                "需確認異動內容、"
                "生效時程及適用範圍。"
            )
        )


        actions.append(

            (
                "比對前後版本，確認"
                "是否需要調整內部制度、"
                "流程、表單、系統"
                "或教育訓練。"
            )
        )


        regulatory_points.append(

            (
                "法規內容已出現版本變動，"
                "應優先確認實際修正條文"
                "及生效安排。"
            )
        )


    elif source_key in {
        "law_db",
        "insurance_law",
    }:

        event_nature = (
            "法規資訊"
        )


    elif (
        source_key
        ==
        "fsc_announcement"
    ):

        event_nature = (
            "監理公告"
        )


    else:

        event_nature = (
            "監理新聞"
        )


    department_set = {

        item[
            "department"
        ]

        for item
        in departments
    }


    if (

        department_set
        .intersection(
            {
                "資訊安全／個資治理",
                "資訊科技",
            }
        )

        and

        contains_any(

            text,

            [
                "個資",
                "個人資料",
                "資安",
                "資訊安全",
                "雲端",
                "存取",
                "權限",
            ]
        )
    ):

        attention.append(

            (
                "可能涉及個人資料、"
                "系統權限、資訊安全"
                "或資料保存要求。"
            )
        )


        actions.append(

            (
                "盤點相關資訊系統、"
                "資料流程、權限設定"
                "與紀錄留存機制。"
            )
        )


    if (

        "風險管理"
        in
        department_set

        and

        contains_any(

            text,

            [
                "委外",
                "第三方",
                "外包",
                "供應商",
            ]
        )
    ):

        attention.append(

            (
                "可能影響委外管理、"
                "供應商審查或第三方"
                "風險管理要求。"
            )
        )


        actions.append(

            (
                "檢視相關委外契約、"
                "供應商評估與"
                "持續監督機制。"
            )
        )


    if (

        "業務通路／行銷"
        in
        department_set

        and

        contains_any(

            text,

            [
                "招攬",
                "適合度",
                "公平待客",
                "業務員",
                "銷售",
            ]
        )
    ):

        attention.append(

            (
                "可能影響業務招攬、"
                "商品適合度、客戶確認"
                "或第一線銷售流程。"
            )
        )


        actions.append(

            (
                "檢視銷售流程、通路話術、"
                "客戶確認及教育訓練內容。"
            )
        )


    if (

        department_set
        .intersection(
            {
                "理賠",
                "客戶服務／申訴",
            }
        )

        and

        contains_any(

            text,

            [
                "理賠",
                "申訴",
                "客服",
                "消費爭議",
                "保險金",
            ]
        )
    ):

        attention.append(

            (
                "可能影響理賠、客戶服務"
                "或申訴處理作業。"
            )
        )


        actions.append(

            (
                "抽查近期相關案件，"
                "確認作業規範、文件"
                "與實際執行是否一致。"
            )
        )


    if (

        "投資／資產負債管理"
        in
        department_set

        and

        contains_any(

            text,

            [
                "投資",
                "國外投資",
                "有價證券",
                "投資限額",
                "資產配置",
            ]
        )
    ):

        attention.append(

            (
                "可能影響保險資金運用、"
                "投資限額或相關"
                "投資管理制度。"
            )
        )


        actions.append(

            (
                "確認投資規範、限額、"
                "授權與現行投資部位"
                "是否受到影響。"
            )
        )


    if (

        department_set
        .intersection(
            {
                "風險管理",
                "財務／會計",
                "商品／精算",
            }
        )

        and

        contains_any(

            text,

            [
                "清償能力",
                "資本適足",
                "風險資本",
                "自有資本",
                "準備金",
                "ifrs17",
                "tis",
                "ics",
            ]
        )
    ):

        attention.append(

            (
                "可能影響資本適足、"
                "風險資本、準備金"
                "或財務衡量方式。"
            )
        )


        actions.append(

            (
                "由風險管理、財務"
                "與精算相關單位比對"
                "現行計算方法、參數、"
                "報表與申報流程。"
            )
        )


    if (

        "商品／精算"
        in
        department_set

        and

        contains_any(

            text,

            [
                "保險商品",
                "商品設計",
                "商品條款",
                "保單條款",
                "保障內容",
            ]
        )
    ):

        attention.append(

            (
                "可能涉及商品設計、"
                "保單條款、保障範圍"
                "或對外說明內容。"
            )
        )


        actions.append(

            (
                "檢視相關商品條款、"
                "核保規則與對客"
                "說明文件是否需要調整。"
            )
        )


    attention = (
        unique_items(
            attention
        )
    )


    if not attention:

        attention = [

            (
                "建議確認事件的適用範圍、"
                "發布日期、生效日期及"
                "與公司業務的關聯。"
            )
        ]


    actions = (
        unique_items(
            actions
        )
    )


    if not actions:

        actions = [

            (
                "由法令遵循單位完成"
                "初步適用性確認，再決定"
                "是否需要跨部門影響評估。"
            )
        ]


    description = clean_text(
        event.get(
            "description",
            ""
        )
    )


    if description:

        summary = (
            summarize_description(
                description
            )
        )

    else:

        summary = (

            f"偵測到「"
            f"{title or '監理事件'}」，"

            "建議確認適用範圍及"
            "與公司業務的關聯。"
        )


    return {

        "summary":
            summary,

        "event_nature":
            event_nature,

        "risk_level":
            "待確認",

        "importance":
            "待確認",

        "responsible_department":
            (
                departments[0][
                    "department"
                ]
                if departments
                else
                "法令遵循"
            ),

        "regulatory_points":
            regulatory_points[:5],

        "departments":
            departments[:5],

        "impact_processes":
            processes[:5],

        "attention_items":
            attention[:5],

        "actions":
            actions[:5],

        "management_summary":
            (
                f"{summary} 建議由"
                f"{departments[0]['department'] if departments else '法令遵循'}"
                "先完成適用性與"
                "風險影響確認。"
            ),

        "analysis_note":
            (
                "目前顯示規則式備援分析；"
                "本機 AI 完成後會更新為"
                "深度分析。"
            ),

        "analysis_mode":
            "規則備援",

        "ai_model":
            "",

        "ai_provider":
            "",
    }


def apply_regulatory_amendment_triage(
    event: dict[str, Any],
    analysis: dict[str, Any],
) -> dict[str, Any]:
    """Provide a conservative initial rating for substantive rule amendments.

    This is a triage default, not a legal conclusion. Specific AI ratings take
    precedence; the fallback is used only when the model returns a placeholder.
    """
    description = clean_text(event.get("description", ""))
    if (
        event.get("category") == "法規命令"
        and event.get("change_status") == "異動"
        and len(description) >= 40
    ):
        analysis = dict(analysis)
        analysis["risk_level"] = "中"
        analysis["importance"] = "重要"
        analysis["rating_note"] = (
            "風險與重要性採法規異動的初步分級；"
            "實際影響仍須比對修正條文及適用範圍。"
        )
    return analysis
