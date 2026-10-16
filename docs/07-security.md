# Seguridad

## Controles obligatorios

- protección de rama, revisión por pull request y responsables definidos en `CODEOWNERS`;
- OIDC o workload identity para CI/CD;
- Secret Scanning y Push Protection cuando estén disponibles en el plan de GitHub;
- state de Terraform remoto, cifrado y bloqueado;
- grupos dedicados en lugar del grupo global `users`;
- filtros de fila, máscaras de columnas y alcance territorial en Unity Catalog;
- investigación externa y webhooks en modo opt-in;
- dependencias revisadas y SBOM por release;
- logs sin tokens, credenciales ni contenido íntegro de clientes.

La disponibilidad de estas funciones depende del plan de GitHub y de la visibilidad del repositorio. Si una protección no está disponible, documente la excepción y aplique el control equivalente en su proceso de cambios.

## Verificación del repositorio

`make sanitize` bloquea hosts de workspace no permitidos, correos no ficticios, IDs concretos, tokens, claves privadas y artefactos locales. Ejecútelo antes de cada commit y en el pipeline de CI.

## PII

El modo sintético utiliza identidades ficticias. En el modo `customer`, la PII permanece en el workspace del cliente y solo la consultan usuarios autorizados. Las capturas, los logs y los ejemplos utilizan referencias enmascaradas.

## Divulgación

Utilice **Private vulnerability reporting** de GitHub, si está habilitado, o contacte al mantenedor por un canal privado. No publique state, `.env`, HAR, cookies, credenciales ni capturas con información sensible.
