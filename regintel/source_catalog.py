"""Official source definitions and polling policy."""

from __future__ import annotations




# =========================================================
# 五個官方資料來源
# =========================================================

SOURCES: dict[
    str,
    dict[
        str,
        str
    ]
] = {

    "law_db": {

        "label":
            "金管會主管法規",

        "group_label":
            "法規資料庫",

        "url":
            (
                "https://law.fsc.gov.tw/"
                "opendata/"
                "%E6%9C%AC%E6%9C%83.xml"
            ),

        "public_url":
            (
                "https://law.fsc.gov.tw/"
                "LawQuery.aspx"
            ),

        "dataset_url":
            (
                "https://data.gov.tw/"
                "dataset/138767"
            ),

        "kind":
            "law_xml",

        "access_type":
            "官方 XML 開放資料",
    },


    "fsc_announcement": {

        "label":
            "金管會重要公告",

        "group_label":
            "金管會公告",

        "url":
            (
                "https://www.fsc.gov.tw/"
                "ch/home.jsp?"
                "id=97&parentpath=0,2"
            ),

        "public_url":
            (
                "https://www.fsc.gov.tw/"
                "ch/home.jsp?"
                "id=97&parentpath=0,2"
            ),

        "dataset_url":
            "",

        "kind":
            "announcement_html",

        "access_type":
            "官方網站公告",
    },


    "fsc_penalty": {

        "label":
            "金管會重大裁罰",

        "group_label":
            "金管會裁罰案例",

        "url":
            (
                "https://www.fsc.gov.tw/"
                "RSS/Messages?"
                "language=chinese&"
                "serno=201202290003"
            ),

        "public_url":
            (
                "https://www.fsc.gov.tw/"
                "ch/home.jsp?"
                "id=131&parentpath=0,2"
            ),

        "dataset_url":
            (
                "https://data.gov.tw/"
                "dataset/10292"
            ),

        "kind":
            "rss",

        "access_type":
            "官方 XML／RSS 資料",
    },


    "insurance_law": {

        "label":
            "保險局主管法規",

        "group_label":
            "保險相關法規",

        "url":
            (
                "https://law.fsc.gov.tw/"
                "opendata/"
                "%E4%BF%9D%E9%9A%AA"
                "%E5%B1%80.xml"
            ),

        "public_url":
            (
                "https://law.fsc.gov.tw/"
                "LawQuery.aspx"
            ),

        "dataset_url":
            (
                "https://data.gov.tw/"
                "dataset/138801"
            ),

        "kind":
            "law_xml",

        "access_type":
            "官方 XML 開放資料",
    },


    "reg_news": {

        "label":
            "金管會新聞稿",

        "group_label":
            "金融監理新聞",

        "url":
            (
                "https://www.fsc.gov.tw/"
                "RSS/Messages?"
                "language=chinese&"
                "serno=201202290009"
            ),

        "public_url":
            (
                "https://www.fsc.gov.tw/"
                "ch/home.jsp?"
                "id=96&parentpath=0,2"
            ),

        "dataset_url":
            "",

        "kind":
            "rss",

        "access_type":
            "官方 XML／RSS 資料",
    },
}


SOURCE_MIN_INTERVAL_SECONDS = {

    "law_db":
        3600,

    "fsc_announcement":
        1800,

    "fsc_penalty":
        1800,

    "insurance_law":
        3600,

    "reg_news":
        1800,
}
