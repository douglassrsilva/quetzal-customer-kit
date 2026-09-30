# Evidências e capturas

Todas as capturas devem ser produzidas em `staging` com dados sintéticos. Oculte barra do navegador, e-mail, hostname, workspace ID, run URL, principal IDs, Lakebase host e PII.

| Arquivo | Evidência |
|---|---|
| `01-repository-private.png` | visibilidade privada e branch protection |
| `02-auth-profile.png` | autenticação válida, sem token |
| `03-sanitize-pass.png` | scanner aprovado |
| `04-terraform-plan.png` | resumo do plan sem valores sensíveis |
| `05-terraform-apply.png` | apply concluído |
| `06-foundation-resources.png` | catálogo, schema e Warehouse |
| `07-bundle-validate.png` | bundle validado |
| `08-bundle-deploy.png` | deploy concluído |
| `09-synthetic-certification.png` | geração e certificação sintéticas bem-sucedidas |
| `10-bootstrap-run.png` | bootstrap manual bem-sucedido |
| `11-app-running.png` | App em RUNNING |
| `12-preflight.png` | preflight do Quetzal |
| `13-genie.png` | nova conversa e resposta com gráfico |
| `14-quetzal-iq.png` | conversa com memória e fontes |
| `15-dashboard.png` | AI/BI incorporado |
| `16-customer-360.png` | Cliente 360 fictício |
| `17-graph-manual.png` | grafo e botão de refresh manual |
| `18-voc-campaigns.png` | Voz do Cliente e campanha em DRAFT |
| `19-logs.png` | logs redigidos e troubleshooting |

Use a persona fictícia `Cliente Demo 000001`, cliente `CUS-DEMO-000001`, catálogo `acme_telco` e domínio `example.com`. Antes do commit, execute `make sanitize` e faça revisão visual independente.
