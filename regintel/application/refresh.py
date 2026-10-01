"""Refresh and cache orchestration for regulatory data."""

from __future__ import annotations

import threading
import time
import urllib.error
from datetime import datetime, timezone
from typing import Any

from ..config import (
    AI_PROVIDER_LABEL,
    CACHE_FILE,
    CACHE_TTL_SECONDS,
    MANUAL_REFRESH_COOLDOWN_SECONDS,
    OLLAMA_MODEL,
    SOURCE_STORE_FILE,
)
from ..domain.event_selection import select_visible_events
from ..domain.law_changes import (
    detect_law_changes,
    has_law_content,
    has_supported_law_change,
    merge_recent_law_signals,
)
from ..domain.risk_analysis import rule_based_analyze_event
from ..domain.text import date_sort_key, now_iso
from ..infrastructure.http_client import classify_error, fetch_url, robots_allowed
from ..infrastructure.json_store import atomic_write_json, load_json_file
from ..infrastructure.parsers import (
    SOURCE_PARSER_VERSION,
    normalize_source_url,
    parse_source,
)
from ..source_catalog import SOURCES, SOURCE_MIN_INTERVAL_SECONDS


_cache_lock = threading.Lock()

_mem_cache: dict[str, Any] = {
    "timestamp": 0.0,
    "events": [],
    "sources": {},
}

_last_manual_refresh_ts = 0.0


# =========================================================
# Source metadata
# =========================================================

def source_metadata(
    source_key: str
) -> dict[
    str,
    Any
]:

    source = (
        SOURCES[
            source_key
        ]
    )


    return {

        "label":
            source[
                "label"
            ],

        "group_label":
            source[
                "group_label"
            ],

        "access_type":
            source[
                "access_type"
            ],

        "endpoint_host":
            urllib.parse.urlparse(
                source[
                    "url"
                ]
            ).netloc,

        "dataset_url":
            source[
                "dataset_url"
            ],

        "public_url":
            source[
                "public_url"
            ],
    }


# =========================================================
# Refresh Data
# =========================================================

