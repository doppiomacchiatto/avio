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

**Follow-up (2026-11-24, Windows): AI Chat runs Record Counts again, for real.** Juan wanted the chat to run the queries and give an aggregated report, not just write them.

- `frontend/src/data/recordCounts.js` (new): the counting logic shared by both pages: `countTargets` (core list + up to 20 `__c`), `countRecords` (4 at a time, failures kept), `summarizeCounts` (total, shares, custom total, empty and failed objects), `recordCountsText`.
- `ClaudeChat.jsx`: the 📊 Record Counts card/chip is back. Proceed runs the COUNT() queries through `/api/soql` (no AI call, no tokens) and posts one report: total records, the three largest objects with their shares, custom-object share, empty and failed objects, and a table with a share bar per object. The report's plain text stays in the conversation, so follow-up questions about the numbers reach the AI. If the object list has not loaded yet, only the core objects are counted and the report says so.
- `SoqlRunner.jsx`: the Counts button uses the shared module (same behaviour); it logs when custom objects are left out because the object list is not loaded.

**Tests (all added, all passing on Windows; the backend one also on Linux):**
1. `tests/backend/test_soql_counts.py` (13 checks): `/api/soql` returns the org's `totalSize` for `COUNT()`, keeps it for partial results, falls back to `len(records)` when it is missing or not an int, strips `attributes`, maps a CLI error to a 500 with the message. `_sf_raw` is replaced in-process, so it runs offline everywhere.
2. `tests/frontend/test_record_counts.mjs` (21 checks): targets, the 20-object cap, concurrency, sorting, failure handling, totals, shares and the report text.
3. `tests/e2e/e2e_counts.mjs` (24 checks): SOQL Runner fills the table sorted by count, one failing object does not stop the others, Counts and Run are disabled while counting, 28 queries (cap 20); AI Chat shows the confirm screen, a counting notice, the aggregated report (total, largest, one row per object, the failure last), makes no AI call for the counts, and sends the report text with the next question.

**Still not verified:** either button against a real org.

## 6. Rules for new suites (from `tests/README.md`)

- Set `APPDATA` / `HOME` / `XDG_DATA_HOME` to a fresh temp folder **before** importing anything from `backend/`.
- Only obviously fake keys; never read or paste a real key.
- No personal data (the repo is public): use `example.com` and aliases like `org-one`.
- Anything that writes to the real Credential Manager must delete it again.
- Do not run `test_stop.py` while `fake_slow.py` is up (port 7889).

## 7. State of the working tree

Everything above is committed on `opencode/mvp-0`. Separately, palermo has staged, uncommitted code-signing changes (on hold); leave them alone.
