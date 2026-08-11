#!/usr/bin/env bash
set -euo pipefail

ACTION=${1:-plan}
REQUEST=${2:?usage: terraform_for_request.sh plan|apply|destroy request.yaml}
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
CLUSTER_NAME=$(python3 -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1]))["metadata"]["name"])' "$REQUEST")
TFVARS=$(mktemp)
trap 'rm -f "$TFVARS"' EXIT

python3 "$ROOT/scripts/validate_request.py" "$REQUEST"
python3 "$ROOT/scripts/render_tfvars.py" "$REQUEST" --output "$TFVARS"

BACKEND_ARGS=()
if [[ -n "${TF_STATE_BUCKET:-}" ]]; then
  BACKEND_ARGS+=("-backend-config=bucket=${TF_STATE_BUCKET}")
  BACKEND_ARGS+=("-backend-config=prefix=gke-clusters/${CLUSTER_NAME}")
fi

terraform -chdir="$ROOT/terraform/cluster" init -reconfigure "${BACKEND_ARGS[@]}"
terraform -chdir="$ROOT/terraform/cluster" "$ACTION" -var-file="$TFVARS" "${@:3}"
