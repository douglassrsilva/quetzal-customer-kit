# Descripción general

Quetzal conecta operaciones de red, impacto en el cliente, ingresos, churn y decisiones humanas. La separación de responsabilidades es deliberada:

| Capa | Responsable | Herramienta |
|---|---|---|
| Identidad, catálogo, esquema, permisos y Warehouse | Plataforma del cliente | Terraform |
| Aplicación, jobs, Genie y AI/BI | Producto Quetzal | DAB |
| Tokens, webhooks y credenciales | Seguridad del cliente | Gestor de secretos |
| Datos y políticas de acceso | Responsables de datos del cliente | Unity Catalog |

Un mismo recurso nunca debe administrarse simultáneamente con Terraform y DAB. El proyecto, la rama y el endpoint de Lakebase son requisitos previos; la vinculación de la base de datos con la aplicación permanece en el bundle.

## Entornos

- `dev`: desarrollo aislado por usuario.
- `staging`: validación integrada y evidencias de aceptación.
- `prod`: promoción aprobada, sin ejecución automática de jobs costosos.

Cada entorno utiliza su propio state de Terraform, identidad, aplicación y configuración.
