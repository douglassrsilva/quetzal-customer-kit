# Bootstrap operacional

No modo de demonstração, gere e certifique as fontes antes do contrato e do bootstrap:

```bash
make synthetic-data TARGET=dev
make data-contract TARGET=dev
make bootstrap TARGET=dev
make memory TARGET=dev
make alerts TARGET=dev
```

`synthetic-data` não possui agenda. Sua segunda tarefa certifica volumes, schemas, chaves, regras de negócio e cobertura das jornadas da demo. No modo `customer`, não execute esse job: publique os adapters governados e comece por `make data-contract`.

O bootstrap cria tabelas e views operacionais, aplica grants ao service principal do App e pode ser repetido com segurança. Managed Memory e alertas não possuem schedule.

Graph Intelligence é uma ação administrativa separada:

```bash
make graph TARGET=dev
```

O job prepara tabelas temporárias, valida volumes e publica um snapshot apenas ao final. Fazer deploy nunca executa o grafo automaticamente.
