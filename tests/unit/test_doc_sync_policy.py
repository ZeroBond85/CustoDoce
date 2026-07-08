"""
Tests for scripts/doc_sync_policy.py — single source of truth for per-doc update rules.

Verifica que cada documento do inventário (LIVE, TIMESTAMP, IMMUTABLE, AUTO,
SNAPSHOT_*, TIMESTAMP_PROTECTED) é corretamente classificado pela função
`policy_for()`. Falha aqui indica que o sync_docs.py está sincronizando docs
com a política errada.
"""

from __future__ import annotations

from scripts.doc_sync_policy import DocPolicy, policy_for


def _p(rel: str) -> str:
    return rel  # alias curto


class TestPolicyAdrImmutable:
    def test_001_architecture_is_immutable(self):
        assert policy_for(_p("docs/adr/001-architecture.md")) == DocPolicy.IMMUTABLE

    def test_002_matcher_is_immutable(self):
        assert policy_for(_p("docs/adr/002-matcher-strategy.md")) == DocPolicy.IMMUTABLE

    def test_003_tier_is_immutable(self):
        assert policy_for(_p("docs/adr/003-tier-strategy.md")) == DocPolicy.IMMUTABLE

    def test_004_db_design_is_immutable(self):
        assert policy_for(_p("docs/adr/004-db-design.md")) == DocPolicy.IMMUTABLE

    def test_005_free_tier_is_immutable(self):
        assert policy_for(_p("docs/adr/005-free-tier-limits.md")) == DocPolicy.IMMUTABLE


class TestPolicyAuto:
    def test_skills_md_is_auto(self):
        assert policy_for(_p("docs/skills.md")) == DocPolicy.AUTO_GENERATED

    def test_api_alert_service_is_auto(self):
        assert policy_for(_p("docs/api/alert_service.md")) == DocPolicy.AUTO_GENERATED

    def test_api_auth_is_auto(self):
        assert policy_for(_p("docs/api/auth.md")) == DocPolicy.AUTO_GENERATED

    def test_api_nested_path_is_auto(self):
        assert policy_for(_p("docs/api/types.md")) == DocPolicy.AUTO_GENERATED


class TestPolicyLive:
    def test_agents_md_is_live(self):
        assert policy_for(_p("AGENTS.md")) == DocPolicy.LIVE

    def test_readme_is_live(self):
        assert policy_for(_p("README.md")) == DocPolicy.LIVE

    def test_regras_is_live(self):
        assert policy_for(_p("REGRAS.md")) == DocPolicy.LIVE

    def test_lessons_is_live(self):
        assert policy_for(_p("LESSONS.md")) == DocPolicy.LIVE

    def test_changelog_is_live(self):
        assert policy_for(_p("docs/changelog.md")) == DocPolicy.LIVE


class TestPolicyTimestamp:
    def test_architecture(self):
        assert policy_for(_p("docs/architecture.md")) == DocPolicy.TIMESTAMP

    def test_troubleshooting(self):
        assert policy_for(_p("docs/troubleshooting.md")) == DocPolicy.TIMESTAMP

    def test_security(self):
        assert policy_for(_p("docs/security.md")) == DocPolicy.TIMESTAMP

    def test_contributing(self):
        assert policy_for(_p("docs/contributing.md")) == DocPolicy.TIMESTAMP

    def test_deployment(self):
        assert policy_for(_p("docs/deployment.md")) == DocPolicy.TIMESTAMP

    def test_deployment_staging(self):
        assert policy_for(_p("docs/deployment-staging.md")) == DocPolicy.TIMESTAMP

    def test_migration_guide(self):
        assert policy_for(_p("docs/migration-guide.md")) == DocPolicy.TIMESTAMP

    def test_tests_readme(self):
        assert policy_for(_p("tests/README.md")) == DocPolicy.TIMESTAMP


class TestPolicyTimestampProtected:
    def test_rollback_prod_is_protected(self):
        assert policy_for(_p("docs/ROLLBACK_PROD.md")) == DocPolicy.TIMESTAMP_PROTECTED
