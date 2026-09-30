#!/usr/bin/env python3
"""Fail closed when origin identifiers, credentials or private artifacts leak."""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".terraform", ".venv", "node_modules", ".pytest_cache", ".ruff_cache", "__pycache__"}
TEXT_SUFFIXES = {
    "", ".css", ".env", ".example", ".html", ".ini", ".js", ".json", ".lock",
    ".md", ".py", ".sh", ".sql", ".toml", ".ts", ".tsx", ".ttl", ".txt", ".yaml", ".yml",
}
SECRET_PATTERNS = {
    "Databricks token": re.compile(r"\bdapi[a-zA-Z0-9]{20,}\b"),
    "GitHub token": re.compile(r"\b(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{20,}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
}
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
HOST = re.compile(r"https://([A-Za-z0-9.-]+\.cloud\.databricks\.com)")
ORIGIN_PATTERNS = {
    "personal catalog": re.compile(r"\bclassic_stable_[a-z0-9_]+_catalog\b", re.IGNORECASE),
    "personal workspace host": re.compile(r"\bfevm-[a-z0-9-]+\.cloud\.databricks\.com\b", re.IGNORECASE),
    "personal LTAP project": re.compile(r"\b[a-z][a-z0-9-]*-ltap\b", re.IGNORECASE),
    "concrete workspace/warehouse ID": re.compile(r"\b(?!0{16}\b)[0-9]{16}\b"),
}
UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.IGNORECASE)


def files() -> list[Path]:
    result = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
            continue
        if path == ROOT / "config/customer.env":
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {"Makefile", "Dockerfile"}:
            result.append(path)
    return sorted(result)


def main() -> None:
    failures: list[str] = []
    forbidden_paths = [ROOT / ".env", ROOT / "terraform.tfstate"]
    if os.getenv("CI", "").lower() == "true":
        forbidden_paths.append(ROOT / "config/customer.env")
    failures.extend(f"forbidden local artifact: {path.relative_to(ROOT)}" for path in forbidden_paths if path.exists())

    for path in files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        relative = path.relative_to(ROOT)
        for label, pattern in ORIGIN_PATTERNS.items():
            if pattern.search(text):
                failures.append(f"{label}: {relative}")
        if relative.suffix in {".yml", ".yaml", ".env"} and UUID.search(text):
            failures.append(f"concrete principal UUID: {relative}")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                failures.append(f"{label}: {relative}")
        for match in EMAIL.finditer(text):
            domain = match.group(1).lower()
            if domain not in {"example.com", "example.org"}:
                failures.append(f"non-example email: {relative}")
        for match in HOST.finditer(text):
            host = match.group(1).lower()
            if host != "customer-workspace.cloud.databricks.com":
                failures.append(f"workspace host: {relative}")

    if failures:
        print("Sanitization failed:")
        for failure in sorted(set(failures)):
            print(f"- {failure}")
        raise SystemExit(1)
    print(f"Sanitization passed across {len(files())} text files")


if __name__ == "__main__":
    main()
