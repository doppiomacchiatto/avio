<!--
DRAFT. Paste everything below the "---" line into the GitHub release body.
BEFORE PUBLISHING (delete this comment):
  [x] Manual verification of the installed build is done (developer, 2026-11-14, no issues)
  [ ] Upload EXACTLY the files whose SHA-256 values are listed below. If you rebuild, recompute them:
        Get-FileHash .\Avio_1.0.1_x64-setup.exe -Algorithm SHA256
  [ ] Tag v1.0.1-beta points at main 50e3c4a (move it if you changed code after tagging)
  [ ] Release type: tick "Set as a pre-release"
  [ ] If the build is signed by the time you publish, delete the "Not code-signed" section and the SmartScreen step
  Hashes below were computed 2026-11-14 from the locally built installers (build of dev commit e4570fc; the app
  code is identical to the tagged main commit).
-->

---

# Avio 1.0.1 Beta

**First public beta of Avio**, a desktop Salesforce metadata explorer (formerly *Vendavis*). Windows 10/11 (x64) only for now. macOS and Linux builds are not published yet.

> **Beta software.** Read-only by default: Avio does not change your org unless you explicitly use a write action (for example the validation-rule Disable All / Restore). Try it on a sandbox first.

## What it does

- **FLS Explorer**: audit field-level security across profiles and permission sets, export to Excel
- **Profiles & PermSets**: browse a profile or permission set's object and field access, export workbooks
- **SOQL Runner**: run queries with history, and optional AI assist
- **Apex Runner**: execute anonymous Apex, view and filter debug logs, optional AI assistant that can save generated classes as `.cls` plus `-meta.xml` source files
- **Org Health**: 35 checks across 7 categories (API limits, audit and changes, automation, data volume, metadata, security, storage), with an exportable report
- **REST Explorer**: call any Salesforce REST endpoint through your authenticated org
- **AI chat (OpenCode AI)**: natural-language Salesforce help with built-in Apex and SOQL guidance from [`forcedotcom/sf-skills`](https://github.com/forcedotcom/sf-skills), plus skills you add yourself. Bring your own API key (Anthropic, OpenAI-compatible gateways, local Ollama, and others).
- Light and dark themes, a built-in debug log, and a one-click "Restart Backend"

## Requirements

1. **Salesforce CLI (`sf`)** installed and on your PATH: `npm install -g @salesforce/cli`
2. **At least one authenticated org**: `sf org login web --alias myorg`
3. *(Optional)* an **AI provider API key**, only for the AI features. Add it under ⚙ Settings.

Avio never asks for your Salesforce password. It reaches your orgs through the Salesforce CLI sessions already on your machine.

## Install

1. Download **`Avio_1.0.1_x64-setup.exe`** below. (An `.msi` is also attached for managed deployments.)
2. Run it. Because this build is not code-signed yet, see the next section.
3. Open Avio, pick an org, and go.

### Not code-signed yet

This beta is **not code-signed**, so Windows SmartScreen may show **"Windows protected your PC"**.

1. Click **More info**
2. Click **Run anyway**

Code signing is planned. To check the download is the file we published, compare its SHA-256 hash:

```powershell
Get-FileHash .\Avio_1.0.1_x64-setup.exe -Algorithm SHA256
```

| File | SHA-256 |
|---|---|
| `Avio_1.0.1_x64-setup.exe` | `28bf6f8f1e2e0c329afc56c0f2dc7c397bd400d00da237dde92b4eef94b3b2ec` |
| `Avio_1.0.1_x64_en-US.msi` | `3a0813c4abbcf945e0e66546008e454c5157b0edc0c09a7b11f3b13516a7daf2` |

## Upgrading from Vendavis

- Avio is a separate app with its own name. Uninstall the old **Vendavis** app once you've switched.
- Your settings, API key and skills move automatically to `%APPDATA%\Avio\` the first time Avio runs. Nothing is overwritten if Avio already has them.

## Privacy and security

- Everything runs on your machine. The app's local backend listens on **loopback only** (`127.0.0.1`), not on your network.
- Avio talks to Salesforce through the Salesforce CLI. **The AI features send your prompts, and any code or logs you include, to the AI provider you configure.** Leave the API key empty to keep AI off.
- Your API key is stored in a plain-text file in `%APPDATA%\Avio\`. Treat that folder like a credential.

## Known limitations

- Windows only in this release; macOS and Linux builds are not published yet
- Not code-signed (see above)
- Loading a large org's objects can take 20 seconds or more, because each Salesforce CLI call takes several seconds
- AI answers can be wrong. Review generated Apex before you deploy it.

## Feedback

Found a bug? Please [open an issue](https://github.com/doppiomacchiatto/avio/issues/new) and include the steps and what you saw. Open the 🐞 Debug log in the app and attach it (check it for org names or other sensitive data first). If Avio saves you time, you can [support its development on Ko-fi](https://ko-fi.com/doppiomacchiato).

Thank you for trying the beta.
