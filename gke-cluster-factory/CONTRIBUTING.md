# Contributing

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

## Before opening a pull request

```bash
ruff check app tests scripts
pytest -q
./scripts/validate_all.sh
node --check app/static/app.js
```

With Terraform and Helm installed:

```bash
terraform fmt -recursive -check terraform
for directory in terraform/bootstrap terraform/cluster terraform/factory-app; do
  terraform -chdir="$directory" init -backend=false
  terraform -chdir="$directory" validate
done
helm lint gitops/charts/platform-baseline
```

## Change rules

- Add a new blueprint version instead of changing an existing production contract in place.
- Add tests for request schema or policy changes.
- Never commit credentials, generated Terraform state, plans, kubeconfigs, or secret values.
- Preserve the Git approval and protected destruction path.
- Document any new Google Cloud IAM permissions.
- Test admission policy changes against both allowed and rejected resources.
- Keep request fields focused on workload intent.

## Commit guidance

Use clear, scoped commit messages such as:

```text
feat(portal): add shared VPC request option
fix(gke): grant backup service identity KMS access
docs(operations): add restore drill
```
