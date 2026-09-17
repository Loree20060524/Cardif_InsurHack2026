"""AI-assisted analysis of a single regulatory event."""

from __future__ import annotations

from typing import Any

from ..config import AI_CACHE_FILE, AI_MAX_INPUT_CHARS
from ..domain.risk_analysis import rule_based_analyze_event
from ..domain.rules import AI_ALLOWED_DEPARTMENTS
from ..domain.schemas import AI_ANALYSIS_SCHEMA
from ..domain.text import clean_text
from ..infrastructure.json_store import atomic_write_json
from ..infrastructure.ollama import call_ollama_structured_json
from .ai_support import (
    ai_event_cache_key,
    load_ai_cache,
    sanitize_ai_analysis,
    serialize_ai_cache,
)


# =========================================================
# 單一事件 AI 分析
# =========================================================

def analyze_event_with_ai(

    event: dict[
        str,
        Any
    ]

) -> dict[
    str,
    Any
]:

    fallback = (
        rule_based_analyze_event(
            event
        )
    )


    cache_key = (
        ai_event_cache_key(
            event
        )
    )


    with serialize_ai_cache():

        cache = (
            load_ai_cache()
        )


        cached = cache[
            "analyses"
        ].get(
            cache_key
        )


        if isinstance(
            cached,
            dict
        ):

            return cached


        description = clean_text(

            event.get(
                "description",
                ""
            )
        )


        if (
            len(description)
            >
            AI_MAX_INPUT_CHARS
        ):

            description = (

                description[
                    :AI_MAX_INPUT_CHARS
                ]

                +

                "…"
            )


        departments_text = (
            "、".join(
                AI_ALLOWED_DEPARTMENTS
            )
        )


        instructions = (

            "你是台灣保險公司的監理法規"
            "與風險預警分析助手。"

            "你的任務不是建立工作派送"
            "或進度追蹤系統，而是協助企業"
            "及早掌握風險與監理趨勢。"

            "只能依據使用者提供的官方監理"
            "事件內容分析，不得自行補寫"
            "未出現在來源中的法令義務、"
            "日期、罰則或事實。"

            "若來源不足以確認某項內容，"
            "請明確寫『待確認』。"

            "請區分一般新聞、監理公告、"
            "法規資訊、法規異動與裁罰處分。"

            "風險程度是指此監理資訊對"
            "保險公司可能造成的法遵、營運、"
            "財務、系統或消費者權益影響。"

            "不要因為文章主題看起來嚴重"
            "就直接判定高風險；應依據法規"
            "強制性、影響範圍、制度流程"
            "修改需求、裁罰暴露與急迫性判斷。"

            "受影響部門只能從以下企業職能選擇："

            f"{departments_text}。"

            "impact_processes 請辨識可能"
            "受影響的企業作業流程，"
            "並說明影響原因。"

            "actions 請提供改善建議與因應措施，"
            "但不要建立任務狀態、完成率、"
            "執行追蹤、逾期管理或責任人派送。"

            "handling_deadline 若官方來源"
            "未提供法定期限，請寫『待確認』；"
            "不得把公司內部建議時程"
            "描述成法定期限。"

            "全部輸出繁體中文，內容要簡潔、"
            "專業、可供企業初步研判。"
        )


        input_text = (

            f"來源分類："
            f"{event.get('source', '')}\n"

            f"來源細項："
            f"{event.get('source_detail', '')}\n"

            f"標題："
            f"{event.get('title', '')}\n"

            f"發布日期："
            f"{event.get('published_at', '')}\n"

            f"類別："
            f"{event.get('category', '')}\n"

            f"系統偵測異動："
            f"{event.get('change_status', '無')}\n"

            f"官方內容：\n"
            f"{description or '官方摘要未提供'}"

            "\n\n"

            "請完成：監理重點摘要、事件性質、"
            "風險程度、重要性、建議處理時程、"
            "主要責任部門、受影響部門與理由、"
            "可能受影響流程、風險提醒與注意事項、"
            "改善建議與因應措施，"
            "以及一段主管摘要。"
        )


        result = (
            call_ollama_structured_json(

                instructions=
                    instructions,

                input_text=
                    input_text,

                schema=
                    AI_ANALYSIS_SCHEMA,
            )
        )


        analysis = (
            sanitize_ai_analysis(
                result,
                fallback
            )
        )


        cache[
            "analyses"
        ][
            cache_key
        ] = analysis


        try:

            atomic_write_json(
                AI_CACHE_FILE,
                cache
            )

        except Exception:

            pass


        return analysis
