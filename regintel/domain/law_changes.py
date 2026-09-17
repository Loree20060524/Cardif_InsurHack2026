"""Detection and retention of regulatory change signals."""

from __future__ import annotations

import hashlib
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

    material = "|".join(

        [

            clean_text(
                event.get(
                    "title",
                    ""
                )
            ),

            clean_text(
                event.get(
                    "description",
                    ""
                )
            ),

            clean_text(
                event.get(
                    "published_at",
                    ""
                )
            ),

            clean_text(
                event.get(
                    "category",
                    ""
                )
            ),
        ]
    )


    return (
        hashlib.sha256(

            material.encode(
                "utf-8",
                errors="ignore"
            )
        )
        .hexdigest()
    )


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


        if changed:

            changed[
                "detected_at"
            ] = detected_at

            changed[
                "workflow_status"
            ] = "待確認"

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
