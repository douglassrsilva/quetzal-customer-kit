# Quetzal Customer Kit

Proyecto reproducible para desplegar Quetzal en un workspace de Databricks administrado por su organización. Incluye la aplicación React/FastAPI, un Databricks Asset Bundle, módulos de Terraform, contratos de datos y guías de instalación y operación.

Puede evaluar la solución con datos sintéticos o conectarla a fuentes gobernadas de su organización. Ninguno de los dos modos requiere almacenar datos, credenciales ni archivos de estado en Git.

## Principios

- ningún token, credencial, dato personal ni archivo de estado en el repositorio;
- Terraform administra la base; DAB administra los artefactos de Databricks;
- Unity Catalog y cómputo serverless de forma predeterminada;
- ningún job recurrente: bootstrap, memoria, alertas y grafo son manuales;
- los conectores y la investigación externa permanecen deshabilitados hasta recibir aprobación explícita;
- los datos reales nunca se almacenan en Git;
- producción cuenta con `prevent_destroy` y aprobación humana.

## Inicio rápido

Requisitos previos: Python 3.11+, Node.js 20+, Terraform 1.7+, Databricks CLI 0.229+ y un perfil OAuth del workspace de destino.

```bash
cp config/customer.env.example config/customer.env
cp terraform/environments/dev/dev.tfvars.example terraform/environments/dev/dev.tfvars

# Reemplace todos los valores de ejemplo antes de continuar.
make preflight
make sanitize

terraform -chdir=terraform/environments/dev init
terraform -chdir=terraform/environments/dev plan -out=tfplan
terraform -chdir=terraform/environments/dev apply tfplan

make frontend-build
make bundle-validate TARGET=dev
make bundle-deploy TARGET=dev
make synthetic-data TARGET=dev
make data-contract TARGET=dev
make bootstrap TARGET=dev
make memory TARGET=dev
```

`synthetic-data` ejecuta un job serverless manual con dos tareas: generación y certificación. La ejecución falla si los volúmenes, esquemas, claves, reglas contables, protección de las identidades ficticias o cobertura de los flujos funcionales son incorrectos. Para fuentes reales, no ejecute este job: implemente los adaptadores del modo `customer`.

El grafo está separado de forma intencional y solo debe ejecutarse cuando sea necesario generar un nuevo snapshot:

```bash
make graph TARGET=dev
```

## Modos de datos

- `synthetic`: fuentes deterministas de telecomunicaciones, sin PII real, para evaluación, desarrollo y pruebas.
- `customer`: vistas de adaptación implementadas por el cliente sobre sus fuentes gobernadas.

El contrato canónico se encuentra en `data_contracts/`. El despliegue de la aplicación no concede acceso automático a las fuentes del cliente.

## Orden de lectura

1. [Descripción general](docs/00-overview.md)
2. [Requisitos previos](docs/01-prerequisites.md)
3. [Terraform](docs/02-terraform.md)
4. [Despliegue con DAB](docs/03-dab-deploy.md)
5. [Bootstrap](docs/04-bootstrap.md)
6. [Validación](docs/05-validation.md)
7. [Operación](docs/06-operations.md)
8. [Seguridad](docs/07-security.md)
9. [Plan de datos sintéticos](docs/08-data-generation-plan.md)
10. [Guía funcional](PRODUCT_GUIDE.md)
11. [Capturas de referencia](docs/screenshots/README.md)

## Componentes

```text
Base Terraform
  └─ grupos, catálogo/esquema, permisos y SQL Warehouse

Databricks Asset Bundle
  ├─ Databricks App
  ├─ dashboard AI/BI
  ├─ espacios Genie
  ├─ vinculación de base de datos Lakebase
  └─ jobs manuales

Aplicación Quetzal
  ├─ React + TypeScript
  ├─ FastAPI
  ├─ Unity Catalog / Databricks SQL
  ├─ Unity AI Gateway
  ├─ Lakebase + Managed Agent Memory
  └─ contrato OntoBricks
```

## Soporte

Para un error funcional, abra una issue con el comando ejecutado, el mensaje de error redactado y el identificador de la ejecución. Incluya el resultado de `make sanitize` y `make bundle-validate` cuando corresponda. Nunca publique tokens, PII, archivos `.env`, archivos de state ni payloads de producción.

Para una vulnerabilidad, siga las instrucciones de [SECURITY.md](SECURITY.md) y utilice un canal privado.
