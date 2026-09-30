#!/usr/bin/env python3
"""Render customer-neutral AI/BI, Genie and ontology templates."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
URI = re.compile(r"^https://[A-Za-z0-9.-]+(?::[0-9]+)?(?:/[A-Za-z0-9._~/-]*)?$")


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        raise SystemExit(f"Missing {path}. Copy config/customer.env.example first.")
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise SystemExit(f"Invalid env assignment at {path}:{line_number}")
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def render_tree(source: Path, destination: Path, replacements: dict[str, str]) -> int:
    count = 0
    for template in sorted(source.rglob("*")):
        if not template.is_file():
            continue
        relative = template.relative_to(source)
        output = destination / relative
        text = template.read_text(encoding="utf-8")
        for token, value in replacements.items():
            text = text.replace("{{" + token + "}}", value)
        unresolved = sorted(set(re.findall(r"\{\{[A-Za-z0-9_]+\}\}", text)))
        if unresolved:
            raise SystemExit(f"Unresolved tokens in {template}: {', '.join(unresolved)}")
        if output.suffix == ".json":
            json.loads(text)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=ROOT / "config/customer.env")
    args = parser.parse_args()

    values = {**load_env(args.env_file), **os.environ}
    catalog = values.get("BUNDLE_VAR_catalog", "").strip()
    schema = values.get("BUNDLE_VAR_schema", "").strip()
    ontology_base_uri = values.get("BUNDLE_VAR_ontology_base_uri", "").strip().rstrip("/")
    if not IDENTIFIER.fullmatch(catalog) or not IDENTIFIER.fullmatch(schema):
        raise SystemExit("BUNDLE_VAR_catalog and BUNDLE_VAR_schema must be valid identifiers")
    if not URI.fullmatch(ontology_base_uri):
        raise SystemExit("BUNDLE_VAR_ontology_base_uri must be a customer-owned HTTPS URI")

    replacements = {
        "catalog": catalog,
        "schema": schema,
        "ontology_base_uri": ontology_base_uri,
    }
    output_root = ROOT / "build/generated"
    total = 0
    total += render_tree(ROOT / "dashboards/templates", output_root / "dashboards", replacements)
    total += render_tree(ROOT / "genie_spaces/templates", output_root / "genie_spaces", replacements)
    total += render_tree(ROOT / "ontology/templates", output_root / "ontology", replacements)
    print(f"Rendered {total} customer-specific assets in {output_root}")


if __name__ == "__main__":
    main()
