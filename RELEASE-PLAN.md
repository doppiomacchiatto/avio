# Avio — Release, Signing & Distribution Plan

Tracker for getting Avio from "works on my machine" to "signed download on GitHub". Started 2026-11-14. Tick items as they are done and add the date.

**Supersedes** the signing / "Push v1.0.1" items in `TODO.md`: its Windows advice (`certificateThumbprint`, "EV cert avoids SmartScreen") is out of date, and the push is done.
**Never put secrets in this file** (client secrets, certificates, API keys). Azure resource *names* and endpoints are fine; they are not secret.

## Status

| Area | State |
|---|---|
| Release candidate build | Installed locally from `e4570fc`; **manually verified by the developer 2026-11-14, no issues** (the `HANDOFF-2026-11-14.md` checklist). Installer hashes re-checked against the release notes; no app-code difference between the tag and the dev tip |
| Tag `v1.0.1-beta` | Created 2026-11-14 on `main` merge commit `50e3c4a` (annotated, pushed). No GitHub release published yet. The tagged code was verified by the developer. If code changes before publishing, merge to `main` and move the tag (`git tag -d`, `git push origin :refs/tags/v1.0.1-beta`, re-tag), then rebuild and recompute the hashes |
| Windows signing | Not started (decided to do later) |
| macOS signing | Not started |
| Distribution (GitHub Releases) | Not started; no release published |
| CI workflow | None (`.github/` only has `FUNDING.yml`) |
| Docs / wiki | README only; decision below |
| Funding | GitHub `FUNDING.yml`, README badge, About button done; the project website not done |

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

## 3. macOS signing and notarization

- [ ] Apple Developer Program membership (~$99/year)
- [ ] **Developer ID Application** certificate
- [ ] `bundle.macOS` in `tauri.conf.json`: `signingIdentity`, `providerShortName`, `entitlements` (details in `TODO.md`)
- [ ] Notarize (`xcrun notarytool`, or via the Tauri CI action)
- [ ] Needs a Mac build first; nobody has built this branch on macOS yet (see `HANDOFF-2026-11-14.md`, item 2)
- Until then: testers right-click → Open.

---

## 4. Distribution: GitHub Releases

Binaries go on **GitHub Releases**, never in the repo (about 26 MB per build; git would keep every version).

- [ ] **Confirm the repo is public.** Releases from a private repo require a GitHub login to download. If it must stay private, host the installers on the project website instead.
- [ ] Create the release from the tag `v1.0.1-beta`, tick **pre-release**
- [ ] Attach `Avio_1.0.1_x64-setup.exe` (main download) and optionally the `.msi`; add `.dmg` / `.AppImage` when those exist
- [ ] Put **SHA-256 checksums** in the notes (`Get-FileHash .\Avio_1.0.1_x64-setup.exe -Algorithm SHA256`)
- [x] Release notes drafted 2026-11-14 in `RELEASE-NOTES-v1.0.1-beta.md` (review, then paste into the release; hashes inside must match the uploaded files). Contents: what's new, requirements (Salesforce CLI `sf`, an authenticated org, optional AI key), and while unsigned: *"Windows may show 'Windows protected your PC'. Click More info → Run anyway."*
- [ ] Link the stable URL `https://github.com/doppiomacchiatto/avio/releases/latest` from the README (a Download section) and from the project website. It always points at the newest release.

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
- [ ] Add a Ko-fi link or button on **the project website** (that site's source is not in this repo); link to `https://ko-fi.com/doppiomacchiato`
- [ ] Optional: GitHub Sponsors (apply under Settings → Sponsors) and add `github: doppiomacchiatto` to `FUNDING.yml`

---

## Suggested order

1. Verify the build, then tag `v1.0.1-beta` (section 1)
2. Publish an **unsigned pre-release** on GitHub Releases with checksums and the SmartScreen note (section 4). Signing is not blocking for beta testers.
3. Set up Azure Artifact Signing (section 2), re-release as signed (`v1.0.2-beta` or similar)
4. Mac build, signing and notarization (section 3)
5. CI release workflow (section 4, later)
