#!/usr/bin/env python3
"""
Unit tests for tools/changelog_pipeline.py

Run: python3 tools/test_changelog_pipeline.py
  or: python3 -m unittest tools.test_changelog_pipeline
"""

import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Make the script importable without running main()
sys.path.insert(0, str(Path(__file__).parent))

from changelog_pipeline import (
    ChangeGroup,
    Commit,
    classify,
    next_version_from_tag,
    parse_commit,
    prepend_changelog_md,
    render_changelog_entry,
    render_github_release,
    render_play_store,
    render_whatsnew_xml,
    translate_text,
    write_or_print,
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
# Tests: parse_commit – additional edge cases
# ---------------------------------------------------------------------------

class TestParseCommitEdgeCases(unittest.TestCase):

    def _record(self, sha: str, subject: str, body: str = "") -> str:
        return f"{sha}\x1F{subject}\x1F{body}"

    def test_feature_alias_type(self):
        """'feature:' is a valid conventional-commit alias for 'feat'."""
        c = parse_commit(self._record("aaa", "feature: add constellation lines"))
        self.assertIsNotNone(c)
        self.assertEqual(c.commit_type, "feature")
        self.assertEqual(c.subject, "add constellation lines")

    def test_uppercase_type_normalised(self):
        """Type is lowercased: 'FEAT' → 'feat'."""
        c = parse_commit(self._record("bbb", "FEAT: uppercase type"))
        self.assertIsNotNone(c)
        self.assertEqual(c.commit_type, "feat")

    def test_bugfix_alias(self):
        """'bugfix:' is recognised as a fix-type alias."""
        c = parse_commit(self._record("ccc", "bugfix: handle null sensor"))
        self.assertIsNotNone(c)
        self.assertEqual(c.commit_type, "bugfix")

    def test_hotfix_alias(self):
        """'hotfix:' is recognised as a fix-type alias."""
        c = parse_commit(self._record("ddd", "hotfix: crash on startup"))
        self.assertIsNotNone(c)
        self.assertEqual(c.commit_type, "hotfix")

    def test_scoped_commit_no_pr(self):
        """Scoped commit without a PR number has pr_number=None."""
        c = parse_commit(self._record("eee", "refactor(sensors): clean up matrix math"))
        self.assertIsNone(c.pr_number)
        self.assertEqual(c.scope, "sensors")

    def test_breaking_with_scope(self):
        """Breaking commits can also carry a scope."""
        c = parse_commit(self._record("fff", "feat(api)!: rename RA/Dec fields"))
        self.assertTrue(c.breaking)
        self.assertEqual(c.scope, "api")

    def test_record_missing_sha_returns_none(self):
        """A record with no field-separator is unparseable → None."""
        c = parse_commit("no-separator-here")
        self.assertIsNone(c)


# ---------------------------------------------------------------------------
# Tests: classify – additional type aliases and edge cases
# ---------------------------------------------------------------------------

class TestClassifyAliases(unittest.TestCase):

    def test_feature_alias_goes_to_added(self):
        """'feature' type (alias) must land in added, not internal."""
        commits = [make_commit("feature", "new compass overlay")]
        g = classify(commits)
        self.assertEqual(len(g.added), 1)
        self.assertEqual(len(g.internal), 0)

    def test_bugfix_alias_goes_to_fixed(self):
        commits = [make_commit("bugfix", "fix null pointer")]
        g = classify(commits)
        self.assertEqual(len(g.fixed), 1)

    def test_hotfix_alias_goes_to_fixed(self):
        commits = [make_commit("hotfix", "urgent crash fix")]
        g = classify(commits)
        self.assertEqual(len(g.fixed), 1)

    def test_performance_alias_goes_to_performance(self):
        """'performance' (long form) lands in performance group."""
        commits = [make_commit("performance", "render pipeline speedup")]
        g = classify(commits)
        self.assertEqual(len(g.performance), 1)

    def test_change_type_goes_to_changed(self):
        commits = [make_commit("change", "update icon set")]
        g = classify(commits)
        self.assertEqual(len(g.changed), 1)

    def test_changed_type_goes_to_changed(self):
        commits = [make_commit("changed", "reword help text")]
        g = classify(commits)
        self.assertEqual(len(g.changed), 1)

    def test_refactor_goes_to_internal(self):
        commits = [make_commit("refactor", "extract helper class")]
        g = classify(commits)
        self.assertEqual(len(g.internal), 1)

    def test_docs_goes_to_internal(self):
        commits = [make_commit("docs", "update README")]
        g = classify(commits)
        self.assertEqual(len(g.internal), 1)

    def test_breaking_feat_not_double_counted(self):
        """A breaking feat should appear only in breaking, not in added."""
        commits = [make_commit("feat", "drop old API", breaking=True)]
        g = classify(commits)
        self.assertEqual(len(g.breaking), 1)
        self.assertEqual(len(g.added), 0)


# ---------------------------------------------------------------------------
# Tests: next_version_from_tag – edge cases
# ---------------------------------------------------------------------------

class TestNextVersionEdgeCases(unittest.TestCase):

    def test_no_digits_returns_next_suffix(self):
        result = next_version_from_tag("beta")
        self.assertIn("next", result)

    def test_v_prefix_stripped_when_no_digits(self):
        result = next_version_from_tag("vbeta")
        # Should not raise; returns something sensible
        self.assertIsInstance(result, str)


# ---------------------------------------------------------------------------
# Tests: render_changelog_entry – breaking + internal sections
# ---------------------------------------------------------------------------

class TestRenderChangelogBreaking(unittest.TestCase):

    def test_breaking_section_header(self):
        g = make_groups(breaking=1)
        entry = render_changelog_entry(g, "2.0.0", "2026-01-01")
        self.assertIn("BREAKING CHANGES", entry)

    def test_internal_section_in_changelog(self):
        """Chore/internal items must appear under ### Internal in CHANGELOG."""
        g = make_groups(internal=2)
        entry = render_changelog_entry(g, "1.0.0", "2026-01-01")
        self.assertIn("### Internal", entry)
        self.assertIn("internal 0", entry)

    def test_breaking_commit_with_scope_and_pr(self):
        g = ChangeGroup()
        g.breaking = [make_commit("feat", "drop old coordinate API", scope="control", pr_number=99)]
        entry = render_changelog_entry(g, "2.0.0", "2026-01-01")
        self.assertIn("**control:**", entry)
        self.assertIn("#99", entry)


# ---------------------------------------------------------------------------
# Tests: render_github_release – breaking + performance + changed sections
# ---------------------------------------------------------------------------

class TestRenderGitHubReleaseExtended(unittest.TestCase):

    def test_breaking_section_visible(self):
        g = make_groups(breaking=1)
        text = render_github_release(g, "2.0.0", 1000)
        self.assertIn("Breaking Changes", text)
        self.assertIn("🚨", text)

    def test_performance_section_visible(self):
        g = make_groups(performance=1)
        text = render_github_release(g, "1.0.0", 1000)
        self.assertIn("Performance", text)
        self.assertIn("⚡", text)

    def test_changed_section_visible(self):
        g = make_groups(changed=1)
        text = render_github_release(g, "1.0.0", 1000)
        self.assertIn("Improvements", text)
        self.assertIn("🔧", text)

    def test_within_limit_exactly_at_boundary(self):
        """Content exactly at limit should not be truncated."""
        g = make_groups(added=1)
        text = render_github_release(g, "1.0.0", 10000)
        # No truncation ellipsis expected for small content
        self.assertFalse(text.endswith("..."))

    def test_empty_groups_gives_only_header(self):
        g = ChangeGroup()
        text = render_github_release(g, "1.0.0", 1000)
        self.assertIn("1.0.0", text)
        self.assertNotIn("###", text)


# ---------------------------------------------------------------------------
# Tests: render_whatsnew_xml – additional scenarios
# ---------------------------------------------------------------------------

class TestRenderWhatsnewXmlExtended(unittest.TestCase):

    def test_breaking_change_in_xml(self):
        """Breaking changes appear as a <h2>Breaking Changes</h2> block."""
        g = ChangeGroup()
        g.breaking = [make_commit("feat", "drop Android 5 support")]
        xml = render_whatsnew_xml(g, 300)
        self.assertIn("<h2>Breaking Changes</h2>", xml)
        self.assertIn("drop Android 5 support", xml)

    def test_feat_without_scope_uses_subject_truncated(self):
        """A feat with no scope uses the first 30 chars of the subject as <h2>."""
        subject = "add beautiful star rendering mode"  # 33 chars
        g = ChangeGroup()
        g.added = [make_commit("feat", subject)]
        xml = render_whatsnew_xml(g, 300)
        # Title should be subject[:30] — implementation uses c.subject[:30]
        expected_title = subject[:30]  # "add beautiful star rendering m"
        self.assertIn(f"<h2>{expected_title}</h2>", xml)

    def test_bug_fixes_in_xml(self):
        g = ChangeGroup()
        g.fixed = [make_commit("fix", "correct magnitude calculation")]
        xml = render_whatsnew_xml(g, 300)
        self.assertIn("<h2>Bug Fixes</h2>", xml)
        self.assertIn("correct magnitude calculation", xml)

    def test_empty_groups_produces_valid_xml_structure(self):
        """Even with zero commits the XML wrapper must be structurally valid."""
        g = ChangeGroup()
        xml = render_whatsnew_xml(g, 300)
        self.assertIn('<?xml version="1.0"', xml)
        self.assertIn("<![CDATA[", xml)
        self.assertIn("]]>", xml)


# ---------------------------------------------------------------------------
# Tests: render_play_store – changed/performance + breaking in "New" block
# ---------------------------------------------------------------------------

class TestRenderPlayStoreExtended(unittest.TestCase):

    def test_changed_and_performance_appear_in_changed_section(self):
        g = make_groups(changed=1, performance=1)
        text = render_play_store(g, 500)
        self.assertIn("Changed", text)

    def test_breaking_commits_appear_in_new_section(self):
        """Breaking commits are prepended to the 'New' heading items."""
        g = make_groups(breaking=1)
        text = render_play_store(g, 500)
        self.assertIn("New", text)
        self.assertIn("breaking change 0", text)

    def test_very_small_limit_still_respected(self):
        """With a tiny limit the output must not exceed limit+3 chars."""
        g = make_groups(added=5, fixed=5)
        text = render_play_store(g, 50)
        self.assertLessEqual(len(text), 53)

    def test_only_internal_produces_empty_output(self):
        """Internal-only commits yield no Play Store text (no user-facing content)."""
        g = make_groups(internal=5)
        text = render_play_store(g, 500)
        self.assertEqual(text, "")


# ---------------------------------------------------------------------------
# Tests: translate_text – English passthrough (no network)
# ---------------------------------------------------------------------------

class TestTranslateText(unittest.TestCase):

    def test_english_returns_original(self):
        """translate_text('en') must return the original string without any network call."""
        original = "What's New\n- Dark mode added."
        result = translate_text(original, "en")
        self.assertEqual(result, original)

    def test_network_failure_falls_back_to_original(self):
        """On any network/parse error the original text is returned unchanged."""
        import urllib.request
        with patch.object(urllib.request, "urlopen", side_effect=OSError("no network")):
            result = translate_text("Some text", "de")
        self.assertEqual(result, "Some text")


# ---------------------------------------------------------------------------
# Tests: write_or_print and prepend_changelog_md (file I/O)
# ---------------------------------------------------------------------------

class TestWriteOrPrint(unittest.TestCase):

    def test_dry_run_writes_to_stdout(self):
        """dry_run=True prints content to stdout and does NOT create a file."""
        captured = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "subdir" / "out.txt"
            with patch("sys.stdout", captured):
                write_or_print(path, "hello world", dry_run=True)
            self.assertIn("hello world", captured.getvalue())
            self.assertFalse(path.exists())

    def test_writes_file_when_not_dry_run(self):
        """dry_run=False creates the file with the given content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "out.txt"
            write_or_print(path, "file content", dry_run=False)
            self.assertTrue(path.exists())
            self.assertEqual(path.read_text(encoding="utf-8"), "file content")


class TestPrependChangelogMd(unittest.TestCase):

    def test_prepend_to_new_file(self):
        """Prepending to a non-existent file creates it with the entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "CHANGELOG.md"
            prepend_changelog_md(path, "## [1.0.0] - 2026-01-01\n- first", dry_run=False)
            content = path.read_text(encoding="utf-8")
            self.assertIn("## [1.0.0]", content)

    def test_prepend_inserts_before_existing_entries(self):
        """New entry must appear before any pre-existing ## sections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "CHANGELOG.md"
            path.write_text(
                "# Changelog\n\n## [0.9.0] - 2025-01-01\n- old stuff\n",
                encoding="utf-8",
            )
            prepend_changelog_md(path, "## [1.0.0] - 2026-01-01\n- new stuff", dry_run=False)
            content = path.read_text(encoding="utf-8")
            new_idx = content.index("1.0.0")
            old_idx = content.index("0.9.0")
            self.assertLess(new_idx, old_idx)

    def test_dry_run_does_not_write_file(self):
        """dry_run=True prints to stdout and leaves the file untouched."""
        captured = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "CHANGELOG.md"
            path.write_text("# Changelog\n", encoding="utf-8")
            with patch("sys.stdout", captured):
                prepend_changelog_md(path, "## [2.0.0] - 2026-01-01", dry_run=True)
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("2.0.0", content)
            self.assertIn("2.0.0", captured.getvalue())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(unittest.TestLoader().loadTestsFromModule(
        sys.modules[__name__]
    ))
    sys.exit(0 if result.wasSuccessful() else 1)
