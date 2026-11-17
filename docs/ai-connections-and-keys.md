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
| **OpenCode gateway** | [opencode.ai/auth](https://opencode.ai/auth) | `oc_sk_…` | Add credits first. The gateway's free models only work inside OpenCode itself, not from other apps. Its model list is public, so it appears as soon as you pick this provider, before you enter a key. It lists Gemini models but no Gemma. Free models are left out of the list because OpenCode says they require its own app; to try one anyway, choose "Other: type a model id" and enter its id. |
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

If the model you want is not in the list (a brand-new model, or one the provider doesn't advertise), choose **✎ Other: type a model id…** at the bottom of the **Model** list and type its exact id. Avio can't check it until you use it, so a wrong id shows up as a "model not found" error in the panel.

The first connection you save becomes the default (marked ★). The key goes straight into your system keystore and is never shown again; afterwards you only see "key saved" and its last four characters.

### OpenRouter: choose a region, and match your guardrails

When you pick **OpenRouter**, Settings asks **"Where should your prompts be processed?"** with three choices:

| Region | Address | Notes |
|---|---|---|
| **Global** (default) | `openrouter.ai` | OpenRouter picks any region. |
| **EU** | `eu.openrouter.ai` | Prompts processed only in Europe (EU/EEA, UK, Switzerland). Needs OpenRouter's **Business or Enterprise** plan. |
| **US** | `us.openrouter.ai` | Prompts processed only in the US. Same plan requirement. |

In EU and US, a model that OpenRouter hasn't made available in that region fails with an error instead of running somewhere else. This is by design (OpenRouter calls it "fails closed"), and a few consequences are worth knowing:

- **Only some providers serve each region.** A provider might run a model from a data center in the region, but OpenRouter only uses it once it has onboarded that endpoint for the region. In a guardrail's provider list, a provider with no endpoints in your region shows a **"Not in US region"** (or EU) warning. Today the US region has about 15 providers and the EU region about 5, and a model often runs on only one of them (for example, Gemma and Nemotron run on DeepInfra only in the US region). Allow the providers that actually serve your region, or the model won't be available.
- **Cloud "global" deployments are excluded.** Endpoints that can process a request in any region, such as Amazon Bedrock's cross-region profiles or Google Vertex's global location, don't count as in-region.
- **Prices can differ.** Some providers charge a premium for serving a model from a specific region. On a regional address those endpoints are used, so a model can cost more than on Global.
- **To see what a region offers**, use the model list in Settings (it's filtered by your region and workspace), or OpenRouter's models page with the *In-Region Routing* filter. The model list in Settings shows what the region offers. All three addresses use the same OpenRouter key, so switching region keeps your saved key.

**Avio runs against the OpenRouter workspace that owns your API key.** Every OpenRouter key belongs to one workspace, and that workspace's guardrails (plus your account's privacy settings) decide what the key may do. Avio can't see or change them. To use a different workspace, add another connection with a key created in that workspace, for example one connection per workspace.

For OpenRouter connections, the **Model** list is read from OpenRouter's `/models/user` endpoint with your key, so it shows only the models that workspace allows, for the region you picked. The note under the list reads "N models your OpenRouter workspace allows". Avio first checks your key with OpenRouter, so a wrong or revoked key, or an address your guardrail refuses (for example Global when the guardrail allows only US), is reported right there in Settings instead of on your first message. If the list can't be read for another reason, Avio falls back to OpenRouter's ordinary list; if the workspace allows nothing, it says so.

**Set up your OpenRouter guardrails to match what you choose here.** At openrouter.ai, open **Workspaces → Default → Guardrails** (a guardrail does nothing until it is the workspace default or is assigned to your key) and check:

- **Data regions** includes the region you chose in Avio. If the guardrail allows only US and Avio is on Global, every request is refused with a 403.
- The **model** and **provider** allowlists include the models you want to use. To limit yourself to US developers' models, allow only those models; a provider allowlist alone does not do that, because US hosts also serve models from elsewhere.
- Any **privacy** rules (data collection, zero data retention) and **spending limits** are what you expect.

When OpenRouter refuses a request because of a guardrail, Avio says so, and for a region mismatch it names the regions the guardrail allows. Fix it by changing the region in Settings or by adding it to the guardrail.

### Local models (Ollama, LM Studio)

No key is needed. Choose **Ollama (local Llama)**, or enter your server's URL (for example `http://localhost:11434/v1`), pick a model you have pulled, and Save. Notes:

- Local models usually run with a small context window (Ollama defaults to 4,096 tokens), so Avio sends them a condensed version of its Salesforce guidance. See the README for the `skills_local_budget` setting.
- The first request can take a minute or two while the model loads.

### Several connections for one provider

Add a second connection with a different name, for example `OpenAI personal` and `OpenAI work`, each with its own key.

---

## Your conversations: keep them, save them, or let them go

The AI panel in the Apex Runner and the SOQL Runner, and the AI Chat tab, each keep their conversation while you use other tabs. Switch away and come back and the panel is still open with its history, and anything you had typed but not sent. A reply that finishes while you are on another tab is waiting for you. **Clear** empties a conversation. While Avio is open the history lives in memory only. **Nothing is written to disk unless you ask.**

**When you close Avio** with an AI conversation you have not saved, the close dialog lists them ("Apex Runner (6 messages), AI Chat (2 messages)") and asks:

- **Save & Quit** keeps them on this computer for **3 days**. The next time you open the Apex Runner, SOQL Runner or AI Chat, a line at the top of the panel offers **Restore** (loads it back), **Dismiss** (hides the offer) or **Delete** (removes the saved copy). Avio never restores a conversation by itself.
- **Discard & Quit** loses them.
- **Cancel** returns to Avio.

A saved conversation is **deleted automatically 3 days after you saved it**, whether or not you restored it. **⚙ Settings → AI Model → Delete all saved conversations** removes them all now. The offer shows the date the saved copy will be removed.

**To keep a conversation longer, or share it:** each AI panel has **💾 Save** and **📂 Load**. Save writes a file you choose: a `.json` file that Avio can load again, or a `.md` file that is just readable text (for reading or sharing: **Avio cannot load a `.md` back**, so choose `.json` if you want to continue the conversation later). Files you save yourself never expire and Avio never deletes them. **Load** opens a `.json` file saved from Avio; if the panel already has a conversation you choose **Replace** or **Append**. After loading, Avio shows roughly how many tokens will be sent with your next message, because a loaded conversation becomes context for the model and uses tokens.

**Switch Org** starts a new AI Chat, because that chat's object list belongs to the org you are leaving. If it has unsaved messages Avio asks whether to keep them for 3 days or discard them. The Apex Runner and SOQL Runner conversations are not affected.

**Privacy.** Saved conversations and files are **plain text**, protected only by your operating system account. They can contain your Salesforce code, query text and replies that quote your data. They never contain an API key or connection details (keys never reach the page), but anything the AI repeated from your org can be in them. Treat a saved file like the code or data it came from, and check it before sharing. Only the conversation is saved: not the code in the editor, the query or its results.

**Only a load you choose is read.** A file is treated as untrusted: Avio checks that it is a valid Avio conversation, ignores anything it does not understand, refuses very large ones (over 500 messages), and shows the text as text, never as a web page. Be aware that a loaded conversation is sent to your AI provider as context with your next message, so only load files you trust.

**Limits.** Avio can only ask when you close the window or choose Quit. If Windows shuts down, the process is killed, the installer closes Avio, or it crashes, nothing is saved. Where the Apex Runner or SOQL Runner AI panel is closed you will not see its restore offer until you open that panel. Saved conversations are kept to at most 500 messages and about 2 MB of text each (the oldest messages are dropped first); the folder holds at most 60.

Where they are: `chats\` inside Avio's data folder (see the README's "User data").

## Choose which connection a panel uses

- The **default** connection (★) is used whenever a panel is left on "Default". Change it with **★ Make default** in Settings.
- Once you have **two or more connections**, the **Apex Runner**, **SOQL Runner** and **AI Chat** each show a small dropdown in their AI header. Pick a connection there to use it for that panel. The choice is remembered per panel, so you can use OpenAI in the Apex Runner and Claude in AI Chat at the same time.
- A connection without a saved key is labelled "— no key" in the dropdown.
- If you delete the connection a panel was using, that panel falls back to the default.

---

## Stop a reply, and long waits

While a reply is coming in, the **↑ / Send** button turns into a red **■ Stop** button. **Stop** ends the reply at once and keeps what had arrived, marked "Stopped by you. This answer is incomplete." Avio also closes the connection to the provider, so it stops generating and you stop paying for tokens you won't read. If nothing had arrived yet, nothing is added to the conversation. You can send again straight away.

Some models take a long time before the first word, especially **reasoning models** such as Grok, which think first: a minute or two is normal. After 8 seconds without any text, the panel says "Still waiting for the model" and reminds you about Stop. (A local model may be loading instead, and the hint says so for local connections.)

If a provider goes completely silent, Avio gives up on its own: **5 minutes** for cloud providers, **15 minutes** for local models, and then says "No reply from … so Avio stopped waiting." Set `chat_timeout_seconds` in `config.json` to change it (see "Advanced").

## See which skills a reply used

Avio adds Salesforce guidance ("skills") to the request, depending on the panel and your prompt. Under each AI reply, a **🧠 Skills used** line lists what was actually added, for example `Apex Generate, Apex Test Generate`, or `none`. It comes from Avio's backend, so it is reliable. A model's own answer to "is the skill loaded?" is not: it can only guess. In local mode, built-in skills are labelled `(condensed)`.

The Apex Runner always adds the Apex skill and the SOQL Runner always adds the SOQL skill. Skills you added yourself load only when their topic matches your prompt; see the README's "AI skills" section.

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
| `chat_timeout_seconds` | `config.json` | How long a reply may stay completely silent before Avio stops waiting (10 to 3600). Default 300 (5 minutes) for cloud models and 900 (15 minutes) for local ones. |
| `AVIO_SECRET_BACKEND=file` | environment | Force the private file store instead of the system keystore. |

How overrides combine: a panel with a specific connection chosen **ignores** overrides; a panel on "Default" uses the default connection with any override applied on top. An override that points at a different host never uses a saved key; supply `OPENCODE_API_KEY` with it.

---

## Troubleshooting

| You see | Cause and fix |
|---|---|
| **"No API key is saved for connection 'X'"** | The connection has no key. Open Settings, pick it and paste one. |
| **"No model is chosen for connection 'X'"** | Pick a model in Settings and Save. |
| **401 / "Incorrect API key"** from the provider | The key is wrong, expired or belongs to another provider. Paste the right key. |
| **"Rate limited (429) by …"** | The provider is limiting you. The message says why and what to do, and quotes the provider's own reason. A billing 429 (OpenAI `insufficient_quota`) means no credit: add credit on the provider's billing page, because a ChatGPT subscription doesn't cover the API. On **OpenRouter free models** (ids ending `:free`) the limits are strict (20 requests a minute; 50 a day, or 1,000 a day once you have bought $10 of credit) and the free provider is often busy: wait, or pick the same model without `:free`. Otherwise wait the time shown and retry. Avio's Salesforce guidance makes each message large, which counts toward token limits; **⚙ Settings → Skills** can switch it off for a test. |
| **"OpenRouter refused this request (403)"** | An OpenRouter guardrail blocked it. The message says whether it was the **data region** (the guardrail does not allow the region this connection uses; it lists the ones it does) or a model, provider or spending rule. Make the guardrail and Avio agree: change the connection's region in ⚙ Settings, or edit the guardrail at **Workspaces → Default → Guardrails**. See "OpenRouter: choose a region". |
| **"Your OpenRouter plan doesn't include US (or EU) routing"** | The EU and US addresses need OpenRouter's **Business or Enterprise** plan, and refuse every request without it, whatever the model. It is not a guardrail problem. Either upgrade (openrouter.ai/settings/manage-plan), or set the connection's region to **Global** in ⚙ Settings. A guardrail whose **Data regions** allow only EU or US needs the same plan, so on a lower plan allow Global there too. Global still follows the guardrail's allowed models and providers, but it can't promise that prompts are processed in one region. |
| **"The provider stopped the reply with an error"** | The provider reported a problem after it had started answering (OpenRouter does this). Earlier versions ended such a reply silently and looked like a short answer. Retry; the message includes the provider's reason. |
| **404 "model … not found"** | That model isn't available to your key, or the id you typed under "Other" is misspelled. Click **↻ Refresh list** and choose one from it. |
| **"Couldn't fetch models — showing built-in list"** | The provider rejected the key or URL, or it is unreachable. The list shown is a built-in fallback for that provider; fix the key or URL and refresh. |
| **"No reply from … so Avio stopped waiting."** | The provider didn't send anything for 5 minutes (15 for a local model). It may be overloaded or down, or the model was thinking a very long time. Send again; if it repeats, pick another model, or one that more than one host serves. To wait longer, set `chat_timeout_seconds` in `config.json`. |
| **A reply seems stuck** | Press **■ Stop**, then send again. Quitting Avio also always works. |
| **"That saved conversation no longer exists"** | Saved conversations are deleted 3 days after saving (or you deleted it). Use 💾 Save in a panel to keep one as a file. |
| **"That file is not an Avio conversation"** (Load) | Load needs a `.json` file saved with 💾 Save in Avio. A `.md` export is for reading only. |
| **"Could not save …"** in the close dialog | Avio stays open so nothing is lost. Free some disk space or use 💾 Save to write the conversation somewhere else, then close again. |
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
