#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

python3 -m compileall -q "$ROOT/app" "$ROOT/scripts"
python3 "$ROOT/scripts/validate_request.py" "$ROOT/requests/prod/payments-ml-prod-usw1.yaml"
python3 "$ROOT/scripts/validate_request_set.py" --request-root "$ROOT/requests" --repository-root "$ROOT"
python3 "$ROOT/scripts/render_tfvars.py" "$ROOT/requests/prod/payments-ml-prod-usw1.yaml" >/tmp/gke-factory-example.tfvars.json
python3 "$ROOT/scripts/validate_yaml_tree.py" "$ROOT/config" "$ROOT/requests" "$ROOT/gitops" "$ROOT/.github/workflows" "$ROOT/cloudbuild"

if command -v terraform >/dev/null 2>&1; then
  terraform fmt -recursive -check "$ROOT/terraform"
  terraform -chdir="$ROOT/terraform/cluster" init -backend=false
  terraform -chdir="$ROOT/terraform/cluster" validate
  terraform -chdir="$ROOT/terraform/bootstrap" init -backend=false
  terraform -chdir="$ROOT/terraform/bootstrap" validate
  terraform -chdir="$ROOT/terraform/factory-app" init -backend=false
  terraform -chdir="$ROOT/terraform/factory-app" validate
else
  echo "terraform not installed: skipped Terraform validation"
fi
