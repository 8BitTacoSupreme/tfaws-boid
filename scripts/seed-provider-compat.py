#!/usr/bin/env python3
"""Seed canon/provider-compat.json with Terraform + AWS provider compatibility matrix.

Covers: Terraform 1.5–1.8 × AWS provider 4.x–5.x–6.x
Sources: Provider CHANGELOG, upgrade guides, Terraform compatibility docs
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from canon_lib import load_canon, save_canon, make_meta

FILENAME = "provider-compat.json"


def build_compatibility() -> list[dict]:
    """Build the provider compatibility matrix entries."""
    return [
        # ── Terraform 1.5.x ──────────────────────────────────────────
        {
            "terraform_version": ">=1.5.0, <1.6.0",
            "provider_version": ">=4.0.0, <5.0.0",
            "status": "compatible",
            "breaking_changes": [],
            "migration_notes": "Stable combination. TF 1.5 introduced import blocks and check blocks. AWS provider 4.x is the last major version before the v5 rewrite.",
            "min_required_provider": "4.0.0",
            "notes": "TF 1.5 adds: import blocks (declarative import), check blocks (continuous validation), for_each on import. AWS 4.x is mature and well-tested."
        },
        {
            "terraform_version": ">=1.5.0, <1.6.0",
            "provider_version": ">=5.0.0, <6.0.0",
            "status": "compatible",
            "breaking_changes": [
                "AWS provider 5.0 dropped default tags inheritance for aws_autoscaling_group",
                "s3_bucket resource split into multiple resources (bucket, versioning, acl, etc.) is now enforced",
                "Default value changes for enable_dns_support and enable_dns_hostnames on aws_vpc",
                "aws_launch_configuration deprecated in favor of aws_launch_template",
                "provider-level assume_role block no longer accepts inline session policies by default"
            ],
            "migration_notes": "Major upgrade path. Run `terraform plan` after upgrading to see all diffs before applying. The S3 bucket resource split was the most impactful change — aws_s3_bucket no longer accepts inline acl, versioning, logging, lifecycle_rule, server_side_encryption_configuration, etc.",
            "min_required_provider": "5.0.0",
            "notes": "The 4.x → 5.x upgrade is the biggest migration in AWS provider history. Plan for significant refactoring of S3 configurations."
        },
        {
            "terraform_version": ">=1.5.0, <1.6.0",
            "provider_version": ">=6.0.0",
            "status": "compatible",
            "breaking_changes": [
                "Provider 6.0 requires Terraform >=1.5.0 (met)",
                "Resource identity framework changes (affects moved blocks and imports)",
                "Some data source return types changed from list to set",
                "Removed previously deprecated resources and arguments"
            ],
            "migration_notes": "TF 1.5 meets the minimum requirement for provider 6.x but you miss out on features like ephemeral values (TF 1.8+). Consider upgrading TF first.",
            "min_required_provider": "6.0.0",
            "notes": "Provider 6.x works with TF 1.5+ but was designed alongside TF 1.8+ features."
        },
        # ── Terraform 1.6.x ──────────────────────────────────────────
        {
            "terraform_version": ">=1.6.0, <1.7.0",
            "provider_version": ">=4.0.0, <5.0.0",
            "status": "compatible",
            "breaking_changes": [],
            "migration_notes": "TF 1.6 adds testing framework (`terraform test`) and variable validation improvements. AWS provider 4.x works without issues.",
            "min_required_provider": "4.0.0",
            "notes": "TF 1.6 adds: terraform test command (HCL-based testing), S3 backend state locking improvements, config-driven remove blocks."
        },
        {
            "terraform_version": ">=1.6.0, <1.7.0",
            "provider_version": ">=5.0.0, <6.0.0",
            "status": "compatible",
            "breaking_changes": [
                "Same AWS provider 5.0 breaking changes apply (S3 split, tag inheritance, etc.)"
            ],
            "migration_notes": "Best combination for teams that need stability. TF 1.6 testing + AWS 5.x improvements. Use `terraform test` to validate the v5 migration.",
            "min_required_provider": "5.0.0",
            "notes": "Recommended for teams migrating from 4.x → 5.x: TF 1.6's test framework helps validate the migration."
        },
        {
            "terraform_version": ">=1.6.0, <1.7.0",
            "provider_version": ">=6.0.0",
            "status": "compatible",
            "breaking_changes": [
                "Provider 6.0 breaking changes apply (resource identity, removed deprecations)"
            ],
            "migration_notes": "Works but not optimal. TF 1.6 doesn't have ephemeral values or other TF 1.8+ features that provider 6.x was designed for.",
            "min_required_provider": "6.0.0",
            "notes": "Functional but suboptimal. Provider 6.x leverages TF 1.8+ features that aren't available in 1.6."
        },
        # ── Terraform 1.7.x ──────────────────────────────────────────
        {
            "terraform_version": ">=1.7.0, <1.8.0",
            "provider_version": ">=4.0.0, <5.0.0",
            "status": "deprecated",
            "breaking_changes": [],
            "migration_notes": "AWS provider 4.x is end-of-life. No new bug fixes or features. Upgrade to 5.x for security patches and new resource support.",
            "min_required_provider": "4.0.0",
            "notes": "TF 1.7 adds: removed blocks (safe resource removal), provider-defined functions, config-driven import enhancements. But 4.x is EOL."
        },
        {
            "terraform_version": ">=1.7.0, <1.8.0",
            "provider_version": ">=5.0.0, <6.0.0",
            "status": "compatible",
            "breaking_changes": [],
            "migration_notes": "Solid combination. TF 1.7 removed blocks help manage the 4.x → 5.x resource deprecations cleanly.",
            "min_required_provider": "5.0.0",
            "notes": "TF 1.7 'removed' blocks are excellent for managing the S3 resource split migration: cleanly remove old resource references from state."
        },
        {
            "terraform_version": ">=1.7.0, <1.8.0",
            "provider_version": ">=6.0.0",
            "status": "compatible",
            "breaking_changes": [
                "Provider 6.0 breaking changes apply"
            ],
            "migration_notes": "Good combination but TF 1.8 adds ephemeral values that improve secrets handling with provider 6.x.",
            "min_required_provider": "6.0.0",
            "notes": "Works well. But if using provider 6.x, consider upgrading to TF 1.8+ for ephemeral values support."
        },
        # ── Terraform 1.8.x+ ─────────────────────────────────────────
        {
            "terraform_version": ">=1.8.0",
            "provider_version": ">=4.0.0, <5.0.0",
            "status": "deprecated",
            "breaking_changes": [],
            "migration_notes": "AWS provider 4.x is end-of-life and doesn't support ephemeral values or other TF 1.8+ features. Upgrade to 5.x or 6.x.",
            "min_required_provider": "4.0.0",
            "notes": "TF 1.8+ features (ephemeral values, provider-defined functions) are not available with provider 4.x."
        },
        {
            "terraform_version": ">=1.8.0",
            "provider_version": ">=5.0.0, <6.0.0",
            "status": "compatible",
            "breaking_changes": [],
            "migration_notes": "Good combination. TF 1.8 adds ephemeral values (sensitive data handling without state persistence). AWS provider 5.x supports provider-defined functions.",
            "min_required_provider": "5.0.0",
            "notes": "TF 1.8 adds: ephemeral values (write-only attributes), provider functions, improved sensitive data handling. Provider 5.x benefits from all of these."
        },
        {
            "terraform_version": ">=1.8.0",
            "provider_version": ">=6.0.0",
            "status": "compatible",
            "breaking_changes": [
                "Provider 6.0 introduces resource identity framework (changes how resources are tracked internally)",
                "Some previously deprecated resources removed entirely",
                "Data source return types changed from list to set in some cases",
                "Provider 6.0 requires Go module changes for custom providers"
            ],
            "migration_notes": "Best current combination. Full feature support for both TF and provider. Use `terraform test` to validate the upgrade path. Run `terraform plan` in detail to catch any resource identity changes.",
            "min_required_provider": "6.0.0",
            "notes": "Recommended combination for new projects. Full ephemeral values support, write-only attributes, provider functions, and latest resource implementations."
        },
        # ── Key migration paths ──────────────────────────────────────
        {
            "terraform_version": ">=1.5.0",
            "provider_version": "4.x → 5.x migration",
            "status": "breaking",
            "breaking_changes": [
                "aws_s3_bucket: inline acl, cors_rule, grant, lifecycle_rule, logging, object_lock_configuration, replication_configuration, server_side_encryption_configuration, versioning, website arguments removed. Use separate resources.",
                "aws_s3_bucket_acl: now required for non-private ACLs (was automatic)",
                "aws_autoscaling_group: no longer inherits provider default_tags",
                "aws_vpc: enable_dns_support and enable_dns_hostnames defaults changed",
                "aws_db_instance: storage_type default changed from 'standard' to 'gp2'",
                "aws_launch_configuration: deprecated, use aws_launch_template",
                "ec2_classic resources removed (aws_security_group in EC2-Classic, etc.)",
                "Several data sources changed return types"
            ],
            "migration_notes": "This is the most impactful AWS provider migration. Steps: (1) Pin current 4.x version, (2) Run `terraform state show` on all S3 resources to document current config, (3) Split inline S3 configuration to separate resources while still on 4.x, (4) Upgrade to 5.x, (5) Run plan to verify no unexpected changes. The S3 migration guide: https://registry.terraform.io/providers/hashicorp/aws/latest/docs/guides/version-5-upgrade",
            "min_required_provider": "5.0.0",
            "notes": "Budget significant time for this migration. Large codebases may need multiple PRs. The S3 changes alone can take days for complex setups."
        },
        {
            "terraform_version": ">=1.5.0",
            "provider_version": "5.x → 6.x migration",
            "status": "breaking",
            "breaking_changes": [
                "Resource identity framework changes (internal tracking mechanism)",
                "Removed all resources and arguments deprecated in 5.x",
                "Some data source return types changed (list → set)",
                "Provider plugin protocol version bump",
                "Changes to default timeout values for some resources"
            ],
            "migration_notes": "Less impactful than 4.x → 5.x but still requires testing. Steps: (1) Resolve all deprecation warnings in 5.x first, (2) Upgrade to 6.0, (3) Run plan to verify, (4) Watch for resource identity issues with moved blocks and imports.",
            "min_required_provider": "6.0.0",
            "notes": "Comparatively smooth upgrade if you've already addressed 5.x deprecation warnings. The resource identity changes are mostly internal."
        },
        # ── OpenTofu compatibility note ───────────────────────────────
        {
            "terraform_version": "OpenTofu >=1.6.0",
            "provider_version": ">=5.0.0",
            "status": "compatible",
            "breaking_changes": [
                "OpenTofu uses MPL-licensed provider code — same functionality",
                "State encryption available in OpenTofu but not in Terraform",
                "Provider-defined functions may differ slightly"
            ],
            "migration_notes": "AWS provider works identically with OpenTofu. State files are compatible in both directions (TF ↔ OpenTofu) for versions up to 1.7. Migration: replace `terraform` binary with `tofu`. State is compatible.",
            "min_required_provider": "5.0.0",
            "notes": "OpenTofu maintains compatibility with the official AWS provider. State file format is compatible. This entry included because many teams evaluate both."
        }
    ]


def main() -> None:
    data = load_canon(FILENAME)

    data["_meta"] = make_meta(
        description="Terraform core and AWS provider version compatibility matrix. Captures breaking changes, deprecations, and required migration steps between versions.",
        source="terraform-aws-boid Canon — sourced from provider CHANGELOG, upgrade guides, and release notes",
    )
    data["_meta"]["schema"] = {
        "terraform_version": "Terraform core version range",
        "provider_version": "hashicorp/aws provider version range",
        "status": "compatible | deprecated | breaking",
        "breaking_changes": "List of breaking changes in this combination",
        "migration_notes": "Steps to migrate between versions",
        "min_required_provider": "Minimum provider version for this TF version"
    }

    data["compatibility"] = build_compatibility()

    path = save_canon(FILENAME, data)
    print(f"Wrote {len(data['compatibility'])} compatibility entries")
    print(f"Saved to {path}")


if __name__ == "__main__":
    main()
