# Recovery Plan

## Objective

The research-cloud-platform should distinguish between:

1. reproducible platform components that can be rebuilt;
2. persistent state that must be backed up independently.

## Recovery objectives

Current research-platform targets:

- RPO: approximately 24 hours for irreplaceable research data.
- RTO: a few hours for rebuilding the local platform.

These are research-computing targets, not high-availability financial-system targets.

## Rebuildable components

The following should normally be reconstructed rather than treated as primary backup state:

- source code and configuration from GitHub;
- Kubernetes manifests;
- Terraform configuration;
- CI/CD workflows;
- Prometheus configuration;
- Grafana dashboards and provisioning;
- container images from GHCR;
- derived datasets that can be deterministically regenerated from raw data and code.

## State requiring backup

Backup priority should be given to:

- irreplaceable raw research data;
- manually curated source data;
- database state that cannot be reconstructed;
- non-reproducible research artefacts;
- metadata required to interpret primary research data.

Secrets are deliberately excluded from repository backups. They require a separate secure secrets-management process.

## Recovery sequence

1. Restore or provision the operating environment.
2. Clone the Git repository.
3. Restore required secrets through the approved secrets mechanism.
4. Restore irreplaceable research data.
5. Rebuild derived datasets where possible.
6. Recreate infrastructure and services from configuration.
7. Pull or rebuild container images.
8. Start the platform.
9. Run health and monitoring checks.
10. Validate research-data integrity before resuming work.

## Backup vs replication

Replication improves availability by maintaining additional live copies.

Backup provides an independent historical recovery point.

Replication does not protect against logical deletion, corruption, or application bugs that are propagated to all replicas.

## Disaster recovery

A production implementation should keep important backups in an independent failure domain, such as another region, account, storage system, or institutionally managed research-storage service.

A backup stored only on the same laptop or WSL filesystem is useful for testing recovery procedures but is not sufficient disaster recovery.

## Validation

A backup is not considered reliable merely because it exists.

Recovery procedures should periodically verify:

- the archive can be opened;
- expected files are present;
- checksums match;
- the restore procedure is documented and executable.
