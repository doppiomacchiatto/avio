# Avio — TODO / Release Checklist

Release, signing and distribution are tracked in [`RELEASE-PLAN.md`](RELEASE-PLAN.md). This file keeps the short list.

## Before public Beta launch

- [ ] **Code signing — macOS** (details and order: `RELEASE-PLAN.md` section 3)
  - Obtain an Apple Developer ID Application certificate (requires paid Apple Developer Program membership, ~$99/yr)
  - Add signing config to `src-tauri/tauri.conf.json` under `bundle.macOS`:
    ```json
    "macOS": {
      "signingIdentity": "Developer ID Application: <Your Name> (<TEAM_ID>)",
      "providerShortName": "<TEAM_ID>",
      "entitlements": "entitlements.plist"
    }
    ```
  - Notarize via `xcrun notarytool` after build (or configure Tauri CI action)
  - Without this, macOS Gatekeeper shows "unidentified developer" warning on first launch

- [ ] **Code signing — Windows** (plan: `RELEASE-PLAN.md` section 2)
  - Route: Azure Artifact Signing (~$10/month; individuals must be in the US or Canada), via `bundle.windows.signCommand` in `src-tauri/tauri.windows.conf.json`. Fallback: an OV certificate on a hardware token / cloud HSM.
  - Also sign `backend/dist/sf_backend.exe` (a bundled resource that Tauri most likely does not sign).
  - Signing does not remove the SmartScreen warning on day one: EV certificates no longer skip reputation, so it fades over weeks of installs.

- [ ] **Publish the first release on GitHub Releases** (`RELEASE-PLAN.md` sections 1 and 4): tag `v1.0.1-beta`, pre-release, installer + SHA-256 checksums, "More info → Run anyway" note while unsigned

- [x] **Push v1.0.1 Beta to GitHub** (done 2026-11-14: `opencode/mvp-0` pushed and fast-forwarded into `main`; `claude/mvp-0` is archived, see README "Branching and releases")

## MVP-1 features (post-Beta)

- [ ] **Excel template import → deploy Profile/PermSet**
  - Backend: new endpoint `POST /api/orgs/{alias}/deploy-permset`
  - Accepts the Excel template exported from FLS Explorer / Profiles tab
  - Parses rows (object/field/record type) × columns (profile/perm set name) → builds Metadata API XML
  - Deploys via `sf project deploy start` or direct Metadata API call
  - Frontend: "Import & Deploy" button in FLS Explorer and Profiles & PermSets tab

- [ ] **ClaudeChat.jsx console.error cleanup** (line ~436, fires on stream abort — benign but noisy)

## Notes

- Signing is **not blocking** for internal/beta distribution — testers can right-click → Open on macOS or click "More info → Run anyway" on Windows
- Signing config goes on `opencode/mvp-0` (the single dev branch) and reaches `main` at release; `claude/mvp-0` is archived
