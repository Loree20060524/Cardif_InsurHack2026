"""Source payload parsers and normalized event construction."""

from __future__ import annotations

import hashlib
import html
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any

from ..domain.text import clean_text, decode_bytes, local_tag, parse_date
from ..source_catalog import SOURCES


SOURCE_PARSER_VERSION = "regintel-source-parser-v2-law-parent-dates"


def normalize_source_url(value: str) -> str:
    """Undo entity encoding left behind by nested XML/HTML source feeds."""
    url = str(value or "").strip()
    for _ in range(3):
        decoded = html.unescape(url)
        if decoded == url:
            break
        url = decoded
    return url


# =========================================================
# Event normalization
# =========================================================

def event_id(
    source_key: str,
    title: str,
    link: str,
    date: str
) -> str:

    seed = (

        f"{source_key}|"
        f"{title}|"
        f"{link}|"
        f"{date}"
    ).encode(
        "utf-8",
        errors="ignore"
    )


    return (
        hashlib.sha1(
            seed
        )
        .hexdigest()[:16]
    )


def normalize_event(

    source_key: str,

    title: str,

    link: str,

    description: str,

    date: str,

    category: str = ""

) -> dict[
    str,
    Any
]:

    source = (
        SOURCES[
            source_key
        ]
    )


    title = (
        clean_text(
            title
        )
        or
        "未命名監理資訊"
    )


    date = (
        parse_date(
            date
        )
    )

    link = normalize_source_url(link)


    return {

        "id":
            event_id(
                source_key,
                title,
                link,
                date
            ),

        "source_key":
            source_key,

        "source":
            source[
                "group_label"
            ],

        "source_detail":
            source[
                "label"
            ],

        "title":
            title,

        "url":
            (
                link
                or
                source[
                    "public_url"
                ]
            ),

        "published_at":
            date,

        "description":
            clean_text(
                description
            ),

        "category":
            clean_text(
                category
            ),

    }


# =========================================================
# RSS parser
# =========================================================

def parse_rss(
    source_key: str,
    data: bytes
) -> list[
    dict[
        str,
        Any
    ]
]:

    root = (
        ET.fromstring(
            data
        )
    )


    output: list[
        dict[
            str,
            Any
        ]
    ] = []


    for item in root.iter():

        if (
            local_tag(
                item.tag
            ).lower()
            !=
            "item"
        ):

            continue


        values: dict[
            str,
            str
        ] = {}


        for child in list(
            item
        ):

            values[
                local_tag(
                    child.tag
                ).lower()
            ] = (
                ""
                .join(
                    child.itertext()
                )
                .strip()
            )


        output.append(

            normalize_event(

                source_key,

                values.get(
                    "title",
                    ""
                ),

                values.get(
                    "link",
                    ""
                ),

                values.get(
                    "description",
                    ""
                ),

                values.get(

                    "pubdate",

                    values.get(
                        "date",
                        ""
                    )
                ),

                values.get(
                    "category",
                    ""
                ),
            )
        )


    return output


# =========================================================
# Law XML parser
# =========================================================

def find_value(
    record: dict[
        str,
        str
    ],
    keys: list[str]
) -> str:

    for key in keys:

        if record.get(
            key
        ):

            return (
                record[
                    key
                ]
            )


    for (
        record_key,
        value
    ) in record.items():

        if any(

            key.lower()
            in
            record_key.lower()

            for key
            in keys
        ):

            return value


    return ""


