# Base de Terraform

## Configuración

```bash
cp terraform/environments/dev/dev.tfvars.example terraform/environments/dev/dev.tfvars
```

Elija explícitamente entre crear recursos dedicados y reutilizar recursos existentes. Para un catálogo compartido, mantenga `create_catalog = false`; el módulo crea únicamente el esquema dedicado y no modifica los permisos de otros esquemas.

## State remoto

Copie `backend.tf.example` a `backend.tf` y configure un backend cifrado, con bloqueo y propiedad del cliente. El state puede contener IDs internos y no debe adjuntarse a issues ni almacenarse en Git.

## Flujo aprobado

```bash
terraform -chdir=terraform/environments/dev fmt -check -recursive
terraform -chdir=terraform/environments/dev init
terraform -chdir=terraform/environments/dev validate
terraform -chdir=terraform/environments/dev plan -out=tfplan
terraform -chdir=terraform/environments/dev show -no-color tfplan
terraform -chdir=terraform/environments/dev apply tfplan
terraform -chdir=terraform/environments/dev output bundle_values
```

Un segundo `plan` debe devolver cero cambios. El catálogo y el esquema cuentan con `prevent_destroy`. Para los recursos existentes, el cliente sigue siendo responsable de los permisos fuera del esquema de Quetzal.

Este módulo no crea Lakebase: las capacidades y los recursos disponibles varían según el workspace. Registre el proyecto, la rama, el endpoint, el host y el rol propietario en `config/customer.env`; DAB crea y vincula únicamente la base de datos dedicada.
