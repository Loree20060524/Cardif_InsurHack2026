"""Atomic JSON persistence adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def atomic_write_json(
    path: Path,
    payload: dict[
        str,
        Any
    ]
) -> None:

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

    except Exception:

        pass

    return {}
