import inspect
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

os.environ.setdefault("QUETZAL_ALLOW_LOCAL_IDENTITY_FALLBACK", "true")

import app as quetzal
from server import connectors, operations, platform
from server.config import Settings
from server.models import (
    CampaignOptimizeRequest,
    ChatRequest,
    FinancialImpactRequest,
    GenieQueryRequest,
    ReportRequest,
    ScenarioRequest,
)

client = TestClient(quetzal.app)


def test_missing_identity_fails_closed_outside_local_development():
    with patch.dict(os.environ, {"QUETZAL_ALLOW_LOCAL_IDENTITY_FALLBACK": "false"}):
        response = client.get("/api/me")
    assert response.status_code == 401


def test_local_identity_fallback_is_explicit_opt_in():
    with patch.dict(os.environ, {"QUETZAL_ALLOW_LOCAL_IDENTITY_FALLBACK": "true"}):
        response = client.get("/api/me")
    assert response.status_code == 200
    assert response.json()["email"] == "quetzal-operator"


def test_health_and_security_headers():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["version"] == "3.0.0"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"]


def test_request_contracts_reject_untrusted_values():
    assert ReportRequest(country="MX").country == "MX"
    for payload in (
        {"country": "MX' OR 1=1 --"},
        {"country": "US"},
        {"country": "MX", "unexpected": True},
    ):
        try:
            ReportRequest.model_validate(payload)
            raise AssertionError("invalid report payload was accepted")
        except ValidationError:
            pass

    for model, payload in (
        (GenieQueryRequest, {"space": "ingresos", "question": " "}),
        (ChatRequest, {"message": "x" * 4001}),
    ):
        try:
            model.model_validate(payload)
            raise AssertionError("invalid text payload was accepted")
        except ValidationError:
            pass


def test_reports_endpoint_blocks_sql_injection_before_query():
    response = client.post("/api/reports", json={"country": "MX' OR 1=1 --"})
    assert response.status_code == 422
    assert response.json()["detail"] == "Solicitud inválida."


def test_kpi_contract_preserves_frontend_keys_and_semantics():
    row = {
        "total_revenue": "1000",
        "avg_ticket": "40",
        "collected": "900",
        "revenue_period_start": "2025-09-01",
        "revenue_period_end": "2026-08-01",
        "nps": "12.3",
        "csat": "4.1",
        "surveys": "200",
        "satisfaction_as_of": "2026-08-01",
        "network_health": "96.1",
        "towers_alert": "4",
        "latency": "21.0",
        "network_as_of": "2026-08-31T23:00:00Z",
        "active_subscribers": "950",
        "churn_rate": "2.3",
        "subscribers_as_of": "2026-08-01",
    }
    with patch.object(quetzal, "run_sql", return_value=[row]):
        result = quetzal.get_kpis()
    assert result["revenue"]["total_revenue"] == "1000"
    assert result["network"]["uptime"] == "96.1"
    assert result["network"]["health_score"] == "96.1"
    assert result["network"]["metric_semantics"] == "healthy_measurements_pct"


def test_sql_results_are_cached_and_defensively_copied():
    response = SimpleNamespace(
        statement_id="statement-1",
        status=SimpleNamespace(state=platform.StatementState.SUCCEEDED, error=None),
        manifest=SimpleNamespace(schema=SimpleNamespace(columns=[SimpleNamespace(name="value")])),
        result=SimpleNamespace(data_array=[["1"]]),
    )
    execution = Mock()
    execution.execute_statement.return_value = response
    fake_client = SimpleNamespace(statement_execution=execution)
    platform.clear_query_cache()
    with patch.object(platform, "workspace_client", return_value=fake_client):
        first = platform.run_sql("SELECT 1 AS value", cache_ttl=30)
        first[0]["value"] = "changed"
        second = platform.run_sql("SELECT 1 AS value", cache_ttl=30)
    assert second == [{"value": "1"}]
    assert execution.execute_statement.call_count == 1


def test_ai_chat_uses_governed_internal_snapshot():
    first = Mock(status_code=200)
    first.json.return_value = {
        "output": [{
            "type": "function_call",
            "name": "telecom_snapshot",
            "call_id": "call-1",
            "arguments": '{"scope":"network"}',
        }]
    }
    second = Mock(status_code=200)
    second.json.return_value = {
        "model": "test-model",
        "usage": {"total_tokens": 20},
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "Red verificada.", "annotations": []}]}],
    }
    with patch.object(quetzal.http_requests, "post", side_effect=[first, second]) as post, patch.object(
        quetzal, "_execute_telecom_snapshot", return_value='{"scope":"network"}'
    ), patch.object(quetzal, "_headers", return_value={"Authorization": "Bearer test"}):
        result = quetzal.ai_chat(ChatRequest(message="¿Cómo está la red?"))
    assert result["response"] == "Red verificada."
    assert result["internal_data_used"] is True
    assert result["web_search_used"] is False
    assert any(tool["name"] == "telecom_snapshot" for tool in post.call_args_list[0].kwargs["json"]["tools"])


def test_ai_text_extractor_supports_compatible_response_shapes():
    text, citations = quetzal._extract_ai_text({
        "output_text": "Respuesta directa.",
        "output": [{"type": "message", "content": [{
            "type": "text", "text": "Respuesta compatible.",
            "annotations": [{"type": "url_citation", "url": "https://example.com", "title": "Fuente"}],
        }]}],
    })
    assert "Respuesta directa." in text
    assert "Respuesta compatible." in text
    assert citations == [{"url": "https://example.com", "title": "Fuente"}]


