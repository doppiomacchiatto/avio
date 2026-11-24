# Avio - Test Handoff

**Date:** 2026-11-24
**Branch:** `opencode/mvp-0`
**Read with:** `tests/README.md` (layout, ports, rules for new suites). This file is the plan and the open items; it does not repeat the README.

---

## 1. What exists

Plain-script suites, no framework: each prints `PASS <name>` / `FAIL <name>  -- <detail>` and exits non-zero on a crash. Run with `npm test` (backend + frontend), `npm run test:e2e`, `npm run test:packaged`, or one suite with `node scripts/run-tests.mjs --only=test_chats`. CI (`.github/workflows/test.yml`) runs unit + browser suites on Windows on every push and gates releases.

| Layer | Suites | Focus |
|---|---|---|
| `tests/backend/` | 11 Python suites (about 430 checks) | connections and keystore, AI client, skills, error messages, saved chats, Stop and timeout, context-size guard, org login, local-server detection |
| `tests/frontend/` | 6 node suites | block parser, chat system prompt, session store, chat history, history strip (Vite SSR), local-URL detection |
| `tests/e2e/` | 4 Playwright scripts | org switching, AI panel, Stop, chat history strip |
| `tests/packaged/` | 2 PowerShell scripts | installed-build checks (Windows only) |

Coverage is concentrated on the **AI chat side**. The Salesforce-data side is mostly untested (section 3).

## 2. Baseline on macOS (2026-11-24)

`npm test`: 829 checks passed, 5 suites failed. None of the failures came from the Record Counts change (`test_chats.py` fails identically with the change stashed). The suites were written for Windows:

| Suite | Why it fails off Windows |
|---|---|
| `test_chats.py` | looks for `secret.json` in a Windows-style `Avio/` folder under the temp dir |
| `test_orglogin.py` | cannot execute `tests/fixtures/stub_sf.cmd` (a Windows batch file) |
| `test_stop.py` | crashes on startup (traceback not read) |
| `test_errors.py` | the real-522 checks time out against `127.0.0.2` (macOS does not route that loopback address by default) |
| `test_connections.py` | failure not read; assumed to be the Windows Credential Manager keystore |

**Fixed (2026-11-24): the five suites are portable now and the platform guards are gone.** What actually tied each one to Windows, found by running them on Linux (WSL) with the guards removed:

| Suite | Real cause | Fix |
|---|---|---|
| `test_chats.py` | hard-coded `<tmp>/Avio/secret.json`; the data dir is `~/.avio` on macOS and `$XDG_DATA_HOME/avio` on Linux | uses `chats_dir().parent` |
| `test_orglogin.py` | `stub_sf.cmd`, and `tasklist` for the "is the process alive" checks | off Windows it writes a `#!/bin/sh` launcher (`exec python stub_sf.py`) into the temp dir; `alive()` uses `os.kill(pid, 0)` and treats zombies as dead |
| `test_stop.py` | nothing platform-specific: passes on Linux unchanged | none (the macOS crash is unexplained; possibly the openai SDK version, see `test_errors.py`) |
| `test_errors.py` | (1) not the platform: newer openai SDKs (3.59) read `response.request.headers` / `.history`, so the `SimpleNamespace` stand-ins crash on startup; (2) `127.0.0.2` is not routable on macOS | (1) real `httpx2` (or `httpx`) Request/Response objects; (2) uses `127.0.0.2` when it can bind it, else `127.0.0.1` with `ai_client._is_local` patched to treat only that URL as cloud |
| `test_connections.py` | set only `APPDATA`, so on macOS/Linux it read and wrote the **real** `~/.avio` / `~/.local/share/avio` | sets `HOME` and `XDG_DATA_HOME` too (it already uses an in-memory keyring) |

**Verified:** all five pass on Windows and on Linux (Ubuntu 22.04 in WSL, Python 3.10, openai 3.59); the `127.0.0.1` fallback in `test_errors.py` was forced once on Windows and passes. **Not verified on a Mac:** run `npm test` there to confirm.

## 3. Coverage gaps (priority order)

