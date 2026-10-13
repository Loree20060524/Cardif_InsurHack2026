"""Inspect, import, or verify the five local snapshots without exposing secrets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from regintel.infrastructure.postgres_store import DB_ENV_KEYS, StorageError, get_store

DOCUMENT_NAMES = (
    "regintel_cache_v10.json", "regintel_source_store_v10.json",
    "regintel_ai_cache_v10.json", "regintel_event_history_v10.json",
    "regintel_law_versions_v1.json",
)


def load_environment(path: Path) -> None:
    """Load only database settings, never evaluate shell code or print values."""
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.removeprefix("export ").partition("=")
        key, value = key.strip(), value.strip()
        if not separator or key not in DB_ENV_KEYS:
            raise ValueError(f"連線設定檔第 {number} 行格式或變數名稱不正確。")
        if value.startswith(("'", '"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f"連線設定檔第 {number} 行引號未完整關閉。")
            value = value[1:-1]
        if value:
            os.environ[key] = value


def digest(payload: dict) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_snapshot(directory: Path) -> dict[str, dict]:
    documents = {}
    for name in DOCUMENT_NAMES:
        try:
            value = json.loads((directory / name).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            raise ValueError(f"無法完整讀取 {name}，未進行搬移。") from None
        if not isinstance(value, dict):
            raise ValueError(f"{name} 不是 JSON 物件，未進行搬移。")
        digest(value)
        documents[name] = value
    return documents


def verify_snapshot(store, documents: dict[str, dict]) -> None:
    revisions = store.revisions(list(documents))
    for key, payload in documents.items():
        if key not in revisions or digest(store.load(key)) != digest(payload):
            raise ValueError(f"{key} 的資料核對未通過。")


def import_snapshot(store, documents: dict[str, dict]) -> bool:
    """Import atomically into an empty namespace; identical reruns are safe."""
    with store.transaction(import_only=True):
        existing = store.revisions(list(documents))
        if existing:
            if len(existing) == len(documents) and all(
                digest(store.load(key)) == digest(payload) for key, payload in documents.items()
            ):
                return False
            raise ValueError("資料庫已有不同資料，已停止搬移以保留現有內容。請先核對資料庫或使用獨立命名空間。")
        for key, payload in documents.items():
            store.write(key, payload)
        verify_snapshot(store, documents)
    # Verify again on new connections after commit, rather than trusting the
    # importing transaction's own uncommitted view.
    verify_snapshot(store, documents)
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT)
    parser.add_argument("--env-file", type=Path)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="僅檢查本機資料，不連線資料庫（預設）")
    action.add_argument("--apply", action="store_true", help="搬移到尚未有資料的命名空間")
    action.add_argument("--verify", action="store_true", help="核對資料庫與本機快照是否一致")
    args = parser.parse_args(argv)
    try:
        documents = load_snapshot(args.data_dir)
        manifest = [{"document": key, "sha256": digest(value),
                     "bytes": len(json.dumps(value, ensure_ascii=False).encode("utf-8"))}
                    for key, value in documents.items()]
        if not args.apply and not args.verify:
            print(json.dumps({"status": "checked", "documents": manifest}, ensure_ascii=False, indent=2))
            return 0
        if args.env_file:
            load_environment(args.env_file)
        store = get_store()
        if store is None:
            raise ValueError("尚未設定資料庫連線；請用 --env-file 指定本機連線設定檔。")
        if args.apply:
            imported = import_snapshot(store, documents)
            status = "imported_and_verified" if imported else "already_imported_and_verified"
        else:
            verify_snapshot(store, documents)
            status = "verified"
        print(json.dumps({"status": status, "documents": manifest}, ensure_ascii=False, indent=2))
        return 0
    except (StorageError, OSError, ValueError) as exc:
        print(f"資料搬移未完成：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
