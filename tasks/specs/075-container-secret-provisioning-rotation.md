# TASK-075: Container Secret Provisioning and Rotation Runbook

## Objective

Define and document a production-safe secret management flow for the Docker
deployment path, using mounted secret files and `*_FILE` settings instead of
plaintext secret values in `.env`.

## Scope

- Deployment documentation updates
- Environment-variable reference updates
- Operator runbook for secret provisioning and rotation

## Deliverables

1. Provisioning guide
- Host-side secret directory structure and file naming convention
- File permission and ownership expectations
- Docker Compose mount examples (read-only)
- Mapping from mounted secret paths to app `*_FILE` variables

2. Rotation runbook
- How to prepare and validate new secret files
- How to apply changes with minimal downtime
- Which services to restart/recreate (`api`, `worker`, `beat`)
- Post-rotation validation checks (`/health`, smoke checks)

3. Rollback procedure
- How to restore previous secret file versions
- How to restart services back to last-known-good state
- Verification checklist after rollback

## Out of Scope

- Migrating to external secret managers (AWS/GCP/Azure/Vault)
- Orchestrator-specific secret frameworks beyond current Docker Compose flow

## Acceptance Criteria

- Production secret provisioning via mounted files + `*_FILE` variables is fully documented.
- Documentation explicitly discourages storing raw API keys in production `.env`.
- Secret rotation and rollback are documented as operator checklists.
- Deployment and environment docs cross-link to the new secret workflow.
