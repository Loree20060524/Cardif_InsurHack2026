"""Detection and retention of regulatory change signals."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import LAW_SIGNAL_RETENTION_DAYS
from .text import clean_text, now_iso


# =========================================================
# 法規異動偵測
# =========================================================

def law_entity_key(
    event: dict[
        str,
        Any
    ]
) -> str:

    material = (

        f"{event.get('source_key', '')}|"

        f"{clean_text(
            event.get(
                'title',
                ''
            )
        ).lower()}"
    )


    return (
        hashlib.sha1(
            material.encode(
                "utf-8",
                errors="ignore"
            )
        )
        .hexdigest()
    )


def law_fingerprint(
    event: dict[
        str,
        Any
    ]
) -> str:

    # A metadata correction does not establish a change in legal content.
    material = clean_text(event.get("description", ""))


    return (
        hashlib.sha256(

            material.encode(
                "utf-8",
                errors="ignore"
            )
        )
        .hexdigest()
    )


def has_law_content(event: dict[str, Any]) -> bool:
    """A readable regulation is not an attachment title or empty record."""
    title = clean_text(event.get("title", ""))
    description = clean_text(event.get("description", ""))
    return bool(description) and not bool(
        re.search(r"\.(?:pdf|docx?|odt|xlsx?|ods)$", title, re.I)
    )


def has_supported_law_change(event: dict[str, Any]) -> bool:
    """Old signals without a recorded content basis must not imply a change."""
    return has_law_content(event) and bool(clean_text(event.get("change_basis", "")))


def detect_law_changes(

    previous_events:
        list[
            dict[
                str,
                Any
            ]
        ],

    current_events:
        list[
            dict[
                str,
                Any
            ]
        ],

    has_baseline: bool

) -> list[
    dict[
        str,
        Any
    ]
]:

    if not has_baseline:

        return []


    old_map = {

        law_entity_key(
            event
        ):
            event

        for event
        in previous_events
    }


    changes: list[
        dict[
            str,
            Any
        ]
    ] = []


    detected_at = now_iso()


    for event in current_events:

        if not has_law_content(event):
            continue

        key = law_entity_key(
            event
        )

        previous = old_map.get(
            key
        )


        changed: (
            dict[
                str,
                Any
            ]
            |
            None
        ) = None


        if previous is None:

            changed = dict(
                event
            )

            changed[
                "change_status"
            ] = "新增"


        elif not has_law_content(previous):

            # Newly parsed text alone is not proof of a new requirement.
            continue


        elif (
            law_fingerprint(
                previous
            )
            !=
            law_fingerprint(
                event
            )
        ):

            changed = dict(
                event
            )

            changed[
                "change_status"
            ] = "異動"

            changed["change_basis"] = "官方來源文字變動；實際條文差異待核對"


        if changed:

            if "change_basis" not in changed:
                changed["change_basis"] = "新增可讀法規資料；適用性待核對"

            changed[
                "detected_at"
            ] = detected_at

            changes.append(
                changed
            )


    return changes


def parse_detected_at(
    value: Any
) -> datetime | None:

    try:

        dt = datetime.fromisoformat(

            str(value).replace(
                "Z",
                "+00:00"
            )
        )


        if dt.tzinfo is None:

            dt = dt.replace(
                tzinfo=timezone.utc
            )


        return dt


    except Exception:

        return None


def merge_recent_law_signals(

    old_signals:
        list[
            dict[
                str,
                Any
            ]
        ],

    new_signals:
        list[
            dict[
                str,
                Any
            ]
        ]

) -> list[
    dict[
        str,
        Any
    ]
]:

    cutoff = (

        datetime.now(
            timezone.utc
        )

        -

        timedelta(
            days=
                LAW_SIGNAL_RETENTION_DAYS
        )
    )


    combined: dict[
        str,
        dict[
            str,
            Any
        ]
    ] = {}


    for event in (

        old_signals
        +
        new_signals
    ):

        if not has_supported_law_change(event):
            continue

        detected = (
            parse_detected_at(
                event.get(
                    "detected_at",
                    ""
                )
            )
        )


        if (
            detected is None
            or
            detected
            .astimezone(
                timezone.utc
            )
            <
            cutoff
        ):

            continue


        key = (

            f"{law_entity_key(event)}|"
            f"{event.get(
                'change_status',
                ''
            )}"
        )


        combined[
            key
        ] = event


    result = list(
        combined.values()
    )


    result.sort(

        key=lambda event:

            parse_detected_at(
                event.get(
                    "detected_at",
                    ""
                )
            )

            or

            datetime.min.replace(
                tzinfo=timezone.utc
            ),

        reverse=True
    )


    return result[:120]
