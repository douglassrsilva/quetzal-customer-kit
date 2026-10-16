# Bootstrap operativo

En el modo `synthetic`, genere y certifique las fuentes antes de validar el contrato y ejecutar el bootstrap:

```bash
make synthetic-data TARGET=dev
make data-contract TARGET=dev
make bootstrap TARGET=dev
make memory TARGET=dev
make alerts TARGET=dev
```

`synthetic-data` no tiene programación. Su segunda tarea certifica volúmenes, esquemas, claves, reglas de negocio y cobertura de los flujos funcionales. En el modo `customer`, no ejecute este job: publique los adaptadores gobernados y comience con `make data-contract`.

El bootstrap crea tablas y vistas operativas, aplica permisos al service principal de la aplicación y puede repetirse de forma segura. Managed Memory y las alertas no tienen programación.

Graph Intelligence es una acción administrativa independiente:

```bash
make graph TARGET=dev
```

El job prepara tablas temporales, valida volúmenes y publica un snapshot únicamente al finalizar. El despliegue nunca ejecuta el grafo de forma automática.