def test_ai_chat_forces_synthesis_after_tool_budget_and_returns_sources():
    calls = []
    for index in range(3):
        response = Mock(status_code=200)
        response.json.return_value = {
            "output": [{
                "type": "function_call", "name": "web_search", "call_id": f"call-{index}",
                "arguments": '{"query":"competencia Ecuador"}',
            }]
        }
        calls.append(response)
    final = Mock(status_code=200)
    final.json.return_value = {
        "model": "test-model",
        "output": [{"type": "message", "content": [{"type": "text", "text": "Claro es el principal competidor."}]}],
    }
    calls.append(final)
    search_result = '[{"title":"ARCOTEL","url":"https://arcotel.gob.ec/data","snippet":"Mercado"}]'
    with patch.object(quetzal.http_requests, "post", side_effect=calls) as post, patch.object(
        quetzal, "_execute_search", return_value=search_result
    ), patch.object(quetzal, "_headers", return_value={"Authorization": "Bearer test"}):
        result = quetzal.ai_chat(ChatRequest(message="¿Cuál es la principal competencia en Ecuador?"))
    assert result["answer_status"] == "verified"
    assert result["response"].startswith("Claro")
    assert result["citations"][0]["url"] == "https://arcotel.gob.ec/data"
    assert result["trace_id"].startswith("iq-")
    assert "tools" not in post.call_args_list[-1].kwargs["json"]


def test_ai_chat_never_labels_empty_model_output_as_verified():
    response = Mock(status_code=200)
    response.json.return_value = {"model": "test-model", "output": []}
    with patch.object(quetzal.http_requests, "post", return_value=response), patch.object(
        quetzal, "_headers", return_value={"Authorization": "Bearer test"}
    ):
        result = quetzal.ai_chat(ChatRequest(message="Explica el mercado", disable_tools=True))
    assert result["answer_status"] == "error"
    assert "no devolvió texto final" in result["response"]


def test_external_followup_keeps_only_web_search_and_preserves_topic():
    tools, mode = quetzal._select_chat_tools(
        continuation_mode="auto",
        history=[
            {"role": "user", "text": "¿Cuál es la principal competencia en Ecuador?", "tools": []},
            {"role": "assistant", "text": "Claro lidera el mercado móvil.", "tools": ["web_search"]},
        ],
        message="¿Y en el mercado de hogares?",
        disable_tools=False,
    )
    assert mode == "external"
    assert [tool["name"] for tool in tools] == ["web_search"]


def test_explicit_internal_switch_after_web_enables_only_snapshot():
    tools, mode = quetzal._select_chat_tools(
        continuation_mode="internal",
        history=[{"role": "assistant", "text": "Contexto competitivo.", "tools": ["web_search"]}],
        message="Ahora compara con nuestros clientes de Quetzal.",
        disable_tools=False,
    )
    assert mode == "internal"
    assert [tool["name"] for tool in tools] == ["telecom_snapshot"]


def test_genie_result_preserves_structured_attachments_and_tracking():
    response = Mock(status_code=200)
    response.json.return_value = {
        "status": "COMPLETED", "created_timestamp": 10, "last_updated_timestamp": 20,
        "attachments": [
            {"attachment_id": "query-1", "query": {
                "query": "SELECT 1", "title": "Red", "description": "Resumen",
                "statement_id": "statement-1", "query_result_metadata": {"row_count": 13},
                "thoughts": [{"content": "Paso", "thought_type": "STEPS"}],
            }},
            {"text": {"content": "Respuesta Genie", "purpose": "ANSWER"}},
            {"suggested_questions": {"questions": ["¿Por país?"]}},
            {"attachment_id": "viz-1", "viz": {"query_attachment_id": "query-1"}},
        ],
    }
    with patch.object(quetzal.http_requests, "get", return_value=response), patch.object(
        quetzal, "_headers", return_value={"Authorization": "Bearer test"}
    ):
        result = quetzal.genie_result("red", "conversation-1", "message-1")
    assert result["conversation_id"] == "conversation-1"
    assert [attachment["type"] for attachment in result["attachments"]] == [
        "query", "text", "suggested_questions", "viz",
    ]
    assert result["attachments"][0]["row_count"] == 13


def test_genie_query_continues_existing_conversation():
    response = Mock(status_code=200)
    response.json.return_value = {"id": "message-follow-up"}
    with patch.object(quetzal.http_requests, "post", return_value=response) as post_request, patch.object(
        quetzal, "_headers", return_value={"Authorization": "Bearer test"}
    ):
        result = client.post("/api/genie/query", json={
            "space": "red",
            "question": "Agora detalhe o Brasil",
            "conversation_id": "conversation-existing",
        })

    assert result.status_code == 200
    assert result.json()["conversation_id"] == "conversation-existing"
    assert result.json()["message_id"] == "message-follow-up"
    assert result.json()["continued"] is True
    assert post_request.call_args.args[0].endswith(
        "/conversations/conversation-existing/messages"
    )