def parse_law_xml(
    source_key: str,
    data: bytes
) -> list[
    dict[
        str,
        Any
    ]
]:

    root = (
        ET.fromstring(
            data
        )
    )


    output: list[
        dict[
            str,
            Any
        ]
    ] = []


    parent_map = {

        child:
            parent

        for parent
        in root.iter()

        for child
        in parent
    }


    record_cache: dict[
        ET.Element,
        dict[str, str]
    ] = {}


    def node_record(
        node: ET.Element
    ) -> dict[str, str]:

        cached = record_cache.get(
            node
        )


        if cached is not None:

            return cached


        record: dict[str, str] = {}


        for child in list(
            node
        ):

            value = clean_text(
                " ".join(
                    child.itertext()
                )
            )


            if value:

                record[
                    local_tag(
                        child.tag
                    )
                ] = value


        record_cache[
            node
        ] = record


        return record


    def parent_law_record(
        node: ET.Element
    ) -> dict[str, str]:

        parent = parent_map.get(
            node
        )


        while parent is not None:

            if local_tag(
                parent.tag
            ) == "Law":

                return node_record(
                    parent
                )


            parent = parent_map.get(
                parent
            )


        return {}


    for node in root.iter():

        children = list(
            node
        )


        if (
            len(children)
            <
            2
            or
            len(children)
            >
            80
        ):

            continue


        record = node_record(
            node
        )


        inherited = parent_law_record(
            node
        )


        title = find_value(

            record,

            [
                "法規名稱",
                "法規名稱中文",
                "名稱",
                "title",
            ]
        )


        if not title:

            continue


        date = find_value(

            record,

            [
                "系統異動時間",
                "修正日期",
                "公發布日",
                "發布日期",
                "生效日期",
                "pubDate",
            ]
        )


        if not date:

            date = find_value(

                inherited,

                [
                    "系統異動時間",
                    "修正日期",
                    "公發布日",
                    "發布日期",
                    "生效日期",
                    "pubDate",
                ]
            )


        description = find_value(

            record,

            [
                "主旨",
                "法規沿革",
                "異動性質",
                "立法理由",
                "法規內容",
                "條文內容",
                "description",
            ]
        )


        link = find_value(

            record,

            [
                "法規網址",
                "下載網址",
                "link",
                "網址",
            ]
        )


        category = find_value(

            record,

            [
                "法規類別",
                "法規體系",
                "category",
            ]
        )


        if not category:

            category = find_value(

                inherited,

                [
                    "法規類別",
                    "法規體系",
                    "category",
                ]
            )


        output.append(

            normalize_event(

                source_key,
                title,
                link,
                description,
                date,
                category,
            )
        )


    unique = {

        event[
            "id"
        ]:
            event

        for event
        in output
    }


    return list(
        unique.values()
    )


# =========================================================
# 金管會重要公告 parser
# =========================================================

def parse_announcement_html(

    source_key: str,

    data: bytes,

    content_type: str

) -> list[
    dict[
        str,
        Any
    ]
]:

    text = (
        decode_bytes(
            data,
            content_type
        )
    )


    pattern = re.compile(

        (
            r'<a[^>]+'
            r'href=["\']'
            r'([^"\']*'
            r'dataserno='
            r'[^"\']*)'
            r'["\'][^>]*>'
            r'(.*?)'
            r'</a>'
        ),

        re.I
        |
        re.S
    )


    output: list[
        dict[
            str,
            Any
        ]
    ] = []


    seen: set[str] = set()


    for match in pattern.finditer(
        text
    ):

        href, raw_title = (
            match.groups()
        )


        title = clean_text(
            raw_title
        )


        if (
            not title
            or
            len(title) < 4
            or
            title in seen
        ):

            continue


        seen.add(
            title
        )


        context_before = (
            clean_text(

                text[
                    max(
                        0,
                        match.start()
                        -
                        800
                    )
                    :
                    match.start()
                ]
            )
        )


        dates = re.findall(

            (
                r"20\d{2}"
                r"[-/.]"
                r"\d{1,2}"
                r"[-/.]"
                r"\d{1,2}"
            ),

            context_before
        )


        date = (
            dates[-1]
            if dates
            else ""
        )


        link = (
            urllib.parse.urljoin(

                "https://www.fsc.gov.tw/",

                html.unescape(
                    href
                )
            )
        )


        output.append(

            normalize_event(

                source_key,

                title,

                link,

                (
                    "金管會重要公告。"
                    "請開啟官方原始來源"
                    "確認完整內容。"
                ),

                date,

                "重要公告",
            )
        )


        if len(
            output
        ) >= 80:

            break


    return output


def parse_source(

    source_key: str,

    data: bytes,

    content_type: str

) -> list[
    dict[
        str,
        Any
    ]
]:

    kind = (
        SOURCES[
            source_key
        ][
            "kind"
        ]
    )


    if kind == "rss":

        return parse_rss(
            source_key,
            data
        )


    if kind == "law_xml":

        return parse_law_xml(
            source_key,
            data
        )


    if kind == "announcement_html":

        return parse_announcement_html(
            source_key,
            data,
            content_type
        )


    return []
