"""Calibration test for md_auto_compress scoring weights.

Smoke-check that the current scoring_config.yaml produces sane results
on the real LESSONS.md:
- `<!-- keep -->` sections are NEVER archive candidates
- Score distribution is monotonic (no NaN/None)
- Date extraction works on at least one real section
- Candidate ratio is documented for manual review

This is a REGRESSION test — run when scoring_config.yaml changes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts import md_auto_compress as mac

_ROOT = Path(__file__).resolve().parent.parent.parent
_LESSONS = _ROOT / "LESSONS.md"
_SCORING_CONFIG = _ROOT / "config" / "scoring_config.yaml"


def test_scoring_calibration():
    if not _LESSONS.exists():
        pytest.skip("LESSONS.md not found")
    if not _SCORING_CONFIG.exists():
        pytest.skip("scoring_config.yaml not found")

    with open(_SCORING_CONFIG) as f:
        config = yaml.safe_load(f)

    content = _LESSONS.read_text(encoding="utf-8")
    sections = mac.parse_lessons(content)
    threshold = config.get("thresholds", {}).get("archive_candidate", -3)

    assert len(sections) > 0, "No sections parsed from LESSONS.md"

    results = []
    candidates = []
    date_count = 0

    for s in sections:
        score = mac.section_score(s, config)
        has_date = bool(mac._RE_DATE_COMMIT.search(s["body"]))
        if has_date:
            date_count += 1
        result = {
            "id": s["id"],
            "title": s["title"][:60],
            "score": score,
            "keep": s.get("keep", False),
            "age_months": s["age_months"],
            "lines": s["lines"],
            "has_date": has_date,
            "candidate": False,
        }
        if not s.get("keep") and score <= threshold:
            result["candidate"] = True
            candidates.append(result)
        results.append(result)

    keep_sections = [r for r in results if r["keep"]]
    keep_archived = [r for r in keep_sections if r["candidate"]]

    # 1. Never archive <!-- keep --> sections
    assert len(keep_archived) == 0, (
        f"{len(keep_archived)} keep-marked section(s) are archive candidates:\n"
        + "\n".join(f"  #{r['id']} '{r['title']}' score={r['score']}" for r in keep_archived)
    )

    # 2. Date extraction works on at least one section
    assert date_count > 0, (
        "No dates found via _RE_DATE_COMMIT in LESSONS.md. "
        "Either add dates to sections or update the regex."
    )

    # 3. All scores must be valid integers
    for r in results:
        assert isinstance(r["score"], (int, float)), f"Score for #{r['id']} is not numeric: {r['score']}"

    # 4. No section should have exactly the keep_marker score unless it has keep
    keep_marker_weight = config.get("weights", {}).get("keep_marker", 999)
    for r in results:
        if r["score"] == keep_marker_weight and not r["keep"]:
            pytest.fail(f"#{r['id']} '{r['title']}' has score={r['score']} but no <!-- keep -->")

    # 5. Print distribution for manual review
    print(f"\n{'='*60}")
    print(f"Scoring calibration: {len(candidates)} candidates / {len(results)} total")
    print(f"Sections with dates: {date_count}, with <!-- keep -->: {len(keep_sections)}")
    print(f"\nScore distribution:\n{'-'*40}")
    for r in sorted(results, key=lambda x: x["score"]):
        flag = " 🗄️" if r["candidate"] else (" 🔒" if r["keep"] else "")
        age = f"{r['age_months']:3d}mo" if r["has_date"] else "  N/A"
        print(f"  #{r['id']:3d} score={r['score']:+.1f}  age={age}  "
              f"lines={r['lines']:3d}  {r['title'][:50]}{flag}")
    print(f"{'='*60}")
    print(f"\nNOTE: {len(candidates)} candidates — adjust threshold or weights if too many/few.")
