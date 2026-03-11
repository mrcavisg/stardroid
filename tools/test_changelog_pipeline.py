#!/usr/bin/env python3
"""
Unit tests for tools/changelog_pipeline.py

Run: python3 tools/test_changelog_pipeline.py
  or: python3 -m unittest tools.test_changelog_pipeline
"""

import sys
import unittest
from pathlib import Path

# Make the script importable without running main()
sys.path.insert(0, str(Path(__file__).parent))

from changelog_pipeline import (
    ChangeGroup,
    Commit,
    classify,
    next_version_from_tag,
    parse_commit,
    render_changelog_entry,
    render_github_release,
    render_play_store,
    render_whatsnew_xml,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_commit(
    commit_type: str = "feat",
    subject: str = "add something",
    scope: str | None = None,
    breaking: bool = False,
    pr_number: int | None = None,
) -> Commit:
    return Commit(
        sha="abc1234",
        commit_type=commit_type,
        scope=scope,
        breaking=breaking,
        subject=subject,
        body="",
        pr_number=pr_number,
        raw="",
    )


def make_groups(
    added: int = 0,
    fixed: int = 0,
    changed: int = 0,
    breaking: int = 0,
    performance: int = 0,
    internal: int = 0,
) -> ChangeGroup:
    g = ChangeGroup()
    g.added = [make_commit("feat", f"new feature {i}", scope=None) for i in range(added)]
    g.fixed = [make_commit("fix", f"fix bug {i}") for i in range(fixed)]
    g.changed = [make_commit("changed", f"change thing {i}") for i in range(changed)]
    g.breaking = [make_commit("feat", f"breaking change {i}", breaking=True) for i in range(breaking)]
    g.performance = [make_commit("perf", f"speed up {i}") for i in range(performance)]
    g.internal = [make_commit("chore", f"internal {i}") for i in range(internal)]
    return g


# ---------------------------------------------------------------------------
# Tests: parse_commit
# ---------------------------------------------------------------------------

class TestParseCommit(unittest.TestCase):

    def _record(self, sha: str, subject: str, body: str = "") -> str:
        return f"{sha}\x1F{subject}\x1F{body}"

    def test_simple_feat(self):
        c = parse_commit(self._record("aaa", "feat: add star labels"))
        self.assertIsNotNone(c)
        self.assertEqual(c.commit_type, "feat")
        self.assertEqual(c.subject, "add star labels")
        self.assertFalse(c.breaking)
        self.assertIsNone(c.scope)

    def test_scoped_fix(self):
        c = parse_commit(self._record("bbb", "fix(renderer): correct star colors"))
        self.assertEqual(c.commit_type, "fix")
        self.assertEqual(c.scope, "renderer")
        self.assertEqual(c.subject, "correct star colors")

    def test_breaking_exclamation(self):
        c = parse_commit(self._record("ccc", "feat!: remove legacy sensor API"))
        self.assertTrue(c.breaking)
        self.assertEqual(c.subject, "remove legacy sensor API")

    def test_pr_number_extracted(self):
        c = parse_commit(self._record("ddd", "fix: crash on startup (#641)"))
        self.assertEqual(c.pr_number, 641)
        self.assertEqual(c.subject, "crash on startup")

    def test_non_conventional_becomes_chore(self):
        c = parse_commit(self._record("eee", "Some random commit message"))
        self.assertEqual(c.commit_type, "chore")
        self.assertEqual(c.subject, "Some random commit message")

    def test_breaking_footer(self):
        c = parse_commit(self._record("fff", "refactor: overhaul DI", "BREAKING CHANGE: module API changed"))
        self.assertTrue(c.breaking)

    def test_empty_record_returns_none(self):
        c = parse_commit("")
        self.assertIsNone(c)


# ---------------------------------------------------------------------------
# Tests: classify
# ---------------------------------------------------------------------------

class TestClassify(unittest.TestCase):

    def test_feat_goes_to_added(self):
        commits = [make_commit("feat", "add dark theme")]
        g = classify(commits)
        self.assertEqual(len(g.added), 1)
        self.assertEqual(len(g.fixed), 0)

    def test_fix_goes_to_fixed(self):
        commits = [make_commit("fix", "fix crash")]
        g = classify(commits)
        self.assertEqual(len(g.fixed), 1)

    def test_breaking_overrides_type(self):
        commits = [make_commit("feat", "remove API", breaking=True)]
        g = classify(commits)
        self.assertEqual(len(g.breaking), 1)
        self.assertEqual(len(g.added), 0)

    def test_perf_goes_to_performance(self):
        commits = [make_commit("perf", "speed up rendering")]
        g = classify(commits)
        self.assertEqual(len(g.performance), 1)

    def test_chore_goes_to_internal(self):
        commits = [make_commit("chore", "update deps")]
        g = classify(commits)
        self.assertEqual(len(g.internal), 1)

    def test_mixed_batch(self):
        commits = [
            make_commit("feat", "A"),
            make_commit("fix", "B"),
            make_commit("chore", "C"),
            make_commit("feat", "D", breaking=True),
        ]
        g = classify(commits)
        self.assertEqual(len(g.added), 1)
        self.assertEqual(len(g.fixed), 1)
        self.assertEqual(len(g.internal), 1)
        self.assertEqual(len(g.breaking), 1)


# ---------------------------------------------------------------------------
# Tests: next_version_from_tag
# ---------------------------------------------------------------------------

class TestNextVersion(unittest.TestCase):

    def test_bumps_patch(self):
        self.assertEqual(next_version_from_tag("v1.12.0"), "1.12.1")

    def test_bumps_patch_no_v(self):
        self.assertEqual(next_version_from_tag("1.11.5"), "1.11.6")

    def test_two_part_version(self):
        self.assertEqual(next_version_from_tag("v2.0"), "2.0.1")

    def test_large_numbers(self):
        self.assertEqual(next_version_from_tag("v10.20.99"), "10.20.100")


# ---------------------------------------------------------------------------
# Tests: render_changelog_entry
# ---------------------------------------------------------------------------

class TestRenderChangelog(unittest.TestCase):

    def test_contains_version_header(self):
        g = make_groups(added=1)
        entry = render_changelog_entry(g, "1.2.3", "2026-01-01")
        self.assertIn("## [1.2.3] - 2026-01-01", entry)

    def test_added_section_present(self):
        g = make_groups(added=2)
        entry = render_changelog_entry(g, "1.0.0", "2026-01-01")
        self.assertIn("### Added", entry)
        self.assertIn("new feature 0", entry)
        self.assertIn("new feature 1", entry)

    def test_fixed_section_present(self):
        g = make_groups(fixed=1)
        entry = render_changelog_entry(g, "1.0.0", "2026-01-01")
        self.assertIn("### Fixed", entry)

    def test_empty_sections_omitted(self):
        g = make_groups(added=1)  # no fixed, no changed
        entry = render_changelog_entry(g, "1.0.0", "2026-01-01")
        self.assertNotIn("### Fixed", entry)
        self.assertNotIn("### Changed", entry)

    def test_pr_link_included(self):
        g = ChangeGroup()
        g.added = [make_commit("feat", "cool feature", pr_number=42)]
        entry = render_changelog_entry(g, "1.0.0", "2026-01-01")
        self.assertIn("#42", entry)

    def test_scope_prefixed(self):
        g = ChangeGroup()
        g.fixed = [make_commit("fix", "crash fixed", scope="sensors")]
        entry = render_changelog_entry(g, "1.0.0", "2026-01-01")
        self.assertIn("**sensors:**", entry)


# ---------------------------------------------------------------------------
# Tests: render_github_release
# ---------------------------------------------------------------------------

class TestRenderGitHubRelease(unittest.TestCase):

    def test_contains_version(self):
        g = make_groups(added=1)
        text = render_github_release(g, "1.2.3", 1000)
        self.assertIn("1.2.3", text)

    def test_truncated_to_limit(self):
        g = make_groups(added=10, fixed=10)
        text = render_github_release(g, "1.0.0", 200)
        self.assertLessEqual(len(text), 203)  # 200 + "..."

    def test_no_internal_items(self):
        g = make_groups(internal=5)
        text = render_github_release(g, "1.0.0", 1000)
        self.assertNotIn("internal", text)


# ---------------------------------------------------------------------------
# Tests: render_whatsnew_xml
# ---------------------------------------------------------------------------

class TestRenderWhatsnewXml(unittest.TestCase):

    def test_valid_xml_wrapper(self):
        g = make_groups(added=1)
        xml = render_whatsnew_xml(g, 300)
        self.assertIn('<?xml version="1.0"', xml)
        self.assertIn('<resources>', xml)
        self.assertIn('whats_new_content', xml)
        self.assertIn('<![CDATA[', xml)
        self.assertIn(']]>', xml)

    def test_feat_appears_as_h2(self):
        g = ChangeGroup()
        g.added = [make_commit("feat", "night mode improvements", scope="nightmode")]
        xml = render_whatsnew_xml(g, 300)
        self.assertIn("<h2>Nightmode</h2>", xml)

    def test_cdata_within_limit(self):
        g = make_groups(added=5, fixed=3)
        xml = render_whatsnew_xml(g, 300)
        # Extract CDATA body
        start = xml.index("<![CDATA[") + len("<![CDATA[")
        end = xml.index("]]>")
        cdata = xml[start:end].strip()
        self.assertLessEqual(len(cdata), 303)  # 300 + "..."


# ---------------------------------------------------------------------------
# Tests: render_play_store
# ---------------------------------------------------------------------------

class TestRenderPlayStore(unittest.TestCase):

    def test_within_limit(self):
        g = make_groups(added=3, fixed=2)
        text = render_play_store(g, 500)
        self.assertLessEqual(len(text), 503)  # 500 + possible "..."

    def test_new_section_present(self):
        g = make_groups(added=2)
        text = render_play_store(g, 500)
        self.assertIn("New", text)

    def test_fixed_section_present(self):
        g = make_groups(fixed=2)
        text = render_play_store(g, 500)
        self.assertIn("Fixed", text)

    def test_empty_fixed_no_fixed_section(self):
        g = make_groups(added=1)
        text = render_play_store(g, 500)
        self.assertNotIn("Fixed", text)

    def test_uses_play_store_colors(self):
        g = make_groups(added=1)
        text = render_play_store(g, 500)
        self.assertIn("#F67E81", text)

    def test_strict_limit_enforced(self):
        # Many items that would exceed 500 chars
        g = make_groups(added=10, fixed=10)
        text = render_play_store(g, 500)
        self.assertLessEqual(len(text), 503)

    def test_empty_groups_returns_empty_string(self):
        g = ChangeGroup()
        text = render_play_store(g, 500)
        self.assertEqual(text, "")


# ---------------------------------------------------------------------------
# Integration: parse → classify → render
# ---------------------------------------------------------------------------

class TestEndToEnd(unittest.TestCase):

    RECORDS = [
        "sha1\x1Ffeat(ui): dark theme overhaul (#620)\x1F",
        "sha2\x1Ffix: crash when rotating device (#630)\x1F",
        "sha3\x1Fchore: update CI dependencies\x1F",
        "sha4\x1Fperf(renderer): reduce draw calls by 40%\x1F",
        "sha5\x1Ffeat!: remove support for Android 5 (#640)\x1FBREAKING CHANGE: minSdk bumped to 26",
    ]

    def setUp(self):
        self.commits = [c for r in self.RECORDS if (c := parse_commit(r))]
        self.groups = classify(self.commits)

    def test_commit_count(self):
        self.assertEqual(len(self.commits), 5)

    def test_breaking_classified(self):
        self.assertEqual(len(self.groups.breaking), 1)
        self.assertEqual(self.groups.breaking[0].pr_number, 640)

    def test_feat_classified_correctly(self):
        self.assertEqual(len(self.groups.added), 1)  # only non-breaking feat

    def test_chore_is_internal(self):
        self.assertEqual(len(self.groups.internal), 1)

    def test_full_changelog_entry(self):
        entry = render_changelog_entry(self.groups, "1.12.1", "2026-03-11")
        self.assertIn("## [1.12.1] - 2026-03-11", entry)
        self.assertIn("dark theme overhaul", entry)
        self.assertIn("crash when rotating device", entry)
        # Chores appear in the Internal section (developer-facing), not in Added/Fixed/Changed
        self.assertIn("### Internal", entry)
        self.assertIn("update CI", entry)  # chore visible under Internal heading
        # But chores must NOT appear under user-facing headings
        added_idx = entry.find("### Added")
        internal_idx = entry.find("### Internal")
        update_ci_idx = entry.find("update CI")
        self.assertGreater(update_ci_idx, internal_idx)  # "update CI" is after ### Internal
        if added_idx != -1:
            self.assertGreater(update_ci_idx, added_idx)  # "update CI" not in Added block

    def test_play_store_within_limit(self):
        text = render_play_store(self.groups, 500)
        self.assertLessEqual(len(text), 503)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(unittest.TestLoader().loadTestsFromModule(
        sys.modules[__name__]
    ))
    sys.exit(0 if result.wasSuccessful() else 1)
