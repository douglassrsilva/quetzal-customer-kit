# Quetzal Command Center

## Visión del producto

Quetzal es una aplicación de operaciones de telecomunicaciones e inteligencia de clientes construida alrededor del alcance, la libertad y la conexión sin fronteras. Combina analítica gobernada, flujos operativos y asistencia de IA para equipos responsables de red, ingresos y experiencia del cliente en América Latina.

## Evolución de Graph Intelligence

El módulo Graph Intelligence conserva intacta la probabilidad individual y gobernada de churn, y agrega contexto operativo a partir de relaciones calificadas entre suscriptores. Convierte las relaciones de llamadas en señales explicables de alcance, exposición, difusión y prioridad de retención.

### Experiencias de negocio

- Cliente 360 muestra una red ego interactiva con contactos calificados, grupo de relaciones, alcance transfronterizo y exposición relacional.
- El Explorador de Red permite profundizar desde los grupos hasta los clientes sin enviar el grafo completo al navegador.
- La atención proactiva utiliza la propensión de churn sin alterarla, los ingresos asociados y la exposición a contactos de alto riesgo para priorizar acciones.
- Quetzal IQ responde preguntas gobernadas sobre alcance, grupos de relaciones, exposición y semántica OntoBricks sin afirmar causalidad.
- Un operador autorizado ejecuta manualmente el snapshot completo desde la aplicación. No se crea ninguna programación recurrente.

### Arquitectura de datos

1. `silver_customer_call_edges`: 300.000 relaciones de llamadas sintéticas y deterministas entre 60.000 clientes existentes de 12 países.
2. `gold_customer_graph_features`: alcance mediante PageRank ponderado, difusión mediante Personalized PageRank, grado, reciprocidad, clustering, grupos de relaciones ponderados y exposición de vecinos.
3. `gold_churn_graph_predictions`: churn base sin alteraciones y un score separado, no probabilístico, de prioridad de retención.
4. `gold_graph_community_summary`: agregados acotados por grupo para el explorador de la aplicación.
5. `ops_graph_run_log`: estado auditado de la ejecución manual y conteos de filas.
6. `gold_quetzal_knowledge_graph_triples`: proyección semántica compatible con OntoBricks y gobernada por `build/generated/ontology/quetzal-telecom-v1.ttl`.

Todos los artefactos residen en el catálogo y el esquema existentes de Unity Catalog. Databricks Asset Bundle administra el job, el notebook, los permisos del recurso de la aplicación y la configuración de runtime.

### Controles de ejecución y costo

- Databricks Workflow exclusivamente manual, sin `schedule` ni trigger continuo.
- Cómputo serverless para jobs cuando el workspace lo permita.
- Solo se conserva el snapshot más reciente de las relaciones y tablas Gold derivadas; el historial de ejecuciones es compacto.
- Los payloads del navegador se limitan a redes ego o grupos agregados.

### Lenguaje visual

- El verde y el cian de Quetzal expresan movimiento, alcance y fronteras abiertas.
- Los grupos utilizan colores accesibles diferenciados; el riesgo nunca se comunica únicamente mediante color.
- El texto accionable tiene un mínimo de 14 px y las aristas del grafo conservan alto contraste en los temas claro y oscuro.
- Las coordenadas estables proporcionadas por el servidor evitan movimientos del layout entre interacciones.

## Seguridad y gobierno

- La identidad existente de Databricks, el alcance por país y el RBAC operativo se aplican a las API del grafo.
- Los identificadores completos de clientes permanecen restringidos a vistas operativas gobernadas.
- Las acciones del grafo requieren intención explícita del operador; los resultados de modelos nunca ejecutan acciones de retención automáticamente.
- Todos los datos de origen son sintéticos y demostrativos.

## Backend de la demo guiada de telecomunicaciones

El backend ofrece una ruta reproducible y de solo lectura para el presentador o para futuras experiencias de frontend:

1. `GET /api/demo/preflight` comprueba la conectividad SQL y la configuración de Genie, AI Gateway, Lakebase, Managed Memory, dashboard, RBAC y el último snapshot de Graph Intelligence. Nunca invoca inferencia de pago ni inicia un job.
2. `GET /api/demo/journey?country=ALL` selecciona de forma determinista el incidente no resuelto con mayor prioridad y un cliente de alto riesgo del mismo mercado autorizado.
3. `GET /api/customers/{customer_id}/360` unifica eventos del cliente, SLA, recomendaciones y evidencia del grafo en una línea de tiempo acotada.
4. `POST /api/demo/financial-impact` transforma supuestos explícitos de tratamiento en una estimación contrafactual de retención con valores intermedios, fórmulas y sensibilidad conservadora, base y optimista.

Los incidentes de red de Cliente 360 y del recorrido guiado se etiquetan como `GEOGRAPHIC_CONTEXT` o `SAME_MARKET_EXAMPLE`, con `direct_customer_attribution=false`. `silver_cdrs` no contiene un identificador de torre, por lo que Quetzal no afirma que un incidente de una torre específica haya afectado a un cliente.

La explicabilidad se etiqueta como `SEPARATED_PROPENSITY_AND_NETWORK_SIGNALS` e `is_shap=false`. Separa la probabilidad individual y gobernada de churn, la prioridad de retención, la exposición relacional y el alcance. PageRank nunca se presenta como modelo de churn y una asociación de red nunca se presenta como causalidad.

## Voz del Cliente y campañas gobernadas

`GET /api/voc/overview` deriva una vista acotada del mercado a partir de `silver_tickets`, `silver_nps`, `ops_sla_policy` y `ops_customer_360`. La asignación de temas es determinista (`voc-rules-v1`), no utiliza inferencia de modelos e incluye ejemplos de clientes enmascarados dentro del alcance territorial del operador. La interfaz identifica estos ejemplos como resúmenes sintéticos y nunca los presenta como transcripciones reales.

`POST /api/campaigns/optimize` convierte un tema opcional de Voz del Cliente en una audiencia gobernada. `campaign-rules-v1` aplica, en este orden: alcance territorial, consentimiento de marketing, disponibilidad del canal, servicio antes que venta, elegibilidad por objetivo y tema, presupuesto y capacidad de contacto. Devuelve un `DRAFT` reproducible con conteos de exclusión, una vista previa acotada de la audiencia e impacto contrafactual. No escribe registros, no invoca conectores ni envía comunicaciones.

### Recorrido del presentador

1. **Preflight** — demuestre que Warehouse, Genie, Quetzal IQ, memoria, AI/BI, RBAC y Graph Intelligence están disponibles sin inferencia de pago ni ejecución de jobs.
2. **Incidente prioritario** — establezca la señal operativa, gravedad, SLA y valor en riesgo sin afirmar atribución directa de torre a cliente.
3. **Voz del Cliente** — filtre el mismo mercado, explique el tema principal, su evidencia y los clientes afectados, y seleccione **Optimizar campaña**.
4. **Cliente 360** — abra un cliente afectado y conecte suscripción, tickets, NPS, SLA, churn base y evidencia relacional.
5. **Recomendación** — explique por qué la recuperación del servicio precede a una oferta comercial y conserve el punto de decisión humana.
6. **Optimizador de Campañas** — ajuste canal, presupuesto y capacidad; explique el embudo de elegibilidad, exclusiones, vista previa de audiencia y estado `NO ENVIADA`.
7. **Impacto financiero** — cierre con supuestos contrafactuales explícitos, sensibilidad y valor protegido, nunca como resultado observado o garantizado.

Este recorrido no requiere ningún job recurrente. La actualización costosa de Graph Intelligence permanece manual y no debe iniciarse durante la presentación.
