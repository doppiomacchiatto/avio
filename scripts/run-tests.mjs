#!/usr/bin/env node
// Runs Avio's test suites (see tests/README.md).
//   node scripts/run-tests.mjs              backend (Python) + frontend (node) suites
//   node scripts/run-tests.mjs --e2e        also the browser tests: starts the backend on 7893 (temp APPDATA,
//                                           no token), vite on 5199 (with the tests/e2e/harness page) and
//                                           fake_slow.py on 7889, then stops them
//   node scripts/run-tests.mjs --packaged   also the checks of the INSTALLED build (Windows only)
//   --only=<substring>                      run only the suites whose file name contains it
// A suite fails if it prints a line starting with "FAIL" (case-sensitive) or exits non-zero.
import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const T = path.join(REPO, "tests");
const WIN = process.platform === "win32";
const args = process.argv.slice(2);
const flag = (f) => args.includes(f);
const only = (args.find((a) => a.startsWith("--only=")) || "").slice(7);

const PY = process.env.AVIO_TEST_PYTHON ||
  path.join(REPO, "backend", ".venv", WIN ? "Scripts\\python.exe" : "bin/python");
if (!fs.existsSync(PY)) { console.error(`Python not found: ${PY} (create backend/.venv or set AVIO_TEST_PYTHON)`); process.exit(2); }
const ENV = { ...process.env, PYTHONIOENCODING: "utf-8", AVIO_TEST_PYTHON: PY };

const BACKEND = ["test_connections", "test_backend", "test_skills", "test_errors", "test_workspace",
  "test_orglogin", "test_chats", "test_stop", "test_context_guard"].map((n) => ["backend", n + ".py"]);
const FRONTEND = ["test_blocks", "test_chatsystem", "test_session", "test_chathistory", "test_strip_ssr"]
  .map((n) => ["frontend", n + ".mjs"]);

const results = [];
function record(name, out, code) {
  const lines = out.split(/\r?\n/);
  const pass = lines.filter((l) => l.startsWith("PASS")).length;
  const fail = lines.filter((l) => l.startsWith("FAIL") || / FAIL$/.test(l) || /\(BAD\)/.test(l)).length;
  const ok = fail === 0 && code === 0;
  results.push({ name, pass, fail, code, ok });
  console.log(`${ok ? "ok  " : "FAIL"}  ${name.padEnd(28)} ${String(pass).padStart(4)} passed, ${fail} failed${code ? `, exit ${code}` : ""}`);
  if (!ok) for (const l of lines.filter((l) => /FAIL|\(BAD\)|Error|Traceback/.test(l)).slice(0, 15)) console.log("        " + l.slice(0, 300));
}
function run(name, cmd, cmdArgs, opts = {}) {
  if (only && !name.includes(only)) return;
  const r = spawnSync(cmd, cmdArgs, { cwd: opts.cwd || REPO, env: ENV, encoding: "utf8", maxBuffer: 64 << 20, timeout: opts.timeout || 600000 });
  const out = (r.stdout || "") + (r.stderr || "");
  if (process.env.AVIO_TEST_VERBOSE) console.log(out);
  record(name, out, r.status ?? (r.error ? 1 : 0));
}

const portBusy = (port) => new Promise((resolve) => {
  const s = net.connect({ host: "127.0.0.1", port, timeout: 1500 });
  s.once("connect", () => { s.destroy(); resolve(true); });
  s.once("error", () => resolve(false));
  s.once("timeout", () => { s.destroy(); resolve(false); });
});

// ---- unit suites ---------------------------------------------------------------------------------------
if (await portBusy(7889)) console.log("warning: something listens on 7889 (fake_slow.py?); test_stop.py needs that port");
for (const [dir, f] of BACKEND) run(f, PY, [path.join(T, dir, f)], { cwd: path.join(T, dir) });
for (const [dir, f] of FRONTEND) run(f, process.execPath, [path.join(T, dir, f)], { cwd: path.join(T, dir) });

