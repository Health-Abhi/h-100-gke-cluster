# gke.tf generation and nonprod publish flow

This is a second, lightweight output path that runs alongside the existing
tfvars/apply pipeline. It does not replace `render_tfvars.py` or the shared
`terraform/cluster` root module — it adds a standalone, per-cluster
`gke.tf` file that gets mirrored into a downstream GitOps repository.

## What gets generated

For every cluster request, `scripts/render_gke_tf.py` renders a `gke.tf`
file into:

```
clusters/<project_id>_<cluster_name>/gke.tf
```

e.g. for project `gcpproject-490711` and cluster `new-demo-clusters`:

```
clusters/gcpproject-490711_new-demo-clusters/gke.tf
```

The file calls a single `module "gke" { ... }` block with the same resolved
values render_tfvars.py produces (project, cluster name, region, node
locations, capacity, network, labels, etc.), for example:

```hcl
module "gke" {
  source = "TODO-SET-GKE-MODULE-SOURCE"

  project_id   = "gcpproject-490711"
  cluster_name = "new-demo-clusters"
  region       = "us-west1"
  ...
}
```

`source` is a placeholder (`TODO-SET-GKE-MODULE-SOURCE`) until you point it
at a real module. Set it repo-wide with the `GKE_MODULE_SOURCE` Actions
variable, or per-invocation with `--module-source` / the `GKE_MODULE_SOURCE`
env var when running the script by hand:

```bash
scripts/render_gke_tf.py requests/dev/my-cluster.yaml \
  --module-source "git::https://github.com/your-org/gke-modules.git//gke?ref=v1.0.0"
```

## Where it's wired in

`.github/workflows/request-apply.yml` calls `render_gke_tf.py` immediately
after a successful `terraform apply` for a request, then commits the
resulting `clusters/**/gke.tf` file to `main` in the same commit as the
request's reconciliation status update.

## Publishing to the downstream repo

`.github/workflows/publish-gke-tf.yml` triggers on push to `main` whenever
`clusters/**/gke.tf` changes. For each changed cluster folder it:

1. Clones the target repo's `nonprod` branch.
2. Copies the folder in (`clusters/<project>_<cluster>/`).
3. Commits on a new branch (`gke-tf/<project>_<cluster>-<sha>`).
4. Opens a pull request against `nonprod` in the target repo.

It never pushes straight to `nonprod` — everything lands as a PR for review.

### Required configuration

Set these in this repo's GitHub Actions settings:

| Name | Type | Default | Purpose |
| --- | --- | --- | --- |
| `GKE_TF_PUBLISH_TOKEN` | Secret | — (required) | Token with `contents` + `pull-requests` write access to the target repo |
| `GKE_TF_TARGET_REPO` | Variable | `Health-Abhi/h100-gke-automation` | `owner/name` of the downstream repo |
| `GKE_TF_TARGET_BRANCH` | Variable | `nonprod` | Branch to open PRs against |
| `GKE_MODULE_SOURCE` | Variable | *(placeholder)* | Terraform module source written into every generated `gke.tf` |

`GKE_TF_PUBLISH_TOKEN` must be a token (fine-grained PAT or GitHub App
installation token) that can read/write `Health-Abhi/h100-gke-automation` —
the default `GITHUB_TOKEN` only has permissions on this repo, not on an
external one.

### Manually (re)publishing one folder

Use `workflow_dispatch` on `publish-gke-tf.yml` with the `folder` input set
to e.g. `clusters/gcpproject-490711_new-demo-clusters` to re-run the publish
step without waiting for a new commit.
