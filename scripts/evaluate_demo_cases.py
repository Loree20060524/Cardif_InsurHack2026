"""Capture three real demo cases and optionally measure fresh local AI outputs."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from regintel import config
from regintel.application import event_analysis, management_summary
from regintel.application.law_comparison import get_law_comparisons
from regintel.domain.text import now_iso


CASES = (
    ("amendment", "b92ed9cff56982bf", "保險經紀人管理規則"),
    ("penalty", "99877b843ca21a11", "台灣人壽懸帳與退費作業裁罰"),
    ("draft", "8fadedef46d6dd78", "保險資金投資創投事業預告"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Generate fresh outputs with the configured local Ollama model.")
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/demo/evaluation.json")
    parser.add_argument("--case", choices=[case[0] for case in CASES], action="append", dest="case_names")
    parser.add_argument("--skip-management", action="store_true", help="Only evaluate the selected event analyses.")
    args = parser.parse_args()
    if args.live and urllib.parse.urlsplit(config.OLLAMA_API_URL).hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("Live demo evaluation only supports a local Ollama endpoint.")
    cases = [case for case in CASES if not args.case_names or case[0] in args.case_names]
    snapshot = json.loads(config.CACHE_FILE.read_text(encoding="utf-8"))
    by_id = {event["id"]: event for event in snapshot["events"]}
    missing = [event_id for _, event_id, _ in cases if event_id not in by_id]
    if missing:
        parser.error(f"Pinned demo sources are missing from the local snapshot: {missing}")
    selected = [by_id[event_id] for _, event_id, _ in cases]
    report = {
        "recorded_at": now_iso(),
        "app_version": config.APP_VERSION,
        "model": config.OLLAMA_MODEL,
        "thinking": config.OLLAMA_THINK,
        "fresh_generation": args.live,
        "source_snapshot_sync": snapshot.get("last_sync"),
        "review_status": "Outputs require source and domain review; no accuracy score is inferred.",
        "human_baseline": None,
        "cases": [],
        "model_calls": [],
    }

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    original_model = event_analysis.call_ollama_structured_json

    def recorded_model(**kwargs):
        # The pinned cases contain public source material only. Keep rejected candidates
        # in the evaluation artifact, never the website's production cache.
        entry = {"input_text": kwargs["input_text"], "review": "checks" in kwargs["schema"].get("properties", {})}
        report["model_calls"].append(entry)
        result = original_model(**kwargs)
        entry["output"] = result
        return result

    # Keep evaluation outputs separate from the website's production AI caches.
    with (
        patch.object(event_analysis, "load_ai_cache", return_value={"analyses": {}, "management": {}}),
        patch.object(event_analysis, "atomic_write_json"),
        patch.object(management_summary, "_cached_summary", return_value=None),
        patch.object(management_summary, "_save_summary"),
        patch.object(event_analysis, "call_ollama_structured_json", side_effect=recorded_model),
        patch.object(management_summary, "call_ollama_structured_json", side_effect=recorded_model),
    ):
        for (kind, _, label), event in zip(cases, selected):
            source = management_summary.management_source_text(event)
            material = management_summary.management_source_material(event)
            case = {
                "kind": kind,
                "label": label,
                "event": event,
                "law_comparisons": get_law_comparisons(event),
                "management_source_chars": len(source),
                "management_input_excerpt": material["text"],
                "management_input_truncated": material["is_excerpt"],
            }
            report["cases"].append(case)
            if args.live:
                print(json.dumps({"running": kind}, ensure_ascii=True), flush=True)
                started = time.perf_counter()
                try:
                    case["analysis"] = event_analysis.analyze_event_with_ai(event, force=True)
                except Exception as exc:
                    case["error"] = f"{type(exc).__name__}: {exc}"
                case["elapsed_seconds"] = round(time.perf_counter() - started, 3)
            save()
            print(json.dumps({key: case[key] for key in ("kind", "elapsed_seconds", "management_input_truncated", "error") if key in case}), flush=True)

        if args.live and not args.skip_management:
            print(json.dumps({"running": "combined_management_summary"}), flush=True)
            started = time.perf_counter()
            try:
                summary = management_summary.generate_management_summary_ai(selected)
                report["management_summary"] = summary
                expected = {event["id"] for event in selected}
                actual = {event["id"] for event in summary.get("source_events", [])}
                report["selected_sources_match"] = expected == actual
            except Exception as exc:
                report["management_error"] = f"{type(exc).__name__}: {exc}"
            report["management_seconds"] = round(time.perf_counter() - started, 3)
            summary_review = report.get("management_summary", {}).get("support_review", {})
            report["completeness_checks"] = {
                "case_reviews_complete": all(case.get("analysis", {}).get("support_review", {}).get("unverified") == 0 for case in report["cases"]),
                "case_actions_available": all(bool(case.get("analysis", {}).get("actions")) for case in report["cases"]),
                "management_summary_supported": any(row.get("id") == "summary" and row.get("status") == "supported" for row in summary_review.get("checks", [])),
                "management_review_complete": summary_review.get("unverified") == 0,
            }
            save()
            print(json.dumps({"management_seconds": report["management_seconds"], "selected_sources_match": report.get("selected_sources_match", False)}), flush=True)
        elif args.live:
            report["completeness_checks"] = {
                "case_reviews_complete": all(case.get("analysis", {}).get("support_review", {}).get("unverified") == 0 for case in report["cases"]),
                "case_actions_available": all(bool(case.get("analysis", {}).get("actions")) for case in report["cases"]),
            }
            save()
    print(json.dumps({"output": str(args.output)}, ensure_ascii=True), flush=True)
    if args.live and (report.get("management_error") or (not args.skip_management and not report.get("selected_sources_match"))
                     or any(case.get("error") or case.get("analysis", {}).get("analysis_mode") != "AI 深度分析" for case in report["cases"])
                     or not all(report.get("completeness_checks", {}).values())):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