// ---- e2e ---------------------------------------------------------------------------------------------------
if (flag("--e2e")) await e2e();
async function e2e() {
  if (!fs.existsSync(path.join(T, "e2e", "node_modules", "playwright-core"))) {
    console.log("installing tests/e2e dependencies (playwright-core)...");
    spawnSync("npm install --no-audit --no-fund", { cwd: path.join(T, "e2e"), stdio: "inherit", shell: true });
  }
  for (const p of [7893, 5199, 7889]) if (await portBusy(p)) { console.log(`FAIL  e2e: port ${p} is already in use; stop that server first`); results.push({ name: "e2e setup", ok: false }); return; }
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "avio-e2e-"));
  const appdata = path.join(tmp, "appdata");
  fs.mkdirSync(path.join(appdata, "Avio"), { recursive: true });
  fs.writeFileSync(path.join(appdata, "Avio", "config.json"), JSON.stringify({ chat_timeout_seconds: 10 })); // e2e_stop's timeout case
  const closeLog = path.join(tmp, "slow_closed.txt");
  const procs = [];
  const start = (cmd, a, cwd, env, log) => {
    const out = fs.openSync(path.join(tmp, log), "w");
    // npx is a .cmd on Windows and needs a shell; pass it as one command string (fixed text, no user input)
    const p = cmd === "npx"
      ? spawn(["npx", ...a].join(" "), { cwd, env, stdio: ["ignore", out, out], shell: true, windowsHide: true })
      : spawn(cmd, a, { cwd, env, stdio: ["ignore", out, out], windowsHide: true });
    procs.push(p); return p;
  };
  // AVIO_SECRET_BACKEND=file: the scripts' connection keys ("k") go to the temp APPDATA, never Credential Manager
  const beEnv = { ...ENV, APPDATA: appdata, HOME: appdata, XDG_DATA_HOME: appdata, SF_BACKEND_PORT: "7893", AVIO_SECRET_BACKEND: "file" };
  delete beEnv.AVIO_API_TOKEN;
  try {
    start(PY, ["main.py"], path.join(REPO, "backend"), beEnv, "backend.log");
    // the app's own vite config plus /_harness/ served from tests/e2e/harness (nothing is written into frontend/)
    start("npx", ["vite", "--config", "../tests/e2e/vite.harness.config.mjs"], path.join(REPO, "frontend"), process.env, "vite.log");
    start(PY, [path.join(T, "fixtures", "fake_slow.py"), closeLog], tmp, ENV, "fake_slow.log");
    const up = async (url) => { for (let i = 0; i < 120; i++) { try { await fetch(url, { signal: AbortSignal.timeout(1500) }); return true; } catch { await new Promise((r) => setTimeout(r, 500)); } } return false; };
    if (!(await up("http://127.0.0.1:7893/api/health")) || !(await up("http://localhost:5199/_harness/index.html"))) {
      console.log(`FAIL  e2e: backend or vite did not start (logs in ${tmp})`); results.push({ name: "e2e setup", ok: false }); return;
    }
    // e2e.mjs calls /api/chats/delete-all: make sure 7893 is the backend started above, on the temp APPDATA
    const chats = await (await fetch("http://127.0.0.1:7893/api/chats")).json();
    if ((chats.chats || []).length) { console.log("FAIL  e2e: the backend on 7893 has saved chats: not the isolated one"); results.push({ name: "e2e setup", ok: false }); return; }
    // and that what it saves lands in the temp APPDATA: save a probe chat, look for its file, delete it again
    const probe = await (await fetch("http://127.0.0.1:7893/api/chats", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ surface: "chat", messages: [{ role: "user", content: "e2e isolation probe" }] }) })).json();
    const chatsDir = path.join(appdata, "Avio", "chats");
    const isolated = fs.existsSync(chatsDir) && fs.readdirSync(chatsDir).length > 0;
    if (probe?.id) await fetch("http://127.0.0.1:7893/api/chats/delete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: probe.id }) });
    if (!isolated) { console.log(`FAIL  e2e: the backend on 7893 does not write to the temp APPDATA (${appdata})`); results.push({ name: "e2e setup", ok: false }); return; }
    const harnessPage = await (await fetch("http://localhost:5199/_harness/index.html")).text();
    if (!harnessPage.includes("Avio e2e harness")) { console.log("FAIL  e2e: vite on 5199 does not serve the harness page"); results.push({ name: "e2e setup", ok: false }); return; }
    run("e2e_switch.mjs", process.execPath, [path.join(T, "e2e", "e2e_switch.mjs"), closeLog], { cwd: path.join(T, "e2e") });
    run("e2e_panel.mjs", process.execPath, [path.join(T, "e2e", "e2e_panel.mjs")], { cwd: path.join(T, "e2e") });
    run("e2e_stop.mjs", process.execPath, [path.join(T, "e2e", "e2e_stop.mjs"), closeLog], { cwd: path.join(T, "e2e") });
    run("e2e.mjs", process.execPath, [path.join(T, "e2e", "e2e.mjs")], { cwd: path.join(T, "e2e") });
  } finally {
    for (const p of procs) {
      if (WIN) spawnSync("taskkill", ["/T", "/F", "/PID", String(p.pid)], { stdio: "ignore" });
      else try { process.kill(p.pid, "SIGTERM"); } catch {}
    }
    await new Promise((r) => setTimeout(r, 1000));
    try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {}
  }
}

// ---- packaged ------------------------------------------------------------------------------------------
if (flag("--packaged")) {
  if (!WIN) console.log("skip  packaged checks: Windows only");
  else for (const f of ["frozen_verify.ps1", "byte_scan.ps1"])
    run(f, "powershell.exe", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path.join(T, "packaged", f)], { timeout: 900000 });
}

const bad = results.filter((r) => !r.ok);
const total = results.reduce((n, r) => n + (r.pass || 0), 0);
console.log(`\n${results.length} suites, ${total} checks passed, ${bad.length ? bad.length + " suite(s) FAILED: " + bad.map((r) => r.name).join(", ") : "no failures"}`);
process.exit(bad.length ? 1 : 0);
