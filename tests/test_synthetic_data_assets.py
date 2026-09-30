import ast
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "notebooks/00_generate_synthetic_sources.py"
CERTIFIER = ROOT / "notebooks/00_certify_synthetic_sources.py"
RESOURCE = ROOT / "resources/synthetic_data.yml"


def test_synthetic_notebooks_are_valid_python():
    ast.parse(GENERATOR.read_text(encoding="utf-8"))
    ast.parse(CERTIFIER.read_text(encoding="utf-8"))


def test_synthetic_job_is_manual_and_certification_is_blocking():
    definition = yaml.safe_load(RESOURCE.read_text(encoding="utf-8"))
    job = definition["resources"]["jobs"]["quetzal_generate_synthetic_sources"]
    assert "schedule" not in job
    assert "trigger" not in job
    assert job["max_concurrent_runs"] == 1
    assert job["tags"]["execution_mode"] == "manual-only"
    assert [task["task_key"] for task in job["tasks"]] == [
        "generate_synthetic_sources",
        "certify_synthetic_sources",
    ]
    assert job["tasks"][1]["depends_on"] == [{"task_key": "generate_synthetic_sources"}]
    assert job["tasks"][0]["notebook_task"]["base_parameters"]["overwrite_confirmation"] == "SYNTHETIC_DEMO_ONLY"


def test_generator_contains_all_approved_canonical_tables_and_safety_gates():
    source = GENERATOR.read_text(encoding="utf-8")
    approved_tables = {
        "bronze_segmentos",
        "bronze_planes",
        "bronze_torres_red",
        "silver_clientes",
        "silver_suscripciones",
        "silver_facturas",
        "silver_tickets",
        "silver_nps",
        "silver_telemetria_red",
        "silver_cdrs",
        "silver_churn_features",
        "gold_churn_predictions",
        "gold_churn_risk_summary",
        "gold_clv_segments",
        "gold_customer_satisfaction",
        "gold_network_health",
        "gold_network_anomalies",
        "gold_subscriber_metrics",
        "gold_billing_health",
        "gold_revenue_by_country_service",
        "gold_arpu_by_segment",
    }
    assert all(f'"{table}"' in source for table in approved_tables)
    assert "SYNTHETIC_DEMO_ONLY" in source
    assert "data_classification' = 'synthetic" in source
    assert "generated_by' = 'quetzal-customer-kit" in source
    assert "Refusing to replace" in source
    assert "@example.com" in source
    assert "+000" in source
    assert "h1 + h2" not in source
    assert "h0 + h2" not in source


def test_certifier_checks_referential_integrity_determinism_and_demo_coverage():
    source = CERTIFIER.read_text(encoding="utf-8")
    required_gates = {
        "fk:subscriptions_customers",
        "fk:invoices_subscriptions",
        "business:invoice_equation",
        "business:single_churn_source",
        "journey:customer_360",
        "journey:proactive_retention",
        "journey:campaign_eligible",
        "journey:voice_of_customer",
        "journey:sla_breach_candidates",
        "journey:network_incidents",
        "dataset_fingerprint",
    }
    assert all(gate in source for gate in required_gates)
    assert "raise RuntimeError" in source
