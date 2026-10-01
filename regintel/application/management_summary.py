"""AI-assisted management summary generation."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..config import (
    AI_CACHE_FILE,
    AI_PROMPT_VERSION,
    AI_PROVIDER_LABEL,
    OLLAMA_MODEL,
)
from ..domain.schemas import MANAGEMENT_SUMMARY_SCHEMA
from ..domain.text import clean_text, now_iso, unique_items
from ..infrastructure.json_store import atomic_write_json
from ..infrastructure.ollama import call_ollama_structured_json
from .ai_support import (
    load_ai_cache,
    serialize_ai_cache,
)
from .event_analysis import has_analyzable_source_text


# =========================================================
# 管理摘要
# =========================================================

def has_substantive_management_summary(result: Any) -> bool:
    return isinstance(result, dict) and len(clean_text(result.get("summary", ""))) >= 15


def management_cache_key(

    events: list[
        dict[
            str,
            Any
        ]
    ]

) -> str:

    material = {

        "prompt_version":
            AI_PROMPT_VERSION,

        "model":
            OLLAMA_MODEL,

        "events": [

            {

                "id":
                    event.get(
                        "id",
                        ""
                    ),

                "title":
                    event.get(
                        "title",
                        ""
                    ),

                "published_at":
                    event.get(
                        "published_at",
                        ""
                    ),

                "description":
                    clean_text(
                        event.get(
                            "description",
                            ""
                        )
                    )[:1800],
            }

            for event
            in events[:7]
        ],
    }


    return (
        hashlib.sha256(

            json.dumps(
                material,
                ensure_ascii=False,
                sort_keys=True
            ).encode(
                "utf-8"
            )
        )
        .hexdigest()
    )


def generate_management_summary_ai(

    events: list[
        dict[
            str,
            Any
        ]
    ]

) -> dict[
    str,
    Any
]:

    # Headlines without official body text must not become AI evidence.
    events = [
        event for event in events
        if has_analyzable_source_text(event.get("description", ""))
    ][:7]

    if not events:

        return {

            "headline":
                "目前尚無監理事件",

            "summary":
                (
                    "目前沒有足夠資料"
                    "產生管理摘要。"
                ),

            "risk_outlook":
                "待確認",

            "priority_events":
                [],

            "priority_actions":
                [],

            "trend_observations":
                [],

            "management_note":
                (
                    "待取得可分析的官方原文後"
                    "再進行評估。"
                ),

            "analysis_mode":
                "規則備援",
        }


    cache_key = (
        management_cache_key(
            events
        )
    )


    with serialize_ai_cache():

        cache = (
            load_ai_cache()
        )


        cached = cache[
            "management"
        ].get(
            cache_key
        )


        if isinstance(
            cached,
            dict
        ) and has_substantive_management_summary(cached):

            return cached


        event_texts: list[
            str
        ] = []


        for (
            index,
            event
        ) in enumerate(

            events[:7],

            start=1
        ):

            description = (
                clean_text(
                    event.get(
                        "description",
                        ""
                    )
                )[:1800]
            )


            event_texts.append(

                (
                    f"事件 {index}\n"

                    f"標題："
                    f"{event.get('title', '')}\n"

                    f"來源："
                    f"{event.get('source', '')}\n"

                    f"日期："
                    f"{event.get('published_at', '')}\n"

                    f"類型："
                    f"{event.get('analysis', {}).get('event_nature', '')}\n"

                    f"內容："
                    f"{description or '未提供'}"
                )
            )


        instructions = (

            "你是台灣保險公司高階管理層"
            "的監理情報與風險預警助手。"

            "只能依據提供的官方監理事件"
            "產生管理摘要，不得捏造法規要求。"

            "目標是協助管理階層及早掌握"
            "近期風險與監理趨勢，"
            "不是建立任務追蹤。"

            "summary 必須是主管可直接閱讀的"
            "繁體中文自然語言摘要，"
            "不得輸出 JSON 字串。"

            "priority_events 請挑選真正值得"
            "管理階層優先關注的事件並說明原因。"

            "priority_actions 請提供管理層"
            "可考慮的因應方向，但不要產生"
            "任務狀態、完成期限或執行進度。"

            "trend_observations 僅就提供的"
            "少量近期事件歸納重複出現的主題；"
            "不足以證明長期趨勢時請明說。"

            "全部使用繁體中文。"
        )


        result = (
            call_ollama_structured_json(

                instructions=
                    instructions,

                input_text=
                    (
                        "\n\n".join(
                            event_texts
                        )
                        +
                        "\n\n"
                        "請產生本期管理摘要"
                        "與近期主題觀察。"
                    ),

                schema=
                    MANAGEMENT_SUMMARY_SCHEMA,
            )
        )


        if not has_substantive_management_summary(result):
            return {
                "headline": "管理摘要待確認",
                "summary": "模型未產生足夠的管理摘要內容，請核對官方原文後再試。",
                "risk_outlook": "待確認",
                "priority_events": [],
                "priority_actions": [],
                "trend_observations": [],
                "management_note": f"本次選用 {len(events)} 件具可讀內容的事件，但模型結果不足，不標示為深度分析。",
                "analysis_mode": "規則備援",
            }


        priority_events = []


        for item in result.get(
            "priority_events",
            []
        ):

            if not isinstance(
                item,
                dict
            ):

                continue


            title = clean_text(

                item.get(
                    "title",
                    ""
                )
            )


            reason = clean_text(

                item.get(
                    "reason",
                    ""
                )
            )


            if title:

                priority_events.append(

                    {

                        "title":
                            title,

                        "reason":
                            (
                                reason
                                or
                                (
                                    "建議管理階層確認"
                                    "此事件對公司的"
                                    "實際影響。"
                                )
                            ),
                    }
                )


        summary = {

            "headline":
                (
                    clean_text(
                        result.get(
                            "headline",
                            ""
                        )
                    )
                    or
                    "本期監理事件管理摘要"
                ),

            "summary":
                (
                    clean_text(
                        result.get(
                            "summary",
                            ""
                        )
                    )
                    or
                    (
                        "本期監理資訊已完成"
                        "初步整理，建議優先確認"
                        "重要事件與公司業務"
                        "的實際關聯。"
                    )
                ),

            "risk_outlook":
                (
                    clean_text(
                        result.get(
                            "risk_outlook",
                            "待確認"
                        )
                    )
                    or
                    "待確認"
                ),

            "priority_events":
                priority_events[:5],

            "priority_actions":
                unique_items(

                    [

                        value

                        for value
                        in result.get(
                            "priority_actions",
                            []
                        )

                        if isinstance(
                            value,
                            str
                        )
                    ]
                )[:5],

            "trend_observations":
                unique_items(

                    [

                        value

                        for value
                        in result.get(
                            "trend_observations",
                            []
                        )

                        if isinstance(
                            value,
                            str
                        )
                    ]
                )[:5],

            "management_note":
                (
                    clean_text(
                        result.get(
                            "management_note",
                            ""
                        )
                    )
                    or
                    (
                        "本摘要供管理階層快速掌握"
                        "監理風險與趨勢，最終適用性"
                        "仍需由相關專業單位確認。"
                    )
                ) + f" 本次僅分析 {len(events)} 件具可讀官方內容的近期事件。",

            "analysis_mode":
                "AI 深度分析",

            "ai_model":
                OLLAMA_MODEL,

            "ai_provider":
                AI_PROVIDER_LABEL,

            "ai_generated_at":
                now_iso(),
        }


        cache[
            "management"
        ][
            cache_key
        ] = summary


        try:

            atomic_write_json(
                AI_CACHE_FILE,
                cache
            )

        except Exception:

            pass


        return summary