| # | Area | Why it matters |
|---|---|---|
| 1 | `backend/excel_builder.py` (778 lines) | The FLS / Profiles Excel export is a main feature. No tests. |
| 2 | `backend/sf_cli.py` (1058 lines) | Parses `sf` CLI output for objects, fields, FLS, validation rules and limits: where org data meets the UI. |
| 3 | Org routes in `backend/main.py` (`/api/orgs/{alias}/...`, `/api/soql`) | Only mocked in e2e; the routes themselves are untested. |
| 4 | `backend/query_history.py`, `backend/vr_snapshot.py` | Small and easy to cover. |
| 5 | `backend/platform_env.py` | Platform and path logic. |
| 6 | Frontend `apexExport.js`, `healthChecks.js` | No unit suites (`apexExport` is only touched by `test_blocks.mjs`). |
| 7 | Frontend pages: SOQL Runner, Apex Runner, FLS Explorer, Profiles, REST Explorer, Org Health | No e2e flows. |

## 4. Recommended plan

1. **Baseline first.** Run `npm test` on the target machine and record the result.
2. **Extend the `sf` stub** (`tests/fixtures/stub_sf.py`) with canned JSON for objects, fields, profiles, permission sets, validation rules and `data query`. Keeps every test offline and free of personal data. Prefer a cross-platform launcher over a new `.cmd`.
3. **`test_sf_cli.py`**: parsing of the stub output, including error and empty cases.
4. **`test_excel_builder.py`**: build a workbook from fixture data, reopen it with openpyxl, assert sheets, headers and cell values.
5. **`test_org_routes.py`**: call the org endpoints through FastAPI's `TestClient` with the stub (token auth, `SessionExpiredError` handling, error mapping).
6. **Small suites**: `query_history`, `vr_snapshot`, then a node suite for `apexExport` and `healthChecks`.
7. **E2E flows** for SOQL Runner and FLS Explorer if UI coverage is wanted (same Playwright route-mocking pattern as the existing scripts).
8. **Optional:** a separate real-org smoke script against a throwaway scratch org. Not part of CI; needs a decision on whether it is wanted.

**Decisions still open:** keep the plain-script style (recommended, matches the existing suites) or move to pytest; whether to add the optional real-org smoke script.

## 5. Tests owed for the Record Counts change (2026-11-24)

Record Counts moved from AI Chat to **SOQL Runner** (new **📊 Counts** button). Root cause of the old behaviour: the chat chip only sent a prompt, and the chat has no way to run queries, so it only wrote them. Changes:

- `frontend/src/pages/SoqlRunner.jsx`: `runRecordCounts()` runs `SELECT COUNT() FROM <object>` for Account, Contact, Lead, Opportunity, Case, Task, Event and User, plus up to 20 custom objects (`__c`) from the loaded SObject list, four at a time; results go in the normal results table sorted by count; a failed object gets a note and the rest still show.
- `backend/main.py` (`/api/soql`): `totalSize` now comes from the org's result (a `COUNT()` returns no records, so `len(records)` was always 0); falls back to `len(records)` when absent.
- `frontend/src/pages/ClaudeChat.jsx`: the Record Counts card/chip was removed.

**Verified:** `vite build` passes; `npm test` shows no new failures. **Not verified:** the button against a real org; no test covers any of the three changes.

**Tests to add:**
1. Backend: `/api/soql` returns the org's `totalSize` for a `COUNT()` result with empty `records`, and `len(records)` when `totalSize` is missing (Python stub in place of `sf`, so it runs on macOS too).
2. E2E (Playwright, mock `/api/soql` per object): the button fills the table sorted by count; one failing object does not stop the others; the button is disabled while counting; Run is disabled too.
3. Cap check: with more than 20 custom objects loaded, only 20 are queried.

## 6. Rules for new suites (from `tests/README.md`)

- Set `APPDATA` / `HOME` / `XDG_DATA_HOME` to a fresh temp folder **before** importing anything from `backend/`.
- Only obviously fake keys; never read or paste a real key.
- No personal data (the repo is public): use `example.com` and aliases like `org-one`.
- Anything that writes to the real Credential Manager must delete it again.
- Do not run `test_stop.py` while `fake_slow.py` is up (port 7889).

## 7. State of the working tree

Uncommitted on `opencode/mvp-0`: the Record Counts change (3 files, section 5), the platform guards on the five suites (section 2), and this file.
