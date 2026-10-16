#!/usr/bin/env python3
"""Detecta credenciales, identificadores concretos y artefactos locales no permitidos."""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".databricks", ".git", ".terraform", ".venv", "node_modules", ".pytest_cache", ".ruff_cache", "__pycache__"}
TEXT_SUFFIXES = {
    "", ".css", ".env", ".example", ".html", ".ini", ".js", ".json", ".lock",
    ".md", ".py", ".sh", ".sql", ".toml", ".ts", ".tsx", ".ttl", ".txt", ".yaml", ".yml",
}
SECRET_PATTERNS = {
    "token de Databricks": re.compile(r"\bdapi[a-zA-Z0-9]{20,}\b"),
    "token de GitHub": re.compile(r"\b(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{20,}\b"),
    "clave privada": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "clave de acceso de AWS": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
}
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
HOST = re.compile(r"https://([A-Za-z0-9.-]+\.cloud\.databricks\.com)")
ENVIRONMENT_PATTERNS = {
    "catálogo no permitido": re.compile(r"\bclassic_stable_[a-z0-9_]+_catalog\b", re.IGNORECASE),
    "host de workspace no permitido": re.compile(r"\bfevm-[a-z0-9-]+\.cloud\.databricks\.com\b", re.IGNORECASE),
    "proyecto LTAP concreto": re.compile(r"\b[a-z][a-z0-9-]*-ltap\b", re.IGNORECASE),
    "ID concreto de workspace o warehouse": re.compile(r"\b(?!0{16}\b)[0-9]{16}\b"),
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
    failures.extend(f"artefacto local no permitido: {path.relative_to(ROOT)}" for path in forbidden_paths if path.exists())

    for path in files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        relative = path.relative_to(ROOT)
        for label, pattern in ENVIRONMENT_PATTERNS.items():
            if pattern.search(text):
                failures.append(f"{label}: {relative}")
        if relative.suffix in {".yml", ".yaml", ".env"} and UUID.search(text):
            failures.append(f"UUID concreto de un principal: {relative}")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                failures.append(f"{label}: {relative}")
        for match in EMAIL.finditer(text):
            domain = match.group(1).lower()
            if domain not in {"example.com", "example.org"}:
                failures.append(f"email fuera de los dominios de ejemplo: {relative}")
        for match in HOST.finditer(text):
            host = match.group(1).lower()
            if host != "customer-workspace.cloud.databricks.com":
                failures.append(f"host de workspace: {relative}")

    if failures:
        # No publique coincidencias ni rutas en logs de CI: incluso un hallazgo
        # parcial puede facilitar la reconstrucción de un secreto.
        print(f"La verificación de seguridad detectó {len(set(failures))} incidencia(s).")
        print("Revise el repositorio localmente sin copiar los valores a tickets o logs.")
        raise SystemExit(1)
    print(f"Verificación de seguridad aprobada en {len(files())} archivos de texto")


if __name__ == "__main__":
    main()
