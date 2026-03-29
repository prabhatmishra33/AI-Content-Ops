# Production Readiness Checklist (Future Work)

This document captures what should be addressed before moving this backend to a true production environment.

## 1) Identity and Access
- Replace default in-app user store with enterprise IdP (OAuth2/OIDC/SAML).
- Add MFA and password policy controls.
- Use scoped service accounts for worker-to-worker calls.
- Enforce least privilege per role and per endpoint.

## 2) Secrets and Key Management
- Move secrets from `.env` to Vault/KMS/Secret Manager.
- Rotate JWT, model, and connector keys on schedule.
- Encrypt all integration tokens at rest with managed key rotation.

## 3) Data Layer Hardening
- Migrate from SQLite to PostgreSQL.
- Use Alembic migrations in CI/CD (no ad-hoc schema changes).
- Configure backup/restore and restore testing.
- Add data retention and purge jobs for large tables/logs.

## 4) Storage and Media
- Use object storage (S3/GCS/Azure Blob) instead of local disk.
- Use signed URLs for upload/download.
- Add lifecycle rules for upload/temp/thumbnail cleanup.
- Integrate CDN for distribution artifacts.

## 5) Queue and Worker Reliability
- Use Redis HA (Sentinel/Cluster) or enterprise broker.
- Define queue SLOs and auto-scaling rules per queue.
- Add circuit breakers and backpressure handling.
- Add scheduled reprocessing for HOLD jobs with capped retries.

## 6) AI Reliability and Governance
- Prompt/version registry with controlled rollout.
- Structured output validation and guardrails.
- Offline eval datasets for moderation/impact/compliance quality.
- Cost and latency budgets per stage.
- Fallback strategy approved by product/compliance policy.

## 7) Connector Hardening
- YouTube: robust quota budgeting, webhook signature verification, retry policy by error class.
- Secondary connector: signed payloads, idempotent receiver contract, dead-letter replay.
- Outbox pattern for guaranteed delivery semantics.

## 8) API Security
- Global rate limiting and abuse controls.
- Request size/time limits per endpoint.
- Strict CORS policy and secure headers.
- Malware scanning as mandatory (not optional) in production.

## 9) Observability and Operations
- Centralized logs (Loki/ELK/OpenSearch).
- Distributed tracing (OpenTelemetry).
- Production dashboards (latency, error rate, queue lag, hold rate).
- Alerting and on-call routing (PagerDuty/Slack).
- Correlated runbooks for top failure modes.

## 10) Compliance and Audit
- Immutable audit export and retention policy.
- PII redaction and DLP checks.
- Legal hold support and deletion workflows.
- Compliance evidence generation for reviews and decisions.

## 11) Testing and Release Engineering
- Unit + integration + E2E test suites in CI.
- Performance/load testing for expected throughput.
- Security tests: SAST, dependency scan, secret scan.
- Blue/green or canary deploy with rollback automation.

## 12) Infrastructure
- Containerized deployment (Docker/Kubernetes).
- Environment isolation (dev/stage/prod).
- IaC (Terraform/Pulumi) for reproducible infrastructure.
- Disaster recovery RTO/RPO targets documented and tested.

## 13) Recommended Prioritization
- P0:
  - IdP integration, secret manager, PostgreSQL, object storage, mandatory malware scan.
- P1:
  - HA broker, autoscaling workers, full observability + alerting, connector hardening.
- P2:
  - Advanced compliance automation, cost optimization, model governance workflows.

## 14) Handover Notes
- Keep this document updated whenever architecture or operational assumptions change.
- Link all production incidents to runbooks and update prevention controls after RCA.
