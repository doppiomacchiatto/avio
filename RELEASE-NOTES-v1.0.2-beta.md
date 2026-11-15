<!--
DRAFT. Paste everything below the "---" line into the GitHub release body.
BEFORE PUBLISHING (delete this comment):
  [x] Verified by the developer on the installed build (connections UI, panel dropdowns, two providers, keys persist, token path)
  [ ] Upload EXACTLY the files whose SHA-256 values are listed below. If you rebuild, recompute them:
        Get-FileHash .\Avio_1.0.2_x64-setup.exe -Algorithm SHA256
  [ ] Tag v1.0.2-beta points at the main merge commit (move it if code changes after tagging)
  [ ] Release type: tick "Set as a pre-release"
  [ ] If the build is signed by the time you publish, delete the "Not code-signed" section and the SmartScreen step
-->

---

# Avio 1.0.2 Beta

**Recommended for everyone on 1.0.1.** Windows 10/11 (x64). macOS and Linux builds are not published yet.

> **Beta software.** Read-only by default: Avio does not change your org unless you explicitly use a write action (for example the validation-rule Disable All / Restore). Try it on a sandbox first.

## What's new since 1.0.1

- **Saved AI connections.** Add one connection per provider (OpenAI, Anthropic Claude, Google Gemini, OpenRouter, Groq, the OpenCode gateway, a local model such as Ollama, or any OpenAI-compatible URL) under **Settings → AI**. The **Apex Runner, SOQL Runner and AI Chat each have a dropdown** to pick which connection that panel uses, so one session can use OpenAI while another uses Claude. One connection is the default. *OpenAI, Anthropic and Ollama have been tested end to end; the other presets use the same OpenAI-compatible interface but have not been run yet.*
- **API keys live in your operating system's keystore** (Windows Credential Manager), not in a plain-text file. Keys are never shown again after you save them; the app only shows "key saved" and the last four characters. If no system keystore is available, Settings says so and warns that the fallback file is not encrypted.
- **A locked-down local API.** Avio's internal server now requires a secret that is generated on every launch, so other web pages or programs on your PC can't use your saved AI keys.
- **No more silently cut-off answers.** Long AI answers (especially from reasoning models) were being stopped at a 4,096-token limit and shown as if complete. The limit is now much higher, and if a model still hits it, the chat shows **"The model hit its reply limit"** with a **Continue** button.
- **Better support for local models (Ollama).** Small local models lost most of Avio's Salesforce guidance because their context window is tiny; Avio now sends a condensed version to local models. A hint appears when the first request is slow because the model is still loading.
- **Fixes:** AI code blocks that include an ` ```xml ` meta file no longer confuse Save, Replace and Append (those buttons only appear on Apex or SOQL blocks); newer OpenAI models that reject the old `max_tokens` setting now work; a new connection no longer offers another provider's model list; editing a connection's provider can no longer send its saved key to a different provider; the "No API key" message in the panels now tells you what to do.

## Requirements

1. **Salesforce CLI (`sf`)** installed and on your PATH: `npm install -g @salesforce/cli`
2. **At least one authenticated org**: `sf org login web --alias myorg`
3. *(Optional)* an **AI provider API key**, only for the AI features. Add it under ⚙ Settings → AI. A Claude Code login or a Claude Pro/Max subscription can't be used; you need an Anthropic **API** key from `console.anthropic.com` (likewise ChatGPT Plus doesn't include an OpenAI API key).

Avio never asks for your Salesforce password. It reaches your orgs through the Salesforce CLI sessions already on your machine.

## Install

1. Download **`Avio_1.0.2_x64-setup.exe`** below. (An `.msi` is also attached for managed deployments.)
2. Run it. Because this build is not code-signed yet, see the next section.
3. Open Avio, pick an org, and go.

### Not code-signed yet

This beta is **not code-signed**, so Windows SmartScreen may show **"Windows protected your PC"**.

1. Click **More info**
2. Click **Run anyway**

Code signing is planned. To check the download is the file we published, compare its SHA-256 hash:

```powershell
Get-FileHash .\Avio_1.0.2_x64-setup.exe -Algorithm SHA256
```

| File | SHA-256 |
|---|---|
| `Avio_1.0.2_x64-setup.exe` | `fd66d835f389f1ea1516f0fd0296e9b085a65a9c21db61ad1ec7c926816daf0f` |
| `Avio_1.0.2_x64_en-US.msi` | `17fa21acd01ae2e8690b6165fb7f87eb375d0aea841050e293a8617f54a43689` |

## Upgrading

- **From 1.0.1:** install over it. **The first launch moves your saved API key into the Windows keystore** as a connection named after your provider (for example "Anthropic"), keeps your model and URL, and then **deletes the old plain-text `api_key` file** (only after the keystore has returned the key correctly). Older versions can't read the key afterwards, so if you ever go back to 1.0.1 you will need to enter it again. Your other settings and skills are untouched.
- **From Vendavis:** Avio is a separate app with its own name; uninstall Vendavis once you've switched. Your settings move to `%APPDATA%\Avio\` automatically on first run.

## Privacy and security

- Everything runs on your machine. The app's local backend listens on **loopback only** (`127.0.0.1`) and requires a per-launch secret.
- Avio talks to Salesforce through the Salesforce CLI. **The AI features send your prompts, and any code or logs you include, to the AI provider of the connection you choose.** Leave connections out to keep AI off.
- Keys in the Windows keystore protect against copied or backed-up settings files, but any program running as your Windows user can read your Credential Manager entries. Treat the machine accordingly.

## Known limitations

- Windows only in this release; the macOS Keychain and Linux keyring paths are written but not yet tested on those systems
- Not code-signed (see above)
- Windows Credential Manager limits a value to about 1,280 characters; longer values fall back to the private file store and Settings warns you
- Loading a large org's objects can take 20 seconds or more, because each Salesforce CLI call takes several seconds
- Small local models are weak at Salesforce code; expect much better results from the cloud connections
- AI answers can be wrong. Review generated Apex before you deploy it.

## Feedback

Found a bug? Please [open an issue](https://github.com/doppiomacchiatto/avio/issues/new) and include the steps and what you saw. Open the 🐞 Debug log in the app and attach it (check it for org names or other sensitive data first). If Avio saves you time, you can [support its development on Ko-fi](https://ko-fi.com/doppiomacchiato).

Thank you for trying the beta.
