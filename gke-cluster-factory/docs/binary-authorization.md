# Binary Authorization extension

## What the reference does

The GKE cluster enables Binary Authorization evaluation mode. The GitOps baseline also rejects images that are not digest-pinned or do not match the approved registry prefixes in selected application namespaces.

## What the reference does not claim

It does not create:

- a signing key
- an attestor
- an attestation note
- a build provenance policy
- a CI image-signing step
- a project or organization policy that requires a valid attestation

Enabling Binary Authorization by itself is not the same as requiring signed images. The effective project policy must be configured.

## Recommended production extension

1. Define the software trust model.
2. Use Artifact Registry as the approved image source.
3. Build images in an isolated CI project.
4. generate verifiable provenance
5. scan images and enforce severity policy
6. sign or attest only after all required checks pass
7. create Binary Authorization attestors backed by Cloud KMS
8. configure a project or organization policy that requires those attestations
9. define narrow break-glass rules with alerting
10. test enforcement in a non-production cluster before rollout

## Rollout pattern

Start with an audit or dry-run policy where supported. Inventory every image needed by:

- GKE system components
- Argo CD
- policy resources
- observability agents
- application workloads
- emergency tooling

Mirror third-party images into an approved registry, pin digests, scan, and attest them before changing the policy to fail closed.

## Example policy intent

A typical policy says:

- allow Google-managed system images under the platform rules required by GKE
- require one or more trusted attestations for application images
- allow only approved registry locations
- log and alert on break-glass deployment

The exact policy and attestor resources depend on your supply-chain system and compliance requirements, so they are intentionally not hardcoded into this reference.

## Relationship to Kubernetes admission policy

Use both layers:

- Kubernetes admission policy gives immediate, namespace-aware controls such as digest pinning and registry prefixes.
- Binary Authorization evaluates deploy-time trust and attestations at the GKE platform layer.

Neither layer replaces vulnerability management, provenance verification, runtime detection, or incident response.
