"""Build the public-only frontend. Server files and secrets are never published."""

from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent


def main():
    seed_dir = ROOT / "deployment_data"
    seed_dir.mkdir(exist_ok=True)
    for name in ("regintel_cache_v10.json", "regintel_source_store_v10.json", "regintel_event_history_v10.json", "regintel_law_versions_v1.json"):
        source = ROOT / name
        if source.is_file():
            shutil.copyfile(source, seed_dir / name)
        if not (seed_dir / name).is_file():
            raise RuntimeError(f"缺少官方資料快照 {name}；請先在本機更新資料並執行此腳本。")
    output = ROOT / "public"
    output.mkdir(exist_ok=True)
    shutil.copyfile(ROOT / "index.html", output / "index.html")
    shutil.copytree(ROOT / "assets", output / "assets", dirs_exist_ok=True)


if __name__ == "__main__":
    main()
