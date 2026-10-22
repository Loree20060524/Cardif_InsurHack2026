"""Exercise local source-support review on explicit synthetic counterexamples."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from regintel.application.evidence_review import numeric_issue, review_statements
from regintel.config import OLLAMA_API_URL, OLLAMA_MODEL
from regintel.infrastructure.ollama import call_ollama_structured_json


SOURCES = [
    {"source_id": "S1", "title": "合成測試制度", "type": "測試資料", "text": "測試制度：資料提供前應確認使用目的並取得核准。未經核准，不得提供資料；但已依法公開的資訊不受前述核准限制。"},
    {"source_id": "S2", "title": "合成測試草案", "type": "草案", "version_note": "預告草案，尚未生效", "text": "本文件為預告草案，尚未正式發布及生效。草案擬規定資料存取紀錄應保存五年。"},
    {"source_id": "S3", "title": "合成裁罰資料", "type": "測試資料", "text": "甲被罰960萬元；乙被罰1,200萬元；丙被罰400萬元；丁被罰800萬元。"},
    {"source_id": "S4", "title": "合成條件資料", "type": "測試資料", "text": "資料蒐集應具有特定目的及法定情形；其經當事人同意者，應確認同意範圍。"},
]
STATEMENTS = [
    {"id": "supported", "text": "依測試制度，未公開資料提供前應確認使用目的並取得核准。", "source_ids": ["S1"]},
    {"id": "negation", "text": "依測試制度，即使未經核准，也可提供未公開資料。", "source_ids": ["S1"]},
    {"id": "exception", "text": "依測試制度，任何資料都必須事先核准，已依法公開的資訊也不例外。", "source_ids": ["S1"]},
    {"id": "invented_workflow", "text": "資料提供前必須填寫A-17表單並由董事長核准。", "source_ids": ["S1"]},
    {"id": "draft_as_effective", "text": "資料存取紀錄現行法定保存期限為五年。", "source_ids": ["S2"]},
    {"id": "false_total", "text": "針對4家機構，罰鍰總計4,000萬元。甲被罰960萬元；乙被罰1,200萬元；丙被罰400萬元；丁被罰800萬元。", "source_ids": ["S3"]},
    {"id": "consent_strength", "text": "經當事人同意後，才能進行任何資料蒐集。", "source_ids": ["S4"]},
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", default="tmp/evidence-review/live.json")
    args = parser.parse_args()
    if not args.live:
        print(json.dumps({"numeric_conflict_detected": bool(numeric_issue(STATEMENTS[-1]["text"], SOURCES[-1]["text"])), "live_model": False}))
        return 0
    if urlsplit(OLLAMA_API_URL).hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("Live checks require the configured local Ollama endpoint.")
    result = review_statements(STATEMENTS, SOURCES, context="合成測試資料，非真實法規。員工要提供未公開資料。", model=call_ollama_structured_json)
    result["model"] = OLLAMA_MODEL
    result["sample_only"] = "Seven synthetic checks do not establish accuracy on real legal questions."
    accepted = {row["id"] for row in result["checks"] if row["status"] == "supported"}
    result["expected_behavior"] = accepted == {"supported"} and result["unverified"] == 0
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"expected_behavior": result["expected_behavior"], "seconds": result["seconds"],
                      "checks": [{"id": row["id"], "status": row["status"], "reason": row["reason"]} for row in result["checks"]]}, ensure_ascii=False))
    return 0 if result["expected_behavior"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
