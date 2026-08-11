#!/usr/bin/env bash
set -euo pipefail

: "${GITOPS_REPO_URL:?Set GITOPS_REPO_URL to the repository clone URL}"
GITOPS_REVISION=${GITOPS_REVISION:-main}
: "${PLATFORM_ADMIN_GROUP:?Set PLATFORM_ADMIN_GROUP to the Google group for platform administrators}"
ARGOCD_VERSION=${ARGOCD_VERSION:-v3.4.4}
IAM_PRINCIPAL_TYPE=${IAM_PRINCIPAL_TYPE:-Group}
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REQUEST_FILE=${REQUEST_FILE:-}

if [[ -n "$REQUEST_FILE" ]]; then
  readarray -t REQUEST_VALUES < <(python3 - "$REQUEST_FILE" <<'PY'
import sys, yaml
record = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
spec = record["spec"]
print(record["metadata"]["name"])
print(spec["owner"]["google_group"])
print(spec["owner"]["team"])
print(spec["environment"])
print(spec.get("workload", {}).get("exposure", "internal"))
PY
)
  CLUSTER_NAME=${REQUEST_VALUES[0]}
  OWNER_GROUP=${REQUEST_VALUES[1]}
  TEAM=${REQUEST_VALUES[2]}
  ENVIRONMENT=${REQUEST_VALUES[3]}
  WORKLOAD_EXPOSURE=${REQUEST_VALUES[4]}
else
  : "${CLUSTER_NAME:?Set CLUSTER_NAME or REQUEST_FILE}"
  : "${OWNER_GROUP:?Set OWNER_GROUP or REQUEST_FILE}"
  : "${TEAM:?Set TEAM or REQUEST_FILE}"
  : "${ENVIRONMENT:?Set ENVIRONMENT or REQUEST_FILE}"
  WORKLOAD_EXPOSURE=${WORKLOAD_EXPOSURE:-internal}
fi

export GITOPS_REPO_URL GITOPS_REVISION CLUSTER_NAME OWNER_GROUP TEAM ENVIRONMENT WORKLOAD_EXPOSURE PLATFORM_ADMIN_GROUP IAM_PRINCIPAL_TYPE

kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply --server-side --force-conflicts -n argocd -f "https://raw.githubusercontent.com/argoproj/argo-cd/${ARGOCD_VERSION}/manifests/install.yaml"
kubectl rollout status deployment/argocd-server -n argocd --timeout=10m

if [[ -n "${GITOPS_USERNAME:-}" && -n "${GITOPS_TOKEN:-}" ]]; then
  kubectl create secret generic github-repository-credentials \
    --namespace argocd \
    --from-literal=type=git \
    --from-literal=url="$GITOPS_REPO_URL" \
    --from-literal=username="$GITOPS_USERNAME" \
    --from-literal=password="$GITOPS_TOKEN" \
    --dry-run=client -o yaml | kubectl apply -f -
  kubectl label secret github-repository-credentials \
    --namespace argocd \
    argocd.argoproj.io/secret-type=repository \
    --overwrite
fi

python3 - "$ROOT/gitops/bootstrap/root-application.yaml.tpl" <<'PY' | kubectl apply -f -
import os, sys
content = open(sys.argv[1], encoding="utf-8").read()
replacements = {
    "__REPO_URL__": os.environ["GITOPS_REPO_URL"],
    "__REVISION__": os.environ.get("GITOPS_REVISION", "main"),
    "__CLUSTER_NAME__": os.environ["CLUSTER_NAME"],
    "__OWNER_GROUP__": os.environ["OWNER_GROUP"],
    "__TEAM__": os.environ["TEAM"],
    "__ENVIRONMENT__": os.environ["ENVIRONMENT"],
    "__PLATFORM_ADMIN_GROUP__": os.environ["PLATFORM_ADMIN_GROUP"],
    "__WORKLOAD_EXPOSURE__": os.environ["WORKLOAD_EXPOSURE"],
    "__IAM_PRINCIPAL_TYPE__": os.environ.get("IAM_PRINCIPAL_TYPE", "Group").capitalize(),
}
for key, value in replacements.items():
    content = content.replace(key, value)
print(content)
PY

echo "Argo CD is installed and the platform baseline is registered for ${CLUSTER_NAME}."
