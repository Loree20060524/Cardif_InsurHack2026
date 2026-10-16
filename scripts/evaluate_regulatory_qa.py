"""Measure retrieval and configured model answers without altering caches."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from regintel.application.regulatory_qa import answer_regulatory_question, knowledge_index


CASES = [
    {"question": "保險業投資創投事業的預告修正重點是什麼？", "filters": {"date_from": "2026-10-01"}, "expected_title": "預告修正「保險業資金辦理專案運用公共及社會福利事業投資管理辦法」，鼓勵保險業資金投入創投事業"},
    {"question": "保險業各種準備金提存辦法規定什麼？", "expected_title": "保險業各種準備金提存辦法"},
    {"question": "保險經紀人管理規則的最新修正紀錄？", "expected_title": "保險經紀人管理規則"},
    {"question": "火星殖民太空船引擎", "expect_empty": True},
    {"question": "保險業投資創投事業", "filters": {"date_from": "2099-01-01"}, "expect_empty": True},
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Also generate two answers with the configured AI provider")
    parser.add_argument("--output", default="tmp/qa/evaluation.json")
    args = parser.parse_args()
    started = time.perf_counter()
    index = knowledge_index()
    report = {"documents": index.document_count, "passages": len(index.chunks), "index_seconds": round(time.perf_counter() - started, 3), "retrieval_cases": [], "answers": []}
    for case in CASES:
        filters = {"type": "全部", "date_from": "", "date_to": "", **case.get("filters", {})}
        started = time.perf_counter()
        sources = index.search(case["question"], filters)
        passed = not sources if case.get("expect_empty") else bool(sources and sources[0]["title"] == case["expected_title"])
        report["retrieval_cases"].append({"question": case["question"], "filters": filters, "passed": passed, "seconds": round(time.perf_counter() - started, 3), "titles": [s["title"] for s in sources]})
    if args.live:
        for case in (CASES[0], CASES[2], CASES[3]):
            try:
                answer = answer_regulatory_question({"question": case["question"], "filters": case.get("filters", {})})
                report["answers"].append(answer)
                print(json.dumps({"question": case["question"], "status": answer["status"], "timing": answer["timing"], "claims": len(answer["claims"])}, ensure_ascii=False), flush=True)
            except Exception as exc:
                report["answers"].append({"question": case["question"], "error": str(exc)})
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"retrieval_passed": sum(c["passed"] for c in report["retrieval_cases"]), "retrieval_cases": len(CASES), "index_seconds": report["index_seconds"], "output": str(path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
