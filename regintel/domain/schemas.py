"""Structured output contracts for AI responses."""

from __future__ import annotations
from .rules import AI_ALLOWED_DEPARTMENTS




# =========================================================
# AI Schema
# =========================================================

AI_ANALYSIS_SCHEMA = {

    "type":
        "object",

    "additionalProperties":
        False,

    "properties": {

        "summary": {
            "type":
                "string"
        },


        "event_nature": {

            "type":
                "string",

            "enum": [

                "裁罰／處分",
                "法規異動",
                "法規資訊",
                "監理公告",
                "監理新聞",
                "待確認",
            ],
        },


        "risk_level": {

            "type":
                "string",

            "enum": [

                "高",
                "中",
                "低",
                "待確認",
            ],
        },


        "importance": {

            "type":
                "string",

            "enum": [

                "重大",
                "重要",
                "一般",
                "待確認",
            ],
        },


        "rating_reason": {"type": "string", "maxLength": 120},

        "responsible_department": {
            "type":
                "string",
            "enum": [*AI_ALLOWED_DEPARTMENTS, "待確認"],
        },


        "regulatory_points": {
            "maxItems": 3,

            "type":
                "array",

            "items": {
                "type":
                    "string"
            },
        },


        "departments": {
            "maxItems": 5,

            "type":
                "array",

            "items": {

                "type":
                    "object",

                "additionalProperties":
                    False,

                "properties": {

                    "department": {
                        "type":
                            "string",
                        "enum": AI_ALLOWED_DEPARTMENTS,
                    },

                    "reason": {
                        "type":
                            "string"
                    },
                },

                "required": [
                    "department",
                    "reason",
                ],
            },
        },


        "impact_processes": {
            "maxItems": 3,

            "type":
                "array",

            "items": {

                "type":
                    "object",

                "additionalProperties":
                    False,

                "properties": {

                    "process": {
                        "type":
                            "string"
                    },

                    "department": {
                        "type":
                            "string",
                        "enum": AI_ALLOWED_DEPARTMENTS,
                    },

                    "impact": {
                        "type":
                            "string"
                    },
                },

                "required": [

                    "process",
                    "department",
                    "impact",
                ],
            },
        },


        "attention_items": {
            "maxItems": 3,

            "type":
                "array",

            "items": {
                "type":
                    "string"
            },
        },


        "actions": {
            "maxItems": 3,

            "type":
                "array",

            "items": {
                "type":
                    "string"
            },
        },


        "management_summary": {
            "type":
                "string"
        },
    },


    "required": [

        "summary",
        "event_nature",
        "risk_level",
        "importance",
        "responsible_department",
        "regulatory_points",
        "rating_reason",
        "departments",
        "impact_processes",
        "attention_items",
        "actions",
        "management_summary",
    ],
}


MANAGEMENT_SUMMARY_SCHEMA = {

    "type":
        "object",

    "additionalProperties":
        False,

    "properties": {

        "headline": {
            "type":
                "string"
        },


        "summary": {
            "type":
                "string"
        },


        "risk_outlook": {

            "type":
                "string",

            "enum": [

                "高",
                "中",
                "低",
                "待確認",
            ],
        },


        "priority_events": {

            "type":
                "array",

            "items": {

                "type":
                    "object",

                "additionalProperties":
                    False,

                "properties": {

                    "title": {
                        "type":
                            "string"
                    },

                    "reason": {
                        "type":
                            "string"
                    },
                },

                "required": [
                    "title",
                    "reason",
                ],
            },
        },


        "priority_actions": {

            "type":
                "array",

            "items": {
                "type":
                    "string"
            },
        },


        "trend_observations": {

            "type":
                "array",

            "items": {
                "type":
                    "string"
            },
        },


        "management_note": {
            "type":
                "string"
        },
    },


    "required": [

        "headline",
        "summary",
        "risk_outlook",
        "priority_events",
        "priority_actions",
        "trend_observations",
        "management_note",
    ],
}