def test_genie_agent_mode_returns_full_chart_data_and_mode():
    response = Mock(status_code=200)
    response.content = (
        'data: {"type":"response.created","response":{"conversation_id":"agent-conv-1"}}\n\n'
        'data: {"type":"response.output_item.done","item":{"type":"function_call",'
        '"status":"completed","arguments":"{\\"sql\\":\\"SELECT mes, ingresos, clientes FROM gold\\",'
        '\\"title\\":\\"Evolución\\"}"}}\n\n'
        'data: {"type":"response.output_item.done","item":{"type":"function_call_output",'
        '"output":"**Evolución**\\n\\n| mes | ingresos | clientes |\\n|---|---:|---:|\\n'
        '| 2026-01 | 100 | 8 |\\n| 2026-02 | 120 | 9 |"}}\n\n'
        'data: {"type":"response.output_item.done","item":{"type":"message","status":"completed",'
        '"content":[{"type":"output_text","text":"Los ingresos aumentaron."}]}}\n\n'
    ).encode()
    with patch.object(quetzal.http_requests, "post", return_value=response) as post_request, patch.object(
        quetzal, "_headers", return_value={"Authorization": "Bearer test"}
    ):
        result = quetzal._genie_agent_call(
            {"id": "space-1", "name": "Ingresos"},
            "Analiza la evolución",
            "agent-conv-existing",
        )

    assert result["mode"] == "agent"
    assert result["conversation_id"] == "agent-conv-1"
    chart = next(attachment for attachment in result["attachments"] if attachment["type"] == "chart_data")
    assert [column["name"] for column in chart["columns"]] == ["mes", "ingresos", "clientes"]
    assert chart["row_count"] == 2
    assert post_request.call_args.kwargs["json"]["conversation_id"] == "agent-conv-existing"


def test_customer_search_is_parameterized():
    with patch.object(operations, "run_sql", return_value=[]) as run:
        response = client.get("/api/customers/search?q=andres&country=PA")
    assert response.status_code == 200
    assert ":term" in run.call_args.args[0]
    assert run.call_args.kwargs["parameters"] == {"term": "andres", "country": "PA"}


def test_proactive_care_returns_navigable_customer_id():
    with patch.object(operations, "run_sql", return_value=[]) as run:
        operations.proactive_care()
    sql = run.call_args.args[0]
    assert "c.cliente_id AS customer_id" in sql
    assert "customer_ref" in sql
    assert "andres" not in run.call_args.args[0]


def test_customer_recommendations_prioritize_service_before_sales():
    profile = {
        "open_tickets": 2, "churn_probability": 0.81, "overdue_balance": 40,
        "nps_ultimo": 3, "acepta_marketing": True,
    }
    tickets = [{"sla_status": "BREACHED"}, {"sla_status": "WITHIN_TARGET"}]
    offers = [{"product_name": "Fibra", "recommendation_type": "CROSS_SELL"}]
    actions = operations._next_best_actions(profile, tickets, offers)
    assert actions[0]["type"] == "SERVICE_RECOVERY"
    assert actions[1]["type"] == "RETENTION"
    assert all(action["type"] != "CROSS_SELL" for action in actions)


def test_graph_signals_add_context_without_overwriting_churn_probability():
    profile = {
        "open_tickets": 0,
        "churn_probability": 0.52,
        "graph_churn_probability": 0.74,  # legacy value must not drive v3 retention
        "reach_score": 82,
        "network_exposure_score": 68,
        "overdue_balance": 0,
        "nps_ultimo": 8,
        "acepta_marketing": False,
    }
    actions = operations._next_best_actions(profile, [], [])
    assert [action["type"] for action in actions] == ["NETWORK_CARE"]
    assert "exposición" in actions[0]["reason"]


def test_demo_journey_is_deterministic_and_never_claims_tower_attribution():
    incident = {
        "incident_id": "NET-TWR-1", "country": "BR", "severity": "CRITICAL",
        "status": "NEW", "detected_at": "2026-09-09T10:00:00Z",
    }
    customer = {
        "customer_id": "CLI-1", "country": "BR", "churn_probability": 0.88,
        "monthly_revenue": 90,
    }
    access = {"actor": "demo@example.com", "roles": ["CARE_AGENT"], "countries": ["BR"]}
    with patch.object(operations, "_access", return_value=access), patch.object(
        operations, "run_sql", side_effect=[[incident], [customer]],
    ) as run:
        response = client.get("/api/demo/journey?country=BR")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["customer"]["customer_id"] == "CLI-1"
    assert payload["relationship_semantics"] == {
        "association_type": "SAME_MARKET_EXAMPLE",
        "direct_customer_attribution": False,
        "statement": "El cliente se selecciona como ejemplo prioritario del mismo país; no existe vínculo cliente-torre en las fuentes disponibles.",
    }
    assert "ORDER BY priority_score DESC" in run.call_args_list[0].args[0]
    assert run.call_args_list[1].kwargs["parameters"] == {"country": "BR"}
    assert [step["id"] for step in payload["steps"]] == [
        "PREFLIGHT", "INCIDENT", "VOICE_OF_CUSTOMER", "CUSTOMER_360",
        "RECOMMENDATION", "CAMPAIGN_OPTIMIZER", "FINANCIAL_IMPACT",
    ]
    assert payload["steps"][5]["requires_human_approval"] is True


def test_demo_journey_enforces_rbac_before_queries():
    with patch.object(
        operations, "_access",
        return_value={"actor": "viewer@example.com", "roles": [], "countries": ["BR"]},
    ), patch.object(operations, "run_sql") as run:
        response = client.get("/api/demo/journey?country=BR")
    assert response.status_code == 403
    run.assert_not_called()


def test_counterfactual_financial_impact_exposes_formulas_and_intermediates():
    baseline = [{
        "eligible_customers": "5000", "avg_churn_probability": "0.20",
        "avg_monthly_revenue_usd": "50", "avg_lifetime_value_usd": "900",
        "score_as_of": "2026-09-09T00:00:00Z",
    }]
    with patch.object(operations, "run_sql", return_value=baseline) as run:
        response = client.post("/api/demo/financial-impact", json={
            "country": "BR", "treated_customers": 1000,
            "relative_churn_reduction_pct": 10, "cost_per_contact_usd": 5,
            "horizon_months": 12,
        })
    assert response.status_code == 200
    payload = response.json()
    assert payload["estimate_type"] == "COUNTERFACTUAL_ESTIMATE"
    assert payload["result"]["expected_churners_before_treatment"] == 200
    assert payload["result"]["estimated_avoided_churners"] == 20
    assert payload["result"]["estimated_retained_revenue_usd"] == 12000
    assert payload["result"]["estimated_net_impact_usd"] == 7000
    assert payload["sensitivity"]["conservative"]["estimated_net_impact_usd"] < 7000
    assert "contrafactual" in payload["disclaimer"].lower()
    assert run.call_args.kwargs["parameters"] == {"country": "BR"}
    assert ":country" in run.call_args.args[0]


