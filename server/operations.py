"""API operativa de telecomunicaciones: incidentes, impacto, acciones, topología y escenarios."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request

from .config import COUNTRIES, settings
from .connectors import connector_for, dispatch_action
from .managed_memory import managed_agent_memory
from .memory import conversation_store
from .models import (
    ActionCreateRequest,
    ActionDecisionRequest,
    ActionExecutionRequest,
    AlertAcknowledgeRequest,
    AlertStateRequest,
    AlertSubscriptionRequest,
    CampaignOptimizeRequest,
    FinancialImpactRequest,
    IncidentUpdateRequest,
    RecommendationDecisionRequest,
    RecommendationOutcomeRequest,
    ScenarioRequest,
)
from .platform import SqlExecutionError, execute_sql, run_sql, workspace_client

router = APIRouter(prefix="/api", tags=["operations"])
fanout = ThreadPoolExecutor(max_workers=4, thread_name_prefix="quetzal-ops")
log = logging.getLogger("quetzal.operations")

CAUSE_LABELS = {
    "THERMAL": "Sobrecarga térmica del equipo",
    "CONGESTION": "Congestión de capacidad",
    "TRANSPORT": "Degradación de transporte",
    "BACKHAUL": "Latencia elevada en backhaul",
    "RADIO_SIGNAL": "Degradación de señal de radio",
}

ACTION_LABELS = {
    "DISPATCH_FIELD": "Despachar equipo de campo",
    "CREATE_WORK_ORDER": "Crear orden de trabajo",
    "CUSTOMER_NOTICE": "Notificar clientes afectados",
    "RETENTION_CAMPAIGN": "Iniciar campaña de retención",
    "COMPENSATION": "Aprobar compensación",
    "CAPACITY_CHANGE": "Modificar capacidad de red",
}

VOC_THEME_LABELS = {
    "NETWORK_QUALITY": "Calidad y cobertura de red",
    "BILLING": "Facturación y pagos",
    "SERVICE": "Atención y soporte",
    "PLAN_VALUE": "Planes, precio y valor",
    "OTHER": "Otros motivos",
}

VOC_RECOMMENDED_FOCUS = {
    "NETWORK_QUALITY": "Correlacionar reclamos con experiencia de red y priorizar recuperación de servicio.",
    "BILLING": "Revisar claridad de factura, cobros y alternativas de pago antes de contactar.",
    "SERVICE": "Reducir reaperturas, tiempo de resolución y brechas de SLA.",
    "PLAN_VALUE": "Validar necesidad, precio y adecuación del plan con consentimiento vigente.",
    "OTHER": "Revisar una muestra gobernada antes de crear una acción específica.",
}


def _validate_customer_id(customer_id: str) -> str:
    if not customer_id or len(customer_id) > 128 or not all(char.isalnum() or char in "-_" for char in customer_id):
        raise HTTPException(400, "Identificador de cliente inválido.")
    return customer_id


def _next_best_actions(profile: dict, tickets: list[dict], offers: list[dict]) -> list[dict]:
    """Construye recomendaciones deterministas y explicables a partir de señales gobernadas."""
    actions: list[dict] = []
    open_tickets = int(profile.get("open_tickets") or 0)
    baseline_churn = float(profile.get("churn_probability") or 0)
    churn = baseline_churn
    reach = float(profile.get("reach_score") or profile.get("influence_score") or 0)
    exposure = float(profile.get("network_exposure_score") or profile.get("contagion_risk_score") or 0)
    overdue = float(profile.get("overdue_balance") or 0)
    nps = int(profile.get("nps_ultimo") or 0)

    if open_tickets:
        breached = sum(1 for ticket in tickets if ticket.get("sla_status") == "BREACHED")
        actions.append({
            "type": "SERVICE_RECOVERY", "priority": "CRITICAL" if breached else "HIGH",
            "title": "Resolver experiencia antes de vender",
            "reason": f"{open_tickets} ticket(s) abierto(s); {breached} fuera del objetivo de atención.",
            "action": "Priorizar el caso, informar al cliente y cerrar la causa raíz.",
        })
    if churn >= 0.65:
        actions.append({
            "type": "RETENTION", "priority": "HIGH", "title": "Activar tratamiento de retención",
            "reason": f"Propensión individual de churn de {churn:.0%} en el modelo gobernado.",
            "action": "Revisar fricciones y preparar una oferta de permanencia con aprobación humana.",
        })
    if exposure >= 55 or reach >= 75:
        actions.append({
            "type": "NETWORK_CARE",
            "priority": "HIGH" if exposure >= 70 else "MEDIUM",
            "title": "Revisar exposición y alcance relacional",
            "reason": f"Alcance {reach:.0f}/100 y exposición relacional {exposure:.0f}/100 en contactos calificados.",
            "action": "Coordinar retención individual y seguimiento agregado de la comunidad, sin exponer identidades de terceros.",
        })
    if nps <= 6:
        actions.append({
            "type": "NPS_RECOVERY", "priority": "HIGH", "title": "Cerrar el ciclo con detractor",
            "reason": f"Último NPS individual: {nps}.",
            "action": "Contactar para entender la causa, registrar resolución y volver a medir.",
        })
    if overdue > 0:
        actions.append({
            "type": "PAYMENT_ASSISTANCE", "priority": "MEDIUM", "title": "Ofrecer alternativa de pago",
            "reason": f"Saldo vencido de USD {overdue:,.2f}.",
            "action": "Validar elegibilidad para acuerdo antes de aplicar restricciones de servicio.",
        })
    if not open_tickets and churn < 0.65 and bool(profile.get("acepta_marketing")):
        for offer in offers[:2]:
            actions.append({
                "type": offer.get("recommendation_type", "CROSS_SELL"), "priority": "MEDIUM",
                "title": f"Sugerir {offer.get('product_name')}", "reason": offer.get("reason"),
                "action": "Confirmar necesidad, elegibilidad y consentimiento antes de ofertar.",
                "product": offer,
            })
    if not actions:
        actions.append({
            "type": "MONITOR", "priority": "LOW", "title": "Mantener seguimiento",
            "reason": "No hay una señal crítica que justifique intervención inmediata.",
            "action": "Revisar el perfil en el próximo evento relevante.",
        })
    return actions


def _actor(request: Request) -> str:
    for header in ("x-forwarded-email", "x-databricks-user-email", "x-forwarded-user"):
        value = request.headers.get(header)
        if value:
            return value[:200]
    if os.getenv("QUETZAL_ALLOW_LOCAL_IDENTITY_FALLBACK", "false").lower() == "true":
        return "quetzal-operator"
    raise HTTPException(401, "No fue posible verificar la identidad del usuario.")


def _access(request: Request) -> dict:
    """Resuelve la identidad de la aplicación en roles y alcance territorial gobernados."""
    actor = _actor(request)
    configured_admins = {item.strip().lower() for item in os.getenv("QUETZAL_ADMIN_USERS", "").split(",") if item.strip()}
    # El operador local solo existe cuando el fallback de desarrollo fue habilitado explícitamente.
    if actor == "quetzal-operator" or actor.lower() in configured_admins:
        return {"actor": actor, "roles": ["ADMIN", "NOC_OPERATOR", "ACTION_APPROVER", "CARE_AGENT"], "countries": []}
    rows = run_sql(
        "SELECT role, country_scope FROM ops_user_roles WHERE lower(principal) = :principal AND active = true",
        parameters={"principal": actor.lower()}, cache_ttl=15,
    )
    return {
        "actor": actor,
        "roles": sorted({str(row.get("role")) for row in rows if row.get("role")}),
        "countries": sorted({str(row.get("country_scope")) for row in rows if row.get("country_scope")}),
    }


def _require_role(request: Request, *allowed: str) -> dict:
    access = _access(request)
    if "ADMIN" not in access["roles"] and not set(allowed).intersection(access["roles"]):
        raise HTTPException(403, "Tu perfil no tiene permiso para realizar esta operación.")
    return access


def _assert_country_access(access: dict, country: str | None) -> None:
    if country and access["countries"] and country not in access["countries"]:
        raise HTTPException(403, "El país solicitado está fuera de tu alcance operativo.")


def _audit(event_type: str, resource_type: str, resource_id: str, actor: str, detail: dict) -> None:
    execute_sql(
        """
        INSERT INTO ops_audit_log
        VALUES (:event_id, :event_type, :resource_type, :resource_id, :actor, current_timestamp(), :detail_json)
        """,
        parameters={
            "event_id": uuid4().hex,
            "event_type": event_type,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "actor": actor,
            "detail_json": json.dumps(detail, ensure_ascii=False),
        },
    )


def _incident_select(where: str = "TRUE") -> str:
    return f"""
      SELECT c.*,
             COALESCE(s.status, 'NEW') AS status,
             s.assignee,
             s.acknowledged_at,
             s.resolved_at,
             s.updated_at,
             CASE c.severity WHEN 'CRITICAL' THEN 2 WHEN 'HIGH' THEN 4 WHEN 'MEDIUM' THEN 8 ELSE 24 END AS sla_target_hours,
             timestampadd(HOUR, CASE c.severity WHEN 'CRITICAL' THEN 2 WHEN 'HIGH' THEN 4 WHEN 'MEDIUM' THEN 8 ELSE 24 END, c.detected_at) AS sla_deadline_at,
             ROUND(timestampdiff(MINUTE, current_timestamp(), timestampadd(HOUR, CASE c.severity WHEN 'CRITICAL' THEN 2 WHEN 'HIGH' THEN 4 WHEN 'MEDIUM' THEN 8 ELSE 24 END, c.detected_at))/60.0, 1) AS sla_remaining_hours,
             CASE WHEN COALESCE(s.status, 'NEW') = 'RESOLVED' THEN 'MET'
                  WHEN current_timestamp() > timestampadd(HOUR, CASE c.severity WHEN 'CRITICAL' THEN 2 WHEN 'HIGH' THEN 4 WHEN 'MEDIUM' THEN 8 ELSE 24 END, c.detected_at) THEN 'BREACHED'
                  WHEN current_timestamp() > timestampadd(MINUTE, 45, c.detected_at) THEN 'AT_RISK'
                  ELSE 'ON_TRACK' END AS sla_status,
             CASE c.severity WHEN 'CRITICAL' THEN 4 WHEN 'HIGH' THEN 3 WHEN 'MEDIUM' THEN 2 ELSE 1 END AS priority_score
      FROM ops_incident_candidates c
      LEFT JOIN ops_incident_state s ON c.incident_id = s.incident_id
      WHERE {where}
    """


def _customer_profile(customer_id: str) -> list[dict]:
    """Prioriza la vista 360 enriquecida con el grafo y admite el estado previo a la primera ejecución."""
    try:
        return run_sql(
            "SELECT * FROM ops_customer_graph_360 WHERE cliente_id = :customer_id",
            parameters={"customer_id": customer_id},
            cache_ttl=15,
        )
    except SqlExecutionError:
        return run_sql(
            "SELECT * FROM ops_customer_360 WHERE cliente_id = :customer_id",
            parameters={"customer_id": customer_id},
            cache_ttl=15,
        )


def _number(value, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _country_scope(country: str, access: dict, column: str) -> tuple[str, dict[str, str]]:
    """Construye un filtro territorial parametrizado para una columna SQL permitida."""
    if country != "ALL":
        _assert_country_access(access, country)
        return f"{column} = :country", {"country": country}
    if access["countries"]:
        return f"array_contains(split(:country_scope, ','), {column})", {
            "country_scope": ",".join(access["countries"]),
        }
    return "TRUE", {}


def _effective_countries(country: str, access: dict) -> list[str]:
    if country != "ALL":
        return [country]
    return access["countries"] or ["ALL"]


def _ticket_theme_case(alias: str = "t") -> str:
    text = f"lower(concat_ws(' ', coalesce({alias}.categoria, ''), coalesce({alias}.motivo, '')))"
    return f"""CASE
      WHEN {text} RLIKE 'red|internet|señal|senal|cobertura|datos|llamada|latencia' THEN 'NETWORK_QUALITY'
      WHEN {text} RLIKE 'factur|cobro|pago|saldo|recarga' THEN 'BILLING'
      WHEN {text} RLIKE 'atenci|soporte|demora|ticket|reclamo|servicio' THEN 'SERVICE'
      WHEN {text} RLIKE 'plan|precio|tarifa|promoci|beneficio' THEN 'PLAN_VALUE'
      ELSE 'OTHER'
    END"""


def _voc_trend(current: int, previous: int) -> str:
    if previous <= 0:
        return "NO_BASELINE"
    ratio = current / previous
    if ratio > 1.10:
        return "UP"
    if ratio < 0.90:
        return "DOWN"
    return "STABLE"


def _explanation_codes(value) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            pass
        return [item.strip() for item in value.strip("[]").split(",") if item.strip()]
    return []


def _customer_explainability(profile: dict) -> dict:
    """Mantiene la probabilidad de churn separada de las señales no probabilísticas del grafo."""
    baseline = _number(profile.get("baseline_churn_probability"), _number(profile.get("churn_probability")))
    graph_available = bool(profile.get("graph_model_version"))
    priority = profile.get("retention_priority_score")
    priority = _number(priority, baseline * 100) if graph_available else None
    neighbour_risk = _number(profile.get("neighbour_avg_churn_probability"))
    exposure = _number(profile.get("network_exposure_score"), _number(profile.get("contagion_risk_score")))
    reach = _number(profile.get("reach_score"), _number(profile.get("influence_score")))
    diffusion = _number(profile.get("risk_diffusion_score"))
    codes = _explanation_codes(profile.get("graph_explanation_codes"))
    code_labels = {
        "HIGH_RISK_NETWORK_EXPOSURE": "Exposición elevada a contactos con riesgo alto",
        "HIGH_NETWORK_INFLUENCE": "Alcance elevado dentro de la red de contactos (snapshot legado)",
        "HIGH_NETWORK_REACH": "Alcance elevado dentro de la red de contactos",
        "HIGH_RISK_DIFFUSION": "Alta proximidad a focos de riesgo en el grafo ponderado",
        "RELATIONSHIP_BRIDGE": "El cliente conecta zonas poco densas de la red",
        "CROSS_BORDER_REACH": "Alcance de contactos en tres o más países",
        "GRAPH_RISK_UPLIFT": "Código legado de enriquecimiento; no altera la probabilidad v3",
    }
    evidence = [{
        "code": "BASELINE_PROPENSITY",
        "label": "Propensión individual de churn",
        "value": round(baseline, 4),
        "scale": "0_TO_1",
        "direction": "INCREASES_RISK" if baseline >= 0.5 else "LOWERS_RISK",
        "source": "gold_churn_predictions",
    }]
    if graph_available:
        evidence.extend([
            {
                "code": "NEIGHBOUR_RISK",
                "label": "Riesgo promedio de contactos calificados",
                "value": round(neighbour_risk, 4),
                "scale": "0_TO_1",
                "direction": "INCREASES_RISK" if neighbour_risk > baseline else "LOWERS_RISK",
                "source": "gold_customer_graph_features",
            },
            {
                "code": "NETWORK_EXPOSURE",
                "label": "Exposición relacional a churn",
                "value": round(exposure, 1),
                "scale": "0_TO_100",
                "direction": "INCREASES_PRIORITY" if exposure >= 50 else "NEUTRAL",
                "source": "gold_customer_graph_features",
            },
            {
                "code": "NETWORK_REACH",
                "label": "Alcance en la red de contactos",
                "value": round(reach, 1),
                "scale": "0_TO_100",
                "direction": "INCREASES_PRIORITY" if reach >= 70 else "NEUTRAL",
                "source": "gold_customer_graph_features",
            },
        ])
    return {
        "method": "SEPARATED_PROPENSITY_AND_NETWORK_SIGNALS",
        "is_shap": False,
        "model_version": profile.get("graph_model_version") if graph_available else "baseline-only",
        "scores": {
            "individual_baseline": round(baseline, 4),
            "retention_priority": round(priority, 1) if priority is not None else None,
            "network_exposure": round(exposure, 1) if graph_available else None,
            "network_reach": round(reach, 1) if graph_available else None,
            "risk_diffusion": round(diffusion, 1) if graph_available else None,
        },
        "evidence": evidence,
        "reason_codes": [{"code": code, "label": code_labels.get(code, code.replace("_", " ").title())} for code in codes],
        "formula": (
            "Prioridad = 55% propensión individual + 20% exposición relacional + "
            "15% alcance + 10% valor. Es un ranking operativo, no una probabilidad."
        ) if graph_available else "Probabilidad individual gobernada; señales relacionales no disponibles.",
        "limitations": [
            "PageRank mide alcance; no predice churn por sí solo.",
            "Exposición y difusión son asociaciones de red; no demuestran contagio ni causalidad.",
            "La prioridad de retención no sustituye la probabilidad del modelo individual.",
        ],
    }


def _event_time(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _customer_timeline(
    profile: dict,
    subscriptions: list[dict],
    tickets: list[dict],
    billing: list[dict],
    nps: list[dict],
    recommendation_history: list[dict],
    geographic_incidents: list[dict],
    limit: int = 80,
) -> list[dict]:
    events: list[dict] = []

    def add(event_type: str, occurred_at, title: str, detail: dict, source: str, association: str = "DIRECT_CUSTOMER_EVENT") -> None:
        timestamp = _event_time(occurred_at)
        if timestamp:
            events.append({
                "event_type": event_type,
                "occurred_at": timestamp,
                "title": title,
                "detail": detail,
                "source": source,
                "association_type": association,
            })

    add("CHURN_SCORE", profile.get("graph_scored_at") or profile.get("churn_scored_at") or profile.get("scored_at"), "Scoring de churn actualizado", {
        "baseline_probability": profile.get("baseline_churn_probability") or profile.get("churn_probability"),
        "retention_priority": profile.get("retention_priority_score"),
        "network_exposure": profile.get("network_exposure_score") or profile.get("contagion_risk_score"),
        "risk_tier": profile.get("graph_risk_tier"),
    }, "ops_customer_graph_360")
    for item in subscriptions:
        add("SUBSCRIPTION_STARTED", item.get("fecha_inicio"), f"Suscripción {item.get('product_name') or item.get('plan_id')} iniciada", {
            "subscription_id": item.get("suscripcion_id"), "status": item.get("estado"),
            "monthly_price_usd": item.get("precio_mensual_usd"),
        }, "silver_suscripciones")
        add("SUBSCRIPTION_ENDED", item.get("fecha_fin"), f"Suscripción {item.get('product_name') or item.get('plan_id')} finalizada", {
            "subscription_id": item.get("suscripcion_id"), "status": item.get("estado"),
        }, "silver_suscripciones")
    for item in tickets:
        add("SUPPORT_TICKET", item.get("fecha_creacion"), f"Ticket {item.get('ticket_id')}", {
            "category": item.get("categoria"), "reason": item.get("motivo"), "status": item.get("estado"),
            "priority": item.get("prioridad"), "sla_status": item.get("sla_status"),
        }, "silver_tickets")
    for item in billing:
        add("BILLING", item.get("fecha_emision"), f"Factura {item.get('factura_id')}", {
            "amount_usd": item.get("monto_total_usd"), "payment_status": item.get("estado_pago"),
            "days_overdue": item.get("dias_atraso"), "due_at": _event_time(item.get("fecha_vencimiento")),
        }, "silver_facturas")
    for item in nps:
        add("NPS", item.get("fecha_encuesta"), f"NPS {item.get('score')}", {
            "score": item.get("score"), "category": item.get("categoria_nps"), "channel": item.get("canal_encuesta"),
        }, "silver_nps")
    for item in recommendation_history:
        add("RECOMMENDATION", item.get("proposed_at") or item.get("created_at"), item.get("title") or "Recomendación registrada", {
            "recommendation_id": item.get("recommendation_id"), "type": item.get("recommendation_type"),
            "decision": item.get("decision"), "outcome": item.get("outcome"),
        }, "ops_recommendation_log")
    for item in geographic_incidents:
        add("NETWORK_INCIDENT_CONTEXT", item.get("detected_at"), f"Contexto de red en {item.get('country')}", {
            "incident_id": item.get("incident_id"), "severity": item.get("severity"), "status": item.get("status"),
            "direct_customer_attribution": False,
        }, "ops_incident_candidates", "GEOGRAPHIC_CONTEXT")
    events.sort(key=lambda item: (item["occurred_at"], item["event_type"], item["title"]), reverse=True)
    return events[:limit]


def _check_result(name: str, check) -> dict:
    started = time.monotonic()
    try:
        status, detail = check()
    except Exception as exc:  # noqa: BLE001 - dependency SDKs expose heterogeneous failures
        log.warning("preflight_check_failed name=%s error_type=%s", name, type(exc).__name__)
        status, detail = "DEGRADED", {"reason": "La dependencia no está disponible temporalmente."}
    return {
        "name": name,
        "status": status,
        "latency_ms": round((time.monotonic() - started) * 1000),
        "detail": detail,
    }


def _preflight_checks(access: dict) -> list[dict]:
    """Comprueba dependencias en modo de solo lectura, sin invocar modelos ni jobs."""
    def warehouse():
        run_sql("SELECT 1 AS preflight", cache_ttl=0)
        return "READY", {"configured": True, "connectivity": "SQL_OK"}

    def genie():
        client = workspace_client()
        spaces = []
        for key, item in settings.genie_spaces.items():
            if not item.get("id"):
                spaces.append({"space": key, "status": "NOT_CONFIGURED"})
                continue
            client.api_client.do("GET", f"/api/2.0/genie/spaces/{item['id']}")
            spaces.append({"space": key, "status": "READY"})
        status = "READY" if spaces and all(item["status"] == "READY" for item in spaces) else "NOT_CONFIGURED"
        return status, {"spaces": spaces}

    def ai_gateway():
        if not settings.ai_model or not settings.ai_url:
            return "NOT_CONFIGURED", {"reason": "Falta el modelo de IA o la URL del gateway"}
        return "READY", {
            "model_configured": True,
            "gateway_configured": True,
            "validation_mode": "CONFIGURATION_ONLY",
        }

    def lakebase():
        if not conversation_store.enabled:
            return "NOT_CONFIGURED", {"reason": "Las variables de conexión de Lakebase están incompletas"}
        with conversation_store._connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return "READY", {"configured": True, "connectivity": "POSTGRES_OK"}

    def managed_memory():
        if not managed_agent_memory.enabled:
            return "NOT_CONFIGURED", {"reason": "Managed Agent Memory no está configurado"}
        workspace_client().api_client.do("GET", f"/api/2.1/unity-catalog/memory-stores/{managed_agent_memory.store_name}")
        return "READY", {"configured": True, "probe": "METADATA_ONLY"}

    def dashboard():
        if not settings.dashboard_id:
            return "NOT_CONFIGURED", {"reason": "Falta el ID del dashboard"}
        workspace_client().api_client.do("GET", f"/api/2.0/lakeview/dashboards/{settings.dashboard_id}")
        return "READY", {"configured": True, "probe": "METADATA_ONLY"}

    def rbac():
        if not access.get("roles"):
            return "FAILED", {"reason": "El usuario no tiene un rol operativo activo"}
        return "READY", {"roles": access["roles"], "country_scope": access.get("countries") or ["ALL"]}

    def graph_snapshot():
        try:
            rows = run_sql(
                "SELECT status, completed_at FROM ops_graph_run_log WHERE status = 'SUCCEEDED' ORDER BY completed_at DESC LIMIT 1",
                cache_ttl=0,
            )
        except SqlExecutionError:
            rows = []
        if rows:
            return "READY", {"latest_snapshot": rows[0], "source": "RUN_LOG", "policy_status": "CURRENT"}
        # Los snapshots anteriores al registro auditado siguen siendo válidos.
        # Detecta la vista gobernada publicada sin iniciar el job manual.
        published = run_sql(
            """SELECT graph_model_version AS model_version, MAX(graph_scored_at) AS computed_at,
                      COUNT(*) AS customers
               FROM ops_customer_graph_360
               GROUP BY graph_model_version
               ORDER BY computed_at DESC LIMIT 1""",
            cache_ttl=0,
        )
        if not published:
            return "NOT_CONFIGURED", {"reason": "No hay un snapshot publicado de Graph Intelligence"}
        snapshot = published[0]
        qualified = snapshot.get("model_version") in {
            "graph-fusion-v2-qualified", "graph-intelligence-v3-ontobricks",
        }
        return "READY", {
            "latest_snapshot": snapshot,
            "source": "PUBLISHED_VIEW",
            "policy_status": "CURRENT" if qualified else "LEGACY_PENDING_MANUAL_REFRESH",
        }

    def ontobricks():
        try:
            rows = run_sql(
                """SELECT count(*) AS triples, count(DISTINCT subject) AS subjects,
                          count(DISTINCT predicate) AS predicates,
                          max(generated_at) AS generated_at
                   FROM gold_quetzal_knowledge_graph_triples""",
                cache_ttl=0,
            )
        except SqlExecutionError:
            return "NOT_CONFIGURED", {
                "contract": "gold_quetzal_knowledge_graph_triples",
                "reason": "La próxima actualización manual del grafo publicará la exportación compatible",
                "external_app_configured": bool(settings.ontobricks_url),
            }
        return "READY", {
            "contract": "gold_quetzal_knowledge_graph_triples",
            "domain": settings.ontobricks_domain,
            "version": settings.ontobricks_version,
            "external_app_configured": bool(settings.ontobricks_url),
            "snapshot": rows[0] if rows else {},
        }

    return [
        _check_result("warehouse", warehouse),
        _check_result("genie", genie),
        _check_result("ai_gateway", ai_gateway),
        _check_result("lakebase", lakebase),
        _check_result("managed_memory", managed_memory),
        _check_result("dashboard", dashboard),
        _check_result("rbac", rbac),
        _check_result("graph_snapshot", graph_snapshot),
        _check_result("ontobricks", ontobricks),
    ]


@router.get("/me")
def current_operator(request: Request):
    access = _access(request)
    actor = access["actor"]
    return {
        "email": actor,
        "display_name": actor.split("@")[0].replace(".", " ").title(),
        "roles": access["roles"],
        "country_scope": access["countries"] or ["ALL"],
    }


@router.get("/demo/preflight")
def demo_preflight(request: Request):
    """Ejecuta comprobaciones de solo lectura sin inferencia de IA ni ejecución de jobs."""
    access = _require_role(request, "NOC_OPERATOR", "CARE_AGENT", "EXECUTIVE_VIEWER")
    checks = _preflight_checks(access)
    statuses = {item["status"] for item in checks}
    if "FAILED" in statuses:
        overall = "FAILED"
    elif statuses.intersection({"DEGRADED", "NOT_CONFIGURED"}):
        overall = "DEGRADED"
    else:
        overall = "READY"
    return {
        "status": overall,
        "checks": checks,
        "paid_inference_used": False,
        "job_triggered": False,
        "execution_mode": "MANUAL_READ_ONLY",
        "generated_at": datetime.now(UTC).isoformat(),
    }


@router.get("/demo/journey")
def demo_journey(
    request: Request,
    country: str = Query(default="ALL", pattern=r"^(ALL|PA|MX|CO|BR|AR|CL|PE|EC|CR|GT|DO|UY)$"),
):
    """Selecciona un flujo determinista entre un incidente y un cliente del mismo mercado."""
    access = _require_role(request, "NOC_OPERATOR", "CARE_AGENT", "EXECUTIVE_VIEWER")
    if country != "ALL":
        _assert_country_access(access, country)
    clauses = ["COALESCE(s.status, 'NEW') <> 'RESOLVED'"]
    parameters: dict[str, str] = {}
    if country != "ALL":
        clauses.append("c.country = :country")
        parameters["country"] = country
    elif access["countries"]:
        clauses.append("array_contains(split(:country_scope, ','), c.country)")
        parameters["country_scope"] = ",".join(access["countries"])
    incidents = run_sql(
        _incident_select(" AND ".join(clauses))
        + " ORDER BY priority_score DESC, c.revenue_at_risk DESC, c.detected_at DESC, c.incident_id LIMIT 1",
        parameters=parameters,
        cache_ttl=0,
    )
    if not incidents:
        return {
            "available": False,
            "reason": "NO_UNRESOLVED_INCIDENT_IN_SCOPE",
            "scope": {"requested_country": country, "authorized_countries": access["countries"] or ["ALL"]},
            "steps": [],
            "generated_at": datetime.now(UTC).isoformat(),
        }
    incident = incidents[0]
    market = str(incident.get("country"))
    customer_parameters = {"country": market}
    try:
        customers = run_sql(
            """
            SELECT cliente_id AS customer_id, nombre_completo AS customer_name,
                   pais_codigo AS country, segmento_nombre AS segment,
                   COALESCE(graph_churn_probability, churn_probability) AS churn_probability,
                   churn_probability AS baseline_churn_probability, graph_churn_probability,
                   graph_lift, graph_risk_tier, influence_score, contagion_risk_score,
                   monthly_revenue, revenue_lifetime_est, nps_ultimo AS nps,
                   open_tickets, overdue_balance, graph_recommended_action,
                   graph_explanation_codes
            FROM ops_customer_graph_360
            WHERE pais_codigo = :country
            ORDER BY COALESCE(graph_churn_probability, churn_probability) DESC,
                     monthly_revenue DESC, open_tickets DESC, cliente_id
            LIMIT 1
            """,
            parameters=customer_parameters,
            cache_ttl=0,
        )
    except SqlExecutionError:
        customers = run_sql(
            """
            SELECT cliente_id AS customer_id, nombre_completo AS customer_name,
                   pais_codigo AS country, segmento_nombre AS segment,
                   churn_probability, churn_probability AS baseline_churn_probability,
                   monthly_revenue, revenue_lifetime_est, nps_ultimo AS nps,
                   open_tickets, overdue_balance
            FROM ops_customer_360
            WHERE pais_codigo = :country
            ORDER BY churn_probability DESC, monthly_revenue DESC, open_tickets DESC, cliente_id
            LIMIT 1
            """,
            parameters=customer_parameters,
            cache_ttl=0,
        )
    customer = customers[0] if customers else None
    return {
        "available": customer is not None,
        "scope": {
            "requested_country": country,
            "selected_country": market,
            "authorized_countries": access["countries"] or ["ALL"],
        },
        "incident": incident,
        "customer": customer,
        "relationship_semantics": {
            "association_type": "SAME_MARKET_EXAMPLE",
            "direct_customer_attribution": False,
            "statement": "El cliente se selecciona como ejemplo prioritario del mismo país; no existe vínculo cliente-torre en las fuentes disponibles.",
        },
        "steps": [
            {"order": 1, "id": "PREFLIGHT", "title": "Validar dependencias", "endpoint": "/api/demo/preflight"},
            {"order": 2, "id": "INCIDENT", "title": "Entender el incidente prioritario", "resource_id": incident.get("incident_id")},
            {"order": 3, "id": "VOICE_OF_CUSTOMER", "title": "Escuchar temas y señales del mercado", "endpoint": f"/api/voc/overview?country={market}"},
            {"order": 4, "id": "CUSTOMER_360", "title": "Explorar el cliente prioritario del mercado", "resource_id": customer.get("customer_id") if customer else None},
            {"order": 5, "id": "RECOMMENDATION", "title": "Revisar evidencia y próxima mejor acción", "requires_human_approval": True},
            {"order": 6, "id": "CAMPAIGN_OPTIMIZER", "title": "Preparar una audiencia gobernada", "endpoint": "/api/campaigns/optimize", "requires_human_approval": True},
            {"order": 7, "id": "FINANCIAL_IMPACT", "title": "Simular impacto contrafactual", "endpoint": "/api/demo/financial-impact"},
        ],
        "generated_at": datetime.now(UTC).isoformat(),
    }


@router.post("/demo/financial-impact")
def financial_impact(payload: FinancialImpactRequest, request: Request):
    """Estima el impacto económico de retención con supuestos explícitos y reversibles."""
    access = _require_role(request, "NOC_OPERATOR", "CARE_AGENT", "EXECUTIVE_VIEWER")
    if payload.country != "ALL":
        _assert_country_access(access, payload.country)
    clauses = ["upper(estado) IN ('ACTIVO','ACTIVA','ACTIVE')"]
    parameters: dict[str, str] = {}
    if payload.country != "ALL":
        clauses.append("pais_codigo = :country")
        parameters["country"] = payload.country
    elif access["countries"]:
        clauses.append("array_contains(split(:country_scope, ','), pais_codigo)")
        parameters["country_scope"] = ",".join(access["countries"])
    where = " AND ".join(clauses)
    try:
        rows = run_sql(
            f"""
            SELECT COUNT(*) AS eligible_customers,
                   AVG(COALESCE(graph_churn_probability, churn_probability)) AS avg_churn_probability,
                   AVG(monthly_revenue) AS avg_monthly_revenue_usd,
                   AVG(revenue_lifetime_est) AS avg_lifetime_value_usd,
                   MAX(graph_scored_at) AS score_as_of
            FROM ops_customer_graph_360 WHERE {where}
            """,
            parameters=parameters,
            cache_ttl=0,
        )
        score_source = "GRAPH_ENRICHED_WHEN_AVAILABLE"
    except SqlExecutionError:
        rows = run_sql(
            f"""
            SELECT COUNT(*) AS eligible_customers,
                   AVG(churn_probability) AS avg_churn_probability,
                   AVG(monthly_revenue) AS avg_monthly_revenue_usd,
                   AVG(revenue_lifetime_est) AS avg_lifetime_value_usd,
                   MAX(churn_scored_at) AS score_as_of
            FROM ops_customer_360 WHERE {where}
            """,
            parameters=parameters,
            cache_ttl=0,
        )
        score_source = "INDIVIDUAL_BASELINE"
    baseline = rows[0] if rows else {}
    eligible = int(_number(baseline.get("eligible_customers")))
    if eligible <= 0:
        raise HTTPException(404, "No hay clientes elegibles en el alcance solicitado.")
    treated = min(payload.treated_customers, eligible)
    churn = max(0.0, min(1.0, _number(baseline.get("avg_churn_probability"))))
    monthly_revenue = max(0.0, _number(baseline.get("avg_monthly_revenue_usd")))

    def projection(reduction_pct: float) -> dict:
        expected_churners = treated * churn
        avoided_churners = expected_churners * reduction_pct / 100
        retained_revenue = avoided_churners * monthly_revenue * payload.horizon_months
        contact_cost = treated * payload.cost_per_contact_usd
        net_impact = retained_revenue - contact_cost
        return {
            "relative_churn_reduction_pct": round(reduction_pct, 2),
            "expected_churners_before_treatment": round(expected_churners, 2),
            "estimated_avoided_churners": round(avoided_churners, 2),
            "estimated_retained_revenue_usd": round(retained_revenue, 2),
            "estimated_contact_cost_usd": round(contact_cost, 2),
            "estimated_net_impact_usd": round(net_impact, 2),
            "estimated_roi_pct": round(100 * net_impact / contact_cost, 1) if contact_cost else None,
        }

    base_result = projection(payload.relative_churn_reduction_pct)
    return {
        "estimate_type": "COUNTERFACTUAL_ESTIMATE",
        "scope": {
            "requested_country": payload.country,
            "authorized_countries": access["countries"] or ["ALL"],
            "eligible_customers": eligible,
            "treated_customers": treated,
        },
        "assumptions": payload.model_dump(),
        "baseline": {
            "avg_churn_probability": round(churn, 4),
            "avg_monthly_revenue_usd": round(monthly_revenue, 2),
            "avg_lifetime_value_usd": round(_number(baseline.get("avg_lifetime_value_usd")), 2),
            "score_as_of": baseline.get("score_as_of"),
            "score_source": score_source,
        },
        "formulas": {
            "avoided_churners": "treated_customers × avg_churn_probability × relative_churn_reduction_pct",
            "retained_revenue": "avoided_churners × avg_monthly_revenue × horizon_months",
            "net_impact": "retained_revenue − treated_customers × cost_per_contact",
        },
        "result": base_result,
        "sensitivity": {
            "conservative": projection(payload.relative_churn_reduction_pct * 0.75),
            "base": base_result,
            "optimistic": projection(min(100, payload.relative_churn_reduction_pct * 1.25)),
        },
        "disclaimer": "Estimación contrafactual para planificación. No es una previsión causal, compromiso financiero ni resultado observado.",
        "generated_at": datetime.now(UTC).isoformat(),
    }


@router.get("/voc/overview")
def voice_of_customer_overview(
    request: Request,
    country: str = Query(default="ALL", pattern=r"^(ALL|PA|MX|CO|BR|AR|CL|PE|EC|CR|GT|DO|UY)$"),
    window_days: int = Query(default=90, ge=7, le=365),
    max_themes: int = Query(default=8, ge=1, le=8),
):
    """Deriva temas de clientes sintéticos a partir de señales operativas gobernadas."""
    access = _require_role(request, "CARE_AGENT", "NOC_OPERATOR", "EXECUTIVE_VIEWER")
    scope_filter, scope_params = _country_scope(country, access, "c.pais_codigo")
    parameters: dict[str, str | int] = {**scope_params, "window_days": window_days}
    theme_case = _ticket_theme_case("t")
    summary_rows = run_sql(
        f"""
        WITH scoped_customers AS (
          SELECT c.* FROM ops_customer_360 c WHERE {scope_filter}
        ), ticket_anchor AS (
          SELECT max(t.fecha_creacion) AS as_of
          FROM silver_tickets t JOIN scoped_customers c ON t.cliente_id = c.cliente_id
        ), ticket_window AS (
          SELECT t.*, c.segmento_id, sla.resolution_target_hours, a.as_of,
                 CASE WHEN upper(t.estado) NOT IN ('CERRADO','CLOSED','RESUELTO','RESOLVED') THEN true ELSE false END AS is_open,
                 CASE WHEN t.tiempo_resolucion_horas IS NOT NULL
                           AND t.tiempo_resolucion_horas > sla.resolution_target_hours THEN true
                      WHEN upper(t.estado) NOT IN ('CERRADO','CLOSED','RESUELTO','RESOLVED')
                           AND timestampdiff(HOUR, t.fecha_creacion, a.as_of) > sla.resolution_target_hours THEN true
                      ELSE false END AS is_sla_breach
          FROM silver_tickets t JOIN scoped_customers c ON t.cliente_id = c.cliente_id
          CROSS JOIN ticket_anchor a
          LEFT JOIN ops_sla_policy sla ON c.segmento_id = sla.segment_id
          WHERE t.fecha_creacion >= timestampadd(DAY, -1 * :window_days, a.as_of)
        ), nps_anchor AS (
          SELECT max(n.fecha_encuesta) AS as_of
          FROM silver_nps n JOIN scoped_customers c ON n.cliente_id = c.cliente_id
          WHERE n.respondida = true
        ), nps_window AS (
          SELECT n.* FROM silver_nps n JOIN scoped_customers c ON n.cliente_id = c.cliente_id
          CROSS JOIN nps_anchor a
          WHERE n.respondida = true
            AND n.fecha_encuesta >= timestampadd(DAY, -1 * :window_days, a.as_of)
        )
        SELECT (SELECT count(*) FROM scoped_customers) AS customers_observed,
               (SELECT count(*) FROM ticket_window) AS tickets,
               (SELECT count(*) FROM ticket_window WHERE is_open) AS open_tickets,
               (SELECT count(*) FROM ticket_window WHERE is_sla_breach) AS sla_breaches,
               (SELECT round(avg(csat_score), 2) FROM ticket_window WHERE csat_score IS NOT NULL) AS avg_csat,
               (SELECT count(*) FROM nps_window) AS nps_responses,
               (SELECT count(*) FROM nps_window WHERE score <= 6) AS detractors,
               (SELECT round(avg(score), 2) FROM nps_window) AS avg_nps,
               (SELECT count(*) FROM scoped_customers WHERE churn_probability >= 0.65) AS high_churn_customers,
               (SELECT as_of FROM ticket_anchor) AS tickets_as_of,
               (SELECT as_of FROM nps_anchor) AS nps_as_of,
               (SELECT max(churn_scored_at) FROM scoped_customers) AS customer_360_as_of
        """,
        parameters=parameters,
        cache_ttl=15,
    )
    summary_row = summary_rows[0] if summary_rows else {}
    theme_rows = run_sql(
        f"""
        WITH scoped_customers AS (
          SELECT c.* FROM ops_customer_360 c WHERE {scope_filter}
        ), anchor AS (
          SELECT max(t.fecha_creacion) AS as_of
          FROM silver_tickets t JOIN scoped_customers c ON t.cliente_id = c.cliente_id
        ), classified AS (
          SELECT t.*, c.nps_ultimo, sla.resolution_target_hours, a.as_of,
                 {theme_case} AS theme_id,
                 CASE WHEN upper(t.estado) NOT IN ('CERRADO','CLOSED','RESUELTO','RESOLVED') THEN true ELSE false END AS is_open,
                 CASE WHEN t.tiempo_resolucion_horas IS NOT NULL
                           AND t.tiempo_resolucion_horas > sla.resolution_target_hours THEN true
                      WHEN upper(t.estado) NOT IN ('CERRADO','CLOSED','RESUELTO','RESOLVED')
                           AND timestampdiff(HOUR, t.fecha_creacion, a.as_of) > sla.resolution_target_hours THEN true
                      ELSE false END AS is_sla_breach,
                 CASE WHEN lower(coalesce(t.prioridad, '')) RLIKE 'alta|crítica|critica|high|critical'
                           OR coalesce(t.csat_score, 5) <= 3 THEN true ELSE false END AS is_negative
          FROM silver_tickets t JOIN scoped_customers c ON t.cliente_id = c.cliente_id
          CROSS JOIN anchor a
          LEFT JOIN ops_sla_policy sla ON c.segmento_id = sla.segment_id
          WHERE t.fecha_creacion >= timestampadd(DAY, -2 * :window_days, a.as_of)
        )
        SELECT theme_id,
               sum(CASE WHEN fecha_creacion >= timestampadd(DAY, -1 * :window_days, as_of) THEN 1 ELSE 0 END) AS mentions,
               sum(CASE WHEN fecha_creacion < timestampadd(DAY, -1 * :window_days, as_of) THEN 1 ELSE 0 END) AS previous_mentions,
               sum(CASE WHEN fecha_creacion >= timestampadd(DAY, -1 * :window_days, as_of) AND is_negative THEN 1 ELSE 0 END) AS negative_signals,
               sum(CASE WHEN fecha_creacion >= timestampadd(DAY, -1 * :window_days, as_of) AND is_open THEN 1 ELSE 0 END) AS open_cases,
               sum(CASE WHEN fecha_creacion >= timestampadd(DAY, -1 * :window_days, as_of) AND is_sla_breach THEN 1 ELSE 0 END) AS sla_breaches,
               round(avg(CASE WHEN fecha_creacion >= timestampadd(DAY, -1 * :window_days, as_of) THEN nps_ultimo END), 2) AS avg_nps,
               max(fecha_creacion) AS latest_evidence_at
        FROM classified GROUP BY theme_id
        HAVING mentions > 0
        ORDER BY mentions DESC, negative_signals DESC, theme_id
        LIMIT {max_themes}
        """,
        parameters=parameters,
        cache_ttl=15,
    )
    example_rows = run_sql(
        f"""
        WITH scoped_customers AS (
          SELECT c.* FROM ops_customer_360 c WHERE {scope_filter}
        ), anchor AS (
          SELECT max(t.fecha_creacion) AS as_of
          FROM silver_tickets t JOIN scoped_customers c ON t.cliente_id = c.cliente_id
        ), ranked AS (
          SELECT {theme_case} AS theme_id, c.cliente_id AS customer_id,
                 concat(left(c.nombre_completo, 1), '•••', right(c.cliente_id, 4)) AS customer_ref,
                 c.pais_codigo AS country, c.churn_probability, c.nps_ultimo AS nps,
                 c.open_tickets, max(t.fecha_creacion) AS latest_evidence_at,
                 max(CASE WHEN lower(coalesce(t.prioridad, '')) RLIKE 'alta|crítica|critica|high|critical' THEN 1 ELSE 0 END) AS urgent
          FROM silver_tickets t JOIN scoped_customers c ON t.cliente_id = c.cliente_id
          CROSS JOIN anchor a
          WHERE t.fecha_creacion >= timestampadd(DAY, -1 * :window_days, a.as_of)
          GROUP BY {theme_case}, c.cliente_id, c.nombre_completo, c.pais_codigo,
                   c.churn_probability, c.nps_ultimo, c.open_tickets
        )
        SELECT * FROM ranked
        QUALIFY row_number() OVER (
          PARTITION BY theme_id
          ORDER BY urgent DESC, open_tickets DESC, churn_probability DESC, latest_evidence_at DESC, customer_id
        ) <= 3
        ORDER BY theme_id, urgent DESC, open_tickets DESC, churn_probability DESC, customer_id
        """,
        parameters=parameters,
        cache_ttl=15,
    )
    examples_by_theme: dict[str, list[dict]] = {}
    for row in example_rows:
        theme_id = str(row.get("theme_id") or "OTHER")
        examples_by_theme.setdefault(theme_id, []).append({
            "customer_id": row.get("customer_id"),
            "customer_ref": row.get("customer_ref"),
            "country": row.get("country"),
            "churn_probability": row.get("churn_probability"),
            "nps": row.get("nps"),
            "open_tickets": row.get("open_tickets"),
            "customer_360_path": f"/customers/{row.get('customer_id')}/360",
        })
    total_mentions = sum(int(_number(row.get("mentions"))) for row in theme_rows)
    themes = []
    for row in theme_rows:
        theme_id = str(row.get("theme_id") or "OTHER")
        mentions = int(_number(row.get("mentions")))
        previous = int(_number(row.get("previous_mentions")))
        negative = int(_number(row.get("negative_signals")))
        breaches = int(_number(row.get("sla_breaches")))
        avg_nps = row.get("avg_nps")
        share = 100 * mentions / total_mentions if total_mentions else 0
        priority = min(100, share * 0.4 + 30 * negative / max(mentions, 1) + 20 * breaches / max(mentions, 1) + (10 if _number(avg_nps, 10) <= 6 else 0))
        themes.append({
            "theme_id": theme_id,
            "label": VOC_THEME_LABELS.get(theme_id, VOC_THEME_LABELS["OTHER"]),
            "mentions": mentions,
            "share_pct": round(share, 1),
            "negative_signals": negative,
            "open_cases": int(_number(row.get("open_cases"))),
            "sla_breaches": breaches,
            "avg_nps": _number(avg_nps) if avg_nps is not None else None,
            "trend": _voc_trend(mentions, previous),
            "priority_score": round(priority, 1),
            "evidence": [
                f"{mentions} ticket(s) clasificado(s) por categoría y motivo.",
                f"{negative} señal(es) negativas y {breaches} brecha(s) de SLA.",
            ],
            "recommended_focus": VOC_RECOMMENDED_FOCUS.get(theme_id, VOC_RECOMMENDED_FOCUS["OTHER"]),
            "customer_examples": examples_by_theme.get(theme_id, [])[:3],
        })
    summary = {
        "customers_observed": int(_number(summary_row.get("customers_observed"))),
        "tickets": int(_number(summary_row.get("tickets"))),
        "open_tickets": int(_number(summary_row.get("open_tickets"))),
        "sla_breaches": int(_number(summary_row.get("sla_breaches"))),
        "nps_responses": int(_number(summary_row.get("nps_responses"))),
        "detractors": int(_number(summary_row.get("detractors"))),
        "avg_nps": _number(summary_row.get("avg_nps")) if summary_row.get("avg_nps") is not None else None,
        "avg_csat": _number(summary_row.get("avg_csat")) if summary_row.get("avg_csat") is not None else None,
    }
    signals = []
    if summary["sla_breaches"]:
        signals.append({
            "type": "SLA_PRESSURE", "severity": "HIGH", "title": "Presión sobre SLA",
            "description": "Tickets fuera del objetivo de resolución dentro de la ventana analizada.",
            "metric": "sla_breaches", "value": summary["sla_breaches"], "unit": "tickets",
        })
    detractor_pct = 100 * summary["detractors"] / summary["nps_responses"] if summary["nps_responses"] else 0
    signals.append({
        "type": "NPS_SENTIMENT", "severity": "HIGH" if detractor_pct >= 40 else "MEDIUM" if detractor_pct >= 20 else "LOW",
        "title": "Voz detractora", "description": "Participación de detractores entre respuestas NPS de la ventana.",
        "metric": "detractor_pct", "value": round(detractor_pct, 1), "unit": "percent",
    })
    if summary["open_tickets"]:
        signals.append({
            "type": "OPEN_CASES", "severity": "HIGH" if summary["open_tickets"] >= 10 else "MEDIUM",
            "title": "Casos aún abiertos", "description": "La recuperación de servicio debe preceder acciones comerciales.",
            "metric": "open_tickets", "value": summary["open_tickets"], "unit": "tickets",
        })
    return {
        "status": "READY",
        "synthetic": True,
        "scope": {
            "requested_country": country,
            "effective_countries": _effective_countries(country, access),
            "window_days": window_days,
        },
        "summary": summary,
        "themes": themes,
        "signals": signals,
        "source_coverage": [
            {"source": "silver_tickets", "rows": summary["tickets"], "as_of": summary_row.get("tickets_as_of")},
            {"source": "silver_nps", "rows": summary["nps_responses"], "as_of": summary_row.get("nps_as_of")},
            {"source": "ops_customer_360", "rows": summary["customers_observed"], "as_of": summary_row.get("customer_360_as_of")},
            {"source": "ops_sla_policy", "rows": summary["tickets"], "as_of": summary_row.get("tickets_as_of")},
        ],
        "methodology": {
            "type": "DETERMINISTIC_RULE_BASED_SYNTHESIS",
            "ai_inference_used": False,
            "synthetic_data": True,
            "theme_mapping_version": "voc-rules-v1",
        },
        "limitations": [
            "Todos los datos y ejemplos son sintéticos y no representan clientes ni eventos reales.",
            "Los temas se derivan de reglas sobre categoría y motivo; no son sentimiento generado por un modelo.",
            "NPS, tickets y SLA tienen cadencias distintas y no prueban causalidad.",
        ],
        "generated_at": datetime.now(UTC).isoformat(),
    }


@router.post("/campaigns/optimize")
def optimize_campaign(payload: CampaignOptimizeRequest, request: Request):
    """Crea un borrador determinista de campaña sin escrituras, conectores ni ejecución."""
    access = _require_role(request, "CARE_AGENT")
    scope_filter, scope_params = _country_scope(payload.country, access, "c.pais_codigo")
    source_theme = payload.source_theme_id or "ALL"
    parameters: dict[str, str] = {
        **scope_params,
        "channel": payload.channel,
        "objective": payload.objective,
        "source_theme": source_theme,
    }
    theme_case = _ticket_theme_case("t")
    campaign_cte = f"""
      WITH ticket_anchor AS (
        SELECT max(fecha_creacion) AS as_of FROM silver_tickets
      ), ticket_themes AS (
        SELECT t.cliente_id, collect_set({theme_case}) AS theme_ids
        FROM silver_tickets t CROSS JOIN ticket_anchor a
        WHERE t.fecha_creacion >= timestampadd(DAY, -180, a.as_of)
        GROUP BY t.cliente_id
      ), top_offer AS (
        SELECT cliente_id, plan_id, product_name, vertical, precio_usd,
               recommendation_type, recommendation_score, reason
        FROM ops_customer_next_best_offer
        WHERE marketing_eligible = true
        QUALIFY row_number() OVER (
          PARTITION BY cliente_id ORDER BY recommendation_score DESC, precio_usd, plan_id
        ) = 1
      ), base AS (
        SELECT c.cliente_id AS customer_id,
               concat(left(c.nombre_completo, 1), '•••', right(c.cliente_id, 4)) AS customer_ref,
               c.pais_codigo AS country, c.segmento_nombre AS segment,
               c.monthly_revenue, c.churn_probability, c.nps_ultimo AS nps,
               c.open_tickets, c.avg_resolution_hours, c.resolution_target_hours,
               c.overdue_balance, coalesce(c.acepta_marketing, false) AS marketing_consented,
               CASE WHEN :channel = 'EMAIL' THEN c.email IS NOT NULL AND instr(c.email, '@') > 1
                    ELSE c.telefono IS NOT NULL AND length(trim(c.telefono)) >= 6 END AS channel_reachable,
               CASE WHEN c.open_tickets = 0
                          AND (c.resolution_target_hours IS NULL OR c.avg_resolution_hours IS NULL
                               OR c.avg_resolution_hours <= c.resolution_target_hours)
                    THEN true ELSE false END AS service_eligible,
               CASE WHEN :objective = 'RETENTION' THEN c.churn_probability >= 0.50 OR c.nps_ultimo <= 6
                    ELSE c.churn_probability < 0.65 AND c.nps_ultimo > 6 AND o.plan_id IS NOT NULL END AS objective_eligible,
               CASE WHEN :source_theme = 'ALL' THEN true
                    WHEN :source_theme = 'BILLING' THEN array_contains(coalesce(tt.theme_ids, array()), 'BILLING') OR c.overdue_balance > 0
                    ELSE array_contains(coalesce(tt.theme_ids, array()), :source_theme) END AS source_theme_match,
               o.plan_id, o.product_name, o.vertical, o.precio_usd,
               o.recommendation_type, o.recommendation_score, o.reason AS offer_reason
        FROM ops_customer_360 c
        LEFT JOIN ticket_themes tt ON c.cliente_id = tt.cliente_id
        LEFT JOIN top_offer o ON c.cliente_id = o.cliente_id
        WHERE {scope_filter}
      ), eligible AS (
        SELECT *, round(
          CASE WHEN :objective = 'RETENTION'
               THEN 70 * coalesce(churn_probability, 0) + 20 * CASE WHEN nps <= 6 THEN 1 ELSE 0 END
               ELSE coalesce(recommendation_score, 0) END
          + 10 * CASE WHEN :source_theme <> 'ALL' AND source_theme_match THEN 1 ELSE 0 END
          + least(10D, coalesce(monthly_revenue, 0) / 20D), 2
        ) AS selection_score
        FROM base
      )
    """
    funnel_rows = run_sql(
        campaign_cte + """
        SELECT count(*) AS customers_in_scope,
               sum(CASE WHEN marketing_consented THEN 1 ELSE 0 END) AS marketing_consented,
               sum(CASE WHEN marketing_consented AND channel_reachable THEN 1 ELSE 0 END) AS channel_reachable,
               sum(CASE WHEN marketing_consented AND channel_reachable AND service_eligible THEN 1 ELSE 0 END) AS service_eligible,
               sum(CASE WHEN marketing_consented AND channel_reachable AND service_eligible
                              AND objective_eligible AND source_theme_match THEN 1 ELSE 0 END) AS campaign_eligible
        FROM eligible
        """,
        parameters=parameters,
        cache_ttl=0,
    )
    funnel_row = funnel_rows[0] if funnel_rows else {}
    budget_contact_capacity = int(payload.budget_usd // payload.cost_per_contact_usd)
    effective_limit = min(payload.max_customers, payload.contact_capacity, budget_contact_capacity)
    selected_rows = []
    if effective_limit > 0:
        selected_rows = run_sql(
            campaign_cte + f"""
            SELECT * FROM eligible
            WHERE marketing_consented AND channel_reachable AND service_eligible
              AND objective_eligible AND source_theme_match
            ORDER BY selection_score DESC, monthly_revenue DESC, customer_id
            LIMIT {effective_limit}
            """,
            parameters=parameters,
            cache_ttl=0,
        )
    selected_count = len(selected_rows)
    customers_in_scope = int(_number(funnel_row.get("customers_in_scope")))
    consented = int(_number(funnel_row.get("marketing_consented")))
    reachable = int(_number(funnel_row.get("channel_reachable")))
    service_eligible = int(_number(funnel_row.get("service_eligible")))
    campaign_eligible = int(_number(funnel_row.get("campaign_eligible")))
    funnel = {
        "customers_in_scope": customers_in_scope,
        "marketing_consented": consented,
        "channel_reachable": reachable,
        "service_eligible": service_eligible,
        "offer_eligible": campaign_eligible,
        "selected": selected_count,
        "excluded": {
            "no_consent": max(0, customers_in_scope - consented),
            "channel_unreachable": max(0, consented - reachable),
            "service_first": max(0, reachable - service_eligible),
            "no_offer": max(0, service_eligible - campaign_eligible),
            "budget_or_capacity": max(0, campaign_eligible - selected_count),
        },
    }
    audience_preview = []
    for row in selected_rows[:100]:
        reason_codes = ["CONSENT_VERIFIED", "CHANNEL_REACHABLE", "SERVICE_ELIGIBLE"]
        reason_codes.append("HIGH_CHURN_RISK" if payload.objective == "RETENTION" else "PRODUCT_AFFINITY")
        if payload.source_theme_id:
            reason_codes.append("VOC_THEME_MATCH")
        audience_preview.append({
            "customer_id": row.get("customer_id"),
            "customer_ref": row.get("customer_ref"),
            "country": row.get("country"),
            "segment": row.get("segment"),
            "channel": payload.channel,
            "score": _number(row.get("selection_score")),
            "reason_codes": reason_codes,
            "monthly_revenue": _number(row.get("monthly_revenue")),
            "churn_probability": _number(row.get("churn_probability")),
            "offer": {
                "plan_id": row.get("plan_id"),
                "product_name": row.get("product_name"),
                "price_usd": _number(row.get("precio_usd")),
            } if row.get("plan_id") else None,
            "estimated_contact_cost_usd": payload.cost_per_contact_usd,
        })
    response_rate = payload.expected_response_rate_pct / 100
    contact_cost = selected_count * payload.cost_per_contact_usd
    retained_revenue = 0.0
    incremental_revenue = 0.0
    if payload.objective == "RETENTION":
        retained_revenue = sum(
            _number(row.get("monthly_revenue")) * _number(row.get("churn_probability")) * payload.horizon_months
            for row in selected_rows
        ) * response_rate
    else:
        incremental_revenue = sum(
            _number(row.get("precio_usd")) * payload.horizon_months for row in selected_rows
        ) * response_rate
    estimated_conversions = selected_count * response_rate
    net_impact = retained_revenue + incremental_revenue - contact_cost
    draft_material = json.dumps({
        "request": payload.model_dump(),
        "customers": [row.get("customer_id") for row in selected_rows],
    }, sort_keys=True, separators=(",", ":"))
    draft_id = "DRAFT-" + hashlib.sha256(draft_material.encode()).hexdigest()[:12].upper()
    return {
        "draft_id": draft_id,
        "status": "DRAFT",
        "execution": {
            "campaign_sent": False,
            "records_written": False,
            "requires_human_approval": True,
        },
        "scope": {
            "requested_country": payload.country,
            "effective_countries": _effective_countries(payload.country, access),
            "source_theme_id": payload.source_theme_id,
        },
        "constraints": {
            **payload.model_dump(),
            "budget_contact_capacity": budget_contact_capacity,
            "effective_selection_limit": effective_limit,
        },
        "funnel": funnel,
        "audience_preview": audience_preview,
        "impact": {
            "estimate_type": "COUNTERFACTUAL_ESTIMATE",
            "estimated_contact_cost_usd": round(contact_cost, 2),
            "budget_remaining_usd": round(payload.budget_usd - contact_cost, 2),
            "estimated_conversions": round(estimated_conversions, 2),
            "estimated_retained_revenue_usd": round(retained_revenue, 2),
            "estimated_incremental_revenue_usd": round(incremental_revenue, 2),
            "estimated_net_impact_usd": round(net_impact, 2),
        },
        "formulas": {
            "selected": "min(clientes elegibles, máximo solicitado, capacidad de contacto, floor(presupuesto / costo por contacto))",
            "contact_cost": "clientes seleccionados × costo por contacto",
            "estimated_conversions": "clientes seleccionados × tasa de respuesta esperada",
            "retained_revenue": "Σ(ingreso mensual × probabilidad de churn × horizonte) × tasa de respuesta; solo RETENTION",
            "incremental_revenue": "Σ(precio de oferta × horizonte) × tasa de respuesta; solo CROSS_SELL",
            "net_impact": "ingreso retenido + ingreso incremental − costo de contacto",
        },
        "methodology": {
            "type": "DETERMINISTIC_RULE_BASED_OPTIMIZER",
            "ai_inference_used": False,
            "selection_version": "campaign-rules-v1",
            "source_theme_policy": "Cuando source_theme_id está presente, solo son elegibles clientes con una señal temática gobernada correspondiente en los últimos 180 días.",
            "policies": [
                "CONSENT_REQUIRED", "CHANNEL_REACHABILITY_REQUIRED", "SERVICE_BEFORE_SALES",
                "BUDGET_CAP", "CONTACT_CAPACITY_CAP", "DETERMINISTIC_RANKING",
            ],
        },
        "limitations": [
            "El resultado es un borrador sintético; no crea, persiste ni envía una campaña.",
            "El impacto es contrafactual y no representa causalidad ni resultado garantizado.",
            "La disponibilidad del canal se infiere por presencia de email o teléfono, no por entrega confirmada.",
            "La audiencia completa queda acotada por presupuesto y capacidad; la respuesta incluye hasta 100 ejemplos.",
        ],
        "generated_at": datetime.now(UTC).isoformat(),
    }


@router.get("/command/summary")
def command_summary():
    incidents_future = fanout.submit(
        run_sql,
        _incident_select("COALESCE(s.status, 'NEW') <> 'RESOLVED'")
        + " ORDER BY priority_score DESC, c.revenue_at_risk DESC LIMIT 6",
    )
    action_future = fanout.submit(
        run_sql,
        """SELECT COUNT(*) AS pending_actions FROM ops_action_log WHERE status = 'PENDING_APPROVAL'""",
    )
    incidents = incidents_future.result()
    actions = action_future.result()
    return {
        "incidents": incidents,
        "totals": {
            "open_incidents": len(incidents),
            "critical_incidents": sum(1 for row in incidents if row.get("severity") == "CRITICAL"),
            "affected_customers": sum(int(row.get("affected_customers") or 0) for row in incidents),
            "revenue_at_risk": sum(float(row.get("revenue_at_risk") or 0) for row in incidents),
            "pending_actions": int((actions[0] if actions else {}).get("pending_actions") or 0),
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


@router.get("/incidents")
def incidents(
    request: Request,
    status: str | None = Query(default=None, pattern=r"^(NEW|ACKNOWLEDGED|IN_PROGRESS|MONITORING|RESOLVED)$"),
    severity: str | None = Query(default=None, pattern=r"^(CRITICAL|HIGH|MEDIUM|LOW)$"),
    country: str | None = Query(default=None, pattern=r"^[A-Z]{2}$"),
):
    access = _access(request)
    _assert_country_access(access, country)
    clauses = ["TRUE"]
    params: dict[str, str] = {}
    if status:
        clauses.append("COALESCE(s.status, 'NEW') = :status")
        params["status"] = status
    if severity:
        clauses.append("c.severity = :severity")
        params["severity"] = severity
    if country:
        clauses.append("c.country = :country")
        params["country"] = country
    elif access["countries"]:
        clauses.append("array_contains(split(:country_scope, ','), c.country)")
        params["country_scope"] = ",".join(access["countries"])
    return run_sql(
        _incident_select(" AND ".join(clauses))
        + " ORDER BY priority_score DESC, c.revenue_at_risk DESC, c.detected_at DESC LIMIT 100",
        parameters=params,
    )


@router.get("/customers/search")
def customer_search(
    request: Request,
    q: str = Query(min_length=2, max_length=120),
    country: str | None = Query(default=None, pattern=r"^[A-Z]{2}$"),
):
    """Busca clientes por ID, nombre, email o teléfono en el índice gobernado."""
    if country and country not in COUNTRIES:
        raise HTTPException(400, "País inválido.")
    access = _access(request)
    _assert_country_access(access, country)
    clauses = [(
        "(contains(lower(cliente_id), :term) OR "
        "contains(lower(nombre_completo), :term) OR "
        "contains(lower(email), :term) OR contains(lower(telefono), :term))"
    )]
    parameters = {"term": q.strip().lower()}
    if country:
        clauses.append("pais_codigo = :country")
        parameters["country"] = country
    elif access["countries"]:
        clauses.append("array_contains(split(:country_scope, ','), pais_codigo)")
        parameters["country_scope"] = ",".join(access["countries"])
    return run_sql(
        f"""
        SELECT cliente_id, nombre_completo, pais_codigo, segmento_id, marca_comercial,
               estado, nps_ultimo, ROUND(churn_probability, 3) AS churn_probability,
               active_subscriptions, monthly_revenue, open_tickets, overdue_balance
        FROM ops_customer_360
        WHERE {' AND '.join(clauses)}
        ORDER BY CASE WHEN lower(cliente_id) = :term THEN 0 ELSE 1 END,
                 churn_probability DESC, nombre_completo
        LIMIT 25
        """,
        parameters=parameters,
        cache_ttl=10,
    )


@router.get("/customers/{customer_id}/360")
def customer_360(customer_id: str, request: Request):
    """Devuelve el perfil individual de un cliente y recomendaciones explicables."""
    access = _require_role(request, "CARE_AGENT", "NOC_OPERATOR")
    customer_id = _validate_customer_id(customer_id)
    params = {"customer_id": customer_id}
    profiles = _customer_profile(customer_id)
    if not profiles:
        raise HTTPException(404, "Cliente no encontrado.")
    profile = profiles[0]
    customer_country = profile.get("pais_codigo") or profile.get("country")
    _assert_country_access(access, customer_country)
    subscriptions_future = fanout.submit(
        run_sql,
        """
        SELECT s.suscripcion_id, s.plan_id, p.nombre AS product_name, p.vertical, p.tier,
               p.data_gb, p.internet_mbps, p.minutos, p.tv_canales, p.es_bundle,
               s.estado, s.fecha_inicio, s.fecha_fin, s.precio_mensual_usd,
               s.metodo_pago, s.auto_renovacion
        FROM silver_suscripciones s
        LEFT JOIN bronze_planes p ON s.plan_id = p.plan_id
        WHERE s.cliente_id = :customer_id
        ORDER BY CASE WHEN upper(s.estado) IN ('ACTIVA','ACTIVE') THEN 0 ELSE 1 END, s.fecha_inicio DESC
        """,
        parameters=params,
        cache_ttl=15,
    )
    tickets_future = fanout.submit(
        run_sql,
        """
        SELECT t.ticket_id, t.fecha_creacion, t.categoria, t.motivo, t.canal,
               t.prioridad, t.estado, t.tiempo_resolucion_horas, t.csat_score, t.recontacto,
               sla.resolution_target_hours,
               CASE
                 WHEN t.tiempo_resolucion_horas IS NOT NULL AND t.tiempo_resolucion_horas > sla.resolution_target_hours THEN 'BREACHED'
                 WHEN upper(t.estado) NOT IN ('CERRADO','CLOSED','RESUELTO','RESOLVED')
                      AND timestampdiff(HOUR, t.fecha_creacion, current_timestamp()) > sla.resolution_target_hours THEN 'BREACHED'
                 ELSE 'WITHIN_TARGET'
               END AS sla_status
        FROM silver_tickets t
        JOIN silver_clientes c ON t.cliente_id = c.cliente_id
        LEFT JOIN ops_sla_policy sla ON c.segmento_id = sla.segment_id
        WHERE t.cliente_id = :customer_id
        ORDER BY t.fecha_creacion DESC
        LIMIT 30
        """,
        parameters=params,
        cache_ttl=15,
    )
    billing_future = fanout.submit(
        run_sql,
        """
        SELECT factura_id, fecha_emision, fecha_vencimiento, monto_total_usd,
               estado_pago, dias_atraso, fecha_pago
        FROM silver_facturas WHERE cliente_id = :customer_id
        ORDER BY fecha_emision DESC LIMIT 18
        """,
        parameters=params,
        cache_ttl=15,
    )
    nps_future = fanout.submit(
        run_sql,
        """
        SELECT fecha_encuesta, score, categoria_nps, canal_encuesta
        FROM silver_nps WHERE cliente_id = :customer_id AND respondida = true
        ORDER BY fecha_encuesta DESC LIMIT 12
        """,
        parameters=params,
        cache_ttl=15,
    )
    offers_future = fanout.submit(
        run_sql,
        """
        SELECT * FROM ops_customer_next_best_offer
        WHERE cliente_id = :customer_id
        ORDER BY recommendation_score DESC, precio_usd
        """,
        parameters=params,
        cache_ttl=15,
    )
    recommendation_history_future = fanout.submit(
        run_sql,
        """SELECT * FROM ops_recommendation_log WHERE customer_id = :customer_id
           ORDER BY proposed_at DESC LIMIT 25""",
        parameters=params,
        cache_ttl=0,
    )
    geographic_incidents_future = fanout.submit(
        run_sql,
        _incident_select("c.country = :country")
        + " ORDER BY c.detected_at DESC, priority_score DESC LIMIT 12",
        parameters={"country": customer_country},
        cache_ttl=15,
    )
    subscriptions = subscriptions_future.result()
    tickets = tickets_future.result()
    billing = billing_future.result()
    nps = nps_future.result()
    offers = offers_future.result()
    recommendation_history = recommendation_history_future.result()
    geographic_incidents = geographic_incidents_future.result()
    assessed_tickets = [ticket for ticket in tickets if ticket.get("resolution_target_hours") is not None]
    breaches = sum(1 for ticket in assessed_tickets if ticket.get("sla_status") == "BREACHED")
    sla = {
        "policy_name": profile.get("sla_policy_name"),
        "first_response_target_hours": profile.get("first_response_target_hours"),
        "resolution_target_hours": profile.get("resolution_target_hours"),
        "service_target_pct": profile.get("service_target_pct"),
        "policy_source": profile.get("sla_policy_source"),
        "tickets_assessed": len(assessed_tickets),
        "tickets_breached": breaches,
        "ticket_compliance_pct": round(100 * (len(assessed_tickets) - breaches) / len(assessed_tickets), 1) if assessed_tickets else None,
        "estimated_credit_usd": round(float(profile.get("monthly_revenue") or 0) * float(profile.get("sla_breach_credit_pct") or 0) / 100 * breaches, 2),
        "contractual": bool(profile.get("sla_contractual")),
        "source": profile.get("sla_policy_source"),
        "disclaimer": "Contrato individual cuando está disponible; de lo contrario se usa la referencia gobernada del segmento.",
    }
    return {
        "profile": profile,
        "subscriptions": subscriptions,
        "tickets": tickets,
        "billing": billing,
        "nps_history": nps,
        "sla": sla,
        "product_offers": offers,
        "recommendations": _next_best_actions(profile, tickets, offers),
        "recommendation_history": recommendation_history,
        "timeline": _customer_timeline(
            profile, subscriptions, tickets, billing, nps,
            recommendation_history, geographic_incidents,
        ),
        "explainability": _customer_explainability(profile),
        "network_context": {
            "association_type": "GEOGRAPHIC_CONTEXT",
            "direct_customer_attribution": False,
            "country": customer_country,
            "incidents": geographic_incidents,
            "disclaimer": "Incidentes del mismo país para contexto operativo; las fuentes no permiten atribuirlos directamente a este cliente.",
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _job_run_payload(run) -> dict:
    state = getattr(run, "state", None)
    lifecycle = getattr(state, "life_cycle_state", None)
    result = getattr(state, "result_state", None)
    lifecycle_value = getattr(lifecycle, "value", lifecycle)
    result_value = getattr(result, "value", result)
    return {
        "run_id": getattr(run, "run_id", None),
        "run_name": getattr(run, "run_name", None),
        "status": result_value or lifecycle_value,
        "life_cycle_state": lifecycle_value,
        "result_state": result_value,
        "state_message": getattr(state, "state_message", None),
        "start_time": getattr(run, "start_time", None),
        "end_time": getattr(run, "end_time", None),
        "run_page_url": getattr(run, "run_page_url", None),
    }


def _graph_job_id() -> int:
    if not settings.graph_job_id or not settings.graph_job_id.isdigit():
        raise HTTPException(503, "Graph Intelligence todavía no está vinculado al App.")
    return int(settings.graph_job_id)


@router.post("/graph/runs", status_code=202)
def run_graph_intelligence(request: Request):
    """Inicia el workflow administrado por DAB. Esta carga no tiene scheduler."""
    access = _require_role(request, "ADMIN")
    job_id = _graph_job_id()
    active = list(workspace_client().jobs.list_runs(job_id=job_id, active_only=True, limit=1))
    if active:
        return {"started": False, "reason": "ALREADY_RUNNING", "run": _job_run_payload(active[0]), "scheduled": False}
    response = workspace_client().jobs.run_now(job_id=job_id)
    run_id = response.response.run_id if getattr(response, "response", None) else None
    _audit("GRAPH_RUN_REQUESTED", "job", str(job_id), access["actor"], {"run_id": run_id, "scheduled": False})
    return {"started": True, "run_id": run_id, "job_id": job_id, "scheduled": False}


@router.get("/graph/runs/latest")
def latest_graph_run():
    job_id = _graph_job_id()
    runs = list(workspace_client().jobs.list_runs(job_id=job_id, limit=1))
    workflow = _job_run_payload(runs[0]) if runs else None
    snapshot = None
    try:
        rows = run_sql("SELECT * FROM ops_graph_run_log ORDER BY started_at DESC LIMIT 1", cache_ttl=0)
        snapshot = rows[0] if rows else None
    except SqlExecutionError:
        pass
    unified = dict(workflow or {})
    if snapshot:
        unified["computed_at"] = snapshot.get("completed_at")
        unified["snapshot_run_id"] = snapshot.get("run_id")
        if not workflow:
            unified["status"] = snapshot.get("status")
    return {"job_id": job_id, "run": unified or None, "workflow": workflow, "snapshot": snapshot, "scheduled": False}


@router.get("/graph/runs/{run_id}")
def graph_run(run_id: int):
    run = workspace_client().jobs.get_run(run_id=run_id)
    return {"run": _job_run_payload(run), "scheduled": False}


@router.get("/graph/methodology")
def graph_methodology():
    """Describe la semántica activa del grafo sin ejecutar cargas adicionales."""
    snapshot: dict = {}
    triples: dict = {}
    try:
        rows = run_sql(
            """SELECT graph_model_version AS model_version, max(graph_scored_at) AS computed_at,
                      count(*) AS customers
               FROM ops_customer_graph_360 GROUP BY graph_model_version
               ORDER BY computed_at DESC LIMIT 1""",
            cache_ttl=15,
        )
        snapshot = rows[0] if rows else {}
    except SqlExecutionError:
        pass
    try:
        rows = run_sql(
            """SELECT count(*) AS triples, count(DISTINCT subject) AS subjects,
                      count(DISTINCT predicate) AS predicates, max(generated_at) AS generated_at
               FROM gold_quetzal_knowledge_graph_triples""",
            cache_ttl=15,
        )
        triples = rows[0] if rows else {}
    except SqlExecutionError:
        pass
    active_version = str(snapshot.get("model_version") or "not-published")
    is_v3 = active_version == "graph-intelligence-v3-ontobricks"
    return {
        "status": "ACTIVE" if is_v3 else "PENDING_MANUAL_REFRESH",
        "active_model_version": active_version,
        "target_model_version": "graph-intelligence-v3-ontobricks",
        "manual_only": True,
        "snapshot": snapshot,
        "relationship": {
            "label": "Contacto calificado",
            "criteria": ["3+ llamadas", "10+ minutos", "reciprocidad", "actividad en 60 días"],
            "weight": "45% recurrencia logarítmica + 35% duración logarítmica + 20% reciprocidad; decaimiento exponencial por recencia",
            "semantics": "Asociación observada. No implica vínculo personal, influencia causal ni contagio de churn.",
        },
        "algorithms": [
            {
                "id": "BASELINE_CHURN", "label": "Propensión individual", "algorithm": "Modelo ML gobernado existente",
                "output": "Probabilidad 0–1", "role": "Predicción individual; no es modificada por el grafo.",
            },
            {
                "id": "NETWORK_EXPOSURE", "label": "Exposición relacional", "algorithm": "Promedio ponderado de riesgo vecino",
                "output": "Score 0–100", "role": "Contexto directo por fuerza y recencia de la relación.",
            },
            {
                "id": "RISK_DIFFUSION", "label": "Difusión de exposición", "algorithm": "Personalized PageRank ponderado",
                "output": "Percentil 0–100", "role": "Proximidad estructural a clientes de alto riesgo; no es probabilidad.",
            },
            {
                "id": "NETWORK_REACH", "label": "Alcance", "algorithm": "PageRank ponderado",
                "output": "Score 0–100", "role": "Importancia para alcance y priorización; no predice churn por sí solo.",
            },
            {
                "id": "RELATIONSHIP_GROUP", "label": "Grupo de relaciones", "algorithm": "Label Propagation ponderado determinístico",
                "output": "Cohorte operacional", "role": "Agrupa clientes para exploración y acción, sin atribuir causalidad.",
            },
            {
                "id": "RETENTION_PRIORITY", "label": "Prioridad de retención", "algorithm": "Ranking compuesto explicable",
                "output": "Score 0–100", "role": "Orden de trabajo; explícitamente no es probabilidad.",
            },
        ],
        "pagerank_decision": {
            "is_best_churn_algorithm": False,
            "decision": "PageRank se conserva únicamente para alcance. Personalized PageRank se usa para difusión de exposición.",
            "validation_required": "Comparar lift/AUC y calibración contra una cohorte con churn observado antes de afirmar mejora predictiva.",
        },
        "ontobricks": {
            "mode": "LAKEHOUSE_TRIPLE_CONTRACT",
            "version": settings.ontobricks_version,
            "domain": settings.ontobricks_domain,
            "ontology_path": "build/generated/ontology/quetzal-telecom-v1.ttl",
            "triple_table": "gold_quetzal_knowledge_graph_triples",
            "external_app_url": settings.ontobricks_url or None,
            "snapshot": triples,
            "purpose": ["ontología", "navegación", "SHACL/SWRL", "GraphQL", "MCP"],
            "analytics_policy": "Quetzal calcula señales ponderadas; el analytics genérico no debe reemplazarlas porque deduplica relaciones sin peso.",
        },
        "limitations": [
            "Los contactos y eventos son sintéticos.",
            "No existe churn observado positivo en el snapshot actual para comparar AUC o calibración.",
            "La ejecución manual debe publicar v3 antes de que sus nuevas señales aparezcan en los perfiles.",
        ],
    }


@router.get("/customers/{customer_id}/graph")
def customer_graph(
    customer_id: str,
    request: Request,
    max_neighbors: int = Query(default=30, ge=5, le=60),
    affinity: str = Query(default="ALL", pattern=r"^(ALL|FREQUENT|HOUSEHOLD|SOCIAL|WORK|OTHER|CROSS_BORDER)$"),
):
    """Devuelve una red ego acotada para Cliente 360."""
    access = _require_role(request, "CARE_AGENT")
    customer_id = _validate_customer_id(customer_id)
    params = {"customer_id": customer_id, "affinity": affinity}
    try:
        center_rows = run_sql(
            """SELECT cliente_id AS customer_id, nombre_completo AS label, pais_codigo AS country,
                      segmento_nombre AS segment, graph_community_id AS community_id,
                      graph_risk_tier AS risk_tier, graph_churn_probability AS churn_probability,
                      influence_score, contagion_risk_score AS contagion_score,
                      graph_unique_contacts AS unique_contacts,
                      graph_countries_reached AS countries_reached,
                      graph_international_call_pct AS international_call_pct,
                      influenced_revenue_usd, graph_model_version AS model_version,
                      graph_scored_at AS computed_at
               FROM ops_customer_graph_360 WHERE cliente_id = :customer_id""",
            parameters={"customer_id": customer_id}, cache_ttl=15,
        )
    except SqlExecutionError:
        return {"available": False, "reason": "GRAPH_NOT_READY", "nodes": [], "edges": []}
    if not center_rows:
        raise HTTPException(404, "Cliente no encontrado en Graph Intelligence.")
    center = center_rows[0]
    _assert_country_access(access, center.get("country"))
    contacts = run_sql(
        f"""
        WITH related AS (
          SELECT destination_customer_id AS peer_id, 'OUT' AS direction,
                 duration_seconds, dropped, international, contact_affinity, occurred_at
          FROM silver_customer_call_edges WHERE source_customer_id = :customer_id
          UNION ALL
          SELECT source_customer_id AS peer_id, 'IN' AS direction,
                 duration_seconds, dropped, international, contact_affinity, occurred_at
          FROM silver_customer_call_edges WHERE destination_customer_id = :customer_id
        ), aggregated AS (
          SELECT peer_id, count(*) AS calls, round(sum(duration_seconds) / 60D, 1) AS minutes,
                 round(100 * avg(CASE WHEN dropped THEN 1D ELSE 0D END), 1) AS dropped_pct,
                 max(CASE WHEN international THEN 1 ELSE 0 END) = 1 AS international,
                 max(contact_affinity) AS affinity,
                 size(collect_set(direction)) = 2 AS reciprocal,
                 max(occurred_at) AS last_contact_at
          FROM related
          WHERE (:affinity = 'ALL' OR contact_affinity = :affinity)
          GROUP BY peer_id
        )
        SELECT a.*, p.nombre_completo AS label, p.pais_codigo AS country,
               p.segmento_nombre AS segment, p.graph_community_id AS community_id,
               p.graph_risk_tier AS risk_tier, p.graph_churn_probability AS churn_probability,
               p.influence_score, p.contagion_risk_score AS contagion_score
        FROM aggregated a
        JOIN ops_customer_graph_360 p ON a.peer_id = p.cliente_id
        ORDER BY a.calls DESC, a.minutes DESC
        LIMIT {max_neighbors}
        """,
        parameters=params,
        cache_ttl=15,
    )
    center.update({"x": 50.0, "y": 50.0, "is_center": True})
    model_version = str(center.get("model_version") or "graph-fusion-v1")
    center["baseline_churn_probability"] = center.get("churn_probability")
    center["reach_score"] = center.get("influence_score")
    center["network_exposure_score"] = center.get("contagion_score")
    if model_version == "graph-intelligence-v3-ontobricks":
        relationship_definition = {
            "version": "WEIGHTED_V3", "status": "ACTIVE",
            "label": "Contactos calificados y ponderados",
            "criteria": ["3+ llamadas", "10+ minutos", "o reciprocidad", "actividad en 60 días"],
            "affinity_semantics": "El peso combina recurrencia, duración, recencia y reciprocidad; no implica causalidad.",
        }
    elif model_version == "graph-fusion-v2-qualified":
        relationship_definition = {
            "version": "QUALIFIED_V2", "status": "ACTIVE",
            "label": "Relaciones calificadas",
            "criteria": ["3+ llamadas", "10+ minutos", "o reciprocidad", "actividad en 60 días"],
            "affinity_semantics": "FREQUENT indica recurrencia; no presupone vínculo personal.",
        }
    else:
        relationship_definition = {
            "version": "LEGACY_CALL_V1", "status": "PENDING_MANUAL_REFRESH",
            "label": "Snapshot anterior",
            "criteria": ["1+ llamada en 90 días"],
            "affinity_semantics": "Las afinidades personales de este snapshot son sintéticas.",
        }
    nodes = [center]
    edges = []
    total = max(1, len(contacts))
    for index, contact in enumerate(contacts):
        angle = 2 * math.pi * index / total - math.pi / 2
        radius = 28 if index % 2 == 0 else 38
        peer_id = contact.pop("peer_id")
        reach_score = contact.pop("influence_score")
        exposure_score = contact.pop("contagion_score")
        node = {
            "customer_id": peer_id,
            "label": contact.pop("label"),
            "country": contact.pop("country"),
            "segment": contact.pop("segment"),
            "community_id": contact.pop("community_id"),
            "risk_tier": contact.pop("risk_tier"),
            "churn_probability": contact.pop("churn_probability"),
            "influence_score": reach_score,
            "contagion_score": exposure_score,
            "reach_score": reach_score,
            "network_exposure_score": exposure_score,
            "x": round(50 + radius * math.cos(angle), 2),
            "y": round(50 + radius * math.sin(angle), 2),
            "is_center": False,
        }
        nodes.append(node)
        edges.append({"source": customer_id, "target": peer_id, **contact})
    return {
        "available": True,
        "run": {"computed_at": center.get("computed_at"), "window_days": 90},
        "relationship_definition": relationship_definition,
        "summary": {
            "influence_score": center.get("influence_score"),
            "contagion_score": center.get("contagion_score"),
            "reach_score": center.get("reach_score"),
            "network_exposure_score": center.get("network_exposure_score"),
            "community_id": center.get("community_id"),
            "countries_reached": center.get("countries_reached"),
            "international_call_pct": center.get("international_call_pct"),
            "influenced_revenue_usd": center.get("influenced_revenue_usd"),
        },
        "nodes": nodes,
        "edges": edges,
    }


@router.get("/graph/network")
def graph_network(
    request: Request,
    level: str = Query(default="community", pattern=r"^(community|customer)$"),
    country: str = Query(default="ALL", pattern=r"^(ALL|PA|MX|CO|BR|AR|CL|PE|EC|CR|GT|DO|UY)$"),
    community_id: str | None = Query(default=None, max_length=64, pattern=r"^COM-[a-f0-9]{10}$"),
    risk_tier: str = Query(default="ALL", pattern=r"^(ALL|CRITICAL|HIGH|MEDIUM|LOW)$"),
    limit: int = Query(default=120, ge=20, le=250),
):
    """Devuelve grupos o clientes acotados para el explorador del grafo."""
    access = _access(request)
    _assert_country_access(access, None if country == "ALL" else country)
    params: dict = {"country": country, "risk_tier": risk_tier}
    scope = access["countries"]
    params["country_scope"] = ",".join(scope)
    country_filter = "(:country = 'ALL' OR f.country = :country)"
    if scope:
        country_filter += " AND array_contains(split(:country_scope, ','), f.country)"
    try:
        if level == "community":
            nodes = run_sql(
                f"""
                SELECT f.community_id AS node_id,
                       'community' AS node_type,
                       concat('Red ', mode(c.segmento_nombre), ' ', mode(f.country), ' · ',
                         count(DISTINCT f.country), ' país(es)') AS label,
                       mode(f.country) AS country,
                       concat_ws(',', sort_array(collect_set(f.country))) AS countries,
                       mode(c.segmento_nombre) AS dominant_segment,
                       count(DISTINCT f.country) AS countries_reached,
                       count(*) AS customer_count,
                       round(avg(p.graph_churn_probability), 4) AS churn_probability,
                       CASE WHEN avg(p.graph_churn_probability) >= 0.65 THEN 'HIGH'
                            WHEN avg(p.graph_churn_probability) >= 0.40 THEN 'MEDIUM' ELSE 'LOW' END AS risk_tier,
                       sum(CASE WHEN p.risk_tier IN ('CRITICAL','HIGH') THEN 1 ELSE 0 END) AS high_risk_customers,
                       round(avg(f.influence_score), 1) AS influence_score,
                       round(avg(f.contagion_risk_score), 1) AS contagion_score,
                       round(sum(f.influenced_revenue_usd), 2) AS influenced_revenue_usd,
                       round(15 + pmod(xxhash64(f.community_id, 92), 7000) / 100D, 2) AS x,
                       round(15 + pmod(xxhash64(f.community_id, 102), 7000) / 100D, 2) AS y
                FROM gold_customer_graph_features f
                JOIN gold_churn_graph_predictions p USING (customer_id, community_id)
                JOIN ops_customer_360 c ON f.customer_id = c.cliente_id
                WHERE {country_filter}
                  AND (:risk_tier = 'ALL' OR p.risk_tier = :risk_tier)
                GROUP BY f.community_id
                ORDER BY influenced_revenue_usd DESC
                LIMIT {min(limit, 120)}
                """, parameters=params, cache_ttl=15,
            )
            community_ids = [str(node["node_id"]) for node in nodes]
            if not community_ids:
                return {"available": True, "level": level, "summary": {}, "nodes": [], "edges": []}
            quoted = ",".join(f"'{value}'" for value in community_ids)
            edges = run_sql(
                f"""
                SELECT least(a.community_id, b.community_id) AS source,
                       greatest(a.community_id, b.community_id) AS target,
                       count(*) AS calls,
                       round(sum(e.duration_seconds) / 60D, 1) AS minutes,
                       round(100 * avg(CASE WHEN e.dropped THEN 1D ELSE 0D END), 1) AS dropped_pct,
                       true AS international, 'CROSS_BORDER' AS affinity
                FROM silver_customer_call_edges e
                JOIN gold_customer_graph_features a ON e.source_customer_id = a.customer_id
                JOIN gold_customer_graph_features b ON e.destination_customer_id = b.customer_id
                WHERE a.community_id <> b.community_id
                  AND a.community_id IN ({quoted}) AND b.community_id IN ({quoted})
                GROUP BY least(a.community_id, b.community_id), greatest(a.community_id, b.community_id)
                ORDER BY calls DESC LIMIT 100
                """, cache_ttl=15,
            )
        else:
            if not community_id:
                raise HTTPException(400, "community_id es obligatorio para el nivel customer.")
            params["community_id"] = community_id
            nodes = run_sql(
                f"""
                SELECT f.customer_id AS node_id,
                       f.customer_id AS customer_id,
                       'customer' AS node_type,
                       concat(left(c.nombre_completo, 1), '•••', right(f.customer_id, 4)) AS label,
                       f.country, f.segment_id, f.community_id, p.risk_tier,
                       p.graph_churn_probability AS churn_probability,
                       f.influence_score, f.contagion_risk_score AS contagion_score,
                       f.unique_contacts, f.countries_reached, f.influenced_revenue_usd,
                       round(50 + (15 + pmod(xxhash64(f.customer_id, 111), 2500) / 100D)
                         * cos(2 * pi() * pmod(xxhash64(f.customer_id, 112), 1000) / 1000D), 2) AS x,
                       round(50 + (15 + pmod(xxhash64(f.customer_id, 113), 2500) / 100D)
                         * sin(2 * pi() * pmod(xxhash64(f.customer_id, 112), 1000) / 1000D), 2) AS y
                FROM gold_customer_graph_features f
                JOIN gold_churn_graph_predictions p USING (customer_id, community_id)
                JOIN silver_clientes c ON f.customer_id = c.cliente_id
                WHERE f.community_id = :community_id AND {country_filter}
                  AND (:risk_tier = 'ALL' OR p.risk_tier = :risk_tier)
                ORDER BY f.influence_score DESC, p.graph_churn_probability DESC
                LIMIT {limit}
                """, parameters=params, cache_ttl=15,
            )
            node_ids = [str(node["node_id"]) for node in nodes]
            if not node_ids:
                return {"available": True, "level": level, "summary": {}, "nodes": [], "edges": []}
            quoted = ",".join(f"'{value}'" for value in node_ids)
            edges = run_sql(
                f"""SELECT source_customer_id AS source, destination_customer_id AS target,
                           count(*) AS calls, round(sum(duration_seconds) / 60D, 1) AS minutes,
                           round(100 * avg(CASE WHEN dropped THEN 1D ELSE 0D END), 1) AS dropped_pct,
                           max(CASE WHEN international THEN 1 ELSE 0 END) = 1 AS international,
                           max(contact_affinity) AS affinity
                    FROM silver_customer_call_edges
                    WHERE source_customer_id IN ({quoted}) AND destination_customer_id IN ({quoted})
                    GROUP BY source_customer_id, destination_customer_id
                    ORDER BY calls DESC LIMIT 800""", cache_ttl=15,
            )
    except SqlExecutionError:
        return {"available": False, "reason": "GRAPH_NOT_READY", "level": level, "summary": {}, "nodes": [], "edges": []}
    for node in nodes:
        node.setdefault("reach_score", node.get("influence_score"))
        node.setdefault("network_exposure_score", node.get("contagion_score"))
    return {
        "available": True,
        "level": level,
        "summary": {
            "nodes": len(nodes), "edges": len(edges),
            "customers": sum(int(node.get("customer_count") or 1) for node in nodes),
            "high_risk_customers": sum(int(node.get("high_risk_customers") or (1 if node.get("risk_tier") in {"CRITICAL", "HIGH"} else 0)) for node in nodes),
            "influenced_revenue_usd": round(sum(float(node.get("influenced_revenue_usd") or 0) for node in nodes), 2),
        },
        "nodes": nodes,
        "edges": edges,
    }


@router.get("/graph/communities/{community_id}/operational")
def graph_community_operational(
    community_id: str,
    request: Request,
    country: str = Query(default="ALL", pattern=r"^(ALL|PA|MX|CO|BR|AR|CL|PE|EC|CR|GT|DO|UY)$"),
    risk_tier: str = Query(default="ALL", pattern=r"^(ALL|CRITICAL|HIGH|MEDIUM|LOW)$"),
    sort: str = Query(default="priority", pattern=r"^(priority|opportunity|influence)$"),
    limit: int = Query(default=25, ge=10, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
):
    """Convierte un grupo detectado en una cohorte gobernada y accionable."""
    access = _require_role(request, "CARE_AGENT")
    if len(community_id) != 14 or not community_id.startswith("COM-") or not all(
        char in "0123456789abcdef" for char in community_id[4:]
    ):
        raise HTTPException(400, "Identificador de grupo inválido.")
    _assert_country_access(access, None if country == "ALL" else country)
    params: dict[str, str] = {
        "community_id": community_id,
        "country": country,
        "risk_tier": risk_tier,
        "country_scope": ",".join(access["countries"]),
    }
    scope_filter = "(:country = 'ALL' OR f.country = :country)"
    if access["countries"]:
        scope_filter += " AND array_contains(split(:country_scope, ','), f.country)"
    risk_filter = "(:risk_tier = 'ALL' OR p.risk_tier = :risk_tier)"
    scoped = f"""
      SELECT f.*, p.graph_churn_probability, p.graph_lift, p.risk_tier,
             p.recommended_action AS graph_recommended_action,
             c.nombre_completo, c.segmento_nombre, c.monthly_revenue,
             c.nps_ultimo, c.open_tickets, c.avg_resolution_hours,
             c.resolution_target_hours, c.overdue_balance, c.active_subscriptions,
             c.acepta_marketing
      FROM gold_customer_graph_features f
      JOIN gold_churn_graph_predictions p USING (customer_id, community_id)
      JOIN ops_customer_360 c ON f.customer_id = c.cliente_id
      WHERE f.community_id = :community_id AND {scope_filter} AND {risk_filter}
    """
    try:
        groups = run_sql(
            f"""
            WITH scoped AS ({scoped})
            SELECT community_id,
                   mode(country) AS primary_country,
                   mode(segment_id) AS dominant_segment_id,
                   mode(segmento_nombre) AS dominant_segment,
                   concat_ws(',', sort_array(collect_set(country))) AS countries,
                   count(DISTINCT country) AS countries_reached,
                   count(*) AS customer_count,
                   round(avg(graph_churn_probability), 4) AS avg_churn_probability,
                   sum(CASE WHEN risk_tier IN ('CRITICAL','HIGH') THEN 1 ELSE 0 END) AS high_risk_customers,
                   round(sum(monthly_revenue), 2) AS monthly_revenue_usd,
                   round(sum(monthly_revenue * graph_churn_probability), 2) AS monthly_revenue_at_risk_usd,
                   round(avg(influence_score), 1) AS avg_influence_score,
                   round(avg(contagion_risk_score), 1) AS avg_contagion_score,
                   round(avg(international_call_pct), 1) AS international_call_pct,
                   sum(CASE WHEN open_tickets > 0 THEN 1 ELSE 0 END) AS customers_with_open_tickets,
                   sum(CASE WHEN open_tickets > 0 AND avg_resolution_hours > resolution_target_hours THEN 1 ELSE 0 END) AS customers_with_sla_pressure,
                   sum(CASE WHEN nps_ultimo <= 6 THEN 1 ELSE 0 END) AS detractors,
                   sum(CASE WHEN acepta_marketing THEN 1 ELSE 0 END) AS marketing_eligible_customers,
                   max(computed_at) AS computed_at
            FROM scoped GROUP BY community_id
            """,
            parameters=params, cache_ttl=15,
        )
    except SqlExecutionError:
        return {"available": False, "reason": "GRAPH_NOT_READY", "group": None, "members": [], "offers": [], "playbooks": []}
    if not groups:
        raise HTTPException(404, "Grupo de relación no encontrado para el alcance solicitado.")
    group = groups[0]
    group["technical_id"] = community_id
    reach = "Alcance regional" if int(group.get("countries_reached") or 0) >= 3 else "Relaciones locales"
    group["display_name"] = (
        f"Red {group.get('dominant_segment') or group.get('dominant_segment_id') or 'Clientes'} "
        f"{group.get('primary_country') or 'LATAM'} · {reach}"
    )

    order_by = {
        "priority": "CASE WHEN c.active_subscriptions > 0 OR c.open_tickets > 0 OR c.monthly_revenue > 0 THEN 0 ELSE 1 END, p.graph_churn_probability DESC, f.influence_score DESC, c.monthly_revenue DESC",
        "opportunity": "CASE WHEN o.marketing_eligible THEN 0 ELSE 1 END, coalesce(o.recommendation_score, 0) DESC, c.monthly_revenue DESC, p.graph_churn_probability ASC",
        "influence": "CASE WHEN c.active_subscriptions > 0 OR c.open_tickets > 0 OR c.monthly_revenue > 0 THEN 0 ELSE 1 END, f.influence_score DESC, f.contagion_risk_score DESC, c.monthly_revenue DESC",
    }[sort]
    try:
        members = run_sql(
            f"""
        WITH current_plan AS (
          SELECT s.cliente_id, max_by(bp.nombre, s.precio_mensual_usd) AS current_plan
          FROM silver_suscripciones s LEFT JOIN bronze_planes bp ON s.plan_id = bp.plan_id
          WHERE upper(s.estado) IN ('ACTIVA','ACTIVE') GROUP BY s.cliente_id
        ), top_offer AS (
          SELECT * FROM ops_customer_next_best_offer WHERE marketing_eligible = true
          QUALIFY row_number() OVER (PARTITION BY cliente_id ORDER BY recommendation_score DESC, precio_usd) = 1
        )
        SELECT f.customer_id,
               concat(left(c.nombre_completo, 1), '•••', right(f.customer_id, 4)) AS customer_ref,
               f.country, c.segmento_nombre AS segment, cp.current_plan,
               c.monthly_revenue, p.graph_churn_probability AS churn_probability,
               p.graph_lift, p.risk_tier, f.influence_score,
               f.contagion_risk_score AS contagion_score, c.nps_ultimo,
               c.open_tickets, c.overdue_balance, c.active_subscriptions,
               CASE WHEN c.open_tickets > 0 AND c.avg_resolution_hours > c.resolution_target_hours THEN 'AT_RISK'
                    WHEN c.open_tickets > 0 THEN 'OPEN' ELSE 'ON_TRACK' END AS sla_status,
               CASE WHEN c.open_tickets > 0 THEN 'SERVICE_RECOVERY'
                    WHEN p.graph_churn_probability >= 0.65 THEN 'RETENTION'
                    WHEN c.nps_ultimo <= 6 THEN 'NPS_RECOVERY'
                    WHEN c.overdue_balance > 0 THEN 'PAYMENT_ASSISTANCE'
                    WHEN o.marketing_eligible THEN coalesce(o.recommendation_type, 'CROSS_SELL')
                    ELSE 'MONITOR' END AS next_best_action,
               o.plan_id AS proposed_plan_id, o.product_name AS proposed_product,
               o.vertical AS proposed_vertical, o.precio_usd AS proposed_price_usd,
               o.recommendation_score AS offer_score, o.marketing_eligible
        FROM gold_customer_graph_features f
        JOIN gold_churn_graph_predictions p USING (customer_id, community_id)
        JOIN ops_customer_360 c ON f.customer_id = c.cliente_id
        LEFT JOIN current_plan cp ON f.customer_id = cp.cliente_id
        LEFT JOIN top_offer o ON f.customer_id = o.cliente_id
        WHERE f.community_id = :community_id AND {scope_filter} AND {risk_filter}
        ORDER BY {order_by}
        LIMIT {limit} OFFSET {offset}
            """,
            parameters=params, cache_ttl=15,
        )
        offers = run_sql(
            f"""
        SELECT o.plan_id, max(o.product_name) AS product_name, max(o.vertical) AS vertical,
               max(o.tier) AS tier, round(avg(o.precio_usd), 2) AS price_usd,
               max(o.recommendation_type) AS recommendation_type,
               count(DISTINCT o.cliente_id) AS eligible_customers,
               round(avg(o.recommendation_score), 1) AS avg_score,
               max(o.reason) AS reason
        FROM ops_customer_next_best_offer o
        JOIN gold_customer_graph_features f ON o.cliente_id = f.customer_id
        JOIN gold_churn_graph_predictions p USING (customer_id, community_id)
        WHERE f.community_id = :community_id AND o.marketing_eligible = true
          AND {scope_filter} AND {risk_filter}
        GROUP BY o.plan_id
        ORDER BY eligible_customers DESC, avg_score DESC LIMIT 5
            """,
            parameters=params, cache_ttl=15,
        )
    except SqlExecutionError:
        return {
            "available": False, "reason": "OPERATIONAL_DATA_NOT_READY", "group": group,
            "members": [], "offers": [], "playbooks": [],
            "pagination": {"offset": offset, "limit": limit, "total": int(group.get("customer_count") or 0)},
            "filters": {"country": country, "risk_tier": risk_tier, "sort": sort},
        }
    high_risk = int(group.get("high_risk_customers") or 0)
    service_pressure = int(group.get("customers_with_sla_pressure") or 0)
    detractors = int(group.get("detractors") or 0)
    playbooks: list[dict] = []
    if service_pressure or int(group.get("customers_with_open_tickets") or 0):
        playbooks.append({
            "type": "SERVICE_RECOVERY", "priority": "HIGH", "title": "Recuperar servicio antes de vender",
            "audience": service_pressure or int(group.get("customers_with_open_tickets") or 0),
            "reason": "Clientes con tickets abiertos o presión sobre el objetivo de SLA.",
            "action": "Priorizar resolución, comunicación proactiva y crédito cuando sea aplicable.",
        })
    if high_risk:
        playbooks.append({
            "type": "RETENTION", "priority": "HIGH", "title": "Tratar el riesgo cliente por cliente",
            "audience": high_risk, "reason": "Clientes HIGH/CRITICAL dentro del grupo de relaciones.",
            "action": "Abrir Cliente 360, resolver fricciones y aprobar la oferta de permanencia adecuada.",
        })
    if detractors:
        playbooks.append({
            "type": "NPS_RECOVERY", "priority": "MEDIUM", "title": "Cerrar el ciclo con detractores",
            "audience": detractors, "reason": "Último NPS entre 0 y 6.",
            "action": "Entender causa, registrar solución y volver a medir antes de una campaña comercial.",
        })
    if offers:
        playbooks.append({
            "type": "GROWTH", "priority": "MEDIUM", "title": "Activar crecimiento elegible",
            "audience": int(group.get("marketing_eligible_customers") or 0),
            "reason": "Clientes estables con consentimiento y productos compatibles no contratados.",
            "action": "Priorizar las oportunidades de mayor afinidad; validar necesidad antes de ofertar.",
        })
    return {
        "available": True, "group": group, "members": members, "offers": offers,
        "playbooks": playbooks, "pagination": {"offset": offset, "limit": limit, "total": int(group.get("customer_count") or 0)},
        "filters": {"country": country, "risk_tier": risk_tier, "sort": sort},
    }


@router.post("/customers/{customer_id}/recommendations", status_code=201)
def decide_recommendation(customer_id: str, payload: RecommendationDecisionRequest, request: Request):
    access = _require_role(request, "CARE_AGENT")
    customer_id = _validate_customer_id(customer_id)
    customers = run_sql("SELECT pais_codigo FROM ops_customer_360 WHERE cliente_id = :customer_id", parameters={"customer_id": customer_id}, cache_ttl=0)
    if not customers:
        raise HTTPException(404, "Cliente no encontrado.")
    _assert_country_access(access, customers[0].get("pais_codigo"))
    recommendation_id = "REC-" + uuid4().hex[:12].upper()
    execute_sql(
        """INSERT INTO ops_recommendation_log
           VALUES (:id, :customer_id, :type, :product_id, :title, :reason, :score, :status,
                   :actor, current_timestamp(), :actor, current_timestamp(), NULL, NULL, :note)""",
        parameters={"id": recommendation_id, "customer_id": customer_id, "type": payload.recommendation_type,
                    "product_id": payload.product_id, "title": payload.title, "reason": payload.reason,
                    "score": payload.score, "status": payload.decision, "actor": access["actor"], "note": payload.note},
    )
    _audit("RECOMMENDATION_" + payload.decision, "recommendation", recommendation_id, access["actor"], payload.model_dump())
    return {"recommendation_id": recommendation_id, "status": payload.decision}


@router.post("/recommendations/{recommendation_id}/outcome")
def recommendation_outcome(recommendation_id: str, payload: RecommendationOutcomeRequest, request: Request):
    access = _require_role(request, "CARE_AGENT")
    rows = run_sql("SELECT status FROM ops_recommendation_log WHERE recommendation_id = :id", parameters={"id": recommendation_id}, cache_ttl=0)
    if not rows:
        raise HTTPException(404, "Recomendación no encontrada.")
    if rows[0].get("status") != "ACCEPTED":
        raise HTTPException(409, "Solo una recomendación aceptada puede recibir resultado.")
    execute_sql(
        """UPDATE ops_recommendation_log SET status = :status, outcome_value_usd = :value,
           outcome_at = current_timestamp(), updated_by = :actor, updated_at = current_timestamp(), note = :note
           WHERE recommendation_id = :id""",
        parameters={"status": payload.outcome, "value": payload.outcome_value_usd, "actor": access["actor"], "note": payload.note, "id": recommendation_id},
    )
    _audit("RECOMMENDATION_OUTCOME", "recommendation", recommendation_id, access["actor"], payload.model_dump())
    return {"recommendation_id": recommendation_id, "status": payload.outcome}


@router.get("/incidents/{incident_id}")
def incident_detail(incident_id: str):
    rows = run_sql(
        _incident_select("c.incident_id = :incident_id"),
        parameters={"incident_id": incident_id},
        cache_ttl=0,
    )
    if not rows:
        raise HTTPException(404, "Incidente no encontrado.")
    item = rows[0]
    actions = run_sql(
        "SELECT * FROM ops_action_log WHERE incident_id = :incident_id ORDER BY requested_at DESC",
        parameters={"incident_id": incident_id},
        cache_ttl=0,
    )
    cause = str(item.get("probable_cause") or "RADIO_SIGNAL")
    item["root_cause"] = {
        "code": cause,
        "label": CAUSE_LABELS.get(cause, cause),
        "confidence": item.get("cause_confidence"),
        "evidence": [
            {"metric": "anomaly_score", "value": item.get("anomaly_score")},
            {"metric": "latency_ms", "value": item.get("latency_ms")},
            {"metric": "packet_loss_pct", "value": item.get("packet_loss_pct")},
            {"metric": "capacity_pct", "value": item.get("capacity_pct")},
            {"metric": "equipment_temp_c", "value": item.get("equipment_temp_c")},
            {"metric": "tickets_7d", "value": item.get("tickets_7d")},
        ],
    }
    item["recommended_actions"] = _recommended_actions(cause, item)
    item["actions"] = actions
    item["timeline"] = _timeline(item, actions)
    return item


def _recommended_actions(cause: str, incident: dict) -> list[dict]:
    primary = {
        "THERMAL": "DISPATCH_FIELD",
        "CONGESTION": "CAPACITY_CHANGE",
        "TRANSPORT": "CREATE_WORK_ORDER",
        "BACKHAUL": "CREATE_WORK_ORDER",
        "RADIO_SIGNAL": "DISPATCH_FIELD",
    }.get(cause, "CREATE_WORK_ORDER")
    actions = [
        {"type": primary, "label": ACTION_LABELS[primary], "approval_required": True},
        {"type": "CUSTOMER_NOTICE", "label": ACTION_LABELS["CUSTOMER_NOTICE"], "approval_required": True},
    ]
    if int(incident.get("high_churn_customers") or 0) > 0:
        actions.append({"type": "RETENTION_CAMPAIGN", "label": ACTION_LABELS["RETENTION_CAMPAIGN"], "approval_required": True})
    return actions


def _timeline(incident: dict, actions: list[dict]) -> list[dict]:
    result = [
        {"at": incident.get("detected_at"), "type": "DETECTED", "label": "Anomalía detectada por Isolation Forest"},
        {"at": incident.get("detected_at"), "type": "CORRELATED", "label": "Impacto de clientes, tickets y churn correlacionado"},
    ]
    for action in reversed(actions):
        result.append({
            "at": action.get("requested_at"),
            "type": "ACTION",
            "label": f"{ACTION_LABELS.get(action.get('action_type'), action.get('action_type'))} · {action.get('status')}",
        })
    if incident.get("updated_at"):
        result.append({"at": incident["updated_at"], "type": "STATUS", "label": f"Estado actualizado a {incident.get('status')}"})
    return result


@router.patch("/incidents/{incident_id}")
def update_incident(incident_id: str, payload: IncidentUpdateRequest, request: Request):
    _require_role(request, "NOC_OPERATOR")
    if not run_sql(
        "SELECT incident_id FROM ops_incident_candidates WHERE incident_id = :incident_id",
        parameters={"incident_id": incident_id},
        cache_ttl=0,
    ):
        raise HTTPException(404, "Incidente no encontrado.")
    actor = _actor(request)
    execute_sql(
        """
        MERGE INTO ops_incident_state AS target
        USING (SELECT :incident_id AS incident_id) AS source
        ON target.incident_id = source.incident_id
        WHEN MATCHED THEN UPDATE SET
          status = :status,
          assignee = :assignee,
          acknowledged_at = CASE WHEN :status IN ('ACKNOWLEDGED','IN_PROGRESS') AND target.acknowledged_at IS NULL THEN current_timestamp() ELSE target.acknowledged_at END,
          resolved_at = CASE WHEN :status = 'RESOLVED' THEN current_timestamp() ELSE NULL END,
          updated_at = current_timestamp(),
          updated_by = :actor
        WHEN NOT MATCHED THEN INSERT (incident_id, status, assignee, acknowledged_at, resolved_at, updated_at, updated_by)
        VALUES (:incident_id, :status, :assignee,
                CASE WHEN :status IN ('ACKNOWLEDGED','IN_PROGRESS') THEN current_timestamp() END,
                CASE WHEN :status = 'RESOLVED' THEN current_timestamp() END,
                current_timestamp(), :actor)
        """,
        parameters={"incident_id": incident_id, "status": payload.status, "assignee": payload.assignee or actor, "actor": actor},
    )
    _audit("INCIDENT_STATUS_CHANGED", "incident", incident_id, actor, payload.model_dump())
    return {"incident_id": incident_id, "status": payload.status, "assignee": payload.assignee or actor}


@router.get("/network/topology")
def network_topology(country: str | None = Query(default=None, pattern=r"^[A-Z]{2}$"), city: str | None = Query(default=None, max_length=120)):
    params: dict[str, str] = {}
    city_where = "TRUE"
    tower_where = "TRUE"
    if country:
        city_where += " AND t.pais_codigo = :country"
        tower_where += " AND t.pais_codigo = :country"
        params["country"] = country
    if city:
        tower_where += " AND t.ciudad = :city"
        params["city"] = city
    countries_future = fanout.submit(run_sql, """
      SELECT pais_codigo AS country, ROUND(AVG(uptime_pct),2) AS health_score,
             ROUND(AVG(avg_latencia_ms),1) AS latency_ms,
             ROUND(AVG(avg_throughput_mbps),1) AS throughput_mbps,
             ROUND(AVG(avg_packet_loss_pct),2) AS packet_loss_pct,
             ROUND(AVG(avg_uso_capacidad_pct),1) AS capacity_pct,
             SUM(torres_en_alerta) AS towers_alert, MAX(hora) AS as_of
      FROM gold_network_health
      WHERE hora = (SELECT MAX(hora) FROM gold_network_health)
      GROUP BY pais_codigo ORDER BY health_score DESC
    """)
    cities_future = fanout.submit(run_sql, f"""
      WITH anchor AS (SELECT MAX(timestamp) AS ts FROM silver_telemetria_red)
      SELECT t.pais_codigo AS country, t.ciudad AS city, COUNT(DISTINCT t.torre_id) AS towers,
             ROUND(AVG(CASE WHEN lower(t.alerta) IN ('sin alerta','normal','ok','false','0') THEN 100 ELSE 0 END),1) AS health_score,
             ROUND(AVG(t.latencia_ms),1) AS latency_ms, ROUND(AVG(t.throughput_mbps),1) AS throughput_mbps,
             ROUND(AVG(t.uso_capacidad_pct),1) AS capacity_pct,
             SUM(CASE WHEN lower(t.alerta) NOT IN ('sin alerta','normal','ok','false','0') THEN 1 ELSE 0 END) AS towers_alert
      FROM silver_telemetria_red t CROSS JOIN anchor a
      WHERE t.timestamp = a.ts AND {city_where}
      GROUP BY t.pais_codigo, t.ciudad ORDER BY towers_alert DESC, capacity_pct DESC LIMIT 100
    """, parameters=params)
    towers = []
    if country:
        towers = run_sql(f"""
          WITH anchor AS (SELECT MAX(timestamp) AS ts FROM silver_telemetria_red)
          SELECT t.torre_id, t.pais_codigo AS country, t.ciudad AS city, t.tecnologia AS technology,
                 d.latitud AS latitude, d.longitud AS longitude, t.usuarios_conectados AS connected_customers,
                 ROUND(t.latencia_ms,1) AS latency_ms, ROUND(t.throughput_mbps,1) AS throughput_mbps,
                 ROUND(t.packet_loss_pct,2) AS packet_loss_pct, ROUND(t.uso_capacidad_pct,1) AS capacity_pct,
                 t.temperatura_equipo_c AS equipment_temp_c, t.alerta AS alert, t.timestamp AS as_of
          FROM silver_telemetria_red t CROSS JOIN anchor a
          LEFT JOIN bronze_torres_red d ON t.torre_id = d.torre_id
          WHERE t.timestamp = a.ts AND {tower_where}
          ORDER BY CASE WHEN lower(t.alerta) IN ('sin alerta','normal','ok','false','0') THEN 1 ELSE 0 END,
                   t.uso_capacidad_pct DESC LIMIT 200
        """, parameters=params)
    return {
        "countries": countries_future.result(),
        "cities": cities_future.result(),
        "towers": towers,
        "metric_semantics": {"health_score": "percentage_of_measurements_without_alerts", "contractual_uptime": "not_available"},
    }


@router.get("/customer-impact")
def customer_impact(country: str | None = Query(default=None, pattern=r"^[A-Z]{2}$")):
    where = "TRUE"
    params: dict[str, str] = {}
    if country:
        where = "c.pais_codigo = :country"
        params["country"] = country
    rows = run_sql(f"""
      WITH anchor AS (SELECT MAX(scored_at) AS ts FROM gold_churn_predictions)
      SELECT c.pais_codigo AS country,
             COUNT(*) AS customers_scored,
             SUM(CASE WHEN lower(c.risk_tier) IN ('alto','crítico','critico','high','critical') THEN 1 ELSE 0 END) AS high_risk_customers,
             ROUND(AVG(c.churn_probability),3) AS avg_churn_probability,
             ROUND(SUM(CASE WHEN lower(c.risk_tier) IN ('alto','crítico','critico','high','critical') THEN c.gasto_mensual_total ELSE 0 END),0) AS monthly_revenue_at_risk,
             SUM(CASE WHEN c.total_tickets > 2 THEN 1 ELSE 0 END) AS repeat_contact_customers,
             SUM(CASE WHEN c.nps_ultimo <= 6 THEN 1 ELSE 0 END) AS detractors
      FROM gold_churn_predictions c CROSS JOIN anchor a
      WHERE c.scored_at = a.ts AND {where}
      GROUP BY c.pais_codigo ORDER BY monthly_revenue_at_risk DESC
    """, parameters=params)
    return {"countries": rows, "methodology": "latest_churn_scoring_with_customer_value"}


@router.get("/proactive-care")
def proactive_care(country: str | None = Query(default=None, pattern=r"^[A-Z]{2}$"), limit: int = Query(default=20, ge=1, le=100)):
    where = "lower(c.risk_tier) IN ('alto','crítico','critico','high','critical')"
    params: dict[str, object] = {"limit": limit}
    if country:
        where += " AND c.pais_codigo = :country"
        params["country"] = country
    return run_sql(f"""
      WITH anchor AS (SELECT MAX(scored_at) AS ts FROM gold_churn_predictions)
      SELECT c.cliente_id AS customer_id,
             concat('••••', right(c.cliente_id, 6)) AS customer_ref,
             c.pais_codigo AS country, c.segmento_id AS segment,
             ROUND(c.churn_probability,3) AS churn_probability,
             ROUND(c.gasto_mensual_total,2) AS monthly_value,
             c.total_tickets, c.facturas_vencidas, c.nps_ultimo,
             CASE WHEN c.tickets_cancelacion > 0 THEN 'RETENTION_SPECIALIST'
                  WHEN c.facturas_vencidas > 0 THEN 'PAYMENT_PLAN'
                  WHEN c.nps_ultimo <= 6 THEN 'SERVICE_RECOVERY'
                  ELSE 'PROACTIVE_CONTACT' END AS recommended_action,
             CASE WHEN c.churn_probability >= .85 THEN 'URGENT' ELSE 'HIGH' END AS priority
      FROM gold_churn_predictions c CROSS JOIN anchor a
      WHERE c.scored_at = a.ts AND {where}
      ORDER BY c.churn_probability * c.gasto_mensual_total DESC LIMIT :limit
    """, parameters=params)


@router.post("/scenarios/capacity")
def capacity_scenario(payload: ScenarioRequest):
    where = "hora = (SELECT MAX(hora) FROM gold_network_health)"
    params: dict[str, object] = {}
    if payload.country != "ALL":
        where += " AND pais_codigo = :country"
        params["country"] = payload.country
    rows = run_sql(f"""
      SELECT pais_codigo AS country,
             ROUND(AVG(avg_uso_capacidad_pct),1) AS current_capacity_pct,
             ROUND(AVG(avg_throughput_mbps),1) AS throughput_mbps,
             SUM(torres_en_alerta) AS towers_alert,
             SUM(total_mediciones) AS measurements
      FROM gold_network_health WHERE {where}
      GROUP BY pais_codigo ORDER BY current_capacity_pct DESC
    """, parameters=params)
    output = []
    for row in rows:
        current = float(row.get("current_capacity_pct") or 0)
        projected = max(0, current * (1 + payload.growth_pct / 100) * (1 - payload.traffic_shift_pct / 100))
        towers_alert = int(row.get("towers_alert") or 0)
        congestion_factor = max(0.0, (projected - 75) / 25)
        towers_at_risk = round(towers_alert * (1 + congestion_factor))
        estimated_investment = max(0, towers_at_risk - towers_alert) * 85000
        output.append({
            "country": row["country"],
            "current_capacity_pct": round(current, 1),
            "projected_capacity_pct": round(projected, 1),
            "risk": "CRITICAL" if projected >= 90 else "HIGH" if projected >= 80 else "CONTROLLED",
            "towers_at_risk": towers_at_risk,
            "estimated_investment_usd": estimated_investment,
            "recommended_action": "EXPAND_CAPACITY" if projected >= 80 else "MONITOR",
        })
    return {
        "inputs": payload.model_dump(),
        "results": output,
        "totals": {
            "towers_at_risk": sum(x["towers_at_risk"] for x in output),
            "estimated_investment_usd": sum(x["estimated_investment_usd"] for x in output),
        },
        "methodology": "capacity_growth_stress_test_v1",
    }


@router.get("/actions")
def actions(request: Request, status: str | None = Query(default=None, pattern=r"^(PENDING_APPROVAL|APPROVED|REJECTED|EXECUTING|EXECUTED|FAILED)$")):
    access = _access(request)
    where = "TRUE"
    params: dict[str, str] = {}
    if status:
        where = "a.status = :status"
        params["status"] = status
    if access["countries"]:
        where += " AND array_contains(split(:country_scope, ','), c.country)"
        params["country_scope"] = ",".join(access["countries"])
    return run_sql(f"""
      SELECT a.*, c.title AS incident_title, c.country, c.severity,
             x.connector, x.execution_ref, x.detail AS execution_detail, x.completed_at AS executed_at
      FROM ops_action_log a LEFT JOIN ops_incident_candidates c ON a.incident_id = c.incident_id
      LEFT JOIN (
        SELECT * FROM ops_action_attempts
        QUALIFY ROW_NUMBER() OVER (PARTITION BY action_id ORDER BY started_at DESC) = 1
      ) x ON a.action_id = x.action_id
      WHERE {where} ORDER BY a.requested_at DESC LIMIT 200
    """, parameters=params, cache_ttl=0)


@router.post("/incidents/{incident_id}/actions", status_code=201)
def create_action(incident_id: str, payload: ActionCreateRequest, request: Request):
    _require_role(request, "NOC_OPERATOR")
    if not run_sql("SELECT incident_id FROM ops_incident_candidates WHERE incident_id = :incident_id", parameters={"incident_id": incident_id}, cache_ttl=0):
        raise HTTPException(404, "Incidente no encontrado.")
    actor = _actor(request)
    action_id = "ACT-" + uuid4().hex[:12].upper()
    execute_sql(
        """INSERT INTO ops_action_log
        VALUES (:action_id, :incident_id, :action_type, :rationale, 'PENDING_APPROVAL',
                :actor, current_timestamp(), NULL, NULL, NULL)""",
        parameters={"action_id": action_id, "incident_id": incident_id, "action_type": payload.action_type, "rationale": payload.rationale, "actor": actor},
    )
    _audit("ACTION_REQUESTED", "action", action_id, actor, {"incident_id": incident_id, **payload.model_dump()})
    return {"action_id": action_id, "status": "PENDING_APPROVAL", "approval_required": True}


@router.post("/actions/{action_id}/decision")
def decide_action(action_id: str, payload: ActionDecisionRequest, request: Request):
    _require_role(request, "ACTION_APPROVER")
    existing = run_sql("SELECT status, requested_by FROM ops_action_log WHERE action_id = :action_id", parameters={"action_id": action_id}, cache_ttl=0)
    if not existing:
        raise HTTPException(404, "Acción no encontrada.")
    if existing[0]["status"] != "PENDING_APPROVAL":
        raise HTTPException(409, "La acción ya fue decidida.")
    actor = _actor(request)
    if str(existing[0].get("requested_by") or "").lower() == actor.lower():
        raise HTTPException(409, "Segregación de funciones: el solicitante no puede aprobar su propia acción.")
    execute_sql(
        """UPDATE ops_action_log SET status = :status, decided_by = :actor,
           decided_at = current_timestamp(), decision_note = :note WHERE action_id = :action_id""",
        parameters={"status": payload.decision, "actor": actor, "note": payload.note, "action_id": action_id},
    )
    _audit("ACTION_DECIDED", "action", action_id, actor, payload.model_dump())
    return {"action_id": action_id, "status": payload.decision, "decided_by": actor}


@router.post("/actions/{action_id}/execute")
def execute_action(action_id: str, payload: ActionExecutionRequest, request: Request):
    access = _require_role(request, "NOC_OPERATOR")
    rows = run_sql(
        """SELECT a.*, c.country, c.title AS incident_title
           FROM ops_action_log a LEFT JOIN ops_incident_candidates c ON a.incident_id = c.incident_id
           WHERE a.action_id = :action_id""",
        parameters={"action_id": action_id}, cache_ttl=0,
    )
    if not rows:
        raise HTTPException(404, "Acción no encontrada.")
    action = rows[0]
    _assert_country_access(access, action.get("country"))
    if action.get("status") not in ("APPROVED", "FAILED"):
        raise HTTPException(409, "Solo una acción aprobada o fallida puede ejecutarse.")
    attempt_id = "RUN-" + uuid4().hex[:12].upper()
    connector = connector_for(str(action.get("action_type")), payload.connector)
    execute_sql(
        """INSERT INTO ops_action_attempts
           (attempt_id, action_id, connector, status, idempotency_key, request_json,
            response_code, response_json, started_at, completed_at, actor, execution_ref, detail)
           VALUES (:attempt_id, :action_id, :connector, 'EXECUTING', :idempotency_key,
                   :request_json, NULL, NULL, current_timestamp(), NULL, :actor, NULL, NULL)""",
        parameters={"attempt_id": attempt_id, "action_id": action_id, "connector": connector,
                    "idempotency_key": action_id, "request_json": json.dumps(action, default=str), "actor": access["actor"]},
    )
    execute_sql("UPDATE ops_action_log SET status = 'EXECUTING' WHERE action_id = :action_id", parameters={"action_id": action_id})
    result = dispatch_action({**action, "execution_note": payload.note}, payload.connector)
    final_status = "EXECUTED" if result.success else "FAILED"
    execute_sql(
        """UPDATE ops_action_attempts SET status = :status, response_code = :response_code,
           response_json = :response_json, completed_at = current_timestamp(), execution_ref = :execution_ref,
           detail = :detail WHERE attempt_id = :attempt_id""",
        parameters={"status": final_status, "response_code": result.status_code,
                    "response_json": json.dumps(result.as_dict(), ensure_ascii=False), "execution_ref": result.execution_ref,
                    "detail": result.detail, "attempt_id": attempt_id},
    )
    execute_sql("UPDATE ops_action_log SET status = :status WHERE action_id = :action_id", parameters={"status": final_status, "action_id": action_id})
    _audit("ACTION_EXECUTION_" + final_status, "action", action_id, access["actor"], result.as_dict())
    if not result.success:
        raise HTTPException(424, {"action_id": action_id, "status": final_status, **result.as_dict()})
    return {"action_id": action_id, "attempt_id": attempt_id, "status": final_status, **result.as_dict()}


@router.get("/alerts/subscriptions")
def alert_subscriptions(request: Request):
    return run_sql(
        "SELECT * FROM ops_alert_subscriptions WHERE owner = :owner ORDER BY updated_at DESC",
        parameters={"owner": _actor(request)},
        cache_ttl=0,
    )


@router.post("/alerts/subscriptions", status_code=201)
def create_alert_subscription(payload: AlertSubscriptionRequest, request: Request):
    access = _require_role(request, "NOC_OPERATOR")
    actor = access["actor"]
    _assert_country_access(access, None if payload.country == "ALL" else payload.country)
    subscription_id = "SUB-" + uuid4().hex[:12].upper()
    execute_sql(
        """INSERT INTO ops_alert_subscriptions
        VALUES (:id, :owner, :name, :domain, :country, :metric, :operator, :threshold,
                :channel, :enabled, current_timestamp(), current_timestamp())""",
        parameters={
            "id": subscription_id,
            "owner": actor,
            "name": payload.name,
            "domain": payload.domain,
            "country": None if payload.country == "ALL" else payload.country,
            "metric": payload.metric,
            "operator": payload.operator,
            "threshold": payload.threshold,
            "channel": payload.channel,
            "enabled": payload.enabled,
        },
    )
    _audit("ALERT_SUBSCRIBED", "alert_subscription", subscription_id, actor, payload.model_dump())
    return {"subscription_id": subscription_id, "enabled": payload.enabled}


@router.patch("/alerts/subscriptions/{subscription_id}")
def update_alert_subscription(subscription_id: str, payload: AlertStateRequest, request: Request):
    access = _require_role(request, "NOC_OPERATOR")
    rows = run_sql(
        "SELECT owner FROM ops_alert_subscriptions WHERE subscription_id = :id",
        parameters={"id": subscription_id}, cache_ttl=0,
    )
    if not rows:
        raise HTTPException(404, "Regla de alerta no encontrada.")
    if "ADMIN" not in access["roles"] and str(rows[0].get("owner")).lower() != access["actor"].lower():
        raise HTTPException(403, "Solo el propietario puede modificar esta regla.")
    execute_sql(
        "UPDATE ops_alert_subscriptions SET enabled = :enabled, updated_at = current_timestamp() WHERE subscription_id = :id",
        parameters={"enabled": payload.enabled, "id": subscription_id},
    )
    _audit("ALERT_RULE_UPDATED", "alert_subscription", subscription_id, access["actor"], payload.model_dump())
    return {"subscription_id": subscription_id, "enabled": payload.enabled}


def _comparison(operator: str, observed: float, threshold: float) -> bool:
    return {">": observed > threshold, ">=": observed >= threshold, "<": observed < threshold,
            "<=": observed <= threshold, "=": observed == threshold}.get(operator, False)


@router.post("/alerts/evaluate")
def evaluate_alerts(request: Request):
    access = _require_role(request, "NOC_OPERATOR")
    rules = run_sql("SELECT * FROM ops_alert_subscriptions WHERE enabled = true", cache_ttl=0)
    capacity = run_sql(
        """SELECT pais_codigo AS country, ROUND(AVG(avg_uso_capacidad_pct), 2) AS capacity_pct
           FROM gold_network_health WHERE hora = (SELECT MAX(hora) FROM gold_network_health)
           GROUP BY pais_codigo""", cache_ttl=0,
    )
    metric_rows = {"capacity_pct": capacity}
    triggered = 0
    unsupported: list[str] = []
    for rule in rules:
        metric = str(rule.get("metric"))
        if metric not in metric_rows:
            unsupported.append(metric)
            continue
        for row in metric_rows[metric]:
            country = str(row.get("country"))
            if rule.get("country") and rule.get("country") != country:
                continue
            observed = float(row.get(metric) or 0)
            threshold = float(rule.get("threshold") or 0)
            if not _comparison(str(rule.get("operator")), observed, threshold):
                continue
            fingerprint = f"{rule['subscription_id']}:{country}:{metric}:{datetime.now(UTC).strftime('%Y%m%d%H')}"
            event_id = "ALT-" + uuid4().hex[:12].upper()
            notification_status = "DELIVERED" if rule.get("channel") == "IN_APP" else "PENDING_CONNECTOR"
            execute_sql(
                """MERGE INTO ops_alert_events AS target
                   USING (SELECT :fingerprint AS fingerprint) AS source ON target.fingerprint = source.fingerprint
                   WHEN NOT MATCHED THEN INSERT (event_id, subscription_id, fingerprint, country, metric,
                     observed_value, threshold, severity, status, notification_status, detected_at,
                     notified_at, acknowledged_at, acknowledged_by, note)
                   VALUES (:event_id, :subscription_id, :fingerprint, :country, :metric, :observed,
                     :threshold, :severity, 'OPEN', :notification_status, current_timestamp(),
                     CASE WHEN :notification_status = 'DELIVERED' THEN current_timestamp() END, NULL, NULL, NULL)""",
                parameters={"event_id": event_id, "subscription_id": rule["subscription_id"], "fingerprint": fingerprint,
                            "country": country, "metric": metric, "observed": observed, "threshold": threshold,
                            "severity": "CRITICAL" if observed >= threshold * 1.1 else "HIGH",
                            "notification_status": notification_status},
            )
            triggered += 1
    _audit("ALERT_EVALUATION", "alert_engine", "manual", access["actor"], {"triggered": triggered, "unsupported": unsupported})
    return {"rules_evaluated": len(rules), "signals_triggered": triggered, "unsupported_metrics": sorted(set(unsupported))}


@router.get("/alerts/events")
def alert_events(request: Request, status: str = Query(default="OPEN", pattern=r"^(OPEN|ACKNOWLEDGED|ALL)$")):
    access = _access(request)
    clauses = ["TRUE" if status == "ALL" else "e.status = :status"]
    params: dict[str, str] = {} if status == "ALL" else {"status": status}
    if access["countries"]:
        clauses.append("array_contains(split(:country_scope, ','), e.country)")
        params["country_scope"] = ",".join(access["countries"])
    return run_sql(
        f"""SELECT e.*, s.name, s.owner, s.channel FROM ops_alert_events e
            JOIN ops_alert_subscriptions s ON e.subscription_id = s.subscription_id
            WHERE {' AND '.join(clauses)} ORDER BY e.detected_at DESC LIMIT 100""",
        parameters=params, cache_ttl=0,
    )


@router.post("/alerts/events/{event_id}/acknowledge")
def acknowledge_alert(event_id: str, payload: AlertAcknowledgeRequest, request: Request):
    access = _require_role(request, "NOC_OPERATOR")
    execute_sql(
        """UPDATE ops_alert_events SET status = 'ACKNOWLEDGED', acknowledged_at = current_timestamp(),
           acknowledged_by = :actor, note = :note WHERE event_id = :id""",
        parameters={"actor": access["actor"], "note": payload.note, "id": event_id},
    )
    _audit("ALERT_ACKNOWLEDGED", "alert_event", event_id, access["actor"], payload.model_dump())
    return {"event_id": event_id, "status": "ACKNOWLEDGED"}


@router.get("/sla/portfolio")
def sla_portfolio(request: Request):
    access = _access(request)
    where = "TRUE"
    params: dict[str, str] = {}
    if access["countries"]:
        where = "array_contains(split(:country_scope, ','), c.pais_codigo)"
        params["country_scope"] = ",".join(access["countries"])
    rows = run_sql(
        f"""SELECT c.pais_codigo AS country, COUNT(*) AS tickets_assessed,
             SUM(CASE WHEN t.tiempo_resolucion_horas > p.resolution_target_hours THEN 1 ELSE 0 END) AS breached,
             ROUND(100 * AVG(CASE WHEN t.tiempo_resolucion_horas <= p.resolution_target_hours THEN 1 ELSE 0 END), 1) AS compliance_pct,
             ROUND(SUM(CASE WHEN t.tiempo_resolucion_horas > p.resolution_target_hours
                       THEN q.monthly_revenue * p.breach_credit_pct / 100 ELSE 0 END), 2) AS estimated_credit_usd
           FROM silver_tickets t JOIN silver_clientes c ON t.cliente_id = c.cliente_id
           JOIN ops_sla_policy p ON c.segmento_id = p.segment_id
           LEFT JOIN ops_customer_360 q ON t.cliente_id = q.cliente_id
           WHERE t.tiempo_resolucion_horas IS NOT NULL AND {where}
           GROUP BY c.pais_codigo ORDER BY breached DESC""",
        parameters=params, cache_ttl=0,
    )
    return {"countries": rows, "generated_at": datetime.now(UTC).isoformat()}


@router.get("/governance/trust")
def governance_trust():
    freshness = run_sql("""
      WITH sources AS (
        SELECT 'network' AS domain, 'hourly' AS cadence, CAST(MAX(hora) AS TIMESTAMP) AS as_of FROM gold_network_health
        UNION ALL SELECT 'revenue','monthly',CAST(MAX(mes) AS TIMESTAMP) FROM gold_revenue_by_country_service WHERE mes < DATE_TRUNC('MONTH', CURRENT_DATE())
        UNION ALL SELECT 'customers','daily',CAST(MAX(scored_at) AS TIMESTAMP) FROM gold_churn_predictions
        UNION ALL SELECT 'tickets','daily',CAST(MAX(fecha_creacion) AS TIMESTAMP) FROM silver_tickets
      )
      SELECT *, ROUND((UNIX_TIMESTAMP(CURRENT_TIMESTAMP()) - UNIX_TIMESTAMP(as_of))/3600.0,1) AS lag_hours,
        CASE WHEN cadence='hourly' AND as_of >= CURRENT_TIMESTAMP()-INTERVAL 2 HOURS THEN 'FRESH'
             WHEN cadence='daily' AND as_of >= CURRENT_TIMESTAMP()-INTERVAL 48 HOURS THEN 'FRESH'
             WHEN cadence='monthly' AND as_of >= ADD_MONTHS(DATE_TRUNC('MONTH',CURRENT_DATE()),-1) THEN 'FRESH'
             ELSE 'STALE' END AS status
      FROM sources ORDER BY domain
    """, cache_ttl=0)
    audit = run_sql("SELECT * FROM ops_audit_log ORDER BY event_at DESC LIMIT 25", cache_ttl=0)
    return {
        "freshness": freshness,
        "metric_definitions": [
            {"name": "network_health_score", "definition": "Porcentaje de mediciones sin alerta", "contractual_uptime": False, "owner": "Network Operations"},
            {"name": "revenue_at_risk", "definition": "Clientes afectados × valor mensual × factor de severidad", "contractual_uptime": None, "owner": "Finance & CX"},
            {"name": "customer_impact_score", "definition": "Impacto ponderado por clientes, valor, churn y severidad", "contractual_uptime": None, "owner": "Operaciones de Clientes"},
        ],
        "lineage": [
            {"product": "Centro de Incidentes", "sources": ["gold_network_anomalies", "silver_tickets", "gold_churn_predictions"]},
            {"product": "Topología de Red", "sources": ["silver_telemetria_red", "bronze_torres_red", "gold_network_health"]},
            {"product": "Atención Proactiva", "sources": ["gold_churn_predictions"]},
        ],
        "audit": audit,
    }
