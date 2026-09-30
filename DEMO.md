# Quetzal Command Center

## North star

Quetzal is a telecom operations and customer-intelligence application built around reach, freedom and connection without borders. It combines governed analytics, operational workflows and AI assistance for teams responsible for network, revenue and customer experience across Latin America.

## Graph Intelligence evolution

The Graph Intelligence module keeps the governed individual churn probability intact and adds operational context from qualified subscriber relationships. It turns call relationships into explainable reach, exposure, diffusion and retention-priority signals.

### Business experiences

- Customer 360 shows an interactive ego network with qualified contacts, relationship group, cross-border reach and relational exposure.
- Network Explorer provides community-level and customer-level drill-down without sending the full graph to the browser.
- Proactive care uses the unchanged churn propensity, related revenue and high-risk-neighbour exposure to prioritize treatment.
- Quetzal IQ can answer governed questions about reach, relationship groups, exposure and OntoBricks semantics without claiming causality.
- An authorized operator runs the complete snapshot manually from the app. No recurring schedule is created.

### Data architecture

1. `silver_customer_call_edges`: 300,000 deterministic synthetic call relationships across 60,000 existing customers and 12 countries.
2. `gold_customer_graph_features`: weighted PageRank reach, Personalized PageRank diffusion, degree, reciprocity, clustering, weighted relationship groups and neighbour exposure.
3. `gold_churn_graph_predictions`: unchanged baseline churn plus a distinct, non-probabilistic retention-priority score.
4. `gold_graph_community_summary`: bounded community aggregates for the application explorer.
5. `ops_graph_run_log`: audited manual execution state and row counts.
6. `gold_quetzal_knowledge_graph_triples`: OntoBricks-compatible semantic projection governed by the rendered `build/generated/ontology/quetzal-telecom-v1.ttl`.

All assets live in the existing Unity Catalog catalog and schema. The Databricks Asset Bundle owns the job, notebook, app resource permission and runtime configuration.

### Runtime and cost controls

- Manual-only Databricks Workflow; no `schedule` or continuous trigger.
- Serverless job compute where supported by the workspace.
- Latest snapshot only for edges and derived Gold tables; compact run history only.
- Browser payloads are bounded to ego networks or aggregated communities.

### Visual language

- Quetzal green and cyan express movement, reach and open borders.
- Communities use distinct accessible hues; risk is never communicated by colour alone.
- Minimum 14 px actionable text and high-contrast graph edges in light and dark themes.
- Stable server-provided coordinates avoid layout movement between interactions.

## Security and governance

- Existing Databricks identity, country scope and operational RBAC apply to graph APIs.
- Full customer identifiers remain restricted to governed operational views.
- Graph actions require explicit operator intent; model outputs never execute retention actions automatically.
- All source data is synthetic and demonstrative.

## Guided telecom demo backend

The backend exposes a reproducible, read-only path for a presenter or future
frontend experience:

1. `GET /api/demo/preflight` checks SQL connectivity and the configured Genie,
   AI Gateway, Lakebase, Managed Memory, dashboard, RBAC and latest Graph
   Intelligence snapshot. It never invokes paid inference or starts a job.
2. `GET /api/demo/journey?country=ALL` deterministically selects the highest
   priority unresolved incident and a high-risk customer from the same
   authorized market.
3. `GET /api/customers/{customer_id}/360` unifies customer events, SLA,
   recommendations and graph evidence in one bounded timeline.
4. `POST /api/demo/financial-impact` turns explicit treatment assumptions into
   a counterfactual retention estimate with intermediate values, formulas and
   conservative/base/optimistic sensitivity.

Network incidents in Customer 360 and the guided journey are labelled
`GEOGRAPHIC_CONTEXT` or `SAME_MARKET_EXAMPLE`, with
`direct_customer_attribution=false`. `silver_cdrs` has no tower identifier, so
Quetzal does not claim that a particular tower incident affected a customer.

Explainability is labelled `SEPARATED_PROPENSITY_AND_NETWORK_SIGNALS` and
`is_shap=false`. It separates the governed individual churn probability,
retention priority, relational exposure and reach. PageRank is never presented
as a churn model, and network association is never presented as causality.

## Voice of Customer and governed campaigns

`GET /api/voc/overview` derives a bounded market view from `silver_tickets`,
`silver_nps`, `ops_sla_policy` and `ops_customer_360`. Theme assignment is
deterministic (`voc-rules-v1`), uses no model inference and includes masked
customer examples within the operator's territorial scope. The interface calls
these examples synthetic summaries and never presents them as real transcripts.

`POST /api/campaigns/optimize` turns an optional Voice of Customer theme into a
governed audience. `campaign-rules-v1` applies, in order: territorial scope,
marketing consent, channel reachability, service-before-sales, objective and
theme eligibility, then budget and contact capacity. It returns a reproducible
`DRAFT` with exclusion counts, a bounded audience preview and counterfactual
impact. It writes no records, invokes no connector and sends no communication.

### Presenter route

1. **Preflight** — show that Warehouse, Genie, Quetzal IQ, memory, AI/BI, RBAC
   and Graph Intelligence are available without paid inference or job execution.
2. **Priority incident** — establish the operational signal, severity, SLA and
   value at risk without claiming direct tower-to-customer attribution.
3. **Voice of Customer** — filter the same market, explain the leading theme,
   its evidence and affected customers, and select **Optimizar campaña**.
4. **Customer 360** — open one affected customer and connect subscription,
   tickets, NPS, SLA, churn baseline and relationship evidence.
5. **Recommendation** — explain why service recovery precedes a commercial
   offer and preserve the human decision point.
6. **Campaign Optimizer** — adjust channel, budget and capacity; narrate the
   eligibility funnel, exclusions, audience preview and `NO ENVIADA` status.
7. **Financial impact** — close with explicit counterfactual assumptions,
   sensitivity and value protected, never as an observed or guaranteed result.

No recurring job is required for this route. The expensive Graph Intelligence
refresh remains manual and must not be started as part of the presentation.
