from scripts.sync_md_v2 import (
    apply_intelligent,
    inject_frontmatter,
    pulse,
    snapshot,
)

# Mock truth for testing
MOCK_TRUTH = {
    "test_counts": {"unit": 100, "schema": 50},
    "total_tests": 150,
    "pages_count": 20,
    "updated_at": "2026-07-05T00:00:00Z",
}

def test_inject_frontmatter(tmp_path):
    """Verify that files without frontmatter get the default regime."""
    doc = tmp_path / "test_doc.md"
    doc.write_text("# Title\nContent here", encoding="utf-8")

    # Since inject_frontmatter takes targets as a list of Path
    inject_frontmatter([doc])

    content = doc.read_text(encoding="utf-8")
    assert "---" in content
    assert "doc_type: snapshot" in content
    assert "current_version: 0.0.0" in content
    assert "# Title" in content

def test_pulse_ok(tmp_path):
    """Verify pulse returns False (no stale) when truth matches."""
    doc = tmp_path / "ok_doc.md"
    # Frontmatter matching MOCK_TRUTH
    content = (
        "---\n"
        "doc_type: snapshot\n"
        "truth_at:\n"
        "  tests_total: 150\n"
        "  pages_count: 20\n"
        "---\n"
        "# Title\nContent"
    )
    doc.write_text(content, encoding="utf-8")

    # pulse returns True if any are STALE. So for OK, it should be False.
    is_stale = pulse([doc], MOCK_TRUTH)
    assert is_stale is False

def test_pulse_stale(tmp_path):
    """Verify pulse returns True when truth diverges."""
    doc = tmp_path / "stale_doc.md"
    # Divergent truth
    content = (
        "---\n"
        "doc_type: snapshot\n"
        "truth_at:\n"
        "  tests_total: 100\n" # real is 150
        "  pages_count: 20\n"
        "---\n"
        "# Title\nContent"
    )
    doc.write_text(content, encoding="utf-8")

    is_stale = pulse([doc], MOCK_TRUTH)
    assert is_stale is True

def test_snapshot(tmp_path, monkeypatch):
    """Verify that snapshots are created in the correct directory."""
    # Mock _ROOT to use tmp_path
    import scripts.sync_md_v2
    monkeypatch.setattr(scripts.sync_md_v2, "_ROOT", tmp_path)

    doc = tmp_path / "raio-x.md"
    doc.write_text("# Raio X\nContent", encoding="utf-8")

    snapshot("0.2.5", [doc])

    # Check if file exists in docs/archive/releases/
    # Path: tmp_path / docs / archive / releases / YYYY-MM-DD-v0.2.5-raio-x.md
    release_dir = tmp_path / "docs" / "archive" / "releases"
    assert release_dir.exists()

    snapshots = list(release_dir.glob("*.md"))
    assert len(snapshots) == 1
    assert "v0.2.5-raio-x.md" in snapshots[0].name

def test_apply_intelligent_update(tmp_path, monkeypatch):
    """Verify that numbers are updated with the (era X) marker."""
    import scripts.sync_md_v2
    monkeypatch.setattr(scripts.sync_md_v2, "_ROOT", tmp_path)

    doc = tmp_path / "live_doc.md"
    # Current truth in doc: 100 tests, 10 pages
    content = (
        "---\n"
        "doc_type: snapshot\n"
        "truth_at:\n"
        "  tests_total: 100\n"
        "  pages_count: 10\n"
        "---\n"
        "# Title\nTotal: 100 tests. Pages: 10 pages."
    )
    doc.write_text(content, encoding="utf-8")

    # Apply truth (150 tests, 20 pages)
    apply_intelligent(doc, MOCK_TRUTH, dry_run=False)

    new_content = doc.read_text(encoding="utf-8")
    assert "150 tests (era 100)" in new_content
    assert "20 pages (era 10)" in new_content
    assert "tests_total: 150" in new_content
    assert "pages_count: 20" in new_content

def test_apply_intelligent_no_change(tmp_path, monkeypatch):
    """Verify that apply returns False if truth already matches."""
    import scripts.sync_md_v2
    monkeypatch.setattr(scripts.sync_md_v2, "_ROOT", tmp_path)

    doc = tmp_path / "fixed_doc.md"
    content = (
        "---\n"
        "doc_type: snapshot\n"
        "truth_at:\n"
        "  tests_total: 150\n"
        "  pages_count: 20\n"
        "---\n"
        "# Title\n150 tests. 20 pages."
    )
    doc.write_text(content, encoding="utf-8")

    changed = apply_intelligent(doc, MOCK_TRUTH, dry_run=False)
    assert changed is False
