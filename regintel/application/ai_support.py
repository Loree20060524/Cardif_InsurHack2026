"""AI cache keys, validation, and normalization."""

from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from typing import Any

from ..config import (
    AI_CACHE_FILE,
    AI_PROMPT_VERSION,
    AI_PROVIDER_LABEL,
    AI_PROVIDER,
    AI_MODEL,
    AI_THINK,
)
from ..domain.rules import AI_ALLOWED_DEPARTMENTS
from ..domain.text import clean_text, now_iso, unique_items
from ..infrastructure.json_store import load_json_file


_ai_lock = threading.Lock()


_PENDING_TEXTS = {
    "待確認",
    "無法確認",
    "資料不足",
    "資料不足，待確認",
    "官方摘要未提供",
}


def is_meaningful_ai_text(value: Any) -> bool:
    text = clean_text(value if isinstance(value, str) else "")
    normalized = text.rstrip("。．.!！")
    return bool(text and normalized not in _PENDING_TEXTS)


def has_substantive_ai_analysis(result: dict[str, Any]) -> bool:
    """Reject placeholder-only model output as a deep analysis."""
    narrative_signals = 0

    for name in ("summary", "management_summary"):
        narrative_signals += int(is_meaningful_ai_text(result.get(name, "")))

    for name in ("regulatory_points", "attention_items", "actions"):
        values = result.get(name, [])

        if isinstance(values, list) and any(
            is_meaningful_ai_text(value) for value in values
        ):
            narrative_signals += 1

    decision_signals = sum(
        int(is_meaningful_ai_text(result.get(name, "")))
        for name in ("event_nature", "risk_level", "importance")
    )

    return narrative_signals >= 2 or (
        narrative_signals >= 1 and decision_signals >= 2
    )


@contextmanager
def serialize_ai_cache():
    """Serialize read-modify-write cycles for the shared AI cache."""
    with _ai_lock:
        yield


# =========================================================
# AI cache
# =========================================================

def load_ai_cache() -> dict[
    str,
    Any
]:

    cache = (
        load_json_file(
            AI_CACHE_FILE
        )
    )


    if not isinstance(
        cache.get(
            "analyses"
        ),
        dict
    ):

        cache[
            "analyses"
        ] = {}


    if not isinstance(
        cache.get(
            "management"
        ),
        dict
    ):

        cache[
            "management"
        ] = {}


    return cache


def ai_event_cache_key(
    event: dict[
        str,
        Any
    ]
) -> str:

    material = {

        "thinking": AI_THINK,

        "prompt_version":
            AI_PROMPT_VERSION,

        "model":
            AI_MODEL,

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

        "description":
            event.get(
                "description",
                ""
            ),

        "analysis_source_text":
            event.get(
                "analysis_source_text",
                ""
            ),

        "published_at":
            event.get(
                "published_at",
                ""
            ),

        "category":
            event.get(
                "category",
                ""
            ),

        "change_status":
            event.get(
                "change_status",
                ""
            ),

        "url":
            event.get(
                "url",
                ""
            ),
    }


    if AI_PROVIDER != "ollama":
        material["provider"] = AI_PROVIDER

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


# =========================================================
# AI 結果清理
# =========================================================

