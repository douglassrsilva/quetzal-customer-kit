# Bootstrap operacional

Execute somente depois que as tabelas canônicas estiverem disponíveis:

```bash
make data-contract TARGET=dev
make bootstrap TARGET=dev
make memory TARGET=dev
make alerts TARGET=dev
```

O bootstrap cria tabelas e views operacionais, aplica grants ao service principal do App e pode ser repetido com segurança. Managed Memory e alertas não possuem schedule.

Graph Intelligence é uma ação administrativa separada:

```bash
make graph TARGET=dev
```

O job prepara tabelas temporárias, valida volumes e publica um snapshot apenas ao final. Fazer deploy nunca executa o grafo automaticamente.
