#!/usr/bin/env python3
"""Validate customer configuration without contacting the workspace."""

from __future__ import annotations

import re
from pathlib import Path

from render_assets import load_env

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "DATABRICKS_CONFIG_PROFILE",
    "DATABRICKS_HOST",
    "BUNDLE_VAR_app_name",
    "BUNDLE_VAR_catalog",
    "BUNDLE_VAR_schema",
    "BUNDLE_VAR_sql_warehouse_id",
    "BUNDLE_VAR_workspace_id",
    "BUNDLE_VAR_ai_model",
    "BUNDLE_VAR_admin_users",
    "BUNDLE_VAR_app_user_group",
    "BUNDLE_VAR_app_admin_group",
    "BUNDLE_VAR_lakebase_project",
    "BUNDLE_VAR_lakebase_owner_role",
    "BUNDLE_VAR_lakebase_host",
    "BUNDLE_VAR_managed_memory_store",
    "BUNDLE_VAR_ontology_base_uri",
}
PLACEHOLDER = re.compile(r"(?:customer-|acme_|0000000000000000|example\.com)", re.IGNORECASE)


def main() -> None:
    values = load_env(ROOT / "config/customer.env")
    missing = sorted(key for key in REQUIRED if not values.get(key, "").strip())
    examples = sorted(key for key in REQUIRED if PLACEHOLDER.search(values.get(key, "")))
    if missing or examples:
        if missing:
            print("Missing values:", ", ".join(missing))
        if examples:
            print("Replace example values:", ", ".join(examples))
        raise SystemExit(1)
    print(f"Configuration preflight passed ({len(REQUIRED)} required values)")


if __name__ == "__main__":
    main()
