#!/usr/bin/env python3
"""
sync_sf_skills.py: refresh the Salesforce skills bundled in backend/sf_skills/ from forcedotcom/sf-skills.

Used by .github/workflows/sync-sf-skills.yml (daily). Can also be run by hand:

    python scripts/sync_sf_skills.py            # update the bundled files if upstream changed
    python scripts/sync_sf_skills.py --check    # only report, change nothing (exit 0 either way)

What it does:
  1. Looks up the latest upstream release (GitHub "releases/latest") and the commit it points to.
     A release, not main: upstream sometimes pushes and then reverts on main between releases.
  2. Downloads, at that exact commit, only the files Avio already bundles: every file under
     backend/sf_skills/ except VERSION. LICENSE.txt comes from the upstream repo root, the rest from
     skills/<same relative path>. The list of paths comes from this repo, never from upstream, so
     upstream cannot make it write anywhere else. Nothing downloaded is executed.
  3. Compares them with line endings normalised to LF. If any differ, writes the new text (LF),
     updates VERSION, and reports changed=true. New skills and new files that an updated SKILL.md
     links to are listed in the report only; adding them is a manual decision.

Outputs (when GITHUB_OUTPUT is set): changed, tag, commit. A markdown summary for the pull request body
is written to the file named by --body (default: none).

Standard library only, so the workflow needs no pip install.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = os.environ.get("SF_SKILLS_REPO", "forcedotcom/sf-skills")
ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "backend" / "sf_skills"
MAX_BYTES = 1_000_000            # a skill file is a few KB to ~100 KB; anything bigger is suspicious
NOT_SYNCED = {"VERSION"}          # Avio's own file
FROM_REPO_ROOT = {"LICENSE.txt"}  # lives at the upstream repo root, not under skills/


def _get(url: str, accept: str = "application/vnd.github+json") -> bytes:
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "avio-skill-sync"})
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"{url}: larger than {MAX_BYTES} bytes, refusing")
    return data


def _api(path: str):
    return json.loads(_get(f"https://api.github.com/repos/{REPO}/{path}"))


def _norm(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def bundled_files() -> list[str]:
    """Relative POSIX paths of the files Avio bundles (the sync set)."""
    return sorted(
        p.relative_to(SKILLS_DIR).as_posix()
        for p in SKILLS_DIR.rglob("*")
        if p.is_file() and p.relative_to(SKILLS_DIR).as_posix() not in NOT_SYNCED
    )


def upstream_path(rel: str) -> str:
    return rel if rel in FROM_REPO_ROOT else f"skills/{rel}"


def fetch_upstream(commit: str, rel: str) -> str | None:
    """Text of rel at commit, or None if upstream no longer has it."""
    url = f"https://raw.githubusercontent.com/{REPO}/{commit}/{upstream_path(rel)}"
    try:
        raw = _get(url, accept="*/*")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return _norm(raw.decode("utf-8"))  # not UTF-8 text -> error, nothing is written


def linked_files(skill_md: str) -> set[str]:
    """Relative files a SKILL.md links to (markdown links), e.g. references/x.md, assets/y.cls."""
    out = set()
    for target in re.findall(r"\]\(([^)\s#]+)", skill_md):
        if "://" in target or target.startswith(("/", "mailto:")):
            continue
        target = target.removeprefix("./")
        if ".." not in target.split("/"):
            out.add(target)
    return out


def update_version_file(tag: str, commit: str, commit_date: str) -> None:
    path = SKILLS_DIR / "VERSION"
    today = _dt.date.today().isoformat()
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    new = {
        "source": f"https://github.com/{REPO}",
        "fetched": today,
        # first two words are read by get_skills_manifest() in backend/sf_skills.py: <short sha> <date>
        "upstream-commit": f"{commit[:7]} {commit_date} (release {tag}, {commit})",
    }
    out, seen = [], set()
    for line in lines:
        key = line.partition(":")[0].strip()
        if key in new:
            out.append(f"{key}: {new[key]}")
            seen.add(key)
        elif key == "apex-templates":
            out.append("apex-templates: platform-apex-generate/assets/*.cls and references/*.cls "
                       "(the files its SKILL.md links), from the same commit")
        else:
            out.append(line)
    out += [f"{k}: {v}" for k, v in new.items() if k not in seen]
    path.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="report only, write nothing")
    ap.add_argument("--body", help="write a markdown summary (pull request body) to this file")
    args = ap.parse_args()

    release = _api("releases/latest")
    tag = release["tag_name"]
    commit_info = _api(f"commits/{tag}")
    commit = commit_info["sha"]
    commit_date = commit_info["commit"]["committer"]["date"][:10]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError(f"unexpected commit id {commit!r}")
    print(f"upstream {REPO} release {tag} -> {commit} ({commit_date})")

    changed, missing, unchanged = [], [], 0
    new_text: dict[str, str] = {}
    for rel in bundled_files():
        local = _norm((SKILLS_DIR / rel).read_text(encoding="utf-8"))
        remote = fetch_upstream(commit, rel)
        if remote is None:
            missing.append(rel)
        elif remote != local:
            changed.append(rel)
            new_text[rel] = remote
        else:
            unchanged += 1
    print(f"{len(changed)} changed, {unchanged} unchanged, {len(missing)} missing upstream")
    for rel in changed:
        print(f"  changed: {rel}")
    for rel in missing:
        print(f"  missing upstream (kept as is): {rel}")

    # Files an updated SKILL.md now links to that Avio does not bundle (informational)
    bundled = set(bundled_files())
    new_links = []
    for rel, text in new_text.items():
        if rel.endswith("/SKILL.md"):
            skill = rel.split("/")[0]
            for target in sorted(linked_files(text)):
                if f"{skill}/{target}" not in bundled:
                    new_links.append(f"{skill}/{target}")

    if changed and not args.check:
        for rel, text in new_text.items():
            (SKILLS_DIR / rel).write_text(text, encoding="utf-8", newline="\n")
        update_version_file(tag, commit, commit_date)

    if args.body:
        b = [
            f"Automated sync of the Salesforce skills Avio bundles from "
            f"[`{REPO}` release {tag}](https://github.com/{REPO}/releases/tag/{tag}) "
            f"(commit [`{commit[:7]}`](https://github.com/{REPO}/commit/{commit}), {commit_date}).",
            "",
            "These files are injected into AI prompts, so **read the diff before merging**. "
            "Merging does not release anything; the change ships with the next release.",
            "",
            f"**Changed ({len(changed)}):**",
            *[f"- `backend/sf_skills/{r}`" for r in changed],
            "",
            f"Unchanged: {unchanged}.",
        ]
        if missing:
            b += ["", f"**No longer upstream ({len(missing)})**, kept unchanged here; decide by hand:",
                  *[f"- `{r}`" for r in missing]]
        if new_links:
            b += ["", "**New files the updated SKILL.md links to** (not bundled; add by hand if wanted, "
                  "and add them to `SKILL_FILES` in `backend/sf_skills.py` if they must be injected):",
                  *[f"- `{r}`" for r in new_links]]
        if release.get("html_url"):
            b += ["", f"Upstream release notes: {release['html_url']}"]
        Path(args.body).write_text("\n".join(b) + "\n", encoding="utf-8")

    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"changed={'true' if changed else 'false'}\ntag={tag}\ncommit={commit}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