def test_financial_impact_contract_rejects_unsafe_assumptions():
    assert FinancialImpactRequest().horizon_months == 12
    assert client.post("/api/demo/financial-impact", json={
        "country": "US", "treated_customers": 1000,
        "relative_churn_reduction_pct": 15, "cost_per_contact_usd": 8,
        "horizon_months": 12,
    }).status_code == 422
    assert client.post("/api/demo/financial-impact", json={
        "country": "BR", "treated_customers": 0,
        "relative_churn_reduction_pct": 15, "cost_per_contact_usd": 8,
        "horizon_months": 12,
    }).status_code == 422


def test_voice_of_customer_is_synthetic_governed_and_actionable():
    summary = [{
        "customers_observed": "120", "tickets": "20", "open_tickets": "4",
        "sla_breaches": "3", "avg_csat": "3.5", "nps_responses": "30",
        "detractors": "12", "avg_nps": "6.4", "high_churn_customers": "15",
        "tickets_as_of": "2026-09-20", "nps_as_of": "2026-09-18",
        "customer_360_as_of": "2026-09-21",
    }]
    themes = [{
        "theme_id": "NETWORK_QUALITY", "mentions": "12", "previous_mentions": "8",
        "negative_signals": "6", "open_cases": "3", "sla_breaches": "2",
        "avg_nps": "5.5", "latest_evidence_at": "2026-09-20",
    }]
    examples = [{
        "theme_id": "NETWORK_QUALITY", "customer_id": "CLI-1", "customer_ref": "A•••LI-1",
        "country": "BR", "churn_probability": "0.8", "nps": "4", "open_tickets": "2",
    }]
    access = {"actor": "care@example.com", "roles": ["CARE_AGENT"], "countries": ["BR"]}
    with patch.object(operations, "_access", return_value=access), patch.object(
        operations, "run_sql", side_effect=[summary, themes, examples],
    ) as run, patch.object(operations, "execute_sql") as execute:
        response = client.get("/api/voc/overview?country=ALL&window_days=90&max_themes=5")
    assert response.status_code == 200
    payload = response.json()
    assert payload["synthetic"] is True
    assert payload["scope"]["effective_countries"] == ["BR"]
    assert payload["methodology"] == {
        "type": "DETERMINISTIC_RULE_BASED_SYNTHESIS",
        "ai_inference_used": False,
        "synthetic_data": True,
        "theme_mapping_version": "voc-rules-v1",
    }
    theme = payload["themes"][0]
    assert theme["theme_id"] == "NETWORK_QUALITY"
    assert theme["trend"] == "UP"
    assert theme["customer_examples"][0]["customer_360_path"] == "/customers/CLI-1/360"
    assert "name" not in theme["customer_examples"][0]
    assert {item["source"] for item in payload["source_coverage"]} == {
        "silver_tickets", "silver_nps", "ops_customer_360", "ops_sla_policy",
    }
    for call in run.call_args_list:
        assert call.kwargs["parameters"]["country_scope"] == "BR"
        assert call.kwargs["parameters"]["window_days"] == 90
    execute.assert_not_called()


def test_voice_of_customer_enforces_role_and_territory_before_queries():
    with patch.object(
        operations, "_access",
        return_value={"actor": "viewer@example.com", "roles": [], "countries": ["BR"]},
    ), patch.object(operations, "run_sql") as run:
        assert client.get("/api/voc/overview?country=BR").status_code == 403
    run.assert_not_called()
    with patch.object(
        operations, "_access",
        return_value={"actor": "care@example.com", "roles": ["CARE_AGENT"], "countries": ["BR"]},
    ), patch.object(operations, "run_sql") as run:
        assert client.get("/api/voc/overview?country=MX").status_code == 403
    run.assert_not_called()