def sanitize_ai_analysis(

    result: dict[
        str,
        Any
    ],

    fallback: dict[
        str,
        Any
    ]

) -> dict[
    str,
    Any
]:

    ai_is_substantive = has_substantive_ai_analysis(result)


    if not ai_is_substantive:

        result = {}

    allowed = set(
        AI_ALLOWED_DEPARTMENTS
    )


    departments: list[
        dict[
            str,
            str
        ]
    ] = []


    for item in result.get(
        "departments",
        []
    ):

        if not isinstance(
            item,
            dict
        ):

            continue


        department = clean_text(

            item.get(
                "department",
                ""
            )
        )


        reason = clean_text(

            item.get(
                "reason",
                ""
            )
        )


        if department not in allowed:

            continue


        departments.append(

            {

                "department":
                    department,

                "reason":
                    (
                        reason
                        or
                        (
                            "AI 判斷此單位可能"
                            "需要參與影響評估。"
                        )
                    ),
            }
        )


    departments = (
        departments[:5]
        or
        fallback.get(
            "departments",
            []
        )[:5]
    )


    responsible = clean_text(

        result.get(
            "responsible_department",
            ""
        )
    )


    if responsible not in allowed:

        responsible = (

            departments[0][
                "department"
            ]

            if departments

            else

            "法令遵循"
        )


    processes: list[
        dict[
            str,
            str
        ]
    ] = []


    for item in result.get(
        "impact_processes",
        []
    ):

        if not isinstance(
            item,
            dict
        ):

            continue


        process = clean_text(

            item.get(
                "process",
                ""
            )
        )


        department = clean_text(

            item.get(
                "department",
                ""
            )
        )


        impact = clean_text(

            item.get(
                "impact",
                ""
            )
        )


        if not process:

            continue


        if department not in allowed:

            department = responsible


        processes.append(

            {

                "process":
                    process,

                "department":
                    department,

                "impact":
                    (
                        impact
                        or
                        (
                            "此流程可能需要進一步"
                            "確認受影響程度。"
                        )
                    ),
            }
        )


    processes = (

        processes[:5]

        or

        fallback.get(
            "impact_processes",
            []
        )[:5]
    )


    def clean_list(
        name: str,
        limit: int = 5
    ) -> list[str]:

        values = result.get(
            name,
            []
        )


        if not isinstance(
            values,
            list
        ):

            return []


        return (
            unique_items(

                [

                    value

                    for value
                    in values

                    if isinstance(
                        value,
                        str
                    )
                    and
                    is_meaningful_ai_text(
                        value
                    )
                ]
            )[:limit]
        )


    def choose_text(
        name: str,
        default: str = "待確認"
    ) -> str:

        value = clean_text(
            result.get(
                name,
                ""
            )
        )


        if is_meaningful_ai_text(value):

            return value


        fallback_value = clean_text(
            fallback.get(
                name,
                ""
            )
        )


        return fallback_value or default


    summary = (
        choose_text(
            "summary",
            ""
        )
    )


    management_summary = choose_text(
        "management_summary",
        ""
    )


    if not management_summary:

        management_summary = (

            f"{summary} "

            f"建議由{responsible}"
            "先行確認適用性"
            "與風險影響。"
        )


    base_analysis_note = (
        (
            "AI 依據目前取得的官方來源內容進行初步監理影響分析；"
            "最終法規適用性與法律效果仍應由公司專業人員確認。"
        )
        if ai_is_substantive
        else
        (
            "AI 回傳內容不足以形成深度分析，已保留規則式備援結果；"
            "請以官方原文及人工覆核為準。"
        )
    )

    rating_note = clean_text(fallback.get("rating_note", ""))
    if rating_note:
        base_analysis_note += f" {rating_note}"


    return {

        "summary":
            summary,

        "event_nature":
            choose_text(
                "event_nature"
            ),

        "risk_level":
            choose_text(
                "risk_level"
            ),

        "importance":
            choose_text(
                "importance"
            ),

        "responsible_department":
            responsible,

        "regulatory_points":
            (
                clean_list(
                    "regulatory_points",
                    5
                )
                or
                fallback.get(
                    "regulatory_points",
                    []
                )[:5]
            ),

        "departments":
            departments,

        "impact_processes":
            processes,

        "attention_items":
            (
                clean_list(
                    "attention_items",
                    5
                )
                or
                fallback.get(
                    "attention_items",
                    []
                )[:5]
            ),

        "actions":
            (
                clean_list(
                    "actions",
                    5
                )
                or
                fallback.get(
                    "actions",
                    []
                )[:5]
            ),

        "management_summary":
            management_summary,

        "analysis_note":
            base_analysis_note,

        "analysis_mode":
            (
                "AI 深度分析"
                if ai_is_substantive
                else
                "規則備援"
            ),

        "ai_model":
            (
                AI_MODEL
                if ai_is_substantive
                else
                ""
            ),

        "ai_provider":
            (
                AI_PROVIDER_LABEL
                if ai_is_substantive
                else
                ""
            ),

        "ai_generated_at":
            (
                now_iso()
                if ai_is_substantive
                else
                ""
            ),
    }
