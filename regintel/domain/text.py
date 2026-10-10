"""Text, date, and collection normalization for domain data."""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any


# =========================================================
# 工具函式
# =========================================================

def now_iso() -> str:

    return (
        datetime
        .now(
            timezone.utc
        )
        .astimezone()
        .isoformat(
            timespec="seconds"
        )
    )


def clean_text(
    value: Any
) -> str:

    if value is None:

        return ""

    text = (
        html.unescape(
            str(value)
        )
    )

    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


def normalize_document_text(value: str) -> str:
    """Normalize public source text while preserving paragraph breaks."""
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    return "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in value.split("\n")).strip()


def decode_bytes(
    data: bytes,
    content_type: str = ""
) -> str:

    encodings: list[str] = []

    match = re.search(
        r"charset=([\w-]+)",
        content_type,
        re.I
    )

    if match:

        encodings.append(
            match.group(1)
        )

    encodings += [

        "utf-8-sig",
        "utf-8",
        "big5",
        "cp950",
    ]

    for encoding in encodings:

        try:

            return data.decode(
                encoding
            )

        except Exception:

            pass

    return data.decode(
        "utf-8",
        errors="replace"
    )


def local_tag(
    tag: str
) -> str:

    return tag.rsplit(
        "}",
        1
    )[-1]


def parse_date(
    value: str
) -> str:

    value = clean_text(
        value
    )

    if not value:

        return ""

    try:

        dt = (
            parsedate_to_datetime(
                value
            )
        )

        return (
            dt
            .astimezone()
            .isoformat(
                timespec="seconds"
            )
        )

    except Exception:

        pass


    for fmt in (

        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%Y%m%d",
    ):

        try:

            dt = (
                datetime.strptime(
                    value[:10],
                    fmt
                )
            )

            return (
                dt
                .astimezone()
                .isoformat(
                    timespec="seconds"
                )
            )

        except Exception:

            pass


    match = re.search(
        (
            r"(?<!\d)"
            r"(\d{2,3})"
            r"[./-]"
            r"(\d{1,2})"
            r"[./-]"
            r"(\d{1,2})"
            r"(?!\d)"
        ),
        value
    )


    if match:

        year, month, day = map(
            int,
            match.groups()
        )

        if year < 1911:

            year += 1911

        try:

            return (
                datetime(
                    year,
                    month,
                    day
                )
                .astimezone()
                .isoformat(
                    timespec="seconds"
                )
            )

        except Exception:

            pass


    return value


def date_sort_key(
    event: dict[
        str,
        Any
    ]
) -> float:

    value = (
        event.get(
            "published_at",
            ""
        )
    )

    if not value:

        return 0.0

    try:

        return (
            datetime
            .fromisoformat(
                str(value)
                .replace(
                    "Z",
                    "+00:00"
                )
            )
            .timestamp()
        )

    except Exception:

        return 0.0

def unique_items(
    values: list[Any]
) -> list[str]:

    output: list[str] = []

    seen: set[str] = set()

    for value in values:

        text = clean_text(
            value
        )

        if (
            text
            and
            text not in seen
        ):

            seen.add(
                text
            )

            output.append(
                text
            )

    return output


def contains_any(
    text: str,
    keywords: list[str]
) -> bool:

    lower = text.lower()

    return any(

        keyword.lower()
        in
        lower

        for keyword
        in keywords
    )


def summarize_description(
    description: str,
    limit: int = 320
) -> str:

    description = clean_text(
        description
    )

    if (
        len(description)
        <=
        limit
    ):

        return description


    candidate = (
        description[:limit]
    )

    cut = max(

        candidate.rfind(
            "。"
        ),

        candidate.rfind(
            "；"
        ),

        candidate.rfind(
            "！"
        ),

        candidate.rfind(
            "？"
        ),
    )


    if cut >= 120:

        return (
            candidate[
                :cut + 1
            ]
        )


    return (
        candidate.rstrip()
        +
        "…"
    )
