# Avio tests

Plain scripts, no test framework: each suite prints one `PASS <name>` or `FAIL <name>  -- <detail>` line per check
and exits non-zero on a crash. A suite has failed if any line starts with `FAIL` (**case-sensitive**: PowerShell's
`Select-String` is not, and also matches "failures").

## Layout

| Folder | What | Needs |
|---|---|---|
| `backend/` | Python suites for `backend/` (`test_*.py`): connections and keystore, AI client, skills, error messages, workspace models, org login, saved chats, Stop/timeout, context-size guard, local-server detection | `backend/.venv` |
| `frontend/` | node suites for `frontend/src/` (`test_*.mjs`): block parser, chat system prompt, session store, chat history, history strip rendered through Vite, local-URL detection | `frontend/node_modules` |
| `e2e/` | Playwright browser runs against the real backend and the real UI (`e2e_*.mjs`, `e2e.mjs`); `browser.mjs` finds Edge/Chrome; `harness/` + `vite.harness.config.mjs`: the test page for `e2e_stop.mjs` and `e2e.mjs` | servers, see below; `npm install` in `tests/e2e` (the runner does it) |
| `fixtures/` | helpers the suites start: `fake_provider.py` (fake OpenAI-style provider, port 7898: 429 with `Retry-After`, mid-stream error, HTML 522), `fake_slow.py` (slow/silent provider, port 7889, logs closed connections to the file given as its argument), `stub_sf.py` + `stub_sf.cmd` (stand-in for the `sf` CLI), `local_urls.json` (URL -> local/cloud table shared by the backend and frontend local-detection suites) | |
| `packaged/` | checks of an installed release build: `frozen_verify.ps1`, `byte_scan.ps1` | Windows, an installed build |

Backend suites put `backend/` on `sys.path` from the repo root (`Path(__file__).resolve().parents[2]`); frontend
suites import from `frontend/` relative to `import.meta.url`. Nothing depends on where the repo is checked out.

## Running

```
npm test                 # backend + frontend suites
npm run test:e2e         # the above plus the browser tests (starts and stops its own servers)
npm run test:packaged    # the above plus the installed-build checks (Windows)
node scripts/run-tests.mjs --only=test_chats    # one suite (substring of the file name)
```

`scripts/run-tests.mjs` uses `backend/.venv`'s Python (override with `AVIO_TEST_PYTHON`), sets
`PYTHONIOENCODING=utf-8` (a failing check with a non-ASCII message otherwise crashes on a cp1252 console), prints
one line per suite with its pass/fail counts, and exits non-zero if any suite failed. `AVIO_TEST_VERBOSE=1` prints
every suite's full output. A single suite can also be run directly, e.g.
`backend\.venv\Scripts\python.exe tests\backend\test_chats.py` or `node tests\frontend\test_blocks.mjs`.

### Browser tests (`--e2e`)

The runner starts, and afterwards kills (process tree), three servers:

- the backend from source (`backend/main.py`) on **7893**, with a fresh temporary `APPDATA` (its `config.json` sets
  `chat_timeout_seconds: 10`), `AVIO_SECRET_BACKEND=file` (the scripts' connection keys stay in that folder, never in
  Credential Manager) and **no** `AVIO_API_TOKEN`;
- `npx vite --config ../tests/e2e/vite.harness.config.mjs` in `frontend/` (**5199**): the app's own Vite config
  plus the harness page (below);
- `fixtures/fake_slow.py <close-log>` on **7889** (use `127.0.0.2` in a connection URL for a "cloud" provider; `127.0.0.1` counts as local, and only `127.0.0.1` of the loopback range does, see `is_local_url` in `backend/ai_client.py`).

It refuses to start if any of those ports is taken, and before running checks that the backend on 7893 is the
isolated one (no saved chats, and a probe chat it saves lands in the temp `APPDATA`; the scripts call
`/api/chats/delete-all`) and that 5199 serves the harness page. The scripts set `window.__SF_BACKEND_PORT__` and mock
`/api/orgs*` and `/api/sf-version` with Playwright routes: no `sf` CLI and no real org is touched. `App.jsx` calls
Tauri's `listen()` in a plain browser, which throws `transformCallback` errors: expected and ignored.