def refresh_data(
    force: bool = False
) -> dict[
    str,
    Any
]:

    global _last_manual_refresh_ts


    with _cache_lock:

        now = time.time()


        if (

            not force

            and

            _mem_cache[
                "events"
            ]

            and

            now
            -
            _mem_cache[
                "timestamp"
            ]
            <
            CACHE_TTL_SECONDS

        ):

            return dict(
                _mem_cache
            )


        manual_limited = False

        manual_retry_after = 0


        if (
            force
            and
            _last_manual_refresh_ts
        ):

            elapsed = (
                now
                -
                _last_manual_refresh_ts
            )


            if (
                elapsed
                <
                MANUAL_REFRESH_COOLDOWN_SECONDS
            ):

                manual_limited = True

                manual_retry_after = max(

                    1,

                    int(

                        MANUAL_REFRESH_COOLDOWN_SECONDS
                        -
                        elapsed
                    )
                )


        if (
            force
            and
            not manual_limited
        ):

            _last_manual_refresh_ts = now


        old_store = (
            load_json_file(
                SOURCE_STORE_FILE
            )
        )


        store = {

            key:
                value

            for (
                key,
                value
            )
            in old_store.items()

            if (
                key in SOURCES
                and
                isinstance(
                    value,
                    dict
                )
            )
        }


        statuses: dict[
            str,
            Any
        ] = {}


        all_events: list[
            dict[
                str,
                Any
            ]
        ] = []


        failed_sources = 0

        network_checks = 0

        cache_reused = 0


        for (
            source_key,
            source
        ) in SOURCES.items():

            entry = store.get(
                source_key,
                {}
            )


            cached_events = (

                entry.get(
                    "events",
                    []
                )

                if isinstance(
                    entry.get(
                        "events",
                        []
                    ),
                    list
                )

                else

                []
            )


            if (
                source[
                    "kind"
                ]
                ==
                "law_xml"
            ):

                cached_signals = (

                    entry.get(
                        "signal_events",
                        []
                    )

                    if isinstance(
                        entry.get(
                            "signal_events",
                            []
                        ),
                        list
                    )

                    else
                    []
                )

                # Old snapshots included attachment-only metadata as changes.
                cached_signals = [
                    event for event in cached_signals if has_supported_law_change(event)
                ]
                entry["signal_events"] = cached_signals


            else:

                cached_signals = (
                    entry.get(
                        "signal_events",
                        cached_events
                    )
                )

                if not isinstance(
                    cached_signals,
                    list
                ):

                    cached_signals = (
                        cached_events
                    )


            last_checked_ts = float(

                entry.get(
                    "last_checked_ts",
                    0
                )
                or
                0
            )


            last_success_ts = float(

                entry.get(
                    "last_success_ts",
                    0
                )
                or
                0
            )


            parser_outdated = (

                entry.get(
                    "parser_version",
                    ""
                )

                !=

                SOURCE_PARSER_VERSION
            )


            interval = (
                SOURCE_MIN_INTERVAL_SECONDS[
                    source_key
                ]
            )


            should_fetch = True

            skip_reason = ""


            if manual_limited:

                should_fetch = False

                skip_reason = (
                    "manual_cooldown"
                )


            elif (
                not force
                and
                not parser_outdated
                and
                last_checked_ts
                and
                now
                <
                last_checked_ts
                +
                interval
            ):

                should_fetch = False

                skip_reason = (
                    "source_cooldown"
                )


            if not should_fetch:

                cache_reused += 1

                all_events.extend(
                    cached_signals
                )


                statuses[
                    source_key
                ] = {

                    **source_metadata(
                        source_key
                    ),

                    "ok":
                        bool(
                            last_success_ts
                        ),

                    "count":
                        len(
                            cached_events
                        ),

                    "signal_count":
                        len(
                            cached_signals
                        ),

                    "checked_at":
                        entry.get(
                            "checked_at",
                            ""
                        ),

                    "last_success_at":
                        entry.get(
                            "last_success_at",
                            ""
                        ),

                    "status":
                        skip_reason,

                    "using_cache":
                        True,
                }


                continue


            if not robots_allowed(
                source_key
            ):

                all_events.extend(
                    cached_signals
                )


                statuses[
                    source_key
                ] = {

                    **source_metadata(
                        source_key
                    ),

                    "ok":
                        bool(
                            last_success_ts
                        ),

                    "count":
                        len(
                            cached_events
                        ),

                    "signal_count":
                        len(
                            cached_signals
                        ),

                    "status":
                        "robots_blocked",

                    "using_cache":
                        True,

                    "error":
                        (
                            "依網站 robots.txt 設定，"
                            "此路徑目前不進行自動擷取。"
                        ),
                }


                continue


            started = (
                time.time()
            )


            try:

                (
                    status_code,
                    raw,
                    content_type,
                    meta
                ) = fetch_url(

                    source[
                        "url"
                    ],

                    (
                        ""
                        if force or parser_outdated
                        else
                        str(
                            entry.get(
                                "etag",
                                ""
                            )
                        )
                    ),

                    (
                        ""
                        if force or parser_outdated
                        else
                        str(
                            entry.get(
                                "last_modified",
                                ""
                            )
                        )
                    ),
                )


                network_checks += 1


                entry[
                    "last_checked_ts"
                ] = now


                entry[
                    "checked_at"
                ] = now_iso()


                entry[
                    "etag"
                ] = (

                    meta.get(
                        "etag"
                    )

                    or

                    entry.get(
                        "etag",
                        ""
                    )
                )


                entry[
                    "last_modified"
                ] = (

                    meta.get(
                        "last_modified"
                    )

                    or

                    entry.get(
                        "last_modified",
                        ""
                    )
                )


                if (
                    status_code
                    ==
                    304
                ):

                    all_events.extend(
                        cached_signals
                    )


                    statuses[
                        source_key
                    ] = {

                        **source_metadata(
                            source_key
                        ),

                        "ok":
                            True,

                        "count":
                            len(
                                cached_events
                            ),

                        "signal_count":
                            len(
                                cached_signals
                            ),

                        "checked_at":
                            entry[
                                "checked_at"
                            ],

                        "last_success_at":
                            entry.get(
                                "last_success_at",
                                ""
                            ),

                        "status":
                            "not_modified",

                        "using_cache":
                            True,

                        "http_code":
                            304,

                        "latency_ms":
                            round(

                                (
                                    time.time()
                                    -
                                    started
                                )

                                *

                                1000
                            ),
                    }


                else:

                    parsed_events = (
                        parse_source(

                            source_key,
                            raw,
                            content_type
                        )
                    )


                    if not parsed_events:

                        raise ValueError(
                            (
                                "來源回應成功，"
                                "但未解析到資料。"
                            )
                        )


                    if (
                        source[
                            "kind"
                        ]
                        ==
                        "law_xml"
                    ):

                        has_baseline = bool(

                            last_success_ts

                            or

                            cached_events
                        )


                        detected_changes = (
                            detect_law_changes(

                                cached_events,
                                parsed_events,
                                has_baseline
                            )
                        )


                        recent_signals = (
                            merge_recent_law_signals(

                                cached_signals,
                                detected_changes
                            )
                        )


                        entry[
                            "signal_events"
                        ] = recent_signals


                        all_events.extend(
                            recent_signals
                        )


                    else:

                        entry[
                            "signal_events"
                        ] = parsed_events


                        all_events.extend(
                            parsed_events
                        )


                    entry[
                        "events"
                    ] = parsed_events


                    entry[
                        "parser_version"
                    ] = SOURCE_PARSER_VERSION


                    entry[
                        "last_success_ts"
                    ] = now


                    entry[
                        "last_success_at"
                    ] = now_iso()


                    statuses[
                        source_key
                    ] = {

                        **source_metadata(
                            source_key
                        ),

                        "ok":
                            True,

                        "count":
                            len(
                                parsed_events
                            ),

                        "signal_count":
                            len(
                                entry.get(
                                    "signal_events",
                                    []
                                )
                            ),

                        "checked_at":
                            entry[
                                "checked_at"
                            ],

                        "last_success_at":
                            entry[
                                "last_success_at"
                            ],

                        "status":
                            "updated",

                        "using_cache":
                            False,

                        "http_code":
                            status_code,

                        "content_type":
                            content_type,

                        "latency_ms":
                            round(

                                (
                                    time.time()
                                    -
                                    started
                                )

                                *

                                1000
                            ),
                    }


            except urllib.error.HTTPError as exc:

                failed_sources += 1


                entry[
                    "last_checked_ts"
                ] = now


                entry[
                    "checked_at"
                ] = now_iso()


                all_events.extend(
                    cached_signals
                )


                statuses[
                    source_key
                ] = {

                    **source_metadata(
                        source_key
                    ),

                    "ok":
                        bool(
                            last_success_ts
                        ),

                    "count":
                        len(
                            cached_events
                        ),

                    "signal_count":
                        len(
                            cached_signals
                        ),

                    "checked_at":
                        entry[
                            "checked_at"
                        ],

                    "last_success_at":
                        entry.get(
                            "last_success_at",
                            ""
                        ),

                    "status":
                        "http_error",

                    "using_cache":
                        bool(
                            cached_signals
                        ),

                    "http_code":
                        exc.code,

                    "error":
                        (
                            f"HTTP {exc.code}："
                            "來源暫時無法取得。"
                        ),
                }


            except Exception as exc:

                failed_sources += 1


                (
                    code,
                    message
                ) = classify_error(
                    exc
                )


                entry[
                    "last_checked_ts"
                ] = now


                entry[
                    "checked_at"
                ] = now_iso()


                all_events.extend(
                    cached_signals
                )


                statuses[
                    source_key
                ] = {

                    **source_metadata(
                        source_key
                    ),

                    "ok":
                        bool(
                            last_success_ts
                        ),

                    "count":
                        len(
                            cached_events
                        ),

                    "signal_count":
                        len(
                            cached_signals
                        ),

                    "checked_at":
                        entry[
                            "checked_at"
                        ],

                    "last_success_at":
                        entry.get(
                            "last_success_at",
                            ""
                        ),

                    "status":
                        code,

                    "using_cache":
                        bool(
                            cached_signals
                        ),

                    "error":
                        message,
                }


            store[
                source_key
            ] = entry


        try:

            atomic_write_json(
                SOURCE_STORE_FILE,
                store
            )

        except Exception:

            pass


        # =================================================
        # 去重與規則分析
        # =================================================

        # Keep readable law records visible even when no verified delta exists.
        # A source snapshot is not itself a newly changed regulation.
        law_records: list[dict[str, Any]] = []
        for source_key in ("insurance_law", "law_db"):
            source_entry = store.get(source_key, {})
            records = source_entry.get("events", [])
            if isinstance(records, list):
                law_records.extend(
                    sorted(
                        (event for event in records if has_law_content(event)),
                        key=date_sort_key,
                        reverse=True,
                    )[:30]
                )

        all_events = law_records + all_events

        unique: dict[
            str,
            dict[
                str,
                Any
            ]
        ] = {}


        for event in all_events:

            if not event.get(
                "id"
            ):

                continue


            item = dict(
                event
            )

            item["url"] = normalize_source_url(item.get("url", ""))


            item[
                "analysis"
            ] = (
                rule_based_analyze_event(
                    item
                )
            )


            unique[
                item[
                    "id"
                ]
            ] = item


        events = list(
            unique.values()
        )


        visible = select_visible_events(
            events,
            limit=120,
        )


        last_success_ts = max(

            [

                float(
                    entry.get(
                        "last_success_ts",
                        0
                    )
                    or
                    0
                )

                for entry
                in store.values()

                if isinstance(
                    entry,
                    dict
                )
            ]

            or

            [0]
        )


        payload = {

            "timestamp":
                now,

            "last_sync":
                (
                    datetime
                    .fromtimestamp(
                        last_success_ts,
                        timezone.utc
                    )
                    .astimezone()
                    .isoformat(
                        timespec="seconds"
                    )

                    if last_success_ts

                    else

                    now_iso()
                ),

            "events":
                visible,

            "sources":
                statuses,

            "live_count":
                len(
                    visible
                ),

            "stale":
                bool(
                    failed_sources
                ),

            "manual_refresh_limited":
                manual_limited,

            "manual_retry_after_seconds":
                manual_retry_after,

            "refresh_summary": {

                "network_checks":
                    network_checks,

                "cache_reused":
                    cache_reused,

                "failed":
                    failed_sources,
            },

            "ai": {

                "enabled":
                    True,

                "mode":
                    "按需 AI 深度分析",

                "model":
                    OLLAMA_MODEL,

                "provider":
                    AI_PROVIDER_LABEL,
            },

            "positioning": {

                "name":
                    (
                        "保險業 AI 監理情報"
                        "與風險預警平台"
                    ),

                "goal":
                    (
                        "協助企業及早掌握"
                        "風險與監理趨勢"
                    ),
            },
        }


        _mem_cache.update(
            payload
        )


        if visible:

            try:

                atomic_write_json(
                    CACHE_FILE,
                    payload
                )

            except Exception:

                pass


        return dict(
            _mem_cache
        )
