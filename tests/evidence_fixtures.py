"""Deterministic review replies for plumbing tests, never an accuracy benchmark."""

import json
import re


def supported_review_reply(kwargs):
    data = json.loads(kwargs["input_text"])
    sources = {source["source_id"]: source for source in data["sources"]}
    return {"checks": [{"id": statement["id"], "status": "supported", "reason": "測試用核對結果。",
                        "evidence_ids": [re.search(r"\[(E\d+)\]", sources[statement["source_ids"][0]]["text"])[1]]}
                       for statement in data["statements"]]}


def with_review_replies(outputs):
    sequence = iter(outputs)
    def model(**kwargs):
        if "checks" in kwargs["schema"].get("properties", {}):
            return supported_review_reply(kwargs)
        return next(sequence)
    return model