def test_campaign_optimizer_applies_consent_service_budget_capacity_and_theme():
    funnel = [{
        "customers_in_scope": "100", "marketing_consented": "80",
        "channel_reachable": "70", "service_eligible": "50", "campaign_eligible": "20",
    }]
    selected = [{
        "customer_id": f"CLI-{index}", "customer_ref": f"C•••{index:04d}",
        "country": "BR", "segment": "Premium", "monthly_revenue": "100",
        "churn_probability": "0.8", "nps": "5", "selection_score": str(90 - index),
        "plan_id": "PLAN-1", "product_name": "Fibra", "precio_usd": "50",
    } for index in range(5)]
    access = {"actor": "care@example.com", "roles": ["CARE_AGENT"], "countries": ["BR"]}
    request = {
        "country": "BR", "objective": "RETENTION", "channel": "EMAIL",
        "source_theme_id": "NETWORK_QUALITY", "budget_usd": 10,
        "cost_per_contact_usd": 2, "max_customers": 100, "contact_capacity": 50,
        "expected_response_rate_pct": 10, "horizon_months": 12,
    }
    with patch.object(operations, "_access", return_value=access), patch.object(
        operations, "run_sql", side_effect=[funnel, selected],
    ) as run, patch.object(operations, "execute_sql") as execute, patch.object(
        operations, "dispatch_action",
    ) as dispatch:
        response = client.post("/api/campaigns/optimize", json=request)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "DRAFT"
    assert payload["execution"] == {
        "campaign_sent": False, "records_written": False, "requires_human_approval": True,
    }
    assert payload["scope"]["source_theme_id"] == "NETWORK_QUALITY"
    assert payload["constraints"]["budget_contact_capacity"] == 5
    assert payload["constraints"]["effective_selection_limit"] == 5
    assert payload["funnel"]["selected"] == 5
    assert payload["funnel"]["excluded"] == {
        "no_consent": 20, "channel_unreachable": 10, "service_first": 20,
        "no_offer": 30, "budget_or_capacity": 15,
    }
    assert payload["impact"]["estimated_contact_cost_usd"] == 10
    assert payload["impact"]["budget_remaining_usd"] == 0
    assert payload["formulas"]["contact_cost"] == "clientes seleccionados × costo por contacto"
    assert "presupuesto" in payload["formulas"]["selected"]
    assert payload["audience_preview"][0]["reason_codes"] == [
        "CONSENT_VERIFIED", "CHANNEL_REACHABLE", "SERVICE_ELIGIBLE",
        "HIGH_CHURN_RISK", "VOC_THEME_MATCH",
    ]
    assert "marketing_consented AND channel_reachable AND service_eligible" in run.call_args_list[1].args[0]
    assert "LIMIT 5" in run.call_args_list[1].args[0]
    assert run.call_args_list[1].kwargs["parameters"]["source_theme"] == "NETWORK_QUALITY"
    execute.assert_not_called()
    dispatch.assert_not_called()


def test_campaign_optimizer_is_deterministic_and_never_mutates():
    funnel = [{
        "customers_in_scope": "1", "marketing_consented": "1",
        "channel_reachable": "1", "service_eligible": "1", "campaign_eligible": "1",
    }]
    selected = [{
        "customer_id": "CLI-1", "customer_ref": "A•••I-1", "country": "BR",
        "segment": "Mass", "monthly_revenue": "40", "churn_probability": "0.7",
        "selection_score": "70", "plan_id": None,
    }]

    def reads(query, **kwargs):
        return selected if "ORDER BY selection_score" in query else funnel

    body = CampaignOptimizeRequest(country="BR").model_dump()
    with patch.object(operations, "run_sql", side_effect=reads), patch.object(
        operations, "execute_sql",
    ) as execute:
        first = client.post("/api/campaigns/optimize", json=body)
        second = client.post("/api/campaigns/optimize", json=body)
    assert first.status_code == second.status_code == 200
    assert first.json()["draft_id"] == second.json()["draft_id"]
    assert first.json()["execution"]["records_written"] is False
    execute.assert_not_called()


def test_campaign_optimizer_rejects_invalid_budget_and_enforces_rbac_scope():
    invalid = CampaignOptimizeRequest().model_dump()
    invalid["budget_usd"] = 0
    assert client.post("/api/campaigns/optimize", json=invalid).status_code == 422
    with patch.object(
        operations, "_access",
        return_value={"actor": "viewer@example.com", "roles": ["EXECUTIVE_VIEWER"], "countries": ["BR"]},
    ), patch.object(operations, "run_sql") as run:
        assert client.post("/api/campaigns/optimize", json=CampaignOptimizeRequest(country="BR").model_dump()).status_code == 403
    run.assert_not_called()
    with patch.object(
        operations, "_access",
        return_value={"actor": "care@example.com", "roles": ["CARE_AGENT"], "countries": ["BR"]},
    ), patch.object(operations, "run_sql") as run:
        assert client.post("/api/campaigns/optimize", json=CampaignOptimizeRequest(country="MX").model_dump()).status_code == 403
    run.assert_not_called()


def test_customer_360_unifies_timeline_explainability_and_geographic_context():
    profile = {
        "cliente_id": "CLI-1", "pais_codigo": "BR", "churn_probability": 0.50,
        "baseline_churn_probability": 0.50, "graph_churn_probability": 0.50,
        "graph_lift": 0.0, "retention_priority_score": 72,
        "neighbour_avg_churn_probability": 0.80, "network_exposure_score": 70,
        "reach_score": 82, "risk_diffusion_score": 76,
        "graph_explanation_codes": '["HIGH_RISK_NETWORK_EXPOSURE","HIGH_NETWORK_REACH"]',
        "graph_model_version": "graph-intelligence-v3-ontobricks",
        "graph_scored_at": "2026-09-09T09:00:00Z", "open_tickets": 1,
    }

    def governed_reads(query, **kwargs):
        if "silver_suscripciones" in query:
            return [{"suscripcion_id": "SUB-1", "plan_id": "P-1", "product_name": "Fibra", "fecha_inicio": "2025-01-01"}]
        if "silver_tickets" in query:
            return [{"ticket_id": "T-1", "fecha_creacion": "2026-09-08T08:00:00Z", "sla_status": "BREACHED"}]
        if "silver_facturas" in query:
            return [{"factura_id": "F-1", "fecha_emision": "2026-09-01", "monto_total_usd": 50}]
        if "silver_nps" in query:
            return [{"fecha_encuesta": "2026-08-31", "score": 4, "categoria_nps": "DETRACTOR"}]
        if "ops_customer_next_best_offer" in query:
            return []
        if "ops_recommendation_log" in query:
            return [{"recommendation_id": "R-1", "proposed_at": "2026-09-07", "title": "Retención"}]
        if "ops_incident_candidates" in query:
            return [{"incident_id": "NET-1", "country": "BR", "detected_at": "2026-09-09T10:00:00Z", "status": "NEW"}]
        raise AssertionError(f"Unexpected query: {query}")

    with patch.object(operations, "_customer_profile", return_value=[profile]), patch.object(
        operations, "run_sql", side_effect=governed_reads,
    ):
        response = client.get("/api/customers/CLI-1/360")
    assert response.status_code == 200
    payload = response.json()
    assert payload["explainability"]["method"] == "SEPARATED_PROPENSITY_AND_NETWORK_SIGNALS"
    assert payload["explainability"]["is_shap"] is False
    assert payload["explainability"]["scores"]["individual_baseline"] == 0.5
    assert payload["explainability"]["scores"]["retention_priority"] == 72
    assert payload["explainability"]["scores"]["network_exposure"] == 70
    assert payload["network_context"]["association_type"] == "GEOGRAPHIC_CONTEXT"
    assert payload["network_context"]["direct_customer_attribution"] is False
    assert payload["timeline"][0]["event_type"] == "NETWORK_INCIDENT_CONTEXT"
    assert {item["event_type"] for item in payload["timeline"]}.issuperset({"CHURN_SCORE", "SUPPORT_TICKET", "BILLING", "NPS", "RECOMMENDATION"})


