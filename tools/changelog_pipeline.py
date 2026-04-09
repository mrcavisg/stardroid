#!/usr/bin/env python3
"""
Sky Map Changelog Pipeline
==========================
Generates release-note drafts from git commit history for four destinations:

  1. CHANGELOG.md       — Keep a Changelog format, prepended to the file
  2. github_release.md  — GitHub Markdown release notes (~1 000 char guideline)
  3. whatsnew_content.xml — Android resource with HTML markup (~300 chars)
  4. fastlane/          — Play Store changelogs per locale (strict 500-char limit)

Usage
-----
  python3 tools/changelog_pipeline.py <base-tag> [options]

Options
  --version VERSION     Release version label, e.g. "1.12.1" (default: derived from tag+1)
  --output-dir DIR      Where to write draft files (default: ./changelog-draft)
  --translate           Attempt machine translation via Google Translate public endpoint
  --no-translate        Skip translation (English only, default)
  --play-store-limit N  Max characters per Play Store locale file (default: 500)
  --github-limit N      Suggested max chars for GitHub release body (default: 1000)
  --whatsnew-limit N    Max chars for whatsnew_content.xml body (default: 300)
  --dry-run             Print to stdout instead of writing files

Languages translated when --translate is used:
  en (always), es, de, it, fr, pt, pl, ru, ja, ko, zh

Dependencies: Python 3.8+ stdlib only (subprocess, re, json, urllib, textwrap, argparse)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO = "sky-map-team/stardroid"

# Conventional-commit types that appear in user-facing changelogs
FEAT_TYPES = {"feat", "feature"}
FIX_TYPES = {"fix", "bugfix", "hotfix"}
PERF_TYPES = {"perf", "performance"}
BREAKING_MARKER = "!"  # type ends with ! or has "BREAKING CHANGE:" footer

# Types hidden from user-facing outputs (kept in full CHANGELOG.md under Chore)
INTERNAL_TYPES = {"chore", "ci", "build", "test", "refactor", "style", "docs"}

# Play Store locale directories → BCP-47 translation codes
LOCALE_MAP: dict[str, str] = {
    "en-US": "en",
    "es-419": "es",
    "de-DE": "de",
    "it-IT": "it",
    "fr-FR": "fr",
    "pt-PT": "pt",
    "pl-PL": "pl",
    "ru-RU": "ru",
    "ja-JP": "ja",
    "ko-KR": "ko",
    "zh-CN": "zh-CN",
}

# Day-mode colours used in the Play Store styled text (mirrors existing default.txt)
PS_COLOR = "#F67E81"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Commit:
    sha: str
    commit_type: str          # e.g. "feat", "fix"
    scope: Optional[str]      # e.g. "renderer"
    breaking: bool
    subject: str
    body: str
    pr_number: Optional[int]  # extracted from subject "(#123)"
    raw: str


@dataclass
class ChangeGroup:
    added: list[Commit] = field(default_factory=list)
    changed: list[Commit] = field(default_factory=list)
    fixed: list[Commit] = field(default_factory=list)
    performance: list[Commit] = field(default_factory=list)
    internal: list[Commit] = field(default_factory=list)
    breaking: list[Commit] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def git(*args: str, cwd: Optional[Path] = None) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True, text=True,
        cwd=cwd or Path.cwd(),
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)!r} failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


def resolve_tag(tag: str) -> str:
    """Make sure the tag exists locally."""
    try:
        git("rev-parse", "--verify", tag)
        return tag
    except RuntimeError:
        raise ValueError(f"Tag '{tag}' not found. Run `git fetch --tags` first.")


def get_log_since(base_tag: str) -> list[str]:
    """Return raw commit subjects + SHAs since *base_tag* up to HEAD."""
    fmt = "%H\x1F%s\x1F%b\x1E"
    raw = git("log", f"{base_tag}..HEAD", f"--format={fmt}", "--no-merges")
    records: list[str] = []
    for record in raw.split("\x1E"):
        record = record.strip()
        if record:
            records.append(record)
    return records


def tag_date(tag: str) -> str:
    try:
        raw = git("log", "-1", "--format=%ai", tag)
        return raw.split()[0]
    except Exception:
        return str(date.today())


def next_version_from_tag(tag: str) -> str:
    """Guess version string from tag, bumping patch: v1.12.0 → 1.12.1."""
    digits = re.findall(r"\d+", tag)
    if len(digits) >= 3:
        major, minor, patch = int(digits[0]), int(digits[1]), int(digits[2])
        return f"{major}.{minor}.{patch + 1}"
    if len(digits) == 2:
        return f"{digits[0]}.{digits[1]}.1"
    return f"{tag.lstrip('v')}-next"


# ---------------------------------------------------------------------------
# Conventional-commit parser
# ---------------------------------------------------------------------------

_CC_PATTERN = re.compile(
    r"^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s*(?P<subject>.+)$"
)
_PR_PATTERN = re.compile(r"\(#(?P<n>\d+)\)\s*$")
_BREAKING_FOOTER = re.compile(r"BREAKING[\s-]CHANGE:", re.MULTILINE)


def parse_commit(record: str) -> Optional[Commit]:
    parts = record.split("\x1F", 2)
    if len(parts) < 2:
        return None
    sha, subject = parts[0].strip(), parts[1].strip()
    body = parts[2].strip() if len(parts) == 3 else ""

    m = _CC_PATTERN.match(subject)
    if not m:
        # Non-conventional commit: classify as internal
        return Commit(
            sha=sha, commit_type="chore", scope=None, breaking=False,
            subject=subject, body=body, pr_number=None, raw=record,
        )

    ctype = m.group("type").lower()
    scope = m.group("scope")
    breaking = bool(m.group("breaking")) or bool(_BREAKING_FOOTER.search(body))
    clean_subject = m.group("subject").strip()

    pr_match = _PR_PATTERN.search(clean_subject)
    pr_number = int(pr_match.group("n")) if pr_match else None
    if pr_match:
        clean_subject = clean_subject[: pr_match.start()].strip()

    return Commit(
        sha=sha, commit_type=ctype, scope=scope, breaking=breaking,
        subject=clean_subject, body=body, pr_number=pr_number, raw=record,
    )


def classify(commits: list[Commit]) -> ChangeGroup:
    g = ChangeGroup()
    for c in commits:
        if c.breaking:
            g.breaking.append(c)
        elif c.commit_type in FEAT_TYPES:
            g.added.append(c)
        elif c.commit_type in FIX_TYPES:
            g.fixed.append(c)
        elif c.commit_type in PERF_TYPES:
            g.performance.append(c)
        elif c.commit_type in {"changed", "change"}:
            g.changed.append(c)
        else:
            g.internal.append(c)
    return g


def pr_link(commit: Commit) -> str:
    if commit.pr_number:
        return f" ([#{commit.pr_number}](https://github.com/{REPO}/pull/{commit.pr_number}))"
    return ""


# ---------------------------------------------------------------------------
# Output A: CHANGELOG.md (Keep a Changelog)
# ---------------------------------------------------------------------------

def render_changelog_entry(g: ChangeGroup, version: str, release_date: str) -> str:
    lines = [f"## [{version}] - {release_date}", ""]

    def section(title: str, items: list[Commit]) -> list[str]:
        if not items:
            return []
        out = [f"### {title}"]
        for c in items:
            scope_prefix = f"**{c.scope}:** " if c.scope else ""
            out.append(f"- {scope_prefix}{c.subject}{pr_link(c)}")
        out.append("")
        return out

    if g.breaking:
        lines += section("⚠ BREAKING CHANGES", g.breaking)
    lines += section("Added", g.added)
    lines += section("Changed", g.changed)
    lines += section("Fixed", g.fixed)
    lines += section("Performance", g.performance)

    all_internal = g.internal
    if all_internal:
        lines += section("Internal", all_internal)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Output B: GitHub Release notes
# ---------------------------------------------------------------------------

def render_github_release(g: ChangeGroup, version: str, limit: int) -> str:
    lines = [f"## What's New in {version}", ""]

    def add_section(emoji: str, title: str, items: list[Commit]) -> None:
        if not items:
            return
        lines.append(f"### {emoji} {title}")
        for c in items:
            scope_prefix = f"**{c.scope}:** " if c.scope else ""
            lines.append(f"- {scope_prefix}{c.subject}{pr_link(c)}")
        lines.append("")

    if g.breaking:
        add_section("🚨", "Breaking Changes", g.breaking)
    add_section("✨", "New Features", g.added)
    add_section("🔧", "Improvements", g.changed)
    add_section("🐛", "Bug Fixes", g.fixed)
    add_section("⚡", "Performance", g.performance)

    text = "\n".join(lines).rstrip()
    if len(text) > limit:
        text = text[:limit - 3] + "..."
    return text


# ---------------------------------------------------------------------------
# Output C: whatsnew_content.xml
# ---------------------------------------------------------------------------

def _fmt_xml_item(c: Commit) -> str:
    scope = f"{c.scope}: " if c.scope else ""
    return f"{scope}{c.subject}"


def render_whatsnew_xml(g: ChangeGroup, limit: int) -> str:
    """
    Builds the CDATA body for whatsnew_content.xml.
    Uses <h2> headings followed by a short paragraph, mirroring the existing style.
    """
    parts: list[str] = []

    # Group feats by scope for cleaner presentation
    if g.breaking:
        subjects = "; ".join(_fmt_xml_item(c) for c in g.breaking[:2])
        parts.append(f"<h2>Breaking Changes</h2>\n    {subjects}.")

    for c in g.added[:4]:
        title = c.scope.title() if c.scope else c.subject[:30]
        body_text = c.subject if not c.scope else f"{c.subject}."
        parts.append(f"<h2>{title}</h2>\n    {body_text}")

    if g.fixed:
        fixed_items = "; ".join(_fmt_xml_item(c) for c in g.fixed[:3])
        parts.append(f"<h2>Bug Fixes</h2>\n    {fixed_items}.")

    cdata_body = "\n\n".join(parts)

    # Enforce character limit on CDATA body
    if len(cdata_body) > limit:
        cdata_body = cdata_body[:limit - 3] + "..."

    return f"""<?xml version="1.0" encoding="utf-8"?>
