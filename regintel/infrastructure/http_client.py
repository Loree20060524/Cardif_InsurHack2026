"""Rate-limited HTTP and robots.txt adapter."""

from __future__ import annotations

import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from typing import Any

from ..config import (
    HOST_MIN_GAP_SECONDS,
    MAX_RESPONSE_BYTES,
    REQUEST_TIMEOUT,
    SSL_CONTEXT,
    USER_AGENT,
)
from ..domain.text import clean_text, decode_bytes
from ..source_catalog import SOURCES


_last_host_request_ts: dict[str, float] = {}

_robots_cache: dict[str, tuple[float, bool]] = {}


# =========================================================
# HTTP 抓取
# =========================================================

def fetch_url(
    url: str,
    etag: str = "",
    last_modified: str = ""
):

    parsed = (
        urllib.parse.urlparse(
            url
        )
    )

    host = (
        parsed.netloc.lower()
    )

    last_request = (
        _last_host_request_ts
        .get(
            host,
            0.0
        )
    )

    wait = (
        HOST_MIN_GAP_SECONDS
        -
        (
            time.time()
            -
            last_request
        )
    )


    if wait > 0:

        time.sleep(
            wait
        )


    _last_host_request_ts[
        host
    ] = time.time()


    headers = {

        "User-Agent":
            USER_AGENT,

        "Accept":
            (
                "application/xml,"
                "text/xml,"
                "application/rss+xml,"
                "text/html,"
                "*/*;q=0.8"
            ),

        "Accept-Encoding":
            "identity",
    }


    if etag:

        headers[
            "If-None-Match"
        ] = etag


    if last_modified:

        headers[
            "If-Modified-Since"
        ] = last_modified


    request = (
        urllib.request.Request(
            url,
            headers=headers
        )
    )


    try:

        with urllib.request.urlopen(
            request,
            timeout=REQUEST_TIMEOUT,
            context=SSL_CONTEXT
        ) as response:

            data = response.read(
                MAX_RESPONSE_BYTES
                +
                1
            )

            if (
                len(data)
                >
                MAX_RESPONSE_BYTES
            ):

                raise ValueError(
                    "來源回應超過允許大小。"
                )


            return (

                getattr(
                    response,
                    "status",
                    200
                ),

                data,

                response.headers.get(
                    "Content-Type",
                    ""
                ),

                {

                    "etag":
                        response.headers.get(
                            "ETag",
                            ""
                        ),

                    "last_modified":
                        response.headers.get(
                            "Last-Modified",
                            ""
                        ),
                },
            )


    except urllib.error.HTTPError as exc:

        if exc.code == 304:

            return (

                304,

                b"",

                "",

                {

                    "etag":
                        (
                            exc.headers.get(
                                "ETag",
                                etag
                            )
                            if exc.headers
                            else etag
                        ),

                    "last_modified":
                        (
                            exc.headers.get(
                                "Last-Modified",
                                last_modified
                            )
                            if exc.headers
                            else last_modified
                        ),
                },
            )


        raise


# =========================================================
# robots.txt
# =========================================================

def robots_allowed(
    source_key: str,
    url: str = "",
) -> bool:

    source = (
        SOURCES[
            source_key
        ]
    )


    if (
        source[
            "kind"
        ]
        !=
        "announcement_html"
        and not url
    ):

        return True


    request_url = url or source["url"]
    parsed = urllib.parse.urlparse(request_url)


    robots_url = (

        f"{parsed.scheme}://"
        f"{parsed.netloc}/"
        "robots.txt"
    )


    now = time.time()


    cached = (
        _robots_cache.get(
            request_url
        )
    )


    if (
        cached
        and
        now
        -
        cached[0]
        <
        6
        *
        3600
    ):

        return cached[1]


    allowed = True


    try:

        (
            status,
            data,
            content_type,
            _
        ) = fetch_url(
            robots_url
        )


        if (
            status == 200
            and
            data
        ):

            parser = (
                urllib.robotparser
                .RobotFileParser()
            )

            parser.set_url(
                robots_url
            )

            parser.parse(

                decode_bytes(
                    data,
                    content_type
                )
                .splitlines()
            )

            allowed = (
                parser.can_fetch(
                    USER_AGENT,
                    request_url
                )
            )


    except Exception:

        allowed = True


    _robots_cache[
        request_url
    ] = (
        now,
        allowed
    )


    return allowed


# =========================================================
# 錯誤分類
# =========================================================

def classify_error(
    exc: Exception
) -> tuple[
    str,
    str
]:

    if isinstance(
        exc,
        urllib.error.URLError
    ):

        reason = (
            exc.reason
        )


        if (
            isinstance(
                reason,
                ssl.SSLCertVerificationError
            )
            or
            "CERTIFICATE_VERIFY_FAILED"
            in
            str(reason)
        ):

            return (
                "ssl_error",
                "SSL 憑證驗證失敗。"
            )


        if (
            isinstance(
                reason,
                socket.timeout
            )
            or
            "timed out"
            in
            str(reason).lower()
        ):

            return (
                "timeout",
                "來源連線逾時。"
            )


        if isinstance(
            reason,
            socket.gaierror
        ):

            return (
                "dns_error",
                "DNS 網域解析失敗。"
            )


        return (

            "network_error",

            clean_text(
                str(reason)
            )[:180],
        )


    if isinstance(
        exc,
        ET.ParseError
    ):

        return (
            "parse_error",
            "XML 資料解析失敗。"
        )


    return (

        "error",

        clean_text(
            str(exc)
        )[:180],
    )
