# GitHub CI/CD plan

Status: **piece B (release.yml, test.yml) and piece A (sync-sf-skills.yml) are built; the plan text below is kept for the reasoning.** Written 2026-11-15 during the v1.0.2-beta work. Today every release is built by hand on the developer's Windows machine (`npm run tauri:build`), the hashes are copied into the release notes, and the GitHub release is published through the browser.

Two independent pieces are planned:

- **A. Skill sync**: a scheduled workflow that notices when the Salesforce skills Avio bundles change upstream and opens a pull request. It never releases anything.
- **B. Build and release**: a tag-triggered workflow that builds the installers for Windows, macOS and Linux and attaches them to a **draft** GitHub release.

Recommended order: **B first** (it unblocks the macOS and Linux work), then A.

## Contents

1. [Why not "auto-release when skills update"](#why-not-auto-release-when-skills-update)
2. [What we found](#what-we-found)
3. [Prerequisite: move the tests into the repo](#prerequisite-move-the-tests-into-the-repo)
4. [Piece B: build and draft release on tag](#piece-b-build-and-draft-release-on-tag)
5. [Piece A: skill sync pull request](#piece-a-skill-sync-pull-request)
6. [Security rules for both](#security-rules-for-both)
7. [Known gotchas](#known-gotchas)
8. [Open questions](#open-questions)
9. [Suggested steps](#suggested-steps)

---

## Why not "auto-release when skills update"

The idea that came up: use a webhook to rebuild and release Avio whenever Salesforce's official skills change. Three problems:

1. **There is no webhook to use.** OpenRouter (the AI model gateway) has nothing to do with Salesforce skills. The source is the GitHub repository [`forcedotcom/sf-skills`](https://github.com/forcedotcom/sf-skills), and a webhook needs admin rights on the repository that sends it. We don't own it. We can only **poll** it (a scheduled workflow), or watch it by hand.
2. **Skill text is part of every AI request.** Avio puts the skill files into the system prompt (see `backend/sf_skills.py`). An unreviewed build of a third party's text, shipped to every user, is a prompt-injection and supply-chain risk. Skills steer the code the model writes.
3. **Upstream churns and reverts.** Releases are weekly and large (hundreds of skills each time), and upstream does revert releases. Avio bundles 5 files. Almost all of the churn is irrelevant to us, and an automated release would also ship a revert.

So: detect changes automatically, **review them as a pull request**, and cut an app release only when a person decides to.

---

## What we found

Checked on 2026-11-15:

- **Upstream cadence.** Tags `1.68.0` (Oct 30), `1.69.0` (Nov 6) and `1.70.0` (Nov 13) on `forcedotcom/sf-skills`. The release commits say things like "Release 350 skills (37 new, 312 updated, 1 removed)", "Release 433 skills", "Release 474 skills". The `1.70.0` notes include **"Revert release 13-11-26 public channels"**.
- **What Avio bundles.** `SKILL_FILES` in `backend/sf_skills.py` lists exactly five files:
  - `platform-apex-generate/SKILL.md`
  - `platform-soql-query/SKILL.md`
  - `platform-soql-query/references/anti-patterns.md`
  - `platform-soql-query/references/query-optimization.md`
  - `platform-soql-query/references/soql-reference.md`
- **No drift today.** All five bundled files were byte-identical (after line-ending normalisation) to upstream `main`.
- **Live source already exists.** Settings → Skills can read skills straight from GitHub (`skills_source = "github"`, cached for an hour in memory). Users on that setting never need a new app release to get updated skills. The default is `"bundled"`.
- **No fallback from GitHub to bundled.** If the GitHub fetch fails, no skill is injected. Only a bad `path` or an unknown source falls back to the bundled copy. Worth fixing separately if the default ever moves to GitHub.
- **No CI at all.** `.github/` contains only `FUNDING.yml`.
- **Tests are outside the repo.** The four suites (connections 108, backend 32, skills 37, org login 35 checks, plus 13 frontend block-parser checks) live in a temp folder, with hard-coded paths and Windows-only helpers.

---

## Prerequisite: move the tests into the repo

Both workflows should run the tests, so they must be committed first.

**Done (2026-11-20):** the suites are in [`tests/`](../tests/README.md) (`backend/`, `frontend/`, `e2e/`, `fixtures/`, `packaged/`) with repo-relative paths and one runner, `scripts/run-tests.mjs` (`npm test`, `npm run test:e2e`, `npm run test:packaged`). Still open from the list below: a POSIX variant of the `sf` stub, `AVIO_SECRET_BACKEND=file` in CI, and keeping network checks out of pass/fail. The original plan:

- Put the Python suites under `backend/tests/` and the block-parser test under `frontend/` (or `scripts/`), and run them from one command (for example `npm test`).
- Replace hard-coded `C:\Users\<user>\...` paths with paths relative to the repo.
- `test_orglogin.py` uses a `.cmd` stub for `sf` and `taskkill`/`tasklist` to prove the process tree is killed. Give it a POSIX variant (a shell-script stub, `kill -0`/`ps`) so it runs on macOS and Linux runners.
- Tests touch the keystore. CI should set `AVIO_SECRET_BACKEND=file` and an isolated `APPDATA`/`HOME`, as the local runs already do.
- Network tests (the live OpenCode catalog) must be marked optional or removed. CI should not depend on third-party endpoints for pass/fail.

---

## Piece B: build and draft release on tag

**Trigger:** pushing a tag matching `v*` (for example `v1.0.3-beta`). Also `workflow_dispatch` for a dry run that builds and uploads artifacts without creating a release.

**Matrix:**

| Runner | Produces |
|---|---|
| `windows-latest` | NSIS `.exe` and `.msi` |
| `macos-latest` (Apple silicon) and an Intel macOS runner | `.dmg` (and app bundle) |
| `ubuntu-22.04` (or 24.04) | `.AppImage` and `.deb` |

**Steps per runner:**

1. Check out the tag.
2. Set up Node, Rust (stable) and Python (the version the backend is pinned to).
3. Create the backend venv and install `requirements.txt`; install `frontend` and root npm dependencies.
4. Run the test suites (fail the build on any failure).
5. `npm run build:backend` (PyInstaller). It must run **on each platform**: the frozen backend is not portable.
6. Build the app with Tauri (for example `tauri-apps/tauri-action`, or `npm run tauri:build`).
7. Compute SHA-256 of every installer and write a `SHA256SUMS.txt`.
8. Upload installers and `SHA256SUMS.txt` to a **draft** GitHub release for the tag (pre-release ticked for `-beta`). The release body comes from `RELEASE-NOTES-<tag>.md` if present.

A person reviews the draft, installs one build, and presses **Publish**. Nothing publishes itself.

**Linux build dependencies** (Tauri v2, verify when implementing): `libwebkit2gtk-4.1-dev`, `build-essential`, `libxdo-dev`, `libssl-dev`, `libayatana-appindicator3-dev`, `librsvg2-dev`, `patchelf`.

**Signing.** Unsigned for now, as today. Windows code signing is on hold until the Azure account exists. macOS needs an Apple Developer ID plus notarisation; until then users right-click → Open. When signing arrives, certificates and passwords become **repository secrets**, available only to the release job on tag pushes from protected refs.

**Versioning.** The app version lives in three files today: `package.json`, `frontend/package.json` and `src-tauri/tauri.conf.json` (all `1.0.2`), plus the title of the release notes and the README heading. `src-tauri/Cargo.toml` says `2.0.0` and is not tied to it. Add a CI check that the tag matches those three, so a mis-tagged build fails early.

---

## Piece A: skill sync pull request

**Built (2026-11-25):** [`.github/workflows/sync-sf-skills.yml`](../.github/workflows/sync-sf-skills.yml) runs **daily** (06:17 UTC) and on demand, using [`scripts/sync_sf_skills.py`](../scripts/sync_sf_skills.py). Differences from the plan below: there is no `UPSTREAM.json`; the script compares every file under `backend/sf_skills/` (except `VERSION`, including the Apex templates and `LICENSE.txt`) with the latest upstream release's commit, and records the release in `VERSION`. When something changed it force-pushes `bot/sf-skills-sync` and opens or refreshes one PR into the default branch, then starts the Tests workflow on that branch with `workflow_dispatch` (a PR opened with `GITHUB_TOKEN` does not trigger `pull_request` workflows). New upstream files and files gone upstream are listed in the PR body, never added or deleted. It needs **Settings > Actions > General > Workflow permissions > Allow GitHub Actions to create and approve pull requests**, and only runs once the workflow is on the default branch. Run `python scripts/sync_sf_skills.py --check` locally to see the state without changing anything.

The original plan:

**Trigger:** a weekly `schedule` (cron) plus `workflow_dispatch`.

**Pinned state:** a new file `backend/sf_skills/UPSTREAM.json`:

```json
{
  "repo": "forcedotcom/sf-skills",
  "tag": "1.70.0",
  "commit": "23d70a44e358330a5f0d47849556024b6fae2ab6",
  "files": {
    "platform-apex-generate/SKILL.md": "<sha256>",
    "platform-soql-query/SKILL.md": "<sha256>"
  }
}
```

**Steps:**

1. Read the latest release tag from `https://api.github.com/repos/forcedotcom/sf-skills/releases/latest`. If it equals the pinned tag, stop.
2. Download only the files listed in `SKILL_FILES` at that tag's commit (use the commit SHA, **not** `main`, so the content is fixed and reproducible).
3. Compare hashes. If none of the five files changed, optionally just bump `UPSTREAM.json` in a tiny PR (or skip); the noise from the other 300+ skills is irrelevant.
4. If any changed: write them into `backend/sf_skills/`, update `UPSTREAM.json`, run the tests, and **open a pull request** with the diff and the upstream release notes in the body.
5. Never merge, tag or release automatically.

A reviewer reads the diff (these are prompts), decides, merges, and only then chooses whether the change is worth a new app version.

**New upstream skills we may want** (for example `platform-apex-test-generate`, which the bundled Apex skill already references but we don't ship): a separate, manual decision. The workflow can post a comment listing new upstream skill folders with names matching our interests, but it should not add them.

---

## Security rules for both

- **Pin actions to a full commit SHA**, not a tag (`uses: owner/action@<sha>`), and update them with Dependabot.
- **Least privilege `permissions:`** per job. Skill sync needs `contents: write` and `pull-requests: write` only. The release job needs `contents: write` only. Everything else `read`.
- **No secrets until signing.** Skill sync and the dry-run build need none (`GITHUB_TOKEN` is enough).
- **Treat downloaded content as untrusted.** Download by pinned commit, write only to the five known paths, reject path traversal, cap file sizes, and never execute anything from it.
- **Don't run untrusted pull-request code with secrets.** Use `pull_request`, not `pull_request_target`, for test runs from forks.
- **Protect `main`** (require the test workflow) so a merged skill PR has passed the suite.
- **Concurrency groups** so two tag builds or two sync runs can't overlap.

---

## Known gotchas

- **Pull requests created with `GITHUB_TOKEN` don't trigger other workflows.** GitHub suppresses that on purpose. Either have the skill-sync workflow run the tests itself before opening the PR (simplest), or open it with a fine-grained PAT or a GitHub App token so the normal PR checks run.
- **Scheduled workflows are disabled** on a repo after 60 days without activity. Mention it in the README or keep a heartbeat.
- **Cron runs on the default branch only.** Merge piece A to the default branch for it to start.
- **GitHub API rate limits** are generous for authenticated `GITHUB_TOKEN` calls; use it for the releases lookup.
- **PyInstaller is per platform**, and a frozen Linux backend must be built on an old enough glibc (ubuntu-22.04) to run on older distributions.
- **Line endings.** Normalise before hashing or diffing skills (Windows checkouts may be CRLF; upstream is LF). The earlier comparison did so.
- **`src-tauri/gen/schemas/windows-schema.json`** is regenerated by every Windows build and is build noise. CI should not commit it.

---

## Open questions

1. Branch model in CI: build tags from `main` only, or also from `opencode/mvp-0`? (Today `main` is release-only and the dev branch carries the `HANDOFF-*.md` files.)
2. Should the default skills source move to GitHub-with-bundled-fallback? That would make piece A less important, at the cost of working offline by default. It needs the missing fallback added first.
3. Which macOS targets: Apple silicon only, or Intel too?
4. Who reviews skill PRs, and how quickly? An unreviewed PR that sits open is harmless; one merged without reading is not.
5. Do we publish the draft by hand always, or allow auto-publish for pre-release tags once the pipeline has proven itself?

---

## Suggested steps

1. ~~Commit the tests into the repo, add `npm test`~~ (done: `tests/`); make them cross-platform.
2. Add a `test` workflow (push and pull request) running them on Windows, macOS and Linux.
3. Add the tag-triggered build workflow (piece B) with `workflow_dispatch` dry run first; verify the three platform builds produce working installers.
4. Add the version-consistency check.
5. Add `UPSTREAM.json` and the skill-sync workflow (piece A).
6. Revisit signing (Azure for Windows, Apple Developer ID for macOS) and move secrets into the release job.
