"""Selection rules for the events shown on the dashboard."""

from __future__ import annotations

import re
from typing import Any, Iterable

from .classification import is_management_signal, is_relevant
from .text import clean_text, date_sort_key


LAW_SOURCE_KEYS = {
    "law_db",
    "insurance_law",
}

SOURCE_GROUP_ORDER = (
    "law",
    "penalty",
    "announcement",
    "news",
)

GENERIC_LAW_ATTACHMENT_STEMS = {
    "attachment",
    "file",
    "下載檔案",
    "附件",
    "附檔",
}


def event_source_group(event: dict[str, Any]) -> str:
    source_key = event.get("source_key", "")

    if source_key in LAW_SOURCE_KEYS:
        return "law"

    if source_key == "fsc_penalty":
        return "penalty"

    if source_key == "fsc_announcement":
        return "announcement"

    return "news"


def is_generic_law_attachment(event: dict[str, Any]) -> bool:
    if event.get("source_key", "") not in LAW_SOURCE_KEYS:
        return False

    title = clean_text(event.get("title", "")).lower()
    stem = re.sub(
        r"\.(?:docx?|odt|pdf|xlsx?|ods)$",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()

    has_context = bool(
        clean_text(event.get("description", ""))
        or clean_text(event.get("category", ""))
    )

    return stem in GENERIC_LAW_ATTACHMENT_STEMS and not has_context


def _event_identity(event: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(event.get("source_key", "")),
        str(event.get("id", "")),
        str(event.get("url", "")),
        str(event.get("title", "")),
    )


def select_visible_events(
    events: Iterable[dict[str, Any]],
    limit: int | None = 120,
    minimum_per_group: int = 6,
) -> list[dict[str, Any]]:
    """Return a recent, relevant list without letting one source hide the rest."""

    if limit is not None and limit <= 0:
        return []

    ranked = sorted(
        (
            event
            for event in events
            if is_relevant(event)
            and is_management_signal(event)
            and not is_generic_law_attachment(event)
        ),
        key=date_sort_key,
        reverse=True,
    )

    selected: list[dict[str, Any]] = []
    selected_ids: set[tuple[str, str, str, str]] = set()

    if limit is None:
        for event in ranked:
            identity = _event_identity(event)
            if identity not in selected_ids:
                selected.append(event)
                selected_ids.add(identity)
        return selected

    for group in SOURCE_GROUP_ORDER:
        group_events = (
            event
            for event in ranked
            if event_source_group(event) == group
        )

        for event in list(group_events)[:minimum_per_group]:
            identity = _event_identity(event)

            if identity in selected_ids:
                continue

            selected.append(event)
            selected_ids.add(identity)

            if len(selected) >= limit:
                break

        if len(selected) >= limit:
            break

    if len(selected) < limit:
        for event in ranked:
            identity = _event_identity(event)

            if identity in selected_ids:
                continue

            selected.append(event)
            selected_ids.add(identity)

            if len(selected) >= limit:
                break

    selected.sort(key=date_sort_key, reverse=True)
    return selected
