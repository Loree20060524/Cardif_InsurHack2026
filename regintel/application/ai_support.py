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
    OLLAMA_MODEL,
)
from ..domain.rules import AI_ALLOWED_DEPARTMENTS
from ..domain.text import clean_text, now_iso, unique_items
from ..infrastructure.json_store import load_json_file


_ai_lock = threading.Lock()


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

        "prompt_version":
            AI_PROMPT_VERSION,

        "model":
            OLLAMA_MODEL,

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

            "法令遵循部"
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
                ]
            )[:limit]
        )


    summary = (

        clean_text(
            result.get(
                "summary",
                ""
            )
        )

        or

        fallback.get(
            "summary",
            ""
        )
    )


    management_summary = clean_text(

        result.get(
            "management_summary",
            ""
        )
    )


    if not management_summary:

        management_summary = (

            f"{summary} "

            f"建議由{responsible}"
            "先行確認適用性"
            "與風險影響。"
        )


    return {

        "summary":
            summary,

        "event_nature":
            (
                clean_text(
                    result.get(
                        "event_nature",
                        "待確認"
                    )
                )
                or
                "待確認"
            ),

        "risk_level":
            (
                clean_text(
                    result.get(
                        "risk_level",
                        "待確認"
                    )
                )
                or
                "待確認"
            ),

        "importance":
            (
                clean_text(
                    result.get(
                        "importance",
                        "待確認"
                    )
                )
                or
                "待確認"
            ),

        "handling_deadline":
            (
                clean_text(
                    result.get(
                        "handling_deadline",
                        "待確認"
                    )
                )
                or
                "待確認"
            ),

        "responsible_department":
            responsible,

        "regulatory_points":
            clean_list(
                "regulatory_points",
                5
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
            (
                "AI 依據目前取得的官方來源"
                "內容進行初步監理影響分析；"
                "最終法規適用性與法律效果"
                "仍應由公司專業人員確認。"
            ),

        "analysis_mode":
            "AI 深度分析",

        "ai_model":
            OLLAMA_MODEL,

        "ai_provider":
            AI_PROVIDER_LABEL,

        "ai_generated_at":
            now_iso(),
    }
