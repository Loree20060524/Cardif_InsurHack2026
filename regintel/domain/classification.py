"""Relevance, department, process, and enforcement classification."""

from __future__ import annotations

from typing import Any

from .rules import (
    CROSS_FINANCE_SCOPE_KEYWORDS,
    CROSS_FINANCE_KEYWORDS,
    DEPARTMENT_RULES,
    INSURANCE_ENTERPRISE_KEYWORDS,
    INSURANCE_KEYWORDS,
    NON_REGULATORY_NEWS_PATTERNS,
    PROCESS_RULES,
    REGULATORY_SIGNAL_KEYWORDS,
)
from .text import clean_text, contains_any


# =========================================================
# 相關性判斷
# =========================================================

def is_relevant(
    event: dict[
        str,
        Any
    ]
) -> bool:

    source_key = event.get(
        "source_key",
        ""
    )

    # 保險局法規直接保留
    if (
        source_key
        ==
        "insurance_law"
    ):

        return True


    text = (

        f"{event.get('title', '')} "
        f"{event.get('description', '')} "
        f"{event.get('category', '')}"
    ).lower()


    return (

        contains_any(
            text,
            INSURANCE_KEYWORDS
        )

        or

        contains_any(
            text,
            CROSS_FINANCE_KEYWORDS
        )
    )


def is_management_signal(
    event: dict[str, Any]
) -> bool:
    """Keep news only when it carries an enterprise regulatory signal."""

    if event.get("source_key", "") != "reg_news":
        return True

    title = clean_text(event.get("title", "")).lower()

    if contains_any(title, NON_REGULATORY_NEWS_PATTERNS):
        return False

    has_enterprise_domain = (
        contains_any(title, INSURANCE_ENTERPRISE_KEYWORDS)
        or (
            contains_any(title, CROSS_FINANCE_KEYWORDS)
            and contains_any(title, CROSS_FINANCE_SCOPE_KEYWORDS)
        )
    )
    has_regulatory_signal = contains_any(
        title,
        REGULATORY_SIGNAL_KEYWORDS,
    )

    return has_enterprise_domain and has_regulatory_signal


# =========================================================
# 部門辨識
# =========================================================

def detect_departments(

    text: str,

    title: str = ""

) -> list[
    dict[
        str,
        str
    ]
]:

    text_lower = (
        text.lower()
    )

    title_lower = (
        title.lower()
    )


    matches: list[
        tuple[
            int,
            int,
            dict[
                str,
                str
            ]
        ]
    ] = []


    for (

        order,

        (
            department,
            keywords,
            reason
        )

    ) in enumerate(
        DEPARTMENT_RULES
    ):

        score = 0


        for keyword in keywords:

            key = keyword.lower()


            if key in title_lower:

                score += 3


            elif key in text_lower:

                score += 1


        if score > 0:

            matches.append(

                (

                    score,

                    -order,

                    {

                        "department":
                            department,

                        "reason":
                            reason,
                    }
                )
            )


    matches.sort(

        reverse=True,

        key=lambda item:
            (
                item[0],
                item[1]
            )
    )


    output: list[
        dict[
            str,
            str
        ]
    ] = []

    seen_departments: set[str] = set()

    for item in matches:

        match = item[2]

        department = match[
            "department"
        ]

        if department in seen_departments:

            continue

        seen_departments.add(
            department
        )

        output.append(
            match
        )

        if len(output) >= 5:

            break

    return output


# =========================================================
# 流程辨識
# =========================================================

def detect_processes(

    text: str,

    departments:
        list[
            dict[
                str,
                str
            ]
        ]

) -> list[
    dict[
        str,
        str
    ]
]:

    output: list[
        dict[
            str,
            str
        ]
    ] = []


    primary_department = (

        departments[0][
            "department"
        ]

        if departments

        else

        "法令遵循"
    )


    for (
        process,
        keywords
    ) in PROCESS_RULES:

        if contains_any(
            text,
            keywords
        ):

            output.append(

                {

                    "process":
                        process,

                    "department":
                        primary_department,

                    "impact":
                        (
                            "依事件內容判斷，"
                            "此作業流程可能需要"
                            "進一步確認是否受到"
                            "監理要求影響。"
                        ),
                }
            )


        if len(
            output
        ) >= 5:

            break


    if not output:

        output.append(

            {

                "process":
                    (
                        "法規適用性評估"
                        "與內部制度檢視"
                    ),

                "department":
                    primary_department,

                "impact":
                    (
                        "建議先確認監理事件"
                        "是否適用公司，再判斷"
                        "是否涉及制度、流程、"
                        "表單或系統調整。"
                    ),
            }
        )


    return output


# =========================================================
# 裁罰事件判斷
# =========================================================

def is_enforcement_event(

    event: dict[
        str,
        Any
    ],

    text: str

) -> bool:

    if (
        event.get(
            "source_key"
        )
        ==
        "fsc_penalty"
    ):

        return True


    title = clean_text(

        event.get(
            "title",
            ""
        )

    ).lower()


    strong_terms = [

        "裁罰",
        "處分案",
        "裁處案",
        "違規處分",
        "違反法令裁處",
    ]


    if contains_any(
        title,
        strong_terms
    ):

        return True


    markers = [

        "裁罰時間",
        "受裁罰之對象",
        "裁罰之法令依據",
        "違反事實理由",
        "違反之事實理由",
        "裁罰結果",
        "處分結果",
    ]


    return (

        sum(

            1

            for marker
            in markers

            if marker
            in text
        )

        >=

        2
    )
