# Managed Secret Backends

Horadus reads secrets from environment variables and supports file-backed variants
via `*_FILE` settings. This makes runtime wiring portable across secret backends:

- direct env injection (small/simple setups)
- mounted files (recommended for production)
- sidecar/CSI integrations from managed secret stores

See `docs/ENVIRONMENT.md` for the full variable list and `*_FILE` mappings.
See `docs/SECRETS_RUNBOOK.md` for Docker Compose provisioning/rotation/rollback workflow.

## Preferred Runtime Pattern

1. Store secret values in a managed backend.
2. Inject or mount those values into runtime (container/task/pod).
3. Point Horadus to mounted paths using `*_FILE` vars where possible.

Example mappings:

- `OPENAI_API_KEY_FILE=/run/secrets/openai_api_key`
- `DATABASE_URL_FILE=/run/secrets/database_url`
- `API_ADMIN_KEY_FILE=/run/secrets/api_admin_key`
- `CELERY_BROKER_URL_FILE=/run/secrets/celery_broker_url`

## AWS

### AWS Secrets Manager + ECS/Fargate

- Store values in AWS Secrets Manager.
- Use ECS task definition `secrets` entries to inject env vars directly, or mount
  through a sidecar/volume workflow if file paths are preferred.
- If mounted to files, wire the corresponding `*_FILE` variables.

### AWS Secrets Manager + EKS

- Use the AWS Secrets Store CSI driver (or External Secrets Operator).
- Mount secrets under `/run/secrets/*` in the application pod.
- Set Horadus `*_FILE` vars to mounted paths.

## Google Cloud

### Secret Manager + GKE

- Use Secret Manager CSI driver (or External Secrets Operator for GKE).
- Mount secrets as files to pod volumes.
- Configure Horadus with `*_FILE` paths.

### Secret Manager + Cloud Run

- Bind secrets to environment variables directly for simple deployments.
- For stricter secret-file parity, use mounted volumes where supported and point
  Horadus to `*_FILE` values.

## Azure

### Key Vault + AKS

- Use Azure Key Vault provider for Secrets Store CSI driver.
- Mount Key Vault secrets into pod filesystem.
- Point `*_FILE` variables to mounted file locations.

### Key Vault + App Service / Container Apps

- Use Key Vault references for env injection where file mounts are unavailable.
- Prefer short-lived credentials and managed identity over static secrets.

## HashiCorp Vault (Self-Managed / HCP Vault)

- Use Vault Agent Injector or CSI integration to write secrets to files.
- Configure Horadus `*_FILE` variables to those rendered file paths.
- Keep TTL/lease renewal managed by Vault components outside application code.

## Rotation Notes

- Favor backend-managed rotation policies for provider keys and DB credentials.
- Keep secret names stable while rotating values to avoid app config churn.
- For Horadus API runtime keys, use the auth key management endpoints and
  persisted metadata path (`API_KEYS_PERSIST_PATH`) to avoid key loss on restart.

## Operational Checklist

- Principle of least privilege for secret access IAM/RBAC.
- Separate dev/stage/prod secret scopes.
- Audit logging enabled at secret backend.
- Rollout/restart policy defined for secret refresh.
- Documented emergency rotation playbook.
