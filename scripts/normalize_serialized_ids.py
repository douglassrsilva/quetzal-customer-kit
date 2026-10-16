#!/usr/bin/env python3
"""Reemplaza IDs exportados de AI/BI y Genie por IDs estables del proyecto."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_ID = re.compile(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])", re.IGNORECASE)


def normalize(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    unique = list(dict.fromkeys(ASSET_ID.findall(text)))
    relative = path.relative_to(ROOT).as_posix()
    mapping = {
        old: hashlib.sha256(f"quetzal-customer-kit:v1:{relative}:{index}".encode()).hexdigest()[:32]
        for index, old in enumerate(unique, 1)
    }
    for old, new in mapping.items():
        text = re.sub(
            rf"(?<![0-9a-f]){re.escape(old)}(?![0-9a-f])",
            new,
            text,
            flags=re.IGNORECASE,
        )
    path.write_text(text, encoding="utf-8")
    return len(mapping)


def main() -> None:
    paths = sorted((ROOT / "dashboards/templates").glob("*.json"))
    paths += sorted((ROOT / "genie_spaces/templates").glob("*.json"))
    total = sum(normalize(path) for path in paths)
    print(f"Normalized {total} serialized object IDs")


if __name__ == "__main__":
    main()
