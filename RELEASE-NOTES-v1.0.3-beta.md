<!--
DRAFT. Paste everything below the "---" line into the GitHub release body.
BEFORE PUBLISHING (delete this comment):
  [ ] Smoke-tested by the developer on the installed 1.0.3 build
  [ ] Upload EXACTLY the files whose SHA-256 values are listed below. If you rebuild, recompute them:
        Get-FileHash .\Avio_1.0.3_x64-setup.exe -Algorithm SHA256
  [ ] Tag v1.0.3-beta points at the main merge commit (handoffs and .opencode/ removed on main)
  [ ] Release type: tick "Set as a pre-release"
-->

---

# Avio 1.0.3 Beta

**Recommended for everyone on 1.0.2.** Windows 10/11 (x64). macOS and Linux builds are not published yet.

> **Beta software.** Read-only by default: Avio does not change your org unless you explicitly use a write action (for example the validation-rule Disable All / Restore). Try it on a sandbox first.

## What's new since 1.0.2

- **Keep your AI conversations.** When you close Avio with an unsaved conversation in the Apex Runner, SOQL Runner or AI Chat, it asks: **Save & Quit**, **Discard & Quit** or **Cancel**. A conversation you keep is offered back with **Restore** the next time you open that panel, for 3 days. Each panel also has **💾 Save to file** and **📂 Load file**: a `.json` file can be loaded again; a `.md` file is readable text only, so a conversation saved only as `.md` still counts as unsaved. Settings → AI Model → **Delete all saved conversations** removes everything Avio kept. Saved conversations are plain text on your disk, protected by your Windows user account; no connection, URL or API key is stored in them.
- **Stop a reply.** A **■ Stop** button replaces Send while the AI is answering. The text so far is kept and marked as stopped, and Avio closes the connection so the provider stops generating.
- **Clearer waits and a time limit.** While waiting for a cloud model, the panel explains that reasoning models can take a minute or two before the first word. If a provider sends nothing for 5 minutes (15 for a local model), Avio stops waiting and says so; `chat_timeout_seconds` in `config.json` changes the limit.
- **Switch Org is instant.** The org list is kept for the session, so the picker opens at once; **↻ Refresh org list** asks the Salesforce CLI again. The picker has **Cancel** and a close button when an org is already connected. Switching org clears AI Chat (asking to save it first) and stops a reply that is still arriving.
- **Resizable AI panel.** The AI panel in the Apex Runner and SOQL Runner now has the same width in both, can be resized by dragging the divider (or with the arrow keys; double-click resets it), and remembers its width.
- **Server errors explained.** When an AI provider's server fails (500, 502, 503, 504, 520 to 524, 529), Avio says what the code means, that it is the provider's problem and not your key or settings, that it already tried again, and what to do. Before, the panel could show only "Error code: 522" or a whole HTML error page.

## Tested scope

Tested end to end with GPT-6 Luna, Grok 4.7, Gemma 4 31B and Nemotron 3 / 3.5 Super through OpenRouter's US region on a Business account. **Generated code has not been validated by deployment:** review AI-generated Apex before using it, and try it in a sandbox first.

## Requirements

1. **Salesforce CLI (`sf`)** installed and on your PATH: `npm install -g @salesforce/cli`
2. **At least one authenticated org**: `sf org login web --alias myorg` (or use **Log in with browser** in Avio's org picker)
3. *(Optional)* an **AI provider API key**, only for the AI features. Add it under ⚙ Settings → AI.

## Install

1. Download **`Avio_1.0.3_x64-setup.exe`** below. (An `.msi` is also attached for managed deployments.)
2. Run it. Because this build is not code-signed yet, Windows SmartScreen may show **"Windows protected your PC"**: click **More info**, then **Run anyway**.
3. Open Avio, pick an org, and go.

To check the download is the file we published, compare its SHA-256 hash:

```powershell
Get-FileHash .\Avio_1.0.3_x64-setup.exe -Algorithm SHA256
```

| File | SHA-256 |
|---|---|
| `Avio_1.0.3_x64-setup.exe` | `4E10E48283F3980C4CF4CE8CBEA182B76A044E97DA246ADF95844A4E1270EAAD` |
| `Avio_1.0.3_x64_en-US.msi` | `27029456051102F1AF2A56E4D859A1A4257B462FAC2DA6909B6FC748DE768A06` |

## Upgrading

- **From 1.0.2:** install over it. Your connections, keys, skills and settings are kept.
- **From 1.0.1:** see the 1.0.2 notes: the first launch moves your API key into the Windows keystore.

## Known limitations

- Windows only in this release; not code-signed
- Closes that skip Avio's close dialog (Windows shutdown or sign-out, ending the process, a crash) cannot offer to save conversations
- Restore offers only the newest kept conversation per panel; the Apex and SOQL Runner offers appear when that AI panel is open
- Stop was checked against a test provider; whether every vendor stops billing at the moment the connection closes has not been confirmed
- **Local models (Ollama, LM Studio) are experimental.** Avio sends them a condensed version of its Salesforce skills (about 6,000 characters, without the code templates or skills you added), and Ollama's default context window is small, so a long prompt can be cut without warning. Small local models also write noticeably weaker Salesforce code. Use a cloud model for Apex generation; full local support (context checks and a list of recommended models) is planned for a future release.
- AI answers can be wrong. Review generated Apex before you deploy it.

## Feedback

Found a bug? Please [open an issue](https://github.com/doppiomacchiatto/avio/issues/new) with the steps and what you saw, and attach the 🐞 Debug log (check it for org names or other sensitive data first). If Avio saves you time, you can [support its development on Ko-fi](https://ko-fi.com/doppiomacchiato).
