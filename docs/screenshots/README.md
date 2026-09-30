# Trazabilidad de las capturas

Esta página no sustituye las instrucciones: únicamente registra dónde se utiliza y qué prueba cada captura. Las imágenes están insertadas inmediatamente después de la explicación y de los pasos que ayudan a validar. Todas deben producirse en `staging` con datos sintéticos. Oculte la barra del navegador, correo, hostname, workspace ID, run URL, principal IDs, host de Lakebase y cualquier PII.

| Archivo | Guía donde aparece | Evidencia |
|---|---|---|
| `assets/01-repository-private.png` | `README.md` | visibilidad privada del repositorio |
| `assets/02-github-actions-ci.png` | `docs/05-validation.md` | pipeline completo aprobado |
| `assets/03-databricks-app-home.png` | `docs/05-validation.md` | aplicación desplegada y legible |
| `assets/04-platform-preflight.png` | `docs/05-validation.md` | capacidades de plataforma listas |
| `assets/05-genie-response-chart.png` | `docs/05-validation.md` | respuesta real de Genie con visualización |
| `assets/06-quetzal-iq-sources.png` | `docs/05-validation.md` | respuesta de Quetzal IQ con fuentes |
| `assets/07-customer-360.png` | `docs/05-validation.md` | perfil 360 de un cliente ficticio |
| `assets/08-unity-ai-gateway.png` | `docs/03-dab-deploy.md` | endpoint de Unity AI Gateway configurado |

Cada figura debe incluir un pie que explique qué prueba, qué elemento debe revisar el cliente y qué valores están deliberadamente ocultos. No se aceptan placeholders ni capturas de otro producto.

Utilice la persona ficticia `Cliente Demo 000001`, el cliente `CUS-DEMO-000001`, el catálogo `acme_telco` y el dominio `example.com`. Antes del commit, ejecute `make sanitize` y realice una revisión visual independiente.
