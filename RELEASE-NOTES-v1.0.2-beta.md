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
- **See which skills were used.** Every AI reply now shows a **Skills used** line listing the Salesforce guidance Avio actually added to the request, so you no longer have to ask the model. The SOQL Runner now always includes the SOQL skill, and skills you added are matched more strictly (a test-class prompt no longer loads an Apex debug-log skill, which also saves tokens).
- **Type any model id, and OpenCode models list without a key.** Settings has an *Other: type a model id* choice for models a provider's list doesn't show. The OpenCode gateway's public model list now appears as soon as you pick it (without its free models, which OpenCode says only work inside its own app).
- **Log in to Salesforce from Avio.** If the Salesforce CLI has no logged-in org, the org picker now offers **Log in with browser** for Production or Sandbox / test (it runs `sf org login web` with the right login URL and the alias `avio-prod` or `avio-dev`). Airgapped or special environments can set their own login URLs in `config.json` (`org_login_urls`; see the README). **＋ Log in to another org** adds more orgs later.
- **The AI tab is now called AI Chat** (it was "OpenCode"), and the AI panels in the SOQL and Apex Runners say "AI": they work with whichever connection you choose, not only OpenCode.
- **Clear rate-limit messages.** A 429 from an AI provider now explains what happened and what to do (for example, on an OpenRouter free model: the free limits, the retry time when the provider gives one, and to pick the paid variant), and a billing 429 says it is about credit. Errors a provider reports after it has started answering are no longer swallowed as a short reply.
- **Skills now include their templates.** A skill that says "start from assets/test-class-template.cls" used to arrive without that file, so the AI had no template to follow (for example, it wrote a test class with no class wrapper and never created the test data factory). Linked templates and samples (`.cls`, `.soql`, `.xml` and similar) are now downloaded with the skill and shown to the model. Skills you added earlier hold only `SKILL.md`: remove and re-add them in Settings → Skills.
- **OpenRouter regions.** Choosing OpenRouter now asks where prompts should be processed (Global, EU or US) and reminds you to set your OpenRouter guardrails to match. Switching region keeps your key. Avio runs against the workspace that owns your key, and the model list shows only the models that workspace's guardrails allow. If a guardrail refuses a request, Avio explains why, including which regions the guardrail allows. EU and US need OpenRouter's Business or Enterprise plan.
- **AI Chat no longer says "no org is connected" when one is.** It used to wait for the org's object list, which only other tabs loaded, so a plain "Hi" could be answered with "no Salesforce org is connected". Chat now works straight away and loads the object list in the background when you open the tab; until it arrives, the AI is told that the list is still loading.
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
| `Avio_1.0.2_x64-setup.exe` | `36049cf3cbcc255a26e366e3951326c90975d61698f6979e06de20889a73e35b` |
| `Avio_1.0.2_x64_en-US.msi` | `9e3dc0bd9c1a497053584040a8674f50cc93b96031715c6e1262d2d33bc8f1e2` |

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
- OpenRouter support was tested with Google Gemma through the US region on a Business account. Other OpenRouter models, the EU region, the free plan's Global address and the workspace-filtered model list on other accounts are untested. In the US region only a few providers serve each model (Gemma and Nemotron run only on DeepInfra, for example), so a provider allowlist in your guardrail must include them
- Small local models are weak at Salesforce code; expect much better results from the cloud connections
- AI answers can be wrong. Review generated Apex before you deploy it.

## Feedback

Found a bug? Please [open an issue](https://github.com/doppiomacchiatto/avio/issues/new) and include the steps and what you saw. Open the 🐞 Debug log in the app and attach it (check it for org names or other sensitive data first). If Avio saves you time, you can [support its development on Ko-fi](https://ko-fi.com/doppiomacchiato).

Thank you for trying the beta.
