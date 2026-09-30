# Seguridad

## Controles obligatorios

- repositorio privado, protección de rama, revisión y CODEOWNERS del cliente;
- OIDC o workload identity para CI/CD;
- Secret Scanning y Push Protection;
- state de Terraform remoto, cifrado y bloqueado;
- grupos dedicados en lugar del grupo global `users`;
- filtros de fila, máscaras de columnas y alcance territorial en Unity Catalog;
- investigación externa y webhooks en modo opt-in;
- dependencias revisadas y SBOM por release;
- logs sin tokens, credenciales ni contenido íntegro de clientes.

> Nota: algunas protecciones de GitHub para repositorios privados requieren GitHub Pro o GitHub Advanced Security. Si el plan no las incluye, documente la excepción y aplique revisión obligatoria mediante el proceso de cambios del cliente.

## Sanitización

`make sanitize` bloquea hosts de workspace, correos no ficticios, IDs concretos, tokens, claves privadas y artefactos locales. Ejecútelo también sobre todo el historial antes de transferir el repositorio.

## PII

El modo sintético utiliza identidades ficticias. En el modo `customer`, la PII permanece en el workspace del cliente y solo la consultan usuarios autorizados. Las capturas, los logs y los ejemplos utilizan referencias enmascaradas.

## Divulgación

Reporte las vulnerabilidades mediante el canal privado aprobado por el cliente. No abra una issue pública ni adjunte state, `.env`, HAR, cookies o capturas sin sanitizar.
