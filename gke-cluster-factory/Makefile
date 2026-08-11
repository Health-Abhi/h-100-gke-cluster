SHELL := /usr/bin/env bash
PYTHON ?= python3

.PHONY: install run test lint validate-example render-example docker-build terraform-fmt gitops-check package

install:
	$(PYTHON) -m venv .venv
	. .venv/bin/activate && pip install -r requirements-dev.txt

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

test:
	pytest -q

lint:
	ruff check app tests scripts

validate-example:
	$(PYTHON) scripts/validate_request.py requests/prod/payments-ml-prod-usw1.yaml

render-example:
	$(PYTHON) scripts/render_tfvars.py requests/prod/payments-ml-prod-usw1.yaml > /tmp/example-h100.tfvars.json
	cat /tmp/example-h100.tfvars.json

docker-build:
	docker build -t gke-cluster-factory:local .

terraform-fmt:
	terraform fmt -recursive -check terraform

gitops-check:
	$(PYTHON) scripts/validate_yaml_tree.py gitops

package:
	cd .. && zip -r gke-cluster-factory-reference-v1.zip gke-cluster-factory-reference-v1 -x '*/.terraform/*' '*/.venv/*' '*/__pycache__/*' '*/.pytest_cache/*' '*/.ruff_cache/*'