def test_customer_360_checks_country_scope_before_fanout():
    access = {"actor": "care@example.com", "roles": ["CARE_AGENT"], "countries": ["BR"]}
    with patch.object(operations, "_access", return_value=access), patch.object(
        operations, "_customer_profile", return_value=[{"cliente_id": "CLI-1", "pais_codigo": "MX"}],
    ), patch.object(operations, "run_sql") as run:
        response = client.get("/api/customers/CLI-1/360")
    assert response.status_code == 403
    run.assert_not_called()


def test_manual_preflight_never_invokes_inference_or_jobs():
    api_client = SimpleNamespace(do=Mock(return_value={}))
    jobs = Mock()
    fake_workspace = SimpleNamespace(api_client=api_client, jobs=jobs)

    def preflight_sql(query, **kwargs):
        if "ops_graph_run_log" in query:
            return [{"run_id": "graph-1", "status": "SUCCEEDED", "completed_at": "2026-09-09"}]
        return [{"preflight": 1}]

    with patch.object(operations, "workspace_client", return_value=fake_workspace), patch.object(
        operations, "run_sql", side_effect=preflight_sql,
    ), patch.object(quetzal.http_requests, "post") as inference:
        response = client.get("/api/demo/preflight")
    assert response.status_code == 200
    payload = response.json()
    assert payload["paid_inference_used"] is False
    assert payload["job_triggered"] is False
    assert payload["execution_mode"] == "MANUAL_READ_ONLY"
    assert {item["name"] for item in payload["checks"]} == {
        "warehouse", "genie", "ai_gateway", "lakebase", "managed_memory",
        "dashboard", "rbac", "graph_snapshot", "ontobricks",
    }
    inference.assert_not_called()
    jobs.assert_not_called()


def test_preflight_accepts_published_legacy_graph_without_triggering_refresh():
    api_client = SimpleNamespace(do=Mock(return_value={}))
    fake_workspace = SimpleNamespace(api_client=api_client, jobs=Mock())

    def preflight_sql(query, **kwargs):
        if "ops_graph_run_log" in query:
            return []
        if "ops_customer_graph_360" in query:
            return [{
                "model_version": "graph-fusion-v1", "computed_at": "2026-09-02",
                "customers": 60000,
            }]
        return [{"preflight": 1}]

    with patch.object(operations, "workspace_client", return_value=fake_workspace), patch.object(
        operations, "run_sql", side_effect=preflight_sql,
    ):
        response = client.get("/api/demo/preflight")

    graph = next(item for item in response.json()["checks"] if item["name"] == "graph_snapshot")
    assert graph["status"] == "READY"
    assert graph["detail"]["source"] == "PUBLISHED_VIEW"
    assert graph["detail"]["policy_status"] == "LEGACY_PENDING_MANUAL_REFRESH"
    fake_workspace.jobs.assert_not_called()


def test_customer_graph_returns_bounded_interactive_payload():
    center = [{
        "customer_id": "CLI-1", "label": "Ana", "country": "BR", "segment": "Premium",
        "community_id": "COM-1234567890", "risk_tier": "HIGH", "churn_probability": 0.8,
        "influence_score": 75, "contagion_score": 60, "unique_contacts": 12,
        "countries_reached": 3, "international_call_pct": 8, "influenced_revenue_usd": 900,
        "computed_at": "2026-09-08T00:00:00Z",
    }]
    contacts = [{
        "peer_id": "CLI-2", "calls": 8, "minutes": 42, "dropped_pct": 2,
        "international": False, "affinity": "SOCIAL", "reciprocal": True,
        "label": "Bia", "country": "BR", "segment": "Mass",
        "community_id": "COM-1234567890", "risk_tier": "MEDIUM",
        "churn_probability": 0.44, "influence_score": 48, "contagion_score": 35,
    }]
    with patch.object(operations, "run_sql", side_effect=[center, contacts]):
        response = client.get("/api/customers/CLI-1/graph?max_neighbors=30&affinity=ALL")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["nodes"][0]["is_center"] is True
    assert payload["edges"][0]["target"] == "CLI-2"
    assert 0 <= payload["nodes"][1]["x"] <= 100
    assert payload["relationship_definition"]["version"] == "LEGACY_CALL_V1"


