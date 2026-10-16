# Requisitos previos

## Accesos

- workspace de Databricks con serverless, Unity Catalog, Apps, AI/BI y Genie habilitados;
- permiso para utilizar o crear un esquema, un Warehouse y grupos;
- proyecto, rama y endpoint de Lakebase Autoscaling aprobados;
- servicio de modelo de Unity AI Gateway aprobado;
- un administrador capaz de configurar la federación OIDC entre GitHub y Databricks;
- grupos separados para usuarios y administradores de Quetzal.

Después de crear el repositorio de su organización, reemplace los responsables de `.github/CODEOWNERS` por usuarios o equipos válidos y configure la protección de la rama principal.

## Herramientas locales

```bash
python --version       # 3.11+
node --version         # 20+
terraform version      # 1.7+
databricks -v          # 0.229+
```

Autentíquese localmente con OAuth U2M:

```bash
databricks auth login --host https://customer-workspace.cloud.databricks.com --profile customer-dev
databricks current-user me --profile customer-dev
```

No utilice un PAT en `config/customer.env`. El archivo acepta únicamente identificadores no secretos y Git lo ignora.
