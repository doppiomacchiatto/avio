# Avio — Release, Signing & Distribution Plan

Tracker for getting Avio from "works on my machine" to "signed download on GitHub". Started 2026-11-14. Tick items as they are done and add the date.

**Supersedes** the signing / "Push v1.0.1" items in `TODO.md`: its Windows advice (`certificateThumbprint`, "EV cert avoids SmartScreen") is out of date, and the push is done.
**Never put secrets in this file** (client secrets, certificates, API keys). Azure resource *names* and endpoints are fine; they are not secret.

## Status

| Area | State |
|---|---|
| Release candidate build | Installed locally from `e4570fc`; **manually verified by the developer 2026-11-14, no issues** (the `HANDOFF-2026-11-14.md` checklist). Installer hashes re-checked against the release notes; no app-code difference between the tag and the dev tip |
| Tag `v1.0.1-beta` | Created 2026-11-14 on `main` merge commit `50e3c4a` (annotated, pushed). The tagged code was verified by the developer. If code changes before publishing, merge to `main` and move the tag (`git tag -d`, `git push origin :refs/tags/v1.0.1-beta`, re-tag), then rebuild and recompute the hashes |
| Windows signing | On hold. Waiting for the developer to sign up for Azure and report back; do not start before then (the repo-side steps need the endpoint/account/profile names) |
| macOS signing | Not started |
| Distribution (GitHub Releases) | **Published 2026-11-14** as a public pre-release with both installers (GitHub's hashes match the notes). Open: the description still says "First Release", so the notes in `RELEASE-NOTES-v1.0.1-beta.md` still need to be pasted in |
| CI workflow | None (`.github/` only has `FUNDING.yml`) |
| Docs / wiki | README only; decision below |
| Funding | Done: GitHub `FUNDING.yml`, README badge, About button. Decided: no Ko-fi link on the project website |

---

## 1a. Next release: v1.0.2-beta (AI fixes, saved connections, keystore, API token)

`v1.0.1-beta` ships with the 4,096-token reply limit and no truncation warning, so long Apex answers from reasoning models are cut off silently, and local (Ollama) models lose most of the skill text. It also keeps the API key in a plain-text file and has an unauthenticated local API. The fixes are on `opencode/mvp-0` (see `HANDOFF-2026-11-14.md`: "AI provider testing and fixes" and "AI connections, OS-keystore keys and API token").

**Behaviour change to announce in the notes:** the first launch moves the saved API key into the OS keystore (Windows Credential Manager) as a "Default" connection and deletes the plain-text file; older versions can't read it afterwards.

- [ ] **Run the new build** (built, not yet installed; see the handoff checklist) and check the Settings connection UI, the panel dropdowns, the token path (shell → page → backend), restart and close
- [ ] Verify a chat through a **saved connection** with two providers side by side

- [ ] Smoke-test the new build (Apex Runner with a cloud model: full answer, Save all finds both classes; with Ollama: no hang, condensed skills; trigger a truncation with a tiny `max_tokens` and check the Continue button)
- [ ] Test OpenAI and the OpenCode gateway once keys are available (the `max_completion_tokens` path is untested against OpenAI)
- [ ] Merge to `main` (handoffs excluded), tag `v1.0.2-beta`, build, new hashes, new release notes (add "reply-limit notice and Continue" and "local model support")

---

## 1. Before the first release

- [x] Run the verification checklist in `HANDOFF-2026-11-14.md` against the installed build (Save, skills, folder pickers, Ko-fi, dark mode): passed, no issues (2026-11-14)
- [x] Fix anything that fails, rebuild, re-verify: nothing to fix
- [x] Tag `main` (2026-11-14): `v1.0.1-beta` on `50e3c4a`, the merge of dev `e4570fc`+docs into `main` (handoffs excluded). App code is identical to the build that was installed for testing.
- [ ] Decide the artifact names. Tauri produces `Avio_1.0.1_x64-setup.exe` (NSIS, the main download) and `Avio_1.0.1_x64_en-US.msi`

---

## 2. Windows code signing

**Chosen route: Azure Artifact Signing** (formerly Trusted Signing / Azure Code Signing). Fallback: an OV certificate from a CA.

### Decisions / open questions
- [ ] **Location:** individuals must be in the **US or Canada**; organizations in the US, Canada, EU, UK, Australia, NZ, Japan, South Korea, Singapore, Switzerland, Norway, Israel. *Answer: ______*
- [ ] Sign as an **individual** or an **organization**? (Individual needs an Azure billing account of type *Individual* whose legal name/address match the photo ID.)
- [ ] Budget OK: **Basic $9.99/month**, 5,000 signatures, **billing starts when the account is created and is not pro-rated**. Needs a *paid* pay-as-you-go subscription (free, trial and sponsored subscriptions are refused).

### Azure setup (owner does these, in the portal)
- [ ] Billing account checked: type Individual, name and sold-to address match the ID (Cost Management + Billing). The identity form copies it and cannot be edited.
- [ ] Register resource provider `Microsoft.CodeSigning` (Subscriptions → Resource providers)
- [ ] Create the **Artifact Signing account** (new resource group, unique name 3–24 chars, Basic tier, region). Record the region endpoint below.
- [ ] Give yourself role **Artifact Signing Identity Verifier** (account → Access control)
- [ ] **Identity validation** (Individual → Public): complete the Verified ID flow with the phone camera and Microsoft Authenticator. Status becomes *Completed* (minutes; longer if documents are requested; 3 upload attempts)
- [ ] Create a **certificate profile** (type *Public Trust*, pick the validated identity)
- [ ] Create the signing identity: an **app registration** (for CI), or use your own login for local signing
- [ ] Assign **Artifact Signing Certificate Profile Signer** to that identity on the account

Record (non-secret):

| Item | Value |
|---|---|
| Region endpoint | `________.codesigning.azure.net` |
| Account name | |
| Certificate profile | |
| Tenant ID / client ID | (IDs only, no client secret here) |

### Repo changes (assistant does these once the names above exist)
- [ ] `cargo install artifact-signing-cli` on the build machine (a third-party CLI that Tauri's docs reference; pin a version)
- [ ] `src-tauri/tauri.windows.conf.json`: add `bundle.windows.signCommand`:
      `artifact-signing-cli -e <endpoint> -a <account> -c <profile> -d Avio %1`
      (Tauri signs `avio.exe` and the NSIS/MSI installers. Use forward slashes if a path is ever added; it runs without a shell.)
- [ ] **Sign `backend/dist/sf_backend.exe` before bundling.** It is bundled as a *resource*, and Tauri most likely does not sign resources. It is a PyInstaller executable, the file antivirus and SmartScreen distrust most. Add an `npm run sign:backend` step to `tauri:build` between `build:backend` and `tauri build`.
- [ ] Local auth: `az login` as an identity that has the Signer role (or set `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`; keep the secret out of the repo)
- [ ] Build, then **verify**: `Get-AuthenticodeSignature` on the installer, on `%LOCALAPPDATA%\Avio\avio.exe`, and on the installed `sf_backend.exe`. All should report `Valid` with your name and a timestamp.
- [ ] Update `README` ("The release binaries are not code-signed yet") and `TODO.md`

### Expectations
- SmartScreen **will still warn at first.** Reputation builds over weeks of clean installs; EV certificates no longer skip this. Signing gives a verified publisher name and fewer antivirus flags.
- Already-signed files stay signed if the subscription is cancelled later.
- Until signed, release notes must tell users: *More info → Run anyway*.

### Fallback: OV certificate from a CA
- [ ] Only if Artifact Signing is not available. Roughly $99–$229 per term (e.g. Certum), more for others. The private key must be on a hardware token or cloud HSM (not a `.pfx` you keep).
- [ ] Sign through `bundle.windows.signCommand` with the vendor's tool; the rest of the repo changes above are identical.

---

## 3. macOS build, then signing and notarization

**Next up (the developer is moving to a Mac).** Build and smoke-test first; the full plan, prerequisites and the risk list from the 2026-11-14 code audit are in `HANDOFF-2026-11-14.md` ("Next: macOS").

- [ ] **Add PyInstaller to the build requirements** (`pyinstaller` is not in `backend/requirements.txt`, so a fresh checkout fails at `npm run build:backend`); update the README "Dev setup"
- [ ] Build on a Mac (`npm run tauri:build`; Python 3.11/3.12 venv). PyInstaller builds for the host CPU, so one `.dmg` per architecture (arm64 / x86_64)
- [ ] Smoke test (checklist in the handoff), including: `sf`/`node` found when launched from Finder, no orphan `sf_backend` after quit, native dialogs, About menu
- [ ] Check the bundled `sf_backend` runs on Apple Silicon unsigned (`codesign -dv`); ad-hoc sign it in the build if the OS kills it
- [ ] Attach the `.dmg` file(s) to the `v1.0.1-beta` pre-release, add their SHA-256 to the notes, update the README platform table (both branches)

Then, signing and notarization:

- [ ] Apple Developer Program membership (~$99/year)
- [ ] **Developer ID Application** certificate
- [ ] `bundle.macOS` in `tauri.conf.json`: `signingIdentity`, `providerShortName`, `entitlements` (details in `TODO.md`)
- [ ] Notarize (`xcrun notarytool`, or via the Tauri CI action)
- Until signed, testers right-click → Open (or `xattr -dr com.apple.quarantine /Applications/Avio.app`).

---

## 4. Distribution: GitHub Releases

Binaries go on **GitHub Releases**, never in the repo (about 26 MB per build; git would keep every version).

- [x] **Repo is public** (verified via the GitHub API, 2026-11-14), so downloads need no login
- [x] Release created from the tag `v1.0.1-beta`, marked **pre-release** (2026-11-14)
- [x] Attached `Avio_1.0.1_x64-setup.exe` and `Avio_1.0.1_x64_en-US.msi`; add `.dmg` / `.AppImage` when those exist
- [ ] **Paste the release notes into the description** (it currently says "First Release"; edit at `https://github.com/doppiomacchiatto/avio/releases/edit/v1.0.1-beta`). Optionally rename the title `v1.0.1-Beta` to `Avio 1.0.1 Beta`
- [ ] SHA-256 checksums in the notes (they are in `RELEASE-NOTES-v1.0.1-beta.md`; they arrive with the paste above)
- [x] Release notes drafted 2026-11-14 in `RELEASE-NOTES-v1.0.1-beta.md` (review, then paste into the release; hashes inside must match the uploaded files). Contents: what's new, requirements (Salesforce CLI `sf`, an authenticated org, optional AI key), and while unsigned: *"Windows may show 'Windows protected your PC'. Click More info → Run anyway."*
- [x] README Download section added (2026-11-14). It links to `https://github.com/doppiomacchiatto/avio/releases`, **not** `/releases/latest`: GitHub's "latest" skips pre-releases and currently just redirects to the releases list. Once a full (non-pre) release exists, `/releases/latest` can be used for a direct link.

### Later: automate with CI
- [ ] `.github/workflows/release.yml` using `tauri-action` on Windows (and macOS/Linux) runners; trigger on tag `v*`; create a **draft** release and review it before publishing
- [ ] Windows signing in CI with GitHub **OIDC** (a federated credential on the app registration, scoped to a `release` environment), so no client secret is stored
- [ ] The CI Windows job must also build and sign `sf_backend.exe` (Python + PyInstaller on the runner)

### Later: auto-update
- [ ] `tauri-plugin-updater`: its own key pair (separate from code signing), `latest.json` attached to each release, update endpoint in `tauri.conf.json`. Not needed for the beta.

---

## 5. Documentation / wiki

**Decision: no GitHub Wiki for now.** A wiki is a separate git repo (`avio.wiki.git`): not versioned with the code, not reviewed with commits, and it ignores the dev/`main` branching.

- [ ] Add a **Download** section to the README once a release exists
- [ ] When more than the README is needed, add a `docs/` folder in the repo (user guide, Skills guide, troubleshooting). Keep developer handoffs out of it; they stay on the dev branch.
- [ ] Optional: publish `docs/` with GitHub Pages (e.g. under your-site.example/avio)
- [ ] Revisit a wiki only if end-user docs outgrow this and non-developers need to edit them

---

## 6. Funding

- [x] `.github/FUNDING.yml` (`ko_fi: doppiomacchiato`), README badge, About → "Support on Ko-fi" (2026-11-14)
- [ ] Confirm the **ko-fi.com/doppiomacchiato** spelling is intentional (GitHub user is `doppiomacchiatto`, two t's)
- [ ] Confirm the ❤ Sponsor button appears on the repo page (Settings → General → Features → Sponsorships)
- ~~Ko-fi link on the project website~~: not needed (developer decision, 2026-11-14)
- [ ] Optional: GitHub Sponsors (apply under Settings → Sponsors) and add `github: doppiomacchiatto` to `FUNDING.yml`

---

## Suggested order

1. Verify the build, then tag `v1.0.1-beta` (section 1)
2. Publish an **unsigned pre-release** on GitHub Releases with checksums and the SmartScreen note (section 4). Signing is not blocking for beta testers.
3. Set up Azure Artifact Signing (section 2), re-release as signed (`v1.0.2-beta` or similar)
4. Mac build, signing and notarization (section 3)
5. CI release workflow (section 4, later)