def test_customer_graph_exposes_qualified_relationship_policy():
    center = [{
        "customer_id": "CLI-1", "country": "BR", "model_version": "graph-fusion-v2-qualified",
        "community_id": "COM-1234567890",
    }]
    with patch.object(operations, "run_sql", side_effect=[center, []]):
        response = client.get("/api/customers/CLI-1/graph?affinity=FREQUENT")
    assert response.status_code == 200
    definition = response.json()["relationship_definition"]
    assert definition["version"] == "QUALIFIED_V2"
    assert definition["status"] == "ACTIVE"
    assert "3+ llamadas" in definition["criteria"]


def test_graph_pipeline_qualifies_contacts_and_is_manual_only():
    source = Path("notebooks/03_graph_intelligence.py").read_text(encoding="utf-8")
    assert "graph-intelligence-v3-ontobricks" in source
    assert "calls >= {min_contact_calls} OR minutes >= {min_contact_minutes} OR reciprocal" in source
    assert "max_contact_recency_days" in source
    assert "relationship_weight" in source
    assert "weighted_pagerank" in source
    assert "risk_diffusion" in source
    assert "retention_priority_score" in source
    assert "gold_quetzal_knowledge_graph_triples" in source
    assert "dbutils.notebook.exit(str(result))" in source.split("except Exception as exc:", 1)[1]
    assert "WHEN 'AFFINITY' THEN 'FREQUENT'" in source
    dab = Path("resources/operations.yml").read_text(encoding="utf-8")
    assert 'min_contact_calls: "3"' in dab
    assert 'min_contact_minutes: "10"' in dab
    assert 'max_contact_recency_days: "60"' in dab
    assert "schedule:" not in dab and "trigger:" not in dab


def test_graph_methodology_separates_probability_reach_and_exposure():
    snapshot = [{"model_version": "graph-intelligence-v3-ontobricks", "customers": 60000}]
    triples = [{"triples": 1500000, "subjects": 250000, "predicates": 18}]
    with patch.object(operations, "run_sql", side_effect=[snapshot, triples]):
        response = client.get("/api/graph/methodology")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ACTIVE"
    assert payload["pagerank_decision"]["is_best_churn_algorithm"] is False
    assert payload["ontobricks"]["triple_table"] == "gold_quetzal_knowledge_graph_triples"
    roles = {item["id"]: item for item in payload["algorithms"]}
    assert roles["BASELINE_CHURN"]["output"] == "Probabilidad 0–1"
    assert roles["NETWORK_REACH"]["algorithm"] == "PageRank ponderado"


def test_customer_graph_applies_authenticated_country_scope():
    center = [{"customer_id": "CLI-1", "country": "MX"}]
    with patch.object(operations, "_access", return_value={"actor": "care@example.com", "roles": ["CARE_AGENT"], "countries": ["BR"]}), patch.object(
        operations, "run_sql", return_value=center
    ):
        response = client.get("/api/customers/CLI-1/graph")
    assert response.status_code == 403


def test_graph_network_marks_node_types_and_summarizes_high_risk():
    community = [{
        "node_id": "COM-1234567890", "node_type": "community", "customer_count": 8,
        "label": "Red Premium BR · 3 país(es)", "dominant_segment": "Premium",
        "high_risk_customers": 3, "influenced_revenue_usd": 1200,
    }]
    with patch.object(operations, "run_sql", side_effect=[community, []]):
        response = client.get("/api/graph/network?level=community")
    assert response.status_code == 200
    payload = response.json()
    assert payload["nodes"][0]["node_type"] == "community"
    assert payload["nodes"][0]["label"] == "Red Premium BR · 3 país(es)"
    assert payload["summary"]["high_risk_customers"] == 3