| Script | Runs | Notes |
|---|---|---|
| `e2e_switch.mjs` | always | Switch Org in the real App; needs `fake_slow.py` and its close-log path as argument |
| `e2e_panel.mjs` | always | AI side panel width/resize/colours; no fake provider |
| `e2e_stop.mjs` | always | Stop button, wait hint and timeout in the three AI panels (harness page); needs the close-log path |
| `e2e.mjs` | always | saved-chat strip: restore, save, load, bad files, Delete, Dismiss (harness page) |

**The harness page.** `e2e_stop.mjs` and `e2e.mjs` open `http://localhost:5199/_harness/index.html`. Its source is
`tests/e2e/harness/` (`index.html`, `main.jsx`); `vite.harness.config.mjs` keeps `frontend/` as Vite's root (so
`/src/...` are the real modules, the same instances the scripts import from the page, styled by the real
`index.css`) and serves `/_harness/*` from `tests/e2e/harness/`. Nothing is copied into `frontend/`, and
`vite build` (which uses `frontend/vite.config.js`) never sees the harness, so it cannot reach `dist` or the
installer. The page sets `window.__SF_BACKEND_PORT__ = 7893` and renders:

- `?p=chat|soql|apex`: the real ClaudeChat, SoqlRunner or ApexRunner page with no org and its AI panel open;
- no `p`: the real `AiHistoryStrip` for the Apex surface, a `#msgs` element with the conversation as JSON, and
  `#add` / `#clear` buttons that change it the way a panel does.

To run a browser script by hand, start the three servers as above, then `node tests/e2e/e2e_panel.mjs` (or
`e2e_switch.mjs <close-log>`, `e2e_stop.mjs <close-log>`, `e2e.mjs`), and stop the servers afterwards (`taskkill /T /F /PID <owner of 7893, 5199, 7889>`).

### Installed-build checks (`--packaged`, Windows)

Run after every release build + install:

- `frozen_verify.ps1` starts a throwaway copy of the installed `%LOCALAPPDATA%\Avio\sf_backend.exe` on **7899**
  (temp `APPDATA`, a test token) and `fixtures/fake_provider.py` on **7898**, checks auth, OpenRouter regions and key
  scope, the model list with a made-up key (real network), the OpenCode keyless list, the error messages, saved
  chats, that no test credential is left in Credential Manager, and that the coding-agent skills are not in the
  build (`frontend/dist`, `backend/build`). Lines ending in `FAIL` or containing `(BAD)` are failures.
- `byte_scan.ps1 [-Version x.y.z]` scans `avio.exe`, `sf_backend.exe` and the installers for personal strings. The
  strings are read at run time, never stored in the repo: `$env:USERNAME`, `$env:USERPROFILE`, and optional extra
  lines from `tests/packaged/scan-strings.local.txt` (git-ignored). Hits are reported by index, not by text.

## Ports

| Port | Used by |
|---|---|
| 7889 | `fake_slow.py`, and `test_stop.py` itself: **do not run `test_stop.py` while `fake_slow.py` is up** |
| 7893 | backend for the browser tests |
| 7898 | `fake_provider.py` (`frozen_verify.ps1`) |
| 7899 | the packaged backend in `frozen_verify.ps1` |
| 5199 | vite for the browser tests |

## Rules

- **Isolated `APPDATA`.** Every suite and server points `APPDATA` (and `HOME`/`XDG_DATA_HOME`) at a fresh temp
  folder, so the real Avio settings, saved chats and key file are never read or changed. Keep it that way in new
  suites: set it before importing anything from `backend/`.
- **Never real keys.** Only obviously fake keys (`"sk-ant-" + "Z9y8X7w6" * 12` and the like). Never read a real key
  file, never paste a key into a test. Network calls are limited to deliberate made-up-key checks in
  `frozen_verify.ps1`.
- **Keystore.** `test_connections.py` swaps in an in-memory keyring. Anything that writes to the real Windows
  Credential Manager (the packaged check's `connection-zz-*` entries) must delete it again; `frozen_verify.ps1`
  reports leftovers.
- **No personal data.** The repo is public: no names, user paths, emails, org aliases or real hosts in tests. Use
  `example.com` addresses and aliases like `org-one`.
