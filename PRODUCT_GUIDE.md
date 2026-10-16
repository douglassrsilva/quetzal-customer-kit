# Guía funcional de Quetzal

## Alcance

Quetzal conecta operaciones de red, experiencia del cliente, ingresos y decisiones operativas en una aplicación gobernada por Databricks. La solución reúne analítica, flujos de trabajo y asistencia de IA para equipos de red, atención, ingresos y retención.

## Graph Intelligence

Graph Intelligence agrega contexto relacional a la probabilidad individual de churn sin modificarla. Las relaciones de llamadas calificadas se convierten en señales explicables de alcance, exposición, difusión y prioridad de retención.

### Funciones principales

- **Cliente 360** muestra una red ego interactiva, contactos calificados, grupo de relaciones, alcance transfronterizo y exposición relacional.
- **Explorador de Red** permite navegar desde grupos agregados hasta clientes sin enviar el grafo completo al navegador.
- **Atención proactiva** combina propensión de churn, ingresos asociados y exposición a contactos de alto riesgo para priorizar la revisión humana.
- **Quetzal IQ** responde preguntas gobernadas sobre alcance, grupos, exposición y semántica OntoBricks sin afirmar causalidad.
- Un administrador autorizado puede generar un nuevo snapshot de forma manual. El proyecto no crea una programación recurrente.

### Arquitectura de datos

1. `silver_customer_call_edges`: relaciones de llamadas sintéticas y deterministas entre clientes existentes.
2. `gold_customer_graph_features`: PageRank ponderado, Personalized PageRank, grado, reciprocidad, clustering, grupos de relaciones y exposición de vecinos.
3. `gold_churn_graph_predictions`: churn base sin alteraciones y un score separado, no probabilístico, de prioridad de retención.
4. `gold_graph_community_summary`: agregados por grupo para el explorador de la aplicación.
5. `ops_graph_run_log`: estado auditado de cada ejecución manual y conteos de filas.
6. `gold_quetzal_knowledge_graph_triples`: proyección semántica compatible con OntoBricks y gobernada por `build/generated/ontology/quetzal-telecom-v1.ttl`.

Todos los artefactos residen en el catálogo y el esquema configurados en Unity Catalog. Databricks Asset Bundles administra el job, el notebook, los permisos de la aplicación y su configuración de runtime.

### Ejecución y costo

- El Workflow se ejecuta de forma manual, sin `schedule` ni trigger continuo.
- Los jobs utilizan cómputo serverless cuando el workspace lo permite.
- Solo se conserva el snapshot más reciente de las relaciones y tablas Gold; el historial de ejecuciones guarda un registro compacto.
- El navegador recibe redes ego o grupos agregados, nunca el grafo completo.

## Seguridad y gobierno

- La identidad de Databricks, el alcance por país y el RBAC operativo se aplican a las API del grafo.
- Los identificadores completos de clientes permanecen restringidos a vistas gobernadas.
- Los resultados de modelos no ejecutan acciones de retención. Toda acción requiere una decisión explícita del operador.
- El modo `synthetic` utiliza exclusivamente identidades y eventos ficticios.

## Flujo integrado de telecomunicaciones

El backend ofrece un flujo reproducible y de solo lectura para comprobar la integración entre las capacidades de Quetzal:

1. `GET /api/demo/preflight` comprueba SQL Warehouse, Genie, AI Gateway, Lakebase, Managed Memory, AI/BI, RBAC y el último snapshot de Graph Intelligence. No invoca un modelo ni inicia jobs.
2. `GET /api/demo/journey?country=ALL` selecciona de forma determinista el incidente no resuelto con mayor prioridad y un cliente de alto riesgo del mismo mercado autorizado.
3. `GET /api/customers/{customer_id}/360` reúne eventos del cliente, SLA, recomendaciones y contexto relacional en una línea de tiempo acotada.
4. `POST /api/demo/financial-impact` calcula una estimación contrafactual de retención a partir de supuestos explícitos y muestra valores intermedios, fórmulas y tres escenarios.

Los nombres de ruta `/api/demo/*` se conservan por compatibilidad con integraciones existentes. Las respuestas se calculan con los datos y la configuración del entorno; no son respuestas prefabricadas.

Los incidentes de red se etiquetan como `GEOGRAPHIC_CONTEXT` o `SAME_MARKET_EXAMPLE`, con `direct_customer_attribution=false`. Como `silver_cdrs` no contiene un identificador de torre, Quetzal no atribuye el impacto de una torre específica a un cliente.

La explicabilidad utiliza la etiqueta `SEPARATED_PROPENSITY_AND_NETWORK_SIGNALS` e `is_shap=false`. La interfaz separa probabilidad individual de churn, prioridad de retención, exposición relacional y alcance. PageRank no se presenta como modelo de churn y una asociación de red no se presenta como causalidad.

## Voz del Cliente y campañas gobernadas

`GET /api/voc/overview` deriva una vista acotada del mercado a partir de `silver_tickets`, `silver_nps`, `ops_sla_policy` y `ops_customer_360`. La asignación de temas es determinista (`voc-rules-v1`), no utiliza inferencia de modelos y muestra ejemplos sintéticos enmascarados dentro del alcance territorial del operador.

`POST /api/campaigns/optimize` convierte un tema de Voz del Cliente en una audiencia gobernada. `campaign-rules-v1` aplica alcance territorial, consentimiento de marketing, disponibilidad del canal, prioridad de servicio, elegibilidad, presupuesto y capacidad de contacto. Devuelve un borrador reproducible con conteos de exclusión, una vista previa acotada e impacto contrafactual. No escribe registros, no invoca conectores y no envía comunicaciones.

## Recorrido operativo sugerido

1. **Validación de capacidades:** confirme que Warehouse, Genie, Quetzal IQ, memoria, AI/BI, RBAC y Graph Intelligence están disponibles.
2. **Incidente prioritario:** revise señal operativa, gravedad, SLA y valor en riesgo sin afirmar atribución directa de torre a cliente.
3. **Voz del Cliente:** filtre el mismo mercado, revise el tema principal y prepare una audiencia gobernada.
4. **Cliente 360:** conecte suscripción, tickets, NPS, SLA, churn base y contexto relacional del cliente.
5. **Recomendación:** compruebe por qué la recuperación del servicio precede a una oferta comercial y conserve la decisión humana.
6. **Optimizador de Campañas:** ajuste canal, presupuesto y capacidad; revise elegibilidad, exclusiones y el estado `NO ENVIADA`.
7. **Impacto financiero:** compare los escenarios contrafactuales y sus supuestos. No interprete la estimación como resultado observado o garantizado.

La actualización de Graph Intelligence permanece manual. Ejecútela desde la función administrativa solo cuando necesite publicar un nuevo snapshot.