<resources>
    <!-- Actual whats new content which changes from release to release. Please do not change the &lt; and &gt; markup -->
    <string name="whats_new_content" translation_description="HTML content listing new features in this release, shown in the What's new dialog and appended to the Help screen. Please do not change the &lt; and &gt; markup.">
<![CDATA[
{cdata_body}
]]>
    </string>
</resources>"""


# ---------------------------------------------------------------------------
# Output D: Play Store changelogs (styled text, 500 char limit per locale)
# ---------------------------------------------------------------------------

def render_play_store(g: ChangeGroup, limit: int) -> str:
    """
    Returns Play Store text matching the existing fastlane default.txt style.
    Uses <b><font color="..."> headings.  Must stay under *limit* characters.
    """
    sections: list[str] = []

    def make_section(label: str, items: list[Commit], max_items: int = 3) -> str:
        if not items:
            return ""
        heading = f'<b><font color="{PS_COLOR}">{label}</font></b>'
        bullets = []
        for c in items[:max_items]:
            scope = f"{c.scope}: " if c.scope else ""
            bullets.append(f"  {scope}{c.subject}.")
        return heading + "\n" + "\n".join(bullets)

    new_items = g.breaking + g.added
    if new_items:
        sections.append(make_section("New", new_items))
    if g.changed or g.performance:
        sections.append(make_section("Changed", g.changed + g.performance))
    if g.fixed:
        sections.append(make_section("Fixed", g.fixed))

    text = "\n".join(s for s in sections if s)

    # Trim to fit within limit
    if len(text) > limit:
        # Try reducing items iteratively
        for max_items in range(2, 0, -1):
            sections = []
            new_items = g.breaking + g.added
            if new_items:
                sections.append(make_section("New", new_items[:max_items]))
            if g.fixed:
                sections.append(make_section("Fixed", g.fixed[:max_items]))
            text = "\n".join(s for s in sections if s)
            if len(text) <= limit:
                break
        if len(text) > limit:
            text = text[:limit - 3] + "..."

    return text


# ---------------------------------------------------------------------------
# Translation (optional, stdlib urllib only)
# ---------------------------------------------------------------------------

def translate_text(text: str, target_lang: str) -> str:
    """
    Uses the public Google Translate web endpoint (no API key).
    Falls back to original text on any error.
    """
    if target_lang == "en":
        return text
    try:
        params = urllib.parse.urlencode({
            "client": "gtx",
            "sl": "en",
            "tl": target_lang,
            "dt": "t",
            "q": text,
        })
        url = f"https://translate.googleapis.com/translate_a/single?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        # data[0] is a list of [translated_chunk, original_chunk, ...]
        translated = "".join(chunk[0] for chunk in data[0] if chunk[0])
        return translated
    except Exception as exc:
        print(f"  [warn] Translation to {target_lang} failed: {exc}", file=sys.stderr)
        return text


# ---------------------------------------------------------------------------
# File writers
# ---------------------------------------------------------------------------

def write_or_print(path: Path, content: str, dry_run: bool) -> None:
    if dry_run:
        print(f"\n{'=' * 60}")
        print(f"FILE: {path}")
        print('=' * 60)
        print(content)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"  wrote {path}  ({len(content)} chars)")


def prepend_changelog_md(changelog_path: Path, entry: str, dry_run: bool) -> None:
    if dry_run:
        print(f"\n{'=' * 60}")
        print(f"FILE: {changelog_path}  [PREPEND]")
        print('=' * 60)
        print(entry)
        return
    existing = ""
    if changelog_path.exists():
        existing = changelog_path.read_text(encoding="utf-8")
    # Insert after the header block (lines starting with #, All notable...)
    header_end = 0
    lines = existing.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("## "):
            header_end = i
            break
    header = "".join(lines[:header_end])
    body = "".join(lines[header_end:])
    new_content = header + entry + "\n\n" + body if body else header + entry + "\n"
    changelog_path.write_text(new_content, encoding="utf-8")
    print(f"  prepended entry to {changelog_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Sky Map Changelog Pipeline — generate release-note drafts from git commits",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("base_tag", help="Git tag to use as the base (e.g. v1.12.0)")
    p.add_argument("--version", help="Version label for the new release (e.g. 1.12.1)")
    p.add_argument("--output-dir", default="changelog-draft", metavar="DIR",
                   help="Directory for draft output files (default: ./changelog-draft)")
    p.add_argument("--translate", dest="translate", action="store_true", default=False,
                   help="Machine-translate Play Store text to configured languages")
    p.add_argument("--no-translate", dest="translate", action="store_false")
    p.add_argument("--play-store-limit", type=int, default=500, metavar="N",
                   help="Max chars per Play Store locale file (default: 500)")
    p.add_argument("--github-limit", type=int, default=1000, metavar="N",
                   help="Suggested max chars for GitHub release body (default: 1000)")
    p.add_argument("--whatsnew-limit", type=int, default=300, metavar="N",
                   help="Max chars for whatsnew CDATA body (default: 300)")
    p.add_argument("--dry-run", action="store_true",
                   help="Print generated content to stdout; do not write files")
    p.add_argument("--write-changelog", action="store_true",
                   help="Prepend the new entry to the top-level CHANGELOG.md (human review recommended first)")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    print(f"Sky Map Changelog Pipeline")
    print(f"  base tag   : {args.base_tag}")

    # Validate tag
    resolve_tag(args.base_tag)

    version = args.version or next_version_from_tag(args.base_tag)
    release_date = str(date.today())
    print(f"  version    : {version}")
    print(f"  date       : {release_date}")

    # Parse commits
    print("\nParsing commits...")
    raw_records = get_log_since(args.base_tag)
    commits: list[Commit] = []
    for rec in raw_records:
        c = parse_commit(rec)
        if c:
            commits.append(c)
    print(f"  {len(commits)} commits found")

    if not commits:
        print("No commits since the base tag. Exiting.")
        sys.exit(0)

    groups = classify(commits)
    print(f"  added={len(groups.added)}  fixed={len(groups.fixed)}  "
          f"changed={len(groups.changed)}  breaking={len(groups.breaking)}  "
          f"internal={len(groups.internal)}")

    out_dir = Path(args.output_dir)
    print(f"\nWriting drafts to {out_dir}/")

    # --- Output A: CHANGELOG.md entry ---
    print("\n[A] CHANGELOG.md entry")
    changelog_entry = render_changelog_entry(groups, version, release_date)
    write_or_print(out_dir / "CHANGELOG_entry.md", changelog_entry, args.dry_run)

    if args.write_changelog and not args.dry_run:
        changelog_path = Path("CHANGELOG.md")
        prepend_changelog_md(changelog_path, changelog_entry, args.dry_run)

    # --- Output B: GitHub Release notes ---
    print("\n[B] GitHub Release notes")
    gh_body = render_github_release(groups, version, args.github_limit)
    write_or_print(out_dir / "github_release.md", gh_body, args.dry_run)
    print(f"  length: {len(gh_body)}/{args.github_limit} chars")

    # --- Output C: whatsnew_content.xml ---
    print("\n[C] whatsnew_content.xml")
    wn_xml = render_whatsnew_xml(groups, args.whatsnew_limit)
    write_or_print(out_dir / "whatsnew_content.xml", wn_xml, args.dry_run)

    # --- Output D: Play Store per locale ---
    print("\n[D] Play Store changelogs")
    ps_en = render_play_store(groups, args.play_store_limit)
    print(f"  en-US: {len(ps_en)}/{args.play_store_limit} chars")

    locale_texts: dict[str, str] = {"en-US": ps_en}

    if args.translate:
        print("  Translating...")
        for locale, lang_code in LOCALE_MAP.items():
            if locale == "en-US":
                continue
            translated = translate_text(ps_en, lang_code)
            locale_texts[locale] = translated
            char_count = len(translated)
            status = "OK" if char_count <= args.play_store_limit else "⚠ OVER LIMIT"
            print(f"  {locale}: {char_count}/{args.play_store_limit} chars  {status}")
    else:
        print("  Skipping translation (pass --translate to enable)")
        print("  Only en-US will be written; copy and translate for other locales.")

    for locale, text in locale_texts.items():
        ps_path = out_dir / "play_store" / locale / "changelogs" / "default.txt"
        write_or_print(ps_path, text, args.dry_run)

    # --- Summary ---
    print("\n" + "=" * 60)
    print("DRAFT COMPLETE — human review recommended before committing")
    print("=" * 60)
    if not args.dry_run:
        print(f"\nFiles written to: {out_dir.resolve()}/")
        print("\nNext steps:")
        print("  1. Review and edit the draft files")
        print(f"  2. Copy {out_dir}/whatsnew_content.xml → app/src/main/res/values/whatsnew_content.xml")
        print(f"  3. Copy {out_dir}/play_store/<locale>/changelogs/default.txt → fastlane/metadata/android/...")
        print(f"  4. Run:  python3 tools/changelog_pipeline.py {args.base_tag} --write-changelog  (to prepend CHANGELOG.md)")
        print("  5. Commit all files")
    print()


if __name__ == "__main__":
    main()
