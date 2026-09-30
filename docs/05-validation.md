# Validación

## Validación local y CI

```bash
make sanitize
python -m pytest -q
make frontend-build
terraform -chdir=terraform/environments/dev fmt -check -recursive
terraform -chdir=terraform/environments/dev validate
make bundle-validate TARGET=dev
```

La siguiente captura muestra una ejecución real y aprobada del pipeline de GitHub Actions. En cada entrega, vuelva a ejecutar el workflow y compruebe que el commit candidato aparece en verde antes de promoverlo:

![Pipeline de validación del Customer Kit](screenshots/assets/02-github-actions-ci.png)

*Figura 1 — CI aprobada: sanitización, pruebas, auditorías de dependencias, build del frontend y validación de Terraform.*

## Certificación de datos sintéticos

```bash
make synthetic-data TARGET=dev
```

El job contiene dos tareas encadenadas. La primera genera las fuentes y derivaciones; la segunda bloquea el éxito hasta comprobar:

- conteos y esquemas esperados;
- claves primarias e integridad referencial;
- PII exclusivamente ficticia y no enrutable;
- coherencia de fechas, facturas, NPS, telemetría y churn;
- cobertura de Cliente 360, SLA, retención, campañas, Voz del Cliente e incidentes de red;
- propiedades `data_classification=synthetic` y `generated_by=quetzal-customer-kit`;
- fingerprint estable para los mismos `customer_count`, `seed` y `anchor_date`.

Una ejecución en verde es la evidencia funcional del dataset. `bundle validate` por sí solo únicamente comprueba la configuración de DAB.

## Aplicación desplegada

Abra la URL generada por Databricks Apps. La página inicial debe cargar sin errores, mostrar la navegación de Quetzal y mantener texto legible tanto en tema claro como oscuro. En Databricks, confirme además que el recurso de la aplicación está en estado `RUNNING`.

![Página inicial de la aplicación Quetzal](screenshots/assets/03-databricks-app-home.png)

*Figura 2 — Quetzal desplegado y operativo. Revise identidad visual, navegación y ausencia de errores visibles; la barra del navegador y el hostname fueron excluidos.*

## Preflight de plataforma

En la aplicación, abra **Inteligencia** y ejecute el preflight. Warehouse, Genie, AI Gateway, Lakebase, Managed Agent Memory, AI/BI, RBAC y Graph Intelligence deben mostrar su estado real. Un componente no configurado debe aparecer como advertencia explícita, nunca como un éxito simulado.

![Preflight de capacidades de Databricks](screenshots/assets/04-platform-preflight.png)

*Figura 3 — Preflight de plataforma. Compruebe qué capacidades están listas antes de iniciar la historia; identificadores internos fueron ocultados.*

## Genie con visualización

Seleccione **Genie**, pulse **Nueva conversación** y formule una pregunta analítica que produzca datos agrupados, por ejemplo: `Compara churn y NPS por mercado`. La respuesta debe conservar el texto de Genie, la consulta rastreable y un gráfico interactivo; al pasar el puntero por una marca debe aparecer su valor. La pestaña **Datos** debe mostrar las filas que sustentan la visualización.

![Respuesta real de Genie con gráfico](screenshots/assets/05-genie-response-chart.png)

*Figura 4 — Respuesta real de Genie. Verifique nueva conversación, respuesta, evidencia consultada y gráfico derivado de los datos; la captura no utiliza contenido prefabricado.*

## Quetzal IQ con fuentes

Cambie a **Quetzal IQ** y realice una pregunta que exija información externa, por ejemplo: `¿Cuál es la principal competencia que tenemos en Ecuador?`. La respuesta debe distinguir fuentes web de snapshots internos, presentar enlaces consultables y conservar el contexto en una pregunta de seguimiento. Si la investigación externa está deshabilitada, Quetzal debe informarlo claramente en vez de reemplazarla por una consulta interna no relacionada.

![Respuesta de Quetzal IQ con fuentes visibles](screenshots/assets/06-quetzal-iq-sources.png)

*Figura 5 — Quetzal IQ con trazabilidad. Compruebe respuesta pertinente, fuentes externas visibles y motor utilizado; IDs de conversación y rastreo fueron redactados.*

## Cliente 360

Abra un cliente sintético desde la búsqueda o desde una recomendación. Verifique que la vista reúne identidad ficticia, suscripciones, experiencia, NPS, SLA, churn individual, contexto relacional y productos recomendados. El usuario solo debe ver países autorizados y una oferta nunca debe activarse sin consentimiento ni decisión humana.

![Vista Cliente 360 con datos sintéticos](screenshots/assets/07-customer-360.png)

*Figura 6 — Cliente 360. Revise que riesgo, SLA, productos y recomendaciones pertenezcan al mismo cliente ficticio y respeten el alcance territorial.*

## Lista final de aceptación

1. Job sintético en `SUCCEEDED`, con la tarea de certificación concluida.
2. Aplicación en estado `RUNNING` y página inicial accesible.
3. Preflight sin capacidades críticas ausentes.
4. Genie crea una nueva conversación, responde y renderiza un gráfico interactivo.
5. Quetzal IQ mantiene el contexto y diferencia los datos internos de la investigación externa.
6. Cliente 360 respeta el alcance territorial y el consentimiento.
7. El dashboard AI/BI carga dentro de la aplicación.
8. Graph Intelligence solo se inicia mediante el botón administrativo.
9. Voz del Cliente y el Optimizador de Campañas no ejecutan comunicaciones reales.

El [índice de evidencias visuales](screenshots/README.md) indica el origen y las reglas de sanitización de cada figura.