def test_graph_group_operational_returns_actionable_members_offers_and_playbooks():
    group = [{
        "community_id": "COM-1234567890", "primary_country": "BR", "dominant_segment": "Premium",
        "countries_reached": 3, "customer_count": 2, "high_risk_customers": 1,
        "customers_with_open_tickets": 1, "customers_with_sla_pressure": 1,
        "detractors": 1, "marketing_eligible_customers": 1,
    }]
    members = [{
        "customer_id": "CLI-1", "customer_ref": "A•••I-1", "risk_tier": "HIGH",
        "next_best_action": "SERVICE_RECOVERY", "proposed_product": "Fibra 600",
    }]
    offers = [{"plan_id": "PLAN-1", "product_name": "Fibra 600", "eligible_customers": 1}]
    with patch.object(operations, "run_sql", side_effect=[group, members, offers]) as run:
        response = client.get(
            "/api/graph/communities/COM-1234567890/operational?sort=opportunity&limit=10&offset=0"
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["group"]["display_name"] == "Red Premium BR · Alcance regional"
    assert payload["group"]["technical_id"] == "COM-1234567890"
    assert payload["members"][0]["next_best_action"] == "SERVICE_RECOVERY"
    assert payload["offers"][0]["product_name"] == "Fibra 600"
    assert {item["type"] for item in payload["playbooks"]} == {
        "SERVICE_RECOVERY", "RETENTION", "NPS_RECOVERY", "GROWTH",
    }
    assert payload["pagination"] == {"offset": 0, "limit": 10, "total": 2}
    assert "coalesce(o.recommendation_score, 0) DESC" in run.call_args_list[1].args[0]
    assert "WHERE marketing_eligible = true" in run.call_args_list[1].args[0]


def test_graph_group_operational_rejects_invalid_id_and_enforces_care_role():
    assert client.get("/api/graph/communities/not-a-group/operational").status_code == 400
    with patch.object(
        operations, "_access",
        return_value={"actor": "viewer@example.com", "roles": ["EXECUTIVE_VIEWER"], "countries": []},
    ), patch.object(operations, "run_sql") as run:
        response = client.get("/api/graph/communities/COM-1234567890/operational")
    assert response.status_code == 403
    run.assert_not_called()


def test_graph_group_operational_applies_territorial_scope_to_queries():
    group = [{
        "community_id": "COM-1234567890", "primary_country": "BR", "dominant_segment": "Mass",
        "countries_reached": 1, "customer_count": 0,
    }]
    with patch.object(
        operations, "_access",
        return_value={"actor": "care@example.com", "roles": ["CARE_AGENT"], "countries": ["BR"]},
    ), patch.object(operations, "run_sql", side_effect=[group, [], []]) as run:
        response = client.get("/api/graph/communities/COM-1234567890/operational?country=BR&limit=10")
    assert response.status_code == 200
    for call in run.call_args_list:
        assert "array_contains(split(:country_scope, ','), f.country)" in call.args[0]
        assert call.kwargs["parameters"]["country_scope"] == "BR"


def test_quetzal_iq_accepts_governed_graph_scope():
    assert quetzal._TELECOM_SNAPSHOT_TOOL["parameters"]["properties"]["scope"]["enum"][-1] == "graph"
    source = inspect.getsource(quetzal.ai_chat)
    assert '"graph"' in source
    assert "graph_terms" in source


def test_graph_workflow_is_manual_only_and_deduplicates_active_run():
    active_run = SimpleNamespace(
        run_id=77, run_name="graph", start_time=1, end_time=None, run_page_url="https://run",
        state=SimpleNamespace(life_cycle_state="RUNNING", result_state=None, state_message="running"),
    )
    fake_workspace = SimpleNamespace(jobs=SimpleNamespace(list_runs=Mock(return_value=iter([active_run]))))
    with patch.object(operations, "settings", SimpleNamespace(graph_job_id="123")), patch.object(
        operations, "workspace_client", return_value=fake_workspace
    ):
        response = client.post("/api/graph/runs")
    assert response.status_code == 202
    assert response.json()["started"] is False
    assert response.json()["scheduled"] is False


def test_settings_normalizes_databricks_host(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "workspace.example.com/")
    monkeypatch.setenv("QUETZAL_ONTOBRICKS_URL", "DISABLED")
    configured = Settings.from_env()
    assert configured.host == "https://workspace.example.com"
    assert configured.ai_url.startswith("https://workspace.example.com/")
    assert configured.ontobricks_url == ""


def test_incident_filters_are_parameterized():
    with patch.object(operations, "run_sql", return_value=[]) as run:
        response = client.get("/api/incidents?severity=CRITICAL&country=MX")
    assert response.status_code == 200
    query = run.call_args.args[0]
    assert "c.severity = :severity" in query
    assert "c.country = :country" in query
    assert run.call_args.kwargs["parameters"] == {"severity": "CRITICAL", "country": "MX"}
    assert "MX" not in query


def test_capacity_scenario_returns_explainable_projection():
    baseline = [{"country": "MX", "current_capacity_pct": "80", "throughput_mbps": "250", "towers_alert": "10", "measurements": "100"}]
    with patch.object(operations, "run_sql", return_value=baseline):
        result = operations.capacity_scenario(ScenarioRequest(country="MX", growth_pct=25, horizon_days=90))
    assert result["results"][0]["projected_capacity_pct"] == 100
    assert result["results"][0]["risk"] == "CRITICAL"
    assert result["totals"]["estimated_investment_usd"] > 0


def test_action_creation_requires_approval_and_audits():
    with patch.object(operations, "run_sql", return_value=[{"incident_id": "NET-QT-1"}]), patch.object(
        operations, "execute_sql"
    ) as execute:
        response = client.post(
            "/api/incidents/NET-QT-1/actions",
            json={"action_type": "CREATE_WORK_ORDER", "rationale": "Backhaul degradation confirmed"},
        )
    assert response.status_code == 201
    assert response.json()["status"] == "PENDING_APPROVAL"
    assert execute.call_count == 2


def test_invalid_operational_filters_are_rejected():
    assert client.get("/api/incidents?severity=DROP%20TABLE").status_code == 422
    assert client.post("/api/scenarios/capacity", json={"country": "US", "growth_pct": 20}).status_code == 422


def test_rbac_blocks_viewer_mutations():
    with patch.object(operations, "run_sql", return_value=[{"role": "EXECUTIVE_VIEWER", "country_scope": "MX"}]):
        response = client.post(
            "/api/incidents/NET-QT-1/actions",
            headers={"x-forwarded-email": "viewer@example.com"},
            json={"action_type": "CREATE_WORK_ORDER", "rationale": "Validated operational rationale"},
        )
    assert response.status_code == 403


def test_segregation_prevents_requester_from_approving_own_action():
    reads = [
        [{"role": "ACTION_APPROVER", "country_scope": None}],
        [{"status": "PENDING_APPROVAL", "requested_by": "operator@example.com"}],
    ]
    with patch.object(operations, "run_sql", side_effect=reads), patch.object(operations, "execute_sql") as execute:
        response = client.post(
            "/api/actions/ACT-1/decision",
            headers={"x-forwarded-email": "operator@example.com"},
            json={"decision": "APPROVED", "note": "self approval must fail"},
        )
    assert response.status_code == 409
    assert execute.call_count == 0


def test_internal_connector_is_idempotent_queue_contract():
    result = connectors.dispatch_action({"action_id": "ACT-1", "action_type": "CREATE_WORK_ORDER"}, "INTERNAL")
    assert result.success is True
    assert result.connector == "INTERNAL"
    assert result.execution_ref.startswith("QZ-")


def test_alert_comparisons_are_explicit():
    assert operations._comparison(">=", 85, 85) is True
    assert operations._comparison("<", 84, 85) is True
    assert operations._comparison("invalid", 100, 1) is False
