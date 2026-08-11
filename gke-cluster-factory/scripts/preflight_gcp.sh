#!/usr/bin/env bash
set -euo pipefail

REQUEST=${1:?usage: preflight_gcp.sh request.yaml}
STRICT=${PREFLIGHT_STRICT:-true}

command -v python3 >/dev/null || { echo "ERROR: python3 is required" >&2; exit 1; }
command -v gcloud >/dev/null || {
  if [[ "$STRICT" == "true" ]]; then
    echo "ERROR: gcloud is required for Google Cloud preflight" >&2
    exit 1
  fi
  echo "WARNING: gcloud is unavailable, so cloud quota and capacity checks were skipped"
  exit 0
}

readarray -t VALUES < <(python3 - "$REQUEST" <<'PY'
import sys, yaml
record = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
spec = record["spec"]
gpu = spec.get("gpu", {})
print(spec["project_id"])
print(spec["region"])
print("true" if gpu.get("enabled") else "false")
print(gpu.get("model") or "")
print(gpu.get("machine_type") or "")
print(gpu.get("accelerator_count") or 0)
print(gpu.get("maximum_nodes") or 0)
print(gpu.get("provisioning_model") or "standard")
print(gpu.get("reservation_name") or "")
print(",".join(gpu.get("zones") or []))
PY
)

PROJECT_ID=${VALUES[0]}
REGION=${VALUES[1]}
GPU_ENABLED=${VALUES[2]}
GPU_MODEL=${VALUES[3]}
GPU_MACHINE_TYPE=${VALUES[4]}
GPU_COUNT=${VALUES[5]}
GPU_MAX_NODES=${VALUES[6]}
PROVISIONING_MODEL=${VALUES[7]}
RESERVATION_NAME=${VALUES[8]}
IFS=',' read -r -a GPU_ZONES <<< "${VALUES[9]}"

if [[ -z "${GKE_SECURITY_GROUP:-}" || "${GKE_SECURITY_GROUP}" == *@example.com ]]; then
  echo "ERROR: GKE_SECURITY_GROUP must be set to your real Cloud Identity group-of-groups" >&2
  exit 1
fi
if [[ -z "${PLATFORM_ADMIN_GROUP:-}" || "${PLATFORM_ADMIN_GROUP}" == *@example.com ]]; then
  echo "ERROR: PLATFORM_ADMIN_GROUP must be set to your real platform administrator group" >&2
  exit 1
fi

if ! gcloud projects describe "$PROJECT_ID" --format='value(projectId)' >/dev/null 2>&1; then
  if [[ "${CREATE_CLUSTER_PROJECTS:-false}" == "true" ]]; then
    echo "INFO: project $PROJECT_ID will be created by Terraform; project-scoped preflight is deferred"
    exit 0
  fi
  echo "ERROR: project $PROJECT_ID does not exist or is not visible to this identity" >&2
  exit 1
fi

echo "OK: project $PROJECT_ID is accessible"

gcloud compute regions describe "$REGION" --project "$PROJECT_ID" --format='value(name)' >/dev/null
echo "OK: region $REGION is available to the project"

if [[ "$GPU_ENABLED" != "true" ]]; then
  echo "OK: no GPU capacity checks are required"
  exit 0
fi

required_gpus=$((GPU_COUNT * GPU_MAX_NODES))
quota_json=$(mktemp)
trap 'rm -f "$quota_json"' EXIT
gcloud compute regions describe "$REGION" --project "$PROJECT_ID" --format=json > "$quota_json"
python3 - "$quota_json" "$required_gpus" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
required = int(sys.argv[2])
matching = [q for q in payload.get("quotas", []) if "H100" in q.get("metric", "").upper()]
if not matching:
    raise SystemExit("ERROR: no H100 quota metric was found in this region; request quota before provisioning")
available = sum(max(0, float(q.get("limit", 0)) - float(q.get("usage", 0))) for q in matching)
if available < required:
    names = ", ".join(q.get("metric", "unknown") for q in matching)
    raise SystemExit(f"ERROR: H100 quota has {available:g} available but the request can consume {required}; metrics: {names}")
print(f"OK: H100 regional quota has {available:g} available for a maximum request of {required}")
PY

for zone in "${GPU_ZONES[@]}"; do
  gcloud compute machine-types describe "$GPU_MACHINE_TYPE" \
    --zone "$zone" --project "$PROJECT_ID" --format='value(name)' >/dev/null
  gcloud compute accelerator-types describe "$GPU_MODEL" \
    --zone "$zone" --project "$PROJECT_ID" --format='value(name)' >/dev/null
  echo "OK: $GPU_MACHINE_TYPE and $GPU_MODEL are offered in $zone"

  if [[ "$PROVISIONING_MODEL" == "reservation" ]]; then
    gcloud compute reservations describe "$RESERVATION_NAME" \
      --zone "$zone" --project "$PROJECT_ID" --format='value(name)' >/dev/null
    echo "OK: reservation $RESERVATION_NAME exists in $zone"
  fi
done

cat <<EOF2
OK: Google Cloud preflight completed
Project: $PROJECT_ID
Region: $REGION
GPU maximum: $required_gpus H100 devices
Provisioning model: $PROVISIONING_MODEL
EOF2
