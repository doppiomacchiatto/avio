<!--
DRAFT. Paste everything below the "---" line into the GitHub release body.
BEFORE PUBLISHING (delete this comment):
  [ ] Version bumped to 1.0.6 (package.json, frontend/package.json, src-tauri/tauri.conf.json, both package-lock.json, README)
  [x] Record Counts checked against a real org on the installed build (2026-11-24)
  [ ] Smoke-tested by the developer on the installed 1.0.6 build
  [ ] Hash rows below filled in (scripts/release-notes.mjs does it in CI). If you rebuild by hand, recompute them:
        Get-FileHash .\Avio_1.0.6_x64-setup.exe -Algorithm SHA256
  [ ] Tag v1.0.6-beta points at the main merge commit
  [ ] Release type: tick "Set as a pre-release"
-->

---

# Avio 1.0.6 Beta

**Recommended for everyone on 1.0.5.** Windows 10/11 (x64). macOS and Linux builds are not published yet.

> **Beta software.** Read-only by default: Avio does not change your org unless you explicitly use a write action (for example the validation-rule Disable All / Restore). Try it on a sandbox first.

## What's new since 1.0.5

- **Record Counts now really counts.** Before, the AI Chat's 📊 Record Counts sent a prompt to the AI model, which cannot run queries, so you got the SOQL back instead of numbers. Avio now runs the queries itself: one `SELECT COUNT()` for Account, Contact, Lead, Opportunity, Case, Task, Event and User, plus up to 20 of your custom objects, four at a time. It uses no AI tokens.
  - **In AI Chat** you get one report: the total number of records, the three largest objects and their share, how much of the total sits in custom objects, which objects are empty, and a table with a share bar for each object. The numbers stay in the conversation, so you can ask the AI about them afterwards.
  - **Typing the request works too.** "record counts", "top objects by record count" or "how many records are in each object" runs the same counts instead of going to the AI. A question about one object's data (for example "count the Accounts in Texas") still goes to the AI.
  - **In SOQL Runner** the new **📊 Counts** button shows the same counts in the results table, where you can export them to CSV.
  - An object that cannot be counted (for example one your user cannot query) shows why, and the others still appear.
  - Custom objects are included once the org's object list has loaded. AI Chat loads it automatically; in SOQL Runner, load the object list first.
- **More reliable counts from the backend:** a `COUNT()` query now returns the org's total. Before, it always came back as 0.
- **Tests:** the test suites now also run on macOS and Linux, new tests cover Record Counts, and every push runs the tests on Windows in GitHub Actions. No change to the app itself.

## Tested scope

Record Counts was tested end to end with mocked org responses (both pages, a failing object, the 20-custom-object cap) and by the developer against a real org on the installed build (AI Chat report: 19 objects counted). AI features were not changed in this release; the scope tested for 1.0.5 still applies. Review AI-generated Apex before using it, and try it in a sandbox first.

## Requirements

1. **Salesforce CLI (`sf`)** installed and on your PATH: `npm install -g @salesforce/cli`
2. **At least one authenticated org**: `sf org login web --alias myorg` (or use **Log in with browser** in Avio's org picker)
3. *(Optional)* an **AI provider API key**, only for the AI features. Add it under ⚙ Settings → AI. Record Counts does not need one.

## Install

1. Download **`Avio_1.0.6_x64-setup.exe`** below. (An `.msi` is also attached for managed deployments.)
2. Run it. Because this build is not code-signed yet, Windows SmartScreen may show **"Windows protected your PC"**: click **More info**, then **Run anyway**.
3. Open Avio, pick an org, and go.

To check the download is the file we published, compare its SHA-256 hash:

```powershell
Get-FileHash .\Avio_1.0.6_x64-setup.exe -Algorithm SHA256
```

| File | SHA-256 |
|---|---|
| `Avio_1.0.6_x64-setup.exe` | `PENDING` |
| `Avio_1.0.6_x64_en-US.msi` | `PENDING` |

## Upgrading

- **From 1.0.2 to 1.0.5:** install over it. Your connections, keys, skills, settings and kept conversations are kept.
- **From 1.0.1:** see the 1.0.2 notes: the first launch moves your API key into the Windows keystore.

## Known limitations

- Windows only in this release; not code-signed
- Record Counts counts at most 20 custom objects, the first 20 in the org's object list
- Built-in skill templates are sent only to cloud models; local models get the condensed rules
- The context check works ahead of time only for providers that report a model's context size (OpenRouter, the OpenCode gateway, Groq); for others Avio relies on the provider's "too long" error and retries once
- Closes that skip Avio's close dialog (Windows shutdown or sign-out, ending the process, a crash) cannot offer to save conversations
- Restore offers only the newest kept conversation per panel; the Apex and SOQL Runner offers appear when that AI panel is open
- Stop was checked against a test provider; whether every vendor stops billing at the moment the connection closes has not been confirmed
- **Local models (Ollama, LM Studio) are experimental.** Avio sends them a condensed version of its Salesforce skills (about 6,000 characters, without the code templates or skills you added), and Ollama's default context window is small, so a long prompt can be cut without warning. Small local models also write noticeably weaker Salesforce code. Use a cloud model for Apex generation.
- AI answers can be wrong. Review generated Apex before you deploy it.

## Feedback

Found a bug? Please [open an issue](https://github.com/doppiomacchiatto/avio/issues/new) with the steps and what you saw, and attach the 🐞 Debug log (check it for org names or other sensitive data first). If Avio saves you time, you can [support its development on Ko-fi](https://ko-fi.com/doppiomacchiato).
