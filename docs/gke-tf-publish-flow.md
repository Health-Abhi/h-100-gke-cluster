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

The portal commits the generated `clusters/<project>_<cluster>/gke.tf`
straight onto `main` in this repo (via `request-apply.yml`). That push is
what `.github/workflows/publish-gke-tf.yml` reacts to — whenever
`clusters/**/gke.tf` changes, including when the portal adds a brand-new
cluster folder. For every push it:

1. Clones the target repo (`h100-gke-automation`).
2. Checks out a **persistent** branch there, `cluster-list` — reusing it if
   it already exists (so cluster folders accumulate on it over time), or
   creating it fresh from `nonprod` the first time.
3. Copies every changed/added cluster folder
   (`clusters/<project>_<cluster>/`) onto that branch.
4. Commits and pushes to `cluster-list`.
5. Ensures there's an open PR from `cluster-list` -> `nonprod`: if one is
   already open, it just leaves a comment noting which folders were added
   in this push (the push itself updates the PR); otherwise it opens a new
   one.

It never pushes straight to `nonprod` — everything lands as (and stays as)
one running PR for review, no matter how many times the portal adds a new
cluster.

`GKE_TF_WORK_BRANCH` (Actions variable, default `cluster-list`) controls the
name of that persistent branch if you want something else.

### Required configuration

Set these in this repo's GitHub Actions settings:

| Name | Type | Default | Purpose |
| --- | --- | --- | --- |
| `GKE_TF_PUBLISH_TOKEN` | Secret | — (required) | Token with `contents` + `pull-requests` write access to the target repo |
| `GKE_TF_TARGET_REPO` | Variable | `Health-Abhi/h100-gke-automation` | `owner/name` of the downstream repo |
| `GKE_TF_TARGET_BRANCH` | Variable | `nonprod` | Branch to open PRs against |
| `GKE_TF_WORK_BRANCH` | Variable | `cluster-list` | Persistent branch in the target repo that cluster folders accumulate on |
| `GKE_MODULE_SOURCE` | Variable | *(placeholder)* | Terraform module source written into every generated `gke.tf` |

`GKE_TF_PUBLISH_TOKEN` must be a token (fine-grained PAT or GitHub App
installation token) that can read/write `Health-Abhi/h100-gke-automation` —
the default `GITHUB_TOKEN` only has permissions on this repo, not on an
external one.

### Manually (re)publishing one folder

Use `workflow_dispatch` on `publish-gke-tf.yml` with the `folder` input set
to e.g. `clusters/gcpproject-490711_new-demo-clusters` to re-run the publish
step without waiting for a new commit.
