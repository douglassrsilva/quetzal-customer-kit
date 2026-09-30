# Fundação Terraform

## Configuração

```bash
cp terraform/environments/dev/dev.tfvars.example terraform/environments/dev/dev.tfvars
```

Escolha explicitamente entre criar recursos dedicados e reutilizar recursos existentes. Para um catálogo compartilhado, mantenha `create_catalog = false`; o módulo cria apenas o schema dedicado e não altera grants de outros schemas.

## State remoto

Copie `backend.tf.example` para `backend.tf` e configure um backend criptografado e com locking pertencente ao cliente. State pode conter IDs internos e não deve ser anexado a issues nem armazenado no Git.

## Fluxo aprovado

```bash
terraform -chdir=terraform/environments/dev fmt -check -recursive
terraform -chdir=terraform/environments/dev init
terraform -chdir=terraform/environments/dev validate
terraform -chdir=terraform/environments/dev plan -out=tfplan
terraform -chdir=terraform/environments/dev show -no-color tfplan
terraform -chdir=terraform/environments/dev apply tfplan
terraform -chdir=terraform/environments/dev output bundle_values
```

Um segundo `plan` deve retornar zero mudanças. Catálogo e schema possuem `prevent_destroy`. Para recursos existentes, o cliente continua responsável por permissões fora do schema Quetzal.

Lakebase não é criado por este módulo: capacidades e recursos disponíveis variam por workspace. Registre project, branch, endpoint, host e owner role em `config/customer.env`; o DAB cria/vincula apenas o database dedicado.
