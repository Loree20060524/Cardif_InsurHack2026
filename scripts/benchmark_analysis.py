"""Compare thinking settings through the real event-analysis path without writing caches."""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from regintel import config
from regintel.application import event_analysis, management_summary
from regintel.domain.schemas import AI_ANALYSIS_SCHEMA, MANAGEMENT_SUMMARY_SCHEMA


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Inspect the local server without loading a model.")
    parser.add_argument("--event", help="Pin a public event ID from the local cache.")
    parser.add_argument("--modes", nargs="+", choices=("configured", "default", "on", "off"), default=["default", "off"])
    parser.add_argument("--summary", action="store_true", help="Exercise the management-summary path.")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--max-seconds", type=float)
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/performance/analysis-benchmark.json")
    args = parser.parse_args()
    endpoint = urllib.parse.urlsplit(config.OLLAMA_API_URL)
    if endpoint.hostname not in {"localhost", "127.0.0.1", "::1"} or endpoint.username or endpoint.password:
        parser.error("This benchmark only connects to a local Ollama server.")
    base = urllib.parse.urlunsplit((endpoint.scheme, endpoint.netloc, "", "", ""))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def api(path: str, body: dict | None = None) -> dict:
        request = urllib.request.Request(
            base + path,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with opener.open(request, timeout=config.OLLAMA_TIMEOUT) as response:
            return json.load(response)

    info = {
        "version": api("/api/version").get("version"),
        "model": config.OLLAMA_MODEL,
        "loaded_models": api("/api/ps").get("models", []),
        "installed_models": [item["name"] for item in api("/api/tags").get("models", [])],
    }
    if config.OLLAMA_MODEL not in info["installed_models"]:
        raise RuntimeError("The configured model is not installed; no model will be downloaded.")
    model_info = api("/api/show", {"model": config.OLLAMA_MODEL})
    info["capabilities"] = model_info.get("capabilities", [])
    info["thinking"] = model_info.get("thinking")
    if args.check:
        print(json.dumps(info, ensure_ascii=True, indent=2), flush=True)
        return 0

    events = json.loads((ROOT / "regintel_cache_v10.json").read_text(encoding="utf-8"))["events"]
    if args.event:
        event = next((item for item in events if item["id"] == args.event), None)
    else:
        readable = [item for item in events if event_analysis.has_analyzable_source_text(item.get("description", ""))]
        penalties = [item for item in readable if item.get("source_key") == "fsc_penalty" and "保險" in item.get("title", "")]
        event = max(penalties or readable, key=lambda item: len(item.get("description", "")), default=None)
    if event is None:
        parser.error("No matching readable event was found in the local cache.")
    records = []
    report = {"server": info, "event": event, "kind": "summary" if args.summary else "event", "runs": records}

    for repeat in range(args.repeat):
        for mode in args.modes:
            model_measurements = {}

            def measured_open(request, **kwargs):
                body = json.loads(request.data.decode("utf-8"))
                if mode == "default":
                    body.pop("think", None)
                elif mode != "configured":
                    body["think"] = mode == "on"
                request.data = json.dumps(body, ensure_ascii=False).encode("utf-8")
                started = time.perf_counter()
                with opener.open(request, **kwargs) as response:
                    raw = response.read(config.MAX_RESPONSE_BYTES)
                payload = json.loads(raw)
                output = json.loads(payload.get("message", {}).get("content", "{}"))
                schema = MANAGEMENT_SUMMARY_SCHEMA if args.summary else AI_ANALYSIS_SCHEMA
                missing = set(schema["required"]) - set(output)
                if missing:
                    raise AssertionError(f"Missing structured analysis fields: {sorted(missing)}")
                model_measurements.update({
                    "http_seconds": round(time.perf_counter() - started, 3),
                    "context_window": body.get("options", {}).get("num_ctx"),
                    "request_think": body.get("think"),
                    "thinking_chars": len(payload.get("message", {}).get("thinking", "")),
                    "raw_analysis": output,
                    "done_reason": payload.get("done_reason"),
                    **{name: payload.get(name) for name in (
                        "total_duration", "load_duration", "prompt_eval_count",
                        "prompt_eval_duration", "eval_count", "eval_duration",
                    )},
                })
                return io.BytesIO(raw)

            started = time.perf_counter()
            print(json.dumps({"status": "running", "mode": mode, "repeat": repeat + 1}), flush=True)
            with (
                patch.object(event_analysis, "load_ai_cache", return_value={"analyses": {}, "management": {}}),
                patch.object(event_analysis, "atomic_write_json"),
                patch.object(management_summary, "_cached_summary", return_value=None),
                patch.object(management_summary, "_save_summary"),
                patch("regintel.infrastructure.ollama.urllib.request.urlopen", side_effect=measured_open),
            ):
                analysis = (
                    management_summary.generate_management_summary_ai([event])
                    if args.summary else event_analysis.analyze_event_with_ai(event)
                )
            elapsed = round(time.perf_counter() - started, 3)
            record = {"mode": mode, "repeat": repeat + 1, "elapsed_seconds": elapsed,
                      "analysis": analysis, **model_measurements}
            records.append(record)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({name: value for name, value in record.items()
                              if name not in {"analysis", "raw_analysis"}}, ensure_ascii=True), flush=True)

    report["loaded_models_after"] = api("/api/ps").get("models", [])
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.max_seconds is not None and any(item["elapsed_seconds"] > args.max_seconds for item in records):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
