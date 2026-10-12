"""Build a public directory containing only the UI and its approved assets."""

from pathlib import Path
import shutil


STATIC_SUFFIXES = {".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".ico", ".woff", ".woff2"}


def build_public(root: Path) -> Path:
    root = root.resolve()
    output = root / "public"
    if output.is_symlink() or not output.resolve().is_relative_to(root):
        raise ValueError("Static output must stay inside the project.")
    sources = {"index.html": root / "index.html"}
    for path in (root / "assets").rglob("*"):
        relative = path.relative_to(root)
        if path.is_file() and path.suffix.lower() in STATIC_SUFFIXES and not any(part.startswith(".") for part in relative.parts):
            if not path.resolve().is_relative_to(root / "assets"):
                raise ValueError("Static assets must stay inside the assets directory.")
            sources[relative.as_posix()] = path
    # Refuse to publish stale files from a previous or manually modified build.
    # Vercel builds start from a clean checkout; no recursive deletion is needed.
    if output.exists():
        for path in output.rglob("*"):
            if path.is_symlink() or (path.is_file() and path.relative_to(output).as_posix() not in sources):
                raise ValueError("Unexpected file in public; use a clean build directory.")
    for name, source in sources.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return output


if __name__ == "__main__":
    destination = build_public(Path(__file__).resolve().parents[1])
    print(f"Prepared static UI: {destination}")
