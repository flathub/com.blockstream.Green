#!/usr/bin/env python3
"""Sync AppStream release notes from green_qt CHANGELOG.md into metainfo."""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_METAINFO = REPO_ROOT / "com.blockstream.Green.metainfo.xml"
CHANGELOG_URL_TEMPLATE = (
    "https://raw.githubusercontent.com/Blockstream/green_qt/{ref}/CHANGELOG.md"
)
RELEASE_URL_TEMPLATE = (
    "https://github.com/Blockstream/green_qt/releases/tag/release_{version}"
)

SECTION_RE = re.compile(r"^###\s+(.+?)\s*$")
VERSION_HEADER_RE = re.compile(
    r"^##\s+\[(?P<version>\d+\.\d+\.\d+)\]\s*(?:-\s*(?P<date>\d{4}-\d{2}-\d{2}))?\s*$"
)
RELEASE_VERSION_RE = re.compile(
    r'<release\b[^>]*\bversion="(?P<version>\d+\.\d+\.\d+)"'
)


def xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def changelog_has_version(changelog: str, version: str) -> bool:
    for line in changelog.splitlines():
        match = VERSION_HEADER_RE.match(line)
        if match and match.group("version") == version:
            return True
    return False


def fetch_changelog(version: str) -> str:
    refs = (f"release_{version}", "master", "main")
    last_error: Exception | None = None
    for ref in refs:
        url = CHANGELOG_URL_TEMPLATE.format(ref=ref)
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                text = response.read().decode("utf-8")
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            last_error = exc
            continue

        if changelog_has_version(text, version):
            return text
        last_error = RuntimeError(f"{ref} has no ## [{version}] section")

    raise RuntimeError(f"Failed to fetch CHANGELOG.md for {version}: {last_error}")


def parse_changelog_section(changelog: str, version: str) -> tuple[str | None, dict[str, list[str]]]:
    lines = changelog.splitlines()
    date: str | None = None
    sections: dict[str, list[str]] = {}
    current_section: str | None = None
    in_target = False

    for line in lines:
        header = VERSION_HEADER_RE.match(line)
        if header:
            if in_target:
                break
            if header.group("version") == version:
                in_target = True
                date = header.group("date")
                current_section = None
            continue

        if not in_target:
            continue

        section = SECTION_RE.match(line)
        if section:
            current_section = section.group(1).strip()
            sections.setdefault(current_section, [])
            continue

        if line.startswith("## "):
            break

        stripped = line.strip()
        if stripped.startswith("- "):
            if current_section is None:
                current_section = "Changed"
                sections.setdefault(current_section, [])
            sections[current_section].append(stripped[2:].strip())

    if not in_target:
        raise RuntimeError(f"Version {version} not found in CHANGELOG.md")

    return date, {name: items for name, items in sections.items() if items}


def render_release_xml(
    version: str,
    date: str,
    sections: dict[str, list[str]],
    *,
    include_details_url: bool = True,
) -> str:
    parts = [f'\t  <release version="{xml_escape(version)}" date="{xml_escape(date)}">']
    if include_details_url:
        url = RELEASE_URL_TEMPLATE.format(version=version)
        parts.append(f'\t    <url type="details">{xml_escape(url)}</url>')
    parts.append("\t    <description>")
    for section_name, items in sections.items():
        parts.append(f"        <p>{xml_escape(section_name)}</p>")
        parts.append("        <ul>")
        for item in items:
            parts.append(f"          <li>{xml_escape(item)}</li>")
        parts.append("        </ul>")
    parts.append("       </description>")
    parts.append("\t  </release>")
    return "\n".join(parts)


def detect_version_from_metainfo(metainfo: str) -> str:
    match = RELEASE_VERSION_RE.search(metainfo)
    if not match:
        raise RuntimeError("Could not find a <release version=...> in metainfo")
    return match.group("version")


def upsert_release(metainfo: str, release_xml: str, version: str) -> str:
    # Match only this release block; do not consume following siblings' indentation.
    release_pattern = re.compile(
        rf"[ \t]*<release\b[^>]*\bversion=\"{re.escape(version)}\"[^>]*>.*?</release>[ \t]*\n?",
        re.DOTALL,
    )
    if release_pattern.search(metainfo):
        return release_pattern.sub(release_xml + "\n", metainfo, count=1)

    releases_open = re.search(r"<releases>\n?", metainfo)
    if not releases_open:
        raise RuntimeError("Could not find <releases> in metainfo")

    insert_at = releases_open.end()
    return metainfo[:insert_at] + release_xml + "\n" + metainfo[insert_at:]


def sync_metainfo(
    metainfo_path: Path,
    *,
    version: str | None = None,
    changelog_path: Path | None = None,
    dry_run: bool = False,
) -> str:
    metainfo = metainfo_path.read_text(encoding="utf-8")
    target_version = version or detect_version_from_metainfo(metainfo)

    if changelog_path is not None:
        changelog = changelog_path.read_text(encoding="utf-8")
    else:
        changelog = fetch_changelog(target_version)

    date, sections = parse_changelog_section(changelog, target_version)
    if not date:
        # Prefer an existing date on the matching release if changelog omitted it.
        existing = re.search(
            rf'<release\b[^>]*\bversion="{re.escape(target_version)}"[^>]*\bdate="([^"]+)"',
            metainfo,
        )
        date = existing.group(1) if existing else None
    if not date:
        raise RuntimeError(f"No release date found for {target_version}")
    if not sections:
        raise RuntimeError(f"No changelog bullets found for {target_version}")

    release_xml = render_release_xml(target_version, date, sections)
    updated = upsert_release(metainfo, release_xml, target_version)

    if updated != metainfo and not dry_run:
        metainfo_path.write_text(updated, encoding="utf-8")

    return target_version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metainfo",
        type=Path,
        default=DEFAULT_METAINFO,
        help="Path to AppStream metainfo XML",
    )
    parser.add_argument(
        "--version",
        help="Version to sync (default: newest <release> in metainfo)",
    )
    parser.add_argument(
        "--changelog",
        type=Path,
        help="Local CHANGELOG.md path (default: fetch from green_qt)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and render, but do not write metainfo",
    )
    args = parser.parse_args(argv)

    try:
        version = sync_metainfo(
            args.metainfo,
            version=args.version,
            changelog_path=args.changelog,
            dry_run=args.dry_run,
        )
    except Exception as exc:  # noqa: BLE001 - CLI surface
        print(f"error: {exc}", file=sys.stderr)
        return 1

    action = "checked" if args.dry_run else "updated"
    print(f"{action} release notes for {version} in {args.metainfo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
