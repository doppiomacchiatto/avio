# Avio v1.0.2 Beta — Salesforce Metadata Explorer

[![Support on Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20Avio-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/doppiomacchiato)

Cross-platform desktop app (macOS · Windows · Linux) built with **Tauri v2** (Rust shell + system WebView), **React**, and a **Python FastAPI** sidecar that drives the Salesforce CLI.

## Download

**[⬇ Download from the Releases page](https://github.com/doppiomacchiatto/avio/releases)**: pick the newest release and download `Avio_<version>_x64-setup.exe` (an `.msi` is also attached).

| Platform | Status |
|---|---|
| Windows 10/11 (x64) | Installer on the Releases page |
| macOS, Linux | No published builds yet; [build from source](#dev-setup-first-time) |

**You need** the [Salesforce CLI](https://developer.salesforce.com/tools/salesforcecli) (`npm install -g @salesforce/cli`) and at least one authenticated org (`sf org login web --alias myorg`). An AI provider API key is optional and only used by the AI features (⚙ Settings).

**Not code-signed yet.** Windows SmartScreen may show "Windows protected your PC": click **More info → Run anyway**. Each release lists the SHA-256 of its installers; to check yours:

```powershell
Get-FileHash .\Avio_1.0.2_x64-setup.exe -Algorithm SHA256
```

Upgrading from Vendavis? Your settings move to `%APPDATA%\Avio\` automatically on first run.

## Architecture

```
┌─────────────────────────────── Avio (one desktop app) ───────────────────────────────┐
│                                                                                       │
│  Tauri shell (Rust)  ──spawns──►  FastAPI backend (Python, PyInstaller binary)        │
│   • native window / menu            • HTTP server on a local port                     │
│   • native dialogs, file I/O        • runs `sf` CLI + Salesforce REST/Tooling API     │
│   • picks the backend port          • builds Excel workbooks, talks to the AI provider│
│        │                                    ▲                       │                 │
│        ▼  loads                             │ HTTP / SSE            ▼                 │
│  React UI (WebView) ────────────────────────┘             Salesforce orgs (via sf)    │
│                                                                                       │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

**Startup.** In a packaged build the Tauri shell picks a free local port, starts the bundled `sf_backend` binary with `SF_BACKEND_PORT` set, and injects `window.__SF_BACKEND_PORT__` into the page. The UI waits for `/api/health` before loading orgs. In dev (`npm run dev`) the backend is started separately on the fixed port 7891. When the window closes, the shell asks the UI to confirm, then stops the backend and its child processes.

**Requests.** The React UI calls the backend over HTTP on localhost (`frontend/src/api/client.js`); the Content Security Policy only allows `localhost` and `127.0.0.1`. The backend listens on loopback only and requires a **per-launch token**: the shell generates a random secret at startup, hands it to the backend (`AVIO_API_TOKEN`) and to the page (`get_api_token`), and every `/api` call must send it as `Authorization: Bearer …` (only `/api/health` and the API docs are open). That stops other web pages and local programs from using your saved AI keys. With no token set, as in `npm run dev`, the backend is open. AI chat uses Server-Sent Events (`/api/ai/chat`) for streaming. The shell also exposes Tauri commands (`api_get`, `api_post`) that proxy requests through Rust; the desktop client only supports GET and POST this way, so destructive actions have a POST alias.

**Native features** are Tauri commands and plugins, not backend routes: `write_file`, `path_exists`, `open_file`, `restart_backend`, `confirm_close`, and the dialog plugin (Save / Choose folder). In Tauri v2, `window.__TAURI__` only exists when `withGlobalTauri` is on (it is off), so the frontend uses `isTauri()` from `client.js` or imports `@tauri-apps/*` directly.

**Salesforce access** goes through the Salesforce CLI (`sf`) using the orgs you already authenticated with `sf org login web`. Avio never asks for Salesforce credentials. `platform_env.py` finds `sf` and `node` even when the app is launched with a minimal OS `PATH` (see below).

### Repository layout

```
avio/
├── backend/                  # Python FastAPI server (localhost REST)
│   ├── main.py               # FastAPI app, all routes
│   ├── sf_cli.py             # Salesforce CLI wrappers (delegates to platform_env)
│   ├── platform_env.py       # OS-specific PATH, tool discovery, Avio data dir
│   ├── ai_client.py          # Provider-neutral AI client (OpenAI-compatible APIs)
│   ├── sf_skills.py          # Salesforce skill context injected into AI prompts
│   ├── sf_skills/            # Bundled skills (platform-apex-generate, platform-soql-query)
│   ├── excel_builder.py      # Excel workbook generation (FLS / object access)
│   ├── query_history.py      # SQLite SOQL history
│   ├── vr_snapshot.py        # Validation-rule "Disable All" restore snapshots
│   └── sf_backend.spec       # PyInstaller spec (built via `npm run build:backend`)
├── src-tauri/                # Tauri v2 shell (Rust)
│   ├── src/main.rs           # Window, backend lifecycle, Tauri commands
│   ├── src/platform.rs       # OS-specific process handling (spawn flags, kill tree)
│   ├── tauri.conf.json       # App config, CSP, bundle resources
│   ├── tauri.windows.conf.json   # Windows-only: bundles sf_backend.exe
│   └── capabilities/         # Permissions granted to the WebView (dialog, shell, window)
├── frontend/                 # React + Vite + Tailwind
│   └── src/
│       ├── App.jsx           # Shell UI: tabs, org picker, settings, About
│       ├── api/client.js     # Backend client, isTauri(), native dialog helpers
│       ├── apexExport.js     # Pure helpers: Apex → .cls/.trigger + meta.xml
│       ├── components/       # OrgPickerModal, TabBar, DebugLogModal, Spinner, …
│       ├── data/             # Static data (Org Health checks)
│       └── pages/            # FlsExplorer, ProfilesExplorer, SoqlRunner, ApexRunner,
│                             # RestExplorer, OrgHealth, ClaudeChat
├── docs/                     # User guides (AI connections and API keys)
├── scripts/venv-run.mjs      # Runs tools from backend/.venv on any OS
└── HANDOFF-*.md              # Session handoff notes for developers
```

### Backend routes (overview)

| Area | Routes |
|---|---|
| App & health | `/api/health`, `/api/sf-version`, `/api/shutdown`, `/api/settings`, `/api/open_file` |
| Org login | `/api/org-login` (start / status), `/api/org-login/options`, `/api/org-login/cancel` |
| Orgs & metadata | `/api/orgs`, `…/objects`, `…/fields`, `…/profiles`, `…/permsets`, `…/fls`, `…/limits`, `…/api-version`, `…/security-settings` |
| Validation rules | `…/validation-rules` (list, toggle, restore snapshot) |
| Query & execute | `/api/soql`, `/api/soql/history`, `/api/apex`, `…/rest` (REST proxy) |
| Export | `/api/export`, `/api/export/principal` (Excel workbooks, streamed progress) |
| AI | `/api/ai/chat` (SSE), `/api/models`, `/api/ai/skills*` (skill sources, fetch, remove) |

---

## Platform Environment (`backend/platform_env.py`)

### The problem

When Avio runs as a packaged `.app` / `.exe` / AppImage, the OS launches it with a minimal `PATH` — only the handful of directories the system considers safe defaults. This omits Homebrew (`/opt/homebrew/bin`), nvm, Volta, npm-global, and all other user-installed tool locations. The Salesforce CLI (`sf`) is a Node.js script, so even if the binary is found, calling it fails immediately if `node` is not on the `PATH`.

A naive fix — hardcoding macOS paths in `sf_cli.py` — would break on Windows and Linux and would require touching multiple files every time a new OS is supported.

### Design: abstract provider pattern

`platform_env.py` introduces a small hierarchy modelled on the Strategy / Template Method pattern:

```
PlatformProvider  (abstract base class)
├── MacOSProvider   — Homebrew, nvm, Volta, n, npm-global, Yarn
├── WindowsProvider — %APPDATA%\npm, nvm-windows, Volta, Chocolatey, Scoop
└── LinuxProvider   — npm-global, nvm, Volta, n, Snap
```

`PlatformProvider` defines the interface every OS must implement:

| Method | Purpose |
|---|---|
| `extra_paths() → List[str]` | **Abstract.** Returns ordered directories to prepend to `PATH`. Each OS knows its own install conventions. |
| `sf_cli_candidates() → List[str]` | **Override.** Absolute paths to check for `sf`/`sfdx` as a last resort when `shutil.which` finds nothing. |
| `augmented_path() → str` | **Concrete.** Merges `extra_paths()` with the current process `PATH`, deduplicating entries. Used as `env["PATH"]` for every subprocess call. |
| `find_tool(*names) → Optional[str]` | **Concrete.** Calls `shutil.which` over the augmented path, then falls back to iterating `sf_cli_candidates()`. |

A module-level factory, `get_platform()`, returns the singleton provider for the running OS using `sys.platform`:

```python
from platform_env import get_platform

plat = get_platform()           # MacOSProvider / WindowsProvider / LinuxProvider
sf   = plat.find_tool("sf", "sfdx")
env  = {"PATH": plat.augmented_path(), **os.environ}
```

`sf_cli.py` imports `get_platform()` and delegates entirely — no platform `if` branches in the CLI wrapper itself.

### Adding a new OS or a new OS-specific function

To support a new platform (e.g. FreeBSD), subclass `PlatformProvider`, implement `extra_paths()`, add it to the `get_platform()` factory, and nothing else changes.

To add a new OS-specific capability — for example `default_config_dir()` (macOS → `~/Library/Application Support`, Windows → `%APPDATA%`, Linux → `~/.config`) — add an abstract method to `PlatformProvider` and implement it in each subclass. All call sites use `get_platform().default_config_dir()` without any platform checks.

### Windows paths (`WindowsProvider`)

The Windows subclass is already implemented and ready for the Windows build phase. It covers:

- `%APPDATA%\npm` — npm global installs (the Windows default)
- `%LOCALAPPDATA%\nvm` — nvm-windows
- `%LOCALAPPDATA%\Volta\bin` — Volta
- `C:\ProgramData\chocolatey\bin` — Chocolatey
- `%USERPROFILE%\scoop\shims` — Scoop
- `C:\Program Files\nodejs` — Node.js installer default

The `sf_cli_candidates()` list also includes `.cmd` wrapper variants, which Windows npm installs generate alongside the bare binary name.

---

## Branching and releases

| Branch | Role |
|---|---|
| `main` | Stable releases. Only receives merges from the dev branch when it is release-ready; releases are tagged `vX.Y.Z`. |
| `opencode/mvp-0` | **Dev branch (single line of development, Windows + macOS + Linux).** Everything lands here. |
| `claude/mvp-0` | **Archived**, kept for history only. Do not commit to it. Everything it had is in `opencode/mvp-0`. |

Feature-based flow:

1. Branch from the dev branch: `git switch -c feat/<short-name> opencode/mvp-0`.
2. Keep commits scoped to one area (backend / Tauri / one frontend page) so they can be reviewed and reverted on their own.
3. Before merging back: `cd frontend && npm run build`, and `cd backend && python -c "import main"` (from the venv).
4. Merge into `opencode/mvp-0`, push, delete the feature branch.
5. When the dev branch is release-ready, merge it into `main` and tag the release.

The AI layer stays provider-neutral (`backend/ai_client.py`, configured in Settings). There is no separate per-vendor branch; use the Anthropic preset in Settings for Claude models.

## Dev setup (first time)

```bash
# 1. Python backend
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Frontend deps
cd ../frontend
npm install

# 3. Root (Tauri + concurrently)
cd ..
npm install
```

## Run in dev mode

```bash
npm run dev
# Starts: Vite dev server (port 5173) + FastAPI backend (port 7891) + Tauri window
```

## Build for distribution

```bash
# Build frontend
npm run build:frontend

# Bundle Python backend with PyInstaller (run once per platform)
npm run build:backend

# Package via Tauri
npx tauri build
# → src-tauri/target/release/bundle/dmg/Avio_*.dmg         (macOS)
# → src-tauri/target/release/bundle/nsis/Avio_*-setup.exe  (Windows installer)
# → src-tauri/target/release/bundle/msi/Avio_*.msi         (Windows MSI)
# → src-tauri/target/release/bundle/appimage/Avio_*.AppImage (Linux)
```

`npm run tauri:build` runs the backend and Tauri steps together (the frontend is built by Tauri's `beforeBuildCommand`). The release binaries are not code-signed yet.

## User data

| OS | Location |
|---|---|
| Windows | `%APPDATA%\Avio\` (`config.json`, `skills\`, `query_history.db`, `vr_snapshots.json`) |
| macOS | `~/.avio/` |
| Linux | `$XDG_DATA_HOME/avio/` (default `~/.local/share/avio/`) |

AI API keys are **not** stored in this folder: see "AI connections and API keys" below. (If no system keystore is available, keys fall back to a private file in `secrets/` here, which is not encrypted, and Settings says so.)

## Logging in to a Salesforce org

Avio uses the orgs your `sf` CLI is already logged in to. If there are none, the org picker shows a login panel instead of an error: choose **Production** or **Sandbox / test** and click **Log in with browser**. Avio runs

```
sf org login web --instance-url <login URL> --alias <alias>
```

and the page continues by itself once you finish in the browser (there is a Cancel button, and a 5-minute limit). The same panel opens from **＋ Log in to another org** under the org list, so you can add an org without a terminal. Avio never sees your password; the CLI keeps the session as usual.

| Choice | Login URL | Alias |
|---|---|---|
| Production | `https://login.salesforce.com` | `avio-prod` |
| Sandbox / test | `https://test.salesforce.com` | `avio-dev` |

**Airgapped or special environments** (a private login host, government or other isolated instances): override either URL in `config.json` (see "User data"). Only `https://` URLs are accepted; anything else is ignored and the default is used.

```json
{
  "org_login_urls": {
    "production": "https://login.example.mil",
    "test": "https://test.example.mil"
  }
}
```

The panel shows the URL it will use (marked "from your config" when overridden) and, under "Prefer a terminal, or the browser can't open?", the exact command to run yourself, plus a **Check for orgs** button. The alias is fixed per type, so logging in a second time as the same type re-points that alias to the new login. To keep both, log in with the CLI under your own alias.

## AI connections and API keys

Under **⚙ Settings → AI Model**, each **AI connection** is one saved provider setup: a name, a provider (OpenAI, Anthropic, Google, OpenRouter, Groq, the OpenCode gateway, Ollama, or any OpenAI-compatible URL), a model and an API key. The Apex Runner, SOQL Runner and AI Chat each get a dropdown (once you have two or more connections) to choose which one that panel uses, so one session can use OpenAI while another uses Claude. One connection is the default.

**To set one up:** get an API key from your provider's console, open ⚙ Settings → AI Model → *＋ New connection…*, pick the provider, paste the key, choose a model and Save. A chat subscription isn't an API key: ChatGPT Plus and a Claude Pro/Max or Claude Code login can't be used.

**How keys are used and stored, in short:**

- Keys live in your **operating system's keystore** (Windows Credential Manager, macOS Keychain, Linux Secret Service), not in `config.json`, which only holds each connection's name, URL and model.
- The page never receives a key. It sends the backend a connection id; the backend reads the key from the keystore and sends it, as a bearer token, **only to that connection's own URL**. No endpoint ever returns a key, and Settings shows only "key saved" and the last four characters.
- Changing a connection's provider or URL drops its saved key, so a key is never sent to a provider it wasn't saved for.
- This protects against copied or backed-up settings files; it does not stop other programs running as you from reading the keystore. The per-launch API token keeps other web pages and programs out of Avio's own API.
- If no system keystore exists, keys fall back to a private, **unencrypted** file and Settings warns you.
- The first run of 1.0.2 or later moves an old plain-text `api_key` file into the keystore as a "Default" connection and deletes the file (after confirming the keystore returns the key). Older versions can't read it afterwards.

**Full guide: [docs/ai-connections-and-keys.md](docs/ai-connections-and-keys.md)** covers per-provider setup, rotating or removing keys, exactly what is sent to your provider, where each OS stores keys, developer overrides and troubleshooting.

## AI skills

AI chats are augmented with Salesforce guidance from [`forcedotcom/sf-skills`](https://github.com/forcedotcom/sf-skills) (`backend/sf_skills.py`).

- **Built-in skills** (`platform-apex-generate`, `platform-soql-query`) are added when the recent user messages contain Apex / SOQL keywords. The Apex Runner always includes the Apex skill and the SOQL Runner always includes the SOQL skill.
- **Added skills** (Settings → Skills → Add) are added only when a specific topic word from the skill's name appears in the conversation (`apex-test-generate` loads for "test", `apex-debug-logs` for "debug" or "logs"). The generic words `apex`, `soql` and `sosl` do not count when a skill has a more specific word, so a test-class prompt does not pull in the debug-log skill; a skill named only with such a word (`apex-guide`) loads in that panel. Skills whose names have no topic words are always included. Total added-skill text is capped at 60,000 characters, best matches first. To inject every added skill regardless, set `"skills_inject": "all"` in `config.json`.
- **Downloads** fetch `SKILL.md` plus every `.md` file it links to. GitHub / URL sources are cached in memory for an hour.
- **Local models (Ollama, LM Studio)** usually run with a ~4K-token context, and Ollama silently drops the middle of a longer prompt. So for a local Gateway URL Avio sends a condensed skill summary (about 6,000 characters of each skill's rules, ~1.5K tokens) instead of the full text. Set `"skills_local_budget"` in `config.json` to change it (`0` = no skills for local models, `-1` = send everything, for models run with a large context). The first request to a local model can take a minute or two while it loads.

- **See what was used.** Under every AI reply, a **"Skills used"** line lists the skills Avio actually added to that request (for example "Apex Generate, Apex Test Generate", or "none"). It comes from the backend, not from the model, so there is no need to ask the model whether a skill was loaded; it can't know.

### Reply length

Avio asks for up to 16,384 tokens from cloud models (reasoning models spend part of that on hidden thinking) and 4,096 from local ones. If a model still stops at its limit, the chat shows **"The model hit its reply limit"** with a **Continue** button instead of presenting a cut-off answer as complete. Override the limit with `"max_tokens"` in `config.json` or the `OPENCODE_MAX_TOKENS` environment variable. If a provider rejects the limit as too large, or wants `max_completion_tokens` (newer OpenAI models), Avio retries automatically.

### Developer override file

A `opencode.config.json` in the project root (git-ignored), or `OPENCODE_API_KEY` / `OPENCODE_BASE_URL` / `OPENCODE_MODEL` in the environment, overrides the default connection's key, URL and model. A panel that has an explicit connection chosen ignores the override, and an override that points at a different host never borrows a saved key. Copy `opencode.config.example.json` to create one, and delete any field you don't want to force. It only applies when running from source; the packaged app doesn't bundle it.

## Environment variables

| Variable            | Default | Purpose                        |
|---------------------|---------|--------------------------------|
| `SF_BACKEND_PORT`   | 7891 (dev) / free port (packaged) | Port for the FastAPI server |
| `OPENCODE_API_KEY`  | — | Developer override of the default connection's API key (not saved anywhere) |
| `OPENCODE_BASE_URL` | — | Developer override of the AI gateway URL (OpenAI-compatible) |
| `OPENCODE_MODEL`    | — | Developer override of the AI model |
| `ANTHROPIC_API_KEY` | — | Legacy fallback, used only when no connection exists |
| `OPENCODE_MAX_TOKENS` | 16384 (cloud) / 4096 (local) | AI reply token limit |
| `AVIO_API_TOKEN`    | — | Backend API token. Set by the app at launch; set it yourself only to test token auth in dev |
| `AVIO_SECRET_BACKEND` | — | `file` forces the private file store instead of the OS keystore (headless Linux, tests) |
| `AVIO_DEBUG`        | off | Verbose Salesforce CLI logging (`VENDAVIS_DEBUG` still works) |

---

## Future State

### Bulk Profile / Permission Set Export (Async Queue)

The current export flow works well for a single profile or permission set scoped to a selected object list (< 200 objects). For very large orgs — or use cases where a user wants to export all objects for a profile without pre-selecting — a synchronous HTTP request will time out and the SF CLI bulk SOQL approach hits practical limits.

The correct architecture for that use case is an asynchronous job queue backed by Apex:

**Salesforce side — Queueable Apex job submission.** Avio submits an Apex job via the Tooling API or Anonymous Apex that enqueues a `QueueableContext` job. The job runs server-side inside the org, iterates all FieldPermissions and ObjectPermissions for the requested principal, and writes results to a Custom Object (e.g. `AvioExportJob__c` with fields for status, result payload URL or chunked JSON blobs, error message, and completed timestamp).

**Callback / polling mechanism.** Because Salesforce cannot push to a local desktop app, Avio polls the `AvioExportJob__c` record on a configurable interval (e.g. every 5 seconds) until status transitions to `Completed` or `Failed`. Alternatively, a Platform Event (`AvioJobComplete__e`) could be subscribed to via CometD/Streaming API for near-real-time notification, but polling is simpler and sufficient for most orgs.

**Job Queue UI component.** A dedicated Job Queue panel in Avio would show all submitted jobs with columns for principal name, object scope, status (Queued / Running / Done / Failed), elapsed time, and an "Open Workbook" action once done. The panel would persist across tab switches and survive app restarts by storing job IDs in local storage. Users could cancel in-flight jobs by calling `System.abortJob()` via anonymous Apex.

**Why this is deferred.** This approach requires deploying Apex classes and a Custom Object to the target org, which is a non-trivial installation step and may be blocked by org security policies. The current synchronous approach — scoped to a user-selected object list — covers the primary use case (auditing a specific application's objects) without any org-side installation. If full-org export becomes a hard requirement, the async queue approach is the right path.

### Apex Code Save to File

The Apex Runner currently holds code only in memory for the session. A natural next step is a **Save** button (💾) in the Execute toolbar that writes the editor contents to a `.cls` file on the user's local drive — defaulting to `~/Downloads/anonymous_apex_<timestamp>.cls` or opening the OS save dialog for a custom path and filename. The saved file could then be opened in an external editor (VS Code, IntelliJ) via the standard OS "open with" mechanism. A complementary **Open** button would let the user load an existing `.cls` file back into the editor. The backend already has `open_file` (OS shell open) and the `openSaveDialog` helper in `client.js` provides the Tauri save dialog; only the read/write endpoints and the toolbar buttons need to be added.

A secondary variant is **AI conversation export** — saving the Claude AI chat transcript (user prompts + assistant responses, including code blocks) as a `.md` or `.txt` file. This is useful for sharing a generated Apex solution with a teammate or keeping a record of the AI-assisted development session.

### Multi-Profile Batch Export

Currently the Profiles & PermSets tab exports one profile at a time. A natural next step is to allow the user to select multiple profiles in the left sidebar (checkboxes, same pattern as objects), then kick off a sequential batch export — one workbook per profile — with the overlay showing "Exporting profile 2 of 3…". Each workbook lands in the output directory named after the profile. The in-process FLS cache makes this fast: Query 1 only runs once per profile, so a 3-profile batch with 5 objects each would complete in roughly the same time as 3 individual exports back to back. The "Exported Workbooks" history panel in the sidebar already supports listing multiple workbooks, so the UI is ready — only the export trigger and the loop need to be added.

### Inline Record Editing in SOQL Runner

The SOQL results grid currently displays query output as a read-only table. A natural evolution is to make individual cells **editable in-place** with a "Commit Changes" button that activates only when at least one cell has been dirtied.

**UX flow.**
- Clicking a cell puts it into edit mode (a borderless `<input>` or `<textarea>` in-place, matching the cell width).
- Edited cells are highlighted (e.g. light yellow/amber background) so the user can see exactly what has changed before committing.
- A **Commit Changes** button lives in the results toolbar. It renders greyed-out (`disabled`, `opacity-50`) until at least one cell is dirty; once a change is made it activates with a blue/green highlight.
- An optional **Discard** button resets all dirty cells back to their original values without making any API calls.

**Under the hood.**
- The component maintains a `dirtyMap` — a `Map<rowIndex_fieldName, newValue>` — updated on every `onChange`. `isDirty = dirtyMap.size > 0` drives the Commit button's disabled state.
- On Commit, the frontend groups dirty cells by record `Id`, then calls a new backend endpoint `PATCH /api/orgs/{alias}/records` with a payload like `[{ sobject, id, fields: { Field__c: "new value" } }]`.
- The backend translates each entry into an `sf data update record` CLI call (or a Composite REST API bulk patch for efficiency on large change sets). Each operation returns success/failure per record; partial failures are surfaced inline on the affected rows without blocking successful ones.
- After a successful commit the `dirtyMap` is cleared, the result rows are updated with the new values, and a green toast confirms how many records were updated.

**Salesforce constraints to surface in the UI.**
- Not all fields are editable (formula fields, system fields like `CreatedDate`, fields the running user lacks FLS write access to). The app should detect non-updateable fields from the `describe` response and render those cells as permanently read-only even in edit mode.
- The `Id` field is never editable and should be visually distinguished (e.g. monospace, locked icon).
- Bulk updates via the Composite API count against Daily API Requests — the footer limit counter should reflect the calls made on Commit.
