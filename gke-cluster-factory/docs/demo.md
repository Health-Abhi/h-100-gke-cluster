# Local demonstration

The local mode demonstrates the user experience, policy checks, IP allocation, request persistence, and Terraform variable rendering without creating billable cloud resources.

## Start with Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

Open `http://localhost:8080`.

## Suggested three-minute demonstration

### Scene 1: the problem

Explain that teams should not choose dozens of low-level GKE settings independently. The platform publishes a few supported products.

### Scene 2: select a blueprint

Open **New cluster** and choose:

```text
Standard Production
```

Enter ownership, project, classification, exposure, capacity, backup, and network intent.

### Scene 3: validation

Submit the form. Show that production automatically requires:

- deletion protection
- backup
- three system nodes
- three general nodes
- three application replicas

Try changing one value to an invalid setting to show a blocked request.

### Scene 4: request record

Open the newly created file under `requests/prod/`. Show:

- actor
- normalized labels
- complete specification
- platform-assigned IP ranges
- status conditions

### Scene 5: Terraform rendering

```bash
python scripts/render_tfvars.py requests/prod/CLUSTER.yaml \
  --output /tmp/cluster.tfvars.json
cat /tmp/cluster.tfvars.json
```

Explain that users never type CIDRs, node service accounts, or security switches.

### Scene 6: production workflow

Open `.github/workflows/request-plan.yml` and `.github/workflows/request-apply.yml`. Explain that the production portal opens a pull request, the plan performs live cloud checks, and merge starts reconciliation.

### Scene 7: GitOps controls

Show `gitops/charts/platform-baseline/templates/`. Highlight namespace RBAC, default-deny networking, Pod hardening, image policy, topology spread, and Service exposure.

## API demonstration

Health:

```bash
curl -s http://localhost:8080/healthz
curl -s http://localhost:8080/readyz
```

Catalog:

```bash
curl -s http://localhost:8080/api/v1/catalog | python -m json.tool
```

Requests:

```bash
curl -s http://localhost:8080/api/v1/requests | python -m json.tool
```

FastAPI interactive API documentation is available at:

```text
http://localhost:8080/docs
```

## Isolated demo request directory

To avoid modifying the included repository request files:

```bash
export FACTORY_REQUEST_DIR=/tmp/gke-factory-demo/requests
mkdir -p "$FACTORY_REQUEST_DIR"
uvicorn app.main:app --port 8080
```

The setting uses the `FACTORY_` prefix, so `request_dir` becomes `FACTORY_REQUEST_DIR`.

## Optional local API token

Set:

```bash
export FACTORY_API_TOKEN='replace-with-a-random-value'
```

Then the API requires:

```bash
curl -H 'Authorization: Bearer replace-with-a-random-value' \
  http://localhost:8080/api/v1/catalog
```

The web UI does not currently collect this token. Use the token option for API testing or add an authenticated reverse proxy. Production browser access is designed around IAP.

## Clean up local mode

Stop the process and remove any demonstration requests you do not want to keep:

```bash
rm -rf /tmp/gke-factory-demo
```

No Google Cloud cleanup is required because local mode never provisions cloud resources.
