# Security policy

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability, exposed credential, privilege escalation path, or data exposure.

Report it through the private security reporting channel configured for the repository owner. Include:

- affected component and version
- reproduction steps
- required privileges
- impact
- suggested mitigation, when known

Remove real credentials, tokens, project IDs, customer data, and sensitive logs from the report.

## Supported version

This reference repository is versioned as a whole. Security fixes should be applied to the latest maintained main branch and then promoted through the organization's release process.

## Credential handling

- Do not commit `.env`, Terraform state, plans, tokens, service-account keys, kubeconfigs, or secret values.
- Prefer Workload Identity Federation and workload identity over service-account keys.
- Store portal GitHub credentials in Secret Manager.
- Use short-lived, least-privilege credentials wherever possible.
- Rotate any credential that appears in logs or Git history.

## Production review

Before production use, perform an organization-specific threat model, IAM review, network review, supply-chain review, backup restore test, and penetration test of the exposed portal path.
