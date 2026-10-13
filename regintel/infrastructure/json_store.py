"""Document persistence: local JSON files or shared Postgres on cloud hosts."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .postgres_store import StorageError, get_store


def atomic_write_json(
    path: Path,
    payload: dict[
        str,
        Any
    ]
) -> None:

    store = get_store()
    if store is not None:
        store.write(path.name, payload)
        return

    path.parent.mkdir(parents=True, exist_ok=True)

    temp = path.with_suffix(
        path.suffix
        +
        ".tmp"
    )

    temp.write_text(

        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2
        ),

        encoding="utf-8"
    )

    temp.replace(
        path
    )


def load_json_file(
    path: Path
) -> dict[
    str,
    Any
]:

    store = get_store()
    if store is not None:
        # A failed database read must never look like a new, empty history.
        return store.load(path.name)

    try:

        if path.exists():

            value = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

            if isinstance(
                value,
                dict
            ):

                return value

    except (OSError, ValueError):

        pass

    return {}


@contextmanager
def document_transaction(*paths: Path, blocking: bool = True) -> Iterator[None]:
    store = get_store()
    if store is None:
        yield
    else:
        with store.transaction(*(path.name for path in paths), blocking=blocking):
            yield


def document_signature(paths: tuple[Path, ...]) -> tuple:
    store = get_store()
    if store is not None:
        revisions = store.revisions([path.name for path in paths])
        return tuple((store.namespace, path.name, revisions.get(path.name, 0)) for path in paths)
    return tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size)
                 if path.exists() else (str(path), 0, 0) for path in paths)


def storage_health() -> dict[str, Any]:
    try:
        store = get_store()
        return store.check() if store is not None else {"backend": "json", "connected": True}
    except StorageError as exc:
        return {"backend": "postgres", "connected": False, "error": str(exc)}
