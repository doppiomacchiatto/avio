# AI connections and API keys

Avio's AI features (the AI panel in the Apex Runner and SOQL Runner, and the AI Chat tab) need a connection to an AI provider. This page explains how to set one up, which connection each part of the app uses, and exactly what happens to your API key.

AI is optional. Without a connection everything else in Avio works as normal.

## Contents

1. [What a connection is](#what-a-connection-is)
2. [Set up a connection](#set-up-a-connection)
3. [Choose which connection a panel uses](#choose-which-connection-a-panel-uses)
4. [Change, rotate or remove a key](#change-rotate-or-remove-a-key)
5. [How your keys are used](#how-your-keys-are-used)
6. [Where keys are stored](#where-keys-are-stored)
7. [Upgrading from an older version](#upgrading-from-an-older-version)
8. [Advanced: developer overrides and settings](#advanced-developer-overrides-and-settings)
9. [Troubleshooting](#troubleshooting)
10. [Security notes](#security-notes)

---

## What a connection is

A **connection** is one saved provider setup:

| Part | Example | Stored in |
|---|---|---|
| Name | `OpenAI work` | `config.json` |
| Provider | OpenAI | `config.json` |
| Gateway URL | `https://api.openai.com/v1` | `config.json` |
| Model | `gpt-5-mini` | `config.json` |
| **API key** | `sk-proj-…` | **your operating system's keystore** |

You can save as many connections as you like, for example one for OpenAI, one for Claude and one for a local model, or two OpenAI accounts. One of them is the **default**.

---

## Set up a connection

### 1. Get an API key from your provider

You need a key from the provider's **API** console. A chat subscription is not a key.

| Provider | Where to get a key | Key looks like | Notes |
|---|---|---|---|
| **OpenAI** | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | `sk-…` | Needs prepaid credit (minimum $5) under [Billing](https://platform.openai.com/settings/organization/billing/). ChatGPT Plus does not include API access. |
| **Anthropic (Claude)** | [console.anthropic.com](https://console.anthropic.com) → API keys | `sk-ant-…` | A Claude Code login or a Claude Pro/Max subscription cannot be used; you need an API key with credit on the Console. |
| **OpenCode gateway** | [opencode.ai/auth](https://opencode.ai/auth) | `oc_sk_…` | Add credits first. The gateway's free models only work inside OpenCode itself, not from other apps. |
| **Google (Gemini)** | Google AI Studio | `AIza…` | |
| **OpenRouter** | [openrouter.ai/keys](https://openrouter.ai/keys) | `sk-or-…` | |
| **Groq** | [console.groq.com/keys](https://console.groq.com/keys) | `gsk_…` | |
| **Ollama / LM Studio (local)** | none | no key | Runs on your own machine; see below. |
| **Custom gateway** | your gateway | any | Any OpenAI-compatible URL. |

OpenAI, Anthropic and Ollama have been tested end to end. The other providers use the same OpenAI-compatible interface but have not been run yet.

### 2. Add it in Avio

1. Click **⚙ Settings** in the top bar. The **AI Settings** dialog opens on the **AI Model** tab.
2. In **AI connection**, choose **＋ New connection…**
3. Pick the **Provider**. The **Gateway URL** fills in by itself (edit it only for a custom gateway).
4. Optionally type a **Connection name** (it defaults to the provider's name).
5. Paste your key into **API Key**. When you click out of the field, Avio loads the provider's real model list.
6. Choose a **Model** (click **↻ Refresh list** to reload it).
7. Click **Save**.

The first connection you save becomes the default (marked ★). The key goes straight into your system keystore and is never shown again; afterwards you only see "key saved" and its last four characters.

### Local models (Ollama, LM Studio)

No key is needed. Choose **Ollama (local Llama)**, or enter your server's URL (for example `http://localhost:11434/v1`), pick a model you have pulled, and Save. Notes:

- Local models usually run with a small context window (Ollama defaults to 4,096 tokens), so Avio sends them a condensed version of its Salesforce guidance. See the README for the `skills_local_budget` setting.
- The first request can take a minute or two while the model loads.

### Several connections for one provider

Add a second connection with a different name, for example `OpenAI personal` and `OpenAI work`, each with its own key.

---

## Choose which connection a panel uses

- The **default** connection (★) is used whenever a panel is left on "Default". Change it with **★ Make default** in Settings.
- Once you have **two or more connections**, the **Apex Runner**, **SOQL Runner** and **AI Chat** each show a small dropdown in their AI header. Pick a connection there to use it for that panel. The choice is remembered per panel, so you can use OpenAI in the Apex Runner and Claude in AI Chat at the same time.
- A connection without a saved key is labelled "— no key" in the dropdown.
- If you delete the connection a panel was using, that panel falls back to the default.

---

## Change, rotate or remove a key

Open **⚙ Settings → AI Model** and pick the connection:

| To… | Do this |
|---|---|
| **Replace (rotate) a key** | Paste the new key into **API Key** and Save. Leave it blank to keep the saved one. |
| **Remove a key but keep the connection** | Click **Remove saved key**. |
| **Delete a connection and its key** | Click **Delete connection**, then click again to confirm. The key is removed from the keystore. |
| **Change the model or name** | Edit the field and Save; the key is kept. |
| **Move a connection to a different provider** | Change the provider or URL, then **paste a new key**. A saved key belongs to the provider it was saved for, so Avio does not reuse it for a different one (it would otherwise be sent to the wrong company). |

---

## How your keys are used

When you send a message in an AI panel:

1. **The page asks Avio's local backend.** The browser part of Avio sends your message, the panel's context and the **connection's id** to the backend on `127.0.0.1`, along with a per-launch secret token. **The key is not part of this request**, and the page never has it.
2. **The backend looks up the connection.** It reads the URL and model from `config.json` and the key from your operating system's keystore, into memory.
3. **The backend calls your provider.** It sends your request over HTTPS to `<Gateway URL>/chat/completions` with the header `Authorization: Bearer <your key>` (the OpenAI-compatible API; Anthropic's URL also gets its required version header) and streams the reply back to the panel.
4. **The model list** in Settings works the same way, using the provider's `/models` endpoint.
5. **The key lives in memory only while the app runs.** Avio keeps one connection object per provider URL and key, and discards them when you save, change or delete connections, or quit.

**The key is only ever sent to that connection's own URL.** It is never sent to Salesforce, to another provider, or to any server run by Avio (Avio has none). Changing a connection's URL drops its saved key, and a developer override that points at a different host never borrows a saved key.

### What your provider receives

Whatever the AI feature needs to answer you: your messages, the code in the editor, the last lines of the debug log (Apex Runner), the current query and a small result preview (SOQL Runner), the list of loaded objects (AI Chat), and Avio's built-in Salesforce guidance text. It does **not** receive your Salesforce credentials or tokens. Your provider bills your account for the usage. If you don't want data sent, don't create a connection.

### What never happens

- A saved key is never displayed again, written to `config.json` or the logs, or returned by any of Avio's endpoints.
- Other web pages and programs on your computer can't ask Avio to use your keys: its local API requires a secret that changes every launch.

---

## Where keys are stored

| System | Location | How to see it |
|---|---|---|
| **Windows** | Credential Manager, Windows Credentials, one entry per connection named `connection-<id>` (service `Avio`) | Control Panel → Credential Manager, or `cmdkey /list` and look for `connection-…@Avio` |
| **macOS** | Keychain, service `Avio`, account `connection-<id>` | Keychain Access → search "Avio" |
| **Linux** | Secret Service (gnome-keyring, KWallet), service `Avio` | for example `secret-tool search service Avio` |

The `<id>` is the connection's name in lowercase with dashes: a connection named "Anthropic" is stored as `connection-anthropic`, and a second connection also named "OpenAI" gets the id `openai-2`, so `connection-openai-2`.

`config.json` (in `%APPDATA%\Avio\` on Windows, `~/.avio/` on macOS, `$XDG_DATA_HOME/avio/` on Linux) holds only each connection's name, URL and model.

**If there is no system keystore** (for example a headless Linux machine), or it refuses a value, Avio falls back to a private file in a `secrets` folder next to `config.json`. That file is **not encrypted**, and Settings shows a warning when this is the case. Windows Credential Manager limits one value to about 1,280 characters, far more than any API key, but longer values would use the fallback.

---

## Upgrading from an older version

Versions before 1.0.2 kept one API key in a plain-text file (`api_key`). The first time 1.0.2 or later starts, Avio:

1. Creates a connection named after your provider (for example **Anthropic**), keeping your saved URL and model.
2. Moves the key into the keystore.
3. Deletes the old `api_key` file, **only after** reading the key back from the keystore and confirming it matches. If anything doesn't match, the old file is left in place.

Older versions can't read the key afterwards, so if you go back to 1.0.1 you'll need to enter it again.

---

## Advanced: developer overrides and settings

These are for developers and scripted setups. Normal use never needs them.

| Setting | Where | Effect |
|---|---|---|
| `OPENCODE_API_KEY`, `OPENCODE_BASE_URL`, `OPENCODE_MODEL` | environment variables | Override the **default** connection's key, URL and model for this run. Nothing is saved. |
| `opencode.config.json` | project root (git-ignored; copy `opencode.config.example.json`) | Same overrides from a file; only applies when running from source. |
| `max_tokens` / `OPENCODE_MAX_TOKENS` | `config.json` / environment | Reply token limit (default 16,384 cloud, 4,096 local). |
| `skills_local_budget` | `config.json` | Characters of Salesforce guidance sent to local models (`0` none, `-1` everything). |
| `AVIO_SECRET_BACKEND=file` | environment | Force the private file store instead of the system keystore. |

How overrides combine: a panel with a specific connection chosen **ignores** overrides; a panel on "Default" uses the default connection with any override applied on top. An override that points at a different host never uses a saved key; supply `OPENCODE_API_KEY` with it.

---

## Troubleshooting

| You see | Cause and fix |
|---|---|
| **"No API key is saved for connection 'X'"** | The connection has no key. Open Settings, pick it and paste one. |
| **"No model is chosen for connection 'X'"** | Pick a model in Settings and Save. |
| **401 / "Incorrect API key"** from the provider | The key is wrong, expired or belongs to another provider. Paste the right key. |
| **429 "You have no credits remaining"** (OpenAI) or a similar billing error | The account has no credit. Add credit in the provider's billing page; a ChatGPT subscription doesn't cover the API. |
| **404 "model … not found"** | That model isn't available to your key. Click **↻ Refresh list** and choose one from it. |
| **"Couldn't fetch models — showing built-in list"** | The provider rejected the key or URL, or it is unreachable. The list shown is a built-in fallback for that provider; fix the key or URL and refresh. |
| **"The selected connection no longer exists"** | It was deleted. Choose another in the panel dropdown, or add it again. |
| **Every request fails with "Unauthorized" (in the 🐞 Debug log)** | The page doesn't have the current per-launch token. Quit and relaunch Avio; if it keeps happening, please report it. |
| **macOS asks to allow Keychain access** | Choose "Always Allow". Until Avio is code-signed this can reappear after an update. |
| **Settings warns "No system keystore is available"** | Keys are in the unencrypted fallback file. On Linux install and unlock a Secret Service such as gnome-keyring, then re-save the key. |

---

## Security notes

- **What the keystore protects against:** copied or backed-up settings files, synced profiles, and anyone reading `config.json`.
- **What it does not:** other programs running as **your** user can read your keystore entries (Windows gives every process of your user the same access). Keep your machine free of untrusted software.
- **Use restricted keys where you can.** Create a separate key per app, set a spend limit with the provider, and revoke the key at the provider if you think it leaked. Deleting it in Avio does not revoke it.
- **Never paste a key into a chat, an issue or a screenshot.** The 🐞 Debug log doesn't record request bodies, so it holds no keys, but a provider's error message can include a masked piece of one (for example `sk-…abcd`). Check the log for that and for org names before sharing it.
