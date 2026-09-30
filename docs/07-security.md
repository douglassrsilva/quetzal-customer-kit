# Segurança

## Controles obrigatórios

- repositório privado, branch protection, revisão e CODEOWNERS do cliente;
- OIDC/workload identity para CI/CD;
- secret scanning e push protection;
- state Terraform remoto, criptografado e bloqueado;
- grupos dedicados em vez do grupo global `users`;
- row filters, column masks e escopo territorial no Unity Catalog;
- pesquisa externa e webhooks em modo opt-in;
- dependências revisadas e SBOM por release;
- logs sem tokens, credenciais ou conteúdo integral de clientes.

## Sanitização

`make sanitize` bloqueia hosts de workspace, e-mails não fictícios, IDs concretos, tokens, chaves privadas e artefatos locais. Execute também contra todo o histórico antes de transferir o repositório.

## PII

O modo sintético usa identidades fictícias. No modo customer, PII permanece no workspace do cliente e só é acessada por usuários autorizados. Screenshots, logs e exemplos usam referências mascaradas.

## Divulgação

Reporte vulnerabilidades por canal privado do cliente. Não abra issue pública e não anexe state, `.env`, HAR, cookies ou screenshots não sanitizadas.
