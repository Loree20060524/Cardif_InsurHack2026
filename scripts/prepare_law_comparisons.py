"""Prepare real official before/after snapshots for the initial demo scope."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from regintel.application.law_comparison import get_law_comparisons
from regintel.infrastructure.law_history import KNOWN_LAWS, capture_law_history
from regintel.infrastructure import law_history
import urllib.parse


def main():
    debug = "--debug" in sys.argv
    if debug:
        original_fetch = law_history._fetch
        def inspect_fetch(url):
            print(f"讀取官方頁面：{url}", flush=True)
            data, mime = original_fetch(url)
            parsed = urllib.parse.urlsplit(url)
            suffix = urllib.parse.urlencode(urllib.parse.parse_qsl(parsed.query)).replace('&', '_').replace('=', '-')
            target = Path(__file__).resolve().parents[1] / "tmp" / "law-comparison-review" / f"{Path(parsed.path).stem}-{suffix}.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            print(f"已保存 {len(data)} bytes：{target.name}", flush=True)
            return data, mime
        law_history._fetch = inspect_fetch
    names = [name for name in sys.argv[1:] if name != "--debug"] or ["保險經紀人管理規則", "保險代理人管理規則", "保險業招攬及核保理賠辦法"]
    for name in names:
        if name not in KNOWN_LAWS:
            raise SystemExit(f"未設定此官方法規身分：{name}")
        if debug:
            try:
                capture_law_history(name, KNOWN_LAWS[name])
            except Exception as exc:
                print(f"{name}: {type(exc).__name__}: {exc}", flush=True)
        result = get_law_comparisons({"title": name, "source_key": "insurance_law"}, fetch_missing=not debug)[0]
        print(json.dumps({key: result.get(key) for key in ("name", "status", "before_version", "after_version", "counts", "fetch_note")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
